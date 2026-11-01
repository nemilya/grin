// Post-processing: depth of field (our own, aware of the cut-outs' alpha — BokehPass lets the transparent margins of cards
// spoil the depth) and "film" after tone mapping: the lamp's vignette, grain, slight chromatic aberration at the edges.
import * as THREE from 'three';
import { Pass, FullScreenQuad } from '../vendor/three/examples/jsm/postprocessing/Pass.js';

// depth is written as 1/distance (cm⁻¹): emptiness (cleared to zero) is infinitely far; cut-outs — by the map's alpha
export function depthMaterial(map) {
  return new THREE.ShaderMaterial({
    uniforms: { map: { value: map }, useMap: { value: map ? 1 : 0 } },
    side: THREE.DoubleSide,
    vertexShader: `
      varying vec2 vUv; varying float vZ;
      void main() {
        vUv = uv;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        vZ = -mv.z;
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      uniform sampler2D map; uniform float useMap;
      varying vec2 vUv; varying float vZ;
      void main() {
        if (useMap > 0.5 && texture2D(map, vUv).a < 0.5) discard;
        gl_FragColor = vec4(1.0 / max(vZ, 0.001), 0.0, 0.0, 1.0);
      }`,
  });
}

const DOF_FRAG = `
  uniform sampler2D tColor; uniform sampler2D tDepth;
  uniform vec2 texel; uniform float focus; uniform float cocScale; uniform float maxCoc;
  varying vec2 vUv;
  float coc(float d) { return clamp(cocScale * abs(d - focus) / max(d, 0.001), 0.0, maxCoc); }
  void main() {
    float d0 = 1.0 / max(texture2D(tDepth, vUv).r, 1e-5);
    float c0 = coc(d0);
    vec4 acc = vec4(texture2D(tColor, vUv).rgb, 1.0);
    const float GA = 2.39996323;
    for (int i = 1; i < SAMPLES; i++) {
      float fi = float(i);
      float r = sqrt(fi / float(SAMPLES)) * maxCoc;
      vec2 off = vec2(cos(fi * GA), sin(fi * GA)) * r;
      vec2 uv = vUv + off * texel;
      float d = 1.0 / max(texture2D(tDepth, uv).r, 1e-5);
      float c = coc(d);
      if (d > d0) c = min(c, c0 * 2.0);          // a sharp foreground doesn't "leak" backwards
      float w = smoothstep(r - 1.5, r + 0.5, c);
      vec3 col = texture2D(tColor, uv).rgb;
      w *= 1.0 + 0.6 * max(0.0, dot(col, vec3(0.3, 0.59, 0.11)) - 0.8); // bright points — more visible bokeh
      acc += vec4(col * w, w);
    }
    gl_FragColor = vec4(acc.rgb / acc.a, 1.0);
  }`;

export class DofPass extends Pass {
  constructor(scene, camera, root, samples = 48) {
    super();
    this.scene = scene; this.camera = camera; this.root = root;
    this.depthTarget = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
    this.material = new THREE.ShaderMaterial({
      defines: { SAMPLES: samples },
      uniforms: { tColor: { value: null }, tDepth: { value: this.depthTarget.texture }, texel: { value: new THREE.Vector2() },
        focus: { value: 50 }, cocScale: { value: 40 }, maxCoc: { value: 26 } },
      vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: DOF_FRAG,
    });
    this.fsQuad = new FullScreenQuad(this.material);
    this._clear = new THREE.Color();
  }

  setSize(w, h) {
    this.depthTarget.setSize(w, h);
    this.material.uniforms.texel.value.set(1 / w, 1 / h);
  }

  render(renderer, writeBuffer, readBuffer) {
    const swapped = [];
    this.root.traverse(o => {
      if (!o.visible) return;
      if (o.isPoints || o.isLine || o.userData.noDepth) { swapped.push([o, 'hide']); o.visible = false; return; }
      if (o.isMesh && o.userData.depthMat) { swapped.push([o, o.material]); o.material = o.userData.depthMat; }
    });
    const bg = this.scene.background;
    this.scene.background = null;
    renderer.getClearColor(this._clear);
    const alpha = renderer.getClearAlpha();
    renderer.setClearColor(0x000000, 1);
    renderer.setRenderTarget(this.depthTarget);
    renderer.clear();
    renderer.render(this.scene, this.camera);
    renderer.setClearColor(this._clear, alpha);
    this.scene.background = bg;
    for (const [o, m] of swapped) { if (m === 'hide') o.visible = true; else o.material = m; }

    this.material.uniforms.tColor.value = readBuffer.texture;
    renderer.setRenderTarget(this.renderToScreen ? null : writeBuffer);
    this.fsQuad.render(renderer);
  }
}

export const GradeShader = {
  uniforms: { tDiffuse: { value: null }, vignette: { value: 0.55 }, grain: { value: 0.045 }, seed: { value: 0 },
    texel: { value: new THREE.Vector2() }, aberration: { value: 0.18 },
    saturation: { value: 1 }, tint: { value: new THREE.Color(1, 1, 1) }, flicker: { value: 0 },
    // silent cinema and autochrome (off by default): coloured starch grain and the softness of the plate, scratches
    // and film dust, the frame "breathing" in the film channel, an iris (radius from the centre, a share of the half-diagonal)
    autochrome: { value: 0 }, scratches: { value: 0 }, dust: { value: 0 }, weave: { value: new THREE.Vector2() },
    iris: { value: 10 }, irisCenter: { value: new THREE.Vector2(0.5, 0.5) } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
  fragmentShader: `
    uniform sampler2D tDiffuse; uniform float vignette; uniform float grain; uniform float seed;
    uniform vec2 texel; uniform float aberration; uniform float saturation; uniform vec3 tint; uniform float flicker;
    uniform float autochrome; uniform float scratches; uniform float dust; uniform vec2 weave;
    uniform float iris; uniform vec2 irisCenter;
    varying vec2 vUv;
    float hash(vec2 p) { p = fract(p * vec2(443.897, 441.423) + seed); p += dot(p, p.yx + 19.19); return fract((p.x + p.y) * p.x); }
    float hash1(float x) { return fract(sin(x * 127.1 + seed * 311.7) * 43758.5453); }
    vec3 samp(vec2 uv, vec2 ab) {
      return vec3(texture2D(tDiffuse, uv + ab).r, texture2D(tDiffuse, uv).g, texture2D(tDiffuse, uv - ab).b);
    }
    void main() {
      vec2 uv = vUv + weave * texel;
      vec2 c = uv - 0.5;
      float r2 = dot(c * vec2(0.75, 1.0), c * vec2(0.75, 1.0));
      vec2 ab = c * r2 * aberration * texel * 60.0;
      vec3 col = samp(uv, ab);
      if (autochrome > 0.0) {
        // the softness of the plate: a slight blur; starch grains — orange, green, violet filters
        vec3 soft = (samp(uv + texel * vec2(1.5, 0.0), ab) + samp(uv - texel * vec2(1.5, 0.0), ab)
                   + samp(uv + texel * vec2(0.0, 1.5), ab) + samp(uv - texel * vec2(0.0, 1.5), ab)) * 0.25;
        col = mix(col, soft, 0.6 * autochrome);
        vec2 cell = floor(uv / texel / 2.2);
        float h = hash(cell * 0.013);
        vec3 starch = h < 0.34 ? vec3(1.18, 0.86, 0.72) : (h < 0.67 ? vec3(0.82, 1.12, 0.8) : vec3(0.86, 0.8, 1.2));
        col = mix(col, col * starch, 0.32 * autochrome);
        col = mix(col, col * 0.86 + vec3(0.075, 0.07, 0.06), 0.55 * autochrome); // pastel: lifted shadows
      }
      col = mix(vec3(dot(col, vec3(0.299, 0.587, 0.114))), col, saturation) * tint * (1.0 + flicker * 0.06);
      col *= 1.0 - vignette * smoothstep(0.08, 0.62, r2 * 1.6);
      if (scratches > 0.0) { // 0–3 vertical scratches per frame: thin, light (on the emulsion) or dark
        for (int i = 0; i < 3; i++) {
          float fi = float(i);
          if (hash1(fi + 1.0) > scratches * 0.6) continue;
          float x = hash1(fi + 11.0);
          float w = texel.x * (0.5 + 1.0 * hash1(fi + 21.0));
          float d = abs(uv.x - x - 0.004 * sin(uv.y * 9.0 + fi));
          float a = (1.0 - smoothstep(w * 0.4, w, d)) * (0.55 + 0.45 * sin(uv.y * 40.0 * hash1(fi + 31.0) + fi));
          col = mix(col, hash1(fi + 41.0) > 0.5 ? vec3(0.78) : vec3(0.12), clamp(a, 0.0, 1.0) * 0.32);
        }
      }
      if (dust > 0.0) { // specks and hairs on the frame: dark spots, different in every frame
        for (int i = 0; i < 6; i++) {
          float fi = float(i);
          if (hash1(fi + 51.0) > dust * 0.5) continue;
          vec2 p = vec2(hash1(fi + 61.0), hash1(fi + 71.0));
          float rad = (1.5 + 5.0 * hash1(fi + 81.0)) * texel.y;
          vec2 q = (uv - p) / vec2(texel.y / texel.x, 1.0);
          float d = length(q * vec2(1.0, 0.4 + hash1(fi + 91.0)));
          col *= 1.0 - 0.75 * (1.0 - smoothstep(rad * 0.5, rad, d));
        }
      }
      if (iris < 2.0) { // the iris: a circle from the centre, a soft edge; outside — a black field
        vec2 q = (vUv - irisCenter) * vec2(texel.y / texel.x, 1.0);
        float rr = length(q) / length(vec2(0.5 * texel.y / texel.x, 0.5));
        col *= 1.0 - smoothstep(iris - 0.02, iris + 0.01, rr);
      }
      float g = hash(vUv * 1000.0) - 0.5;
      col += g * grain * (0.6 + 0.4 * (1.0 - dot(col, vec3(0.33))));
      gl_FragColor = vec4(col, 1.0);
    }`,
};
