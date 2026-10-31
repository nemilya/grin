// Бумажный театр: таймлайн (build/timeline.json) → кадр в момент t. Всё вычисляется из t —
// любой кадр можно отрисовать отдельно (захват кадров — tools/capture.mjs), предпросмотр — тот же код.
//
// Карточки: вырезки с альфой (сгенерированные PNG или заглушки) на слегка изогнутой бумаге с фактурой,
// отбрасывают тени по силуэту. Свет — лампа (spot) + заполняющий; камера — «с рук» (детерминированный шум);
// фокус — своя глубина резкости. Поверх — субтитры (2D-холст): кадр для захвата — композит.
import * as THREE from 'three';
import { EffectComposer } from '../vendor/three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from '../vendor/three/examples/jsm/postprocessing/RenderPass.js';
import { ShaderPass } from '../vendor/three/examples/jsm/postprocessing/ShaderPass.js';
import { OutputPass } from '../vendor/three/examples/jsm/postprocessing/OutputPass.js';
import { paperTextures, placeholder, procedural, rng, hashStr } from './paper.js';
import { DofPass, GradeShader, depthMaterial } from './post.js';
import { shapeCanvas, shapeMesh, traceMesh, updateTrace, spinAngle, fallPose } from './geometry.js';

const DEG = Math.PI / 180;
const PI = Math.PI;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, k) => a + (b - a) * k;
const lerp3 = (a, b, k) => a.map((x, i) => lerp(x, b[i], k));
const smooth = (a, b, x) => { const k = clamp((x - a) / ((b - a) || 1e-6), 0, 1); return k * k * (3 - 2 * k); };
const EASE = {
  linear: x => x,
  in: x => x * x,
  out: x => 1 - (1 - x) * (1 - x),
  inOut: x => x * x * (3 - 2 * x),
};
const ease = (name, x) => (EASE[name] || EASE.inOut)(clamp(x, 0, 1));
const rot3 = r => (Array.isArray(r) ? r : [0, r || 0, 0]);

// ---------------------------------------------------------------- шум «ручной камеры»

function wave(t, seed, freqs) {
  let v = 0, norm = 0;
  freqs.forEach((f, i) => {
    const ph = ((hashStr(seed + i) % 1000) / 1000) * 2 * PI;
    const a = 1 / (1 + i * 0.7);
    v += a * Math.sin(2 * PI * f * t + ph);
    norm += a;
  });
  return v / norm;
}
const HAND_F = [0.07, 0.13, 0.23, 0.37, 0.61, 0.97]; // камера в руках: плавное покачивание и дыхание, без дрожи (> 1 Гц)

// ---------------------------------------------------------------- сцена

export class Stage {
  constructor(tl, { base, scale = 1, samples = 48, debug = false, onProgress = null }) {
    this.subtitles = true;           // сайт: субтитры можно выключить
    this.onProgress = onProgress;    // загрузка ассетов: (готово, всего)
    this.tl = tl;
    this.debug = debug; // рабочий свет: видно композицию, без фокуса и виньетки
    this.base = base;
    this.W = Math.round(tl.width * scale);
    this.H = Math.round(tl.height * scale);
    this.scale = scale;
    this.paper = tl.stage || {};

    this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(this.W, this.H, false);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1;

    this.scene = new THREE.Scene();
    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.camera = new THREE.PerspectiveCamera(34, this.W / this.H, 1, 2000);

    this.composer = new EffectComposer(this.renderer);
    this.composer.setSize(this.W, this.H);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.dof = new DofPass(this.scene, this.camera, this.root, samples);
    this.composer.addPass(this.dof);
    this.composer.addPass(new OutputPass());
    this.grade = new ShaderPass(GradeShader);
    this.grade.uniforms.texel.value.set(1 / this.W, 1 / this.H);
    this.grade.uniforms.vignette.value = this.paper.vignette ?? 0.55;
    this.grade.uniforms.grain.value = this.paper.grain ?? 0.045;
    this.grade.uniforms.scratches.value = this.paper.scratches ?? 0;
    this.grade.uniforms.dust.value = this.paper.dust ?? 0;
    this.composer.addPass(this.grade);
    this.dof.setSize(this.W, this.H);

    this.out = document.createElement('canvas');
    this.out.width = this.W; this.out.height = this.H;
    this.ctx = this.out.getContext('2d');

    this.tex = {};
    this.shot = null;
    this.items = {};
  }

  // ---------------------------------------------------------------- загрузка ассетов

  async load() {
    const loader = new THREE.TextureLoader();
    const all = Object.entries(this.tl.assets);
    if (document.fonts) { // шрифт — до процедурных карточек: интертитры пишут им текст
      const sample = 'Aa Аа';
      await Promise.all([document.fonts.load(`${this._subSize()}px "Paper Serif"`, sample), document.fonts.load(`italic ${this._subSize()}px "Paper Serif"`, sample),
        document.fonts.load('600 40px "Stage Sans"', sample)]).catch(() => {});
    }
    let done = 0;
    const jobs = all.map(async ([key, spec]) => {
      let img = null;
      if (spec.file) {
        try { img = (await loader.loadAsync(this.base + spec.file)).image; } catch (e) { console.warn('нет файла', spec.file); }
      }
      if (!img && spec.kind === 'procedural') img = procedural(spec);
      if (!img) img = placeholder(key, spec);
      this.tex[key] = this._texture(img, spec);
      this.onProgress?.(++done, all.length);
    });
    await Promise.all(jobs);
    paperTextures();
    if (document.fonts) {
      const sample = 'Aa Аа'; // латиница и кириллица — разные файлы шрифта (unicode-range): грузим оба заранее
      await Promise.all([document.fonts.load(`${this._subSize()}px "Paper Serif"`, sample), document.fonts.load(`italic ${this._subSize()}px "Paper Serif"`, sample)]).catch(() => {});
    }
  }

  _texture(img, spec) {
    const t = img instanceof HTMLCanvasElement ? new THREE.CanvasTexture(img) : new THREE.Texture(img);
    t.colorSpace = THREE.SRGBColorSpace;
    t.anisotropy = 8;
    t.needsUpdate = true;
    return { tex: t, aspect: (img.width || 1) / (img.height || 1) };
  }

  _glowTexture(color, size) {
    const key = `glow:${color}:${size ? size.join('x') : ''}`;
    if (!this.tex[key]) this.tex[key] = this._texture(procedural({ draw: 'glow', color, size }), {});
    return this.tex[key];
  }

  // ---------------------------------------------------------------- построение кадра (один раз на кадр-шот)

  shotAt(t) {
    const shots = this.tl.shots;
    let lo = 0, hi = shots.length - 1;
    if (t < shots[0].t0) return shots[0];
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (shots[mid].t0 <= t) lo = mid; else hi = mid - 1;
    }
    return shots[lo];
  }

  _clear() {
    const kill = o => {
      o.children.slice().forEach(kill);
      if (o.geometry) o.geometry.dispose();
      if (o.material && !o.userData.sharedMat) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => m.dispose());
      if (o.userData.depthMat) o.userData.depthMat.dispose();
      if (o.customDepthMaterial) o.customDepthMaterial.dispose();
      if (o.isLight && o.shadow && o.shadow.map) o.shadow.map.dispose();
    };
    this.root.children.slice().forEach(c => { kill(c); this.root.remove(c); });
    this.items = {};
  }

  _build(shot) {
    this._clear();
    for (const el of shot.elements) {
      const obj = this._element(el);
      if (!obj) continue;
      this.root.add(obj.group);
      this.items[el.id] = { ...obj, el };
    }
    this._buildLights(shot);
    this.shot = shot;
  }

  _card(key, spec, el, { curl } = {}) {
    const entry = this.tex[key] || this.tex[Object.keys(this.tex)[0]];
    const isFloor = spec.kind === 'floor';
    let w, h;
    if (spec.size && !el.h) { [w, h] = spec.size; } else { h = el.h || spec.h || 10; w = h * (spec.file ? entry.aspect : (spec.aspect || entry.aspect)); }
    if (el.size) [w, h] = el.size;
    const geo = new THREE.PlaneGeometry(w, h, 16, 16);
    const bend = curl ?? ((this.paper.curl ?? 0.035) * (spec.kind === 'backdrop' ? 0.25 : 1));
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i) / (w / 2);
      pos.setZ(i, -bend * w * 0.5 * x * x);
      if (!isFloor) pos.setY(i, pos.getY(i) + h / 2); // опора — нижний край
    }
    geo.computeVertexNormals();
    const tex = entry.tex;
    let mat;
    const draw = spec.draw;
    if (draw === 'glow' || draw === 'screen' || draw === 'title') {
      mat = new THREE.MeshBasicMaterial({ map: tex, transparent: draw === 'glow', blending: draw === 'glow' ? THREE.AdditiveBlending : THREE.NormalBlending, depthWrite: draw !== 'glow', side: THREE.DoubleSide });
    } else {
      const normal = paperTextures().normal.clone();
      normal.repeat.set(Math.max(1, w / 14), Math.max(1, h / 14));
      normal.needsUpdate = true;
      mat = new THREE.MeshStandardMaterial({
        map: tex, alphaTest: spec.soft ? 0.02 : 0.5, transparent: !!spec.soft, depthWrite: !spec.soft, // soft — слой с мягким краем
        side: THREE.DoubleSide, roughness: this.paper.paper_roughness ?? 0.92, metalness: 0,
        normalMap: spec.kind === 'silhouette' || this.paper.paper_normal === false ? null : normal, normalScale: new THREE.Vector2(0.45, 0.45),
        color: spec.kind === 'silhouette' ? new THREE.Color('#0a0908') : new THREE.Color('#ffffff'),
      });
    }
    const mesh = new THREE.Mesh(geo, mat);
    if (isFloor) mesh.rotation.x = -PI / 2;
    const emissive = draw === 'glow' || draw === 'screen' || draw === 'title';
    mesh.castShadow = !emissive && !isFloor && spec.kind !== 'backdrop' && spec.cast !== false;
    mesh.receiveShadow = !emissive;
    if (!emissive || draw === 'screen' || draw === 'title') {
      mesh.customDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, map: tex, alphaTest: 0.5 });
      mesh.userData.depthMat = depthMaterial(tex);
    } else {
      mesh.userData.noDepth = true;
    }
    if (el.shadow_only) {
      mat.colorWrite = false; mat.depthWrite = false;
      mesh.receiveShadow = false; mesh.castShadow = true; mesh.userData.noDepth = true;
    }
    return { mesh, w, h };
  }

  _element(el) {
    const spec = { ...(this.tl.assets[el.card] || {}), ...(el.color ? { color: el.color } : {}) };
    const group = new THREE.Group();
    const out = { group, spec, h: 0, w: 0 };
    if (spec.draw === 'stars') return this._stars(el, spec, out);
    if (spec.draw === 'dust' || spec.draw === 'flies') return this._particles(el, spec, out);
    if (spec.draw === 'rain') return this._rain(el, spec, out);
    if (spec.draw === 'shape') return this._shape(el, spec, out);
    if (spec.draw === 'trace') return this._trace(el, spec, out);
    let card;
    if (spec.draw === 'glow') {
      const g = this._glowTexture(el.color || spec.color, el.size || spec.size);
      this.tex[el.card + ':' + el.id] = g;
      card = this._card(el.card + ':' + el.id, { ...spec, size: el.size || spec.size || [1, 1] }, el);
      const light = new THREE.PointLight(new THREE.Color(el.color || spec.color || '#ffcf8a'), 0, 0, 2);
      light.position.set(0, (el.size || spec.size || [1, 1])[1] / 2, 2);
      group.add(light);
      out.light = light;
    } else {
      card = this._card(el.card, spec, el);
    }
    group.add(card.mesh);
    out.mesh = card.mesh; out.w = card.w; out.h = card.h;
    if (el.card_prev && this.tex[el.card_prev]) {
      const prev = this._card(el.card_prev, this.tl.assets[el.card_prev], el);
      group.add(prev.mesh);
      out.prev = prev.mesh;
    }
    if (spec.parts) out.parts = this._parts(spec, card, group);
    return out;
  }

  // шарнирная кукла: части цепочкой (плечо → локоть → кисть), латунные скрепки — оси вращения
  _parts(spec, body, group) {
    const parts = {};
    let parent = { obj: body.mesh, w: body.w, h: body.h };
    for (const [name, p] of Object.entries(spec.parts)) {
      const pspec = this.tl.assets[p.card] || p;
      const card = this._card(p.card, { ...pspec, h: p.h, aspect: p.aspect }, {}, { curl: 0.01 });
      const pivot = new THREE.Group();
      const [ax, ay] = p.attach || [0.5, 0.5];
      pivot.position.set((ax - 0.5) * parent.w, ay * parent.h, 0.08);
      const [px, py] = p.pivot || [0.5, 0.95];
      card.mesh.position.set(-(px - 0.5) * card.w, -py * card.h, 0);
      pivot.add(card.mesh);
      parent.obj.add(pivot);
      parts[name] = pivot;
      parent = { obj: card.mesh, w: card.w, h: card.h }; // следующая часть (attach) — в долях этой карточки
    }
    return parts;
  }

  // супрематическая фигура (geometry.js): текстура — по параметрам (у элемента может быть свой цвет, размер)
  _shape(el0, spec, out) {
    const el = { ...spec, ...el0 };
    const p = { shape: el.shape, size: el.size, color: el.color, width: el.width, soft: el.soft, add: el.add, rays: el.rays };
    const key = 'shape:' + JSON.stringify(p);
    if (!this.tex[key]) { const c = shapeCanvas(p); this.tex[key] = { ...this._texture(c, {}), pad: c.userData.pad }; }
    const m = shapeMesh(p, this.tex[key].tex, this.tex[key].pad, el.trail || 0);
    out.group.add(m.mesh, ...m.ghosts);
    out.mesh = m.mesh; out.ghosts = m.ghosts; out.w = m.w; out.h = m.h;
    return out;
  }

  // линия, которая рисуется во времени (geometry.js)
  _trace(el0, spec, out) {
    const m = traceMesh({ ...spec, ...el0 });
    out.group.add(m.mesh);
    out.trace = m.mesh;
    return out;
  }

  _stars(el, spec, out) {
    const [w, h] = spec.size || [120, 90];
    if (spec.backing !== false) { // чёрный картон с проколами; ближний слой звёзд — без картона (параллакс)
      const back = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshStandardMaterial({ color: '#030304', roughness: 1 }));
      back.position.y = h / 2;
      back.userData.depthMat = depthMaterial(null);
      out.group.add(back);
    }
    const r = rng(hashStr(el.id));
    const N = Math.round(w * h * 0.09 * (spec.density ?? 1));
    const posA = new Float32Array(N * 3), size = new Float32Array(N), phase = new Float32Array(N), bright = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      posA[i * 3] = (r() - 0.5) * w; posA[i * 3 + 1] = r() * h; posA[i * 3 + 2] = 0.2;
      const b = Math.pow(r(), 3.2);
      bright[i] = 0.25 + b * 1.9; size[i] = 0.07 + b * 0.32; phase[i] = r() * 100;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(posA, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(size, 1));
    geo.setAttribute('phase', new THREE.BufferAttribute(phase, 1));
    geo.setAttribute('bright', new THREE.BufferAttribute(bright, 1));
    const mat = new THREE.ShaderMaterial({
      uniforms: { time: { value: 0 }, twinkle: { value: 0.3 }, scale: { value: this.H / 2 }, gain: { value: 1 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute float size; attribute float phase; attribute float bright;
        uniform float time; uniform float twinkle; uniform float scale; uniform float gain;
        varying float vB;
        void main() {
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          float tw = 0.5 + 0.5 * sin(time * (1.7 + fract(phase) * 4.0) + phase) * sin(time * 0.63 + phase * 1.7);
          vB = bright * gain * (1.0 - twinkle + twinkle * tw * 1.6);
          gl_PointSize = max(1.5, size * scale * 1.2 / -mv.z * 4.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying float vB;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.0, d);
          gl_FragColor = vec4(vec3(1.0, 0.94, 0.82) * vB * a * a, 1.0);
        }`,
    });
    const pts = new THREE.Points(geo, mat);
    out.group.add(pts);
    out.points = pts;
    out.h = h; out.w = w;
    return out;
  }

  // дождь: косые нити, падают в коробке box [x, y, z] вокруг pos; fx.rain — сила (0..1)
  _rain(el0, spec, out) {
    const el = { ...spec, ...el0 };  // параметры — в библии (кусок декорации) или в кадре
    const [bx, by, bz] = el.box || [40, 40, 10];
    const N = el.n || 900;
    const r = rng(hashStr(el.id + 'rain'));
    const pos = new Float32Array(N * 6), seed = new Float32Array(N * 8);
    for (let i = 0; i < N; i++) {
      const x = (r() - 0.5) * bx, z = (r() - 0.5) * bz, s = [r(), r(), r(), 0];
      for (let e = 0; e < 2; e++) {
        pos.set([x, 0, z], (i * 2 + e) * 3);
        seed.set([...s.slice(0, 3), e], (i * 2 + e) * 4);
      }
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('seed', new THREE.BufferAttribute(seed, 4));
    const mat = new THREE.ShaderMaterial({
      uniforms: { time: { value: 0 }, height: { value: by }, len: { value: el.len || 1.6 }, speed: { value: el.speed || 38 },
        slant: { value: el.slant ?? 0.12 }, gain: { value: el.gain ?? 0.35 }, color: { value: new THREE.Color(el.color || '#c8d2da') } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute vec4 seed; uniform float time; uniform float height; uniform float len; uniform float speed; uniform float slant;
        varying float vA;
        void main() {
          float sp = speed * (0.8 + 0.4 * seed.y);
          float y = height * 0.5 - mod(time * sp + seed.x * height, height);
          y -= seed.w * len * (0.7 + 0.6 * seed.z);
          vec3 p = position + vec3(-slant * (y - height * 0.5), y, 0.0);
          vA = (1.0 - seed.w * 0.85) * (0.4 + 0.6 * seed.z);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
        }`,
      fragmentShader: `
        uniform float gain; uniform vec3 color; varying float vA;
        void main() { gl_FragColor = vec4(color * vA * gain, 1.0); }`,
    });
    const lines = new THREE.LineSegments(geo, mat);
    lines.frustumCulled = false;
    out.group.add(lines);
    out.points = lines;
    return out;
  }

  _particles(el, spec, out) {
    const [bx, by, bz] = el.box || [12, 12, 8];
    const flies = spec.draw === 'flies';
    const N = flies ? 46 : 260;
    const r = rng(hashStr(el.id + spec.draw));
    const posA = new Float32Array(N * 3), seed = new Float32Array(N * 4);
    for (let i = 0; i < N; i++) {
      posA[i * 3] = (r() - 0.5) * bx; posA[i * 3 + 1] = (r() - 0.5) * by; posA[i * 3 + 2] = (r() - 0.5) * bz;
      seed[i * 4] = r(); seed[i * 4 + 1] = r(); seed[i * 4 + 2] = r(); seed[i * 4 + 3] = flies && r() < 0.25 ? 1 : 0;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(posA, 3));
    geo.setAttribute('seed', new THREE.BufferAttribute(seed, 4));
    const mat = new THREE.ShaderMaterial({
      uniforms: { time: { value: 0 }, scale: { value: this.H / 2 }, flies: { value: flies ? 1 : 0 }, gain: { value: 1 } },
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute vec4 seed; uniform float time; uniform float scale; uniform float flies;
        varying float vB; varying float vRing;
        void main() {
          vec3 p = position;
          float sp = flies > 0.5 ? 0.9 : 0.12;
          p.x += sin(time * sp * (0.6 + seed.x) + seed.y * 40.0) * (flies > 0.5 ? 2.5 : 0.8);
          p.y += sin(time * sp * (0.5 + seed.y) + seed.z * 40.0) * (flies > 0.5 ? 1.8 : 0.6) + (flies > 0.5 ? 0.0 : -mod(time * 0.05 * seed.z, 1.0));
          p.z += cos(time * sp * (0.4 + seed.z) + seed.x * 40.0) * 0.8;
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          vRing = seed.w;
          float base = flies > 0.5 ? (seed.w > 0.5 ? 1.6 : 0.22) : (0.035 + seed.x * 0.06);
          vB = flies > 0.5 ? (0.35 + 0.65 * abs(sin(time * (1.0 + seed.y * 3.0) + seed.x * 9.0))) * (seed.w > 0.5 ? 0.35 : 1.0)
                           : 0.15 + seed.y * 0.5;
          gl_PointSize = max(1.0, base * scale * 4.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        uniform float flies; uniform float gain; varying float vB; varying float vRing;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = vRing > 0.5 ? smoothstep(0.08, 0.0, abs(d - 0.4)) : smoothstep(0.5, 0.0, d);
          vec3 c = flies > 0.5 ? vec3(0.75, 1.0, 0.8) : vec3(1.0, 0.86, 0.62);
          gl_FragColor = vec4(c * vB * a * gain, 1.0);
        }`,
    });
    const pts = new THREE.Points(geo, mat);
    out.group.add(pts);
    out.points = pts;
    return out;
  }

  _buildLights(shot) {
    const L = shot.light;
    const key = L.key || {};
    if (key.type === 'sun') {
      const d = new THREE.DirectionalLight(new THREE.Color(key.color), 0);
      d.castShadow = (key.shadow ?? 1) > 0;
      d.shadow.mapSize.set(2048, 2048);
      Object.assign(d.shadow.camera, { left: -60, right: 60, top: 60, bottom: -60, near: 1, far: 300 });
      d.shadow.radius = Math.max(1, (key.shadow ?? 1) * 2);
      d.shadow.bias = -0.0006;
      this.root.add(d, d.target);
      this.key = d;
    } else {
      const s = new THREE.SpotLight(new THREE.Color(key.color || '#ffffff'), 0, 0, (key.angle || 50) * DEG, key.penumbra ?? 0.8, 2);
      s.castShadow = (key.shadow ?? 2) > 0;
      s.shadow.mapSize.set(2048, 2048);
      s.shadow.camera.near = 2; s.shadow.camera.far = 400;
      s.shadow.radius = Math.max(1, (key.shadow ?? 2) * 2);
      s.shadow.bias = -0.0004; s.shadow.normalBias = 0.02;
      this.root.add(s, s.target);
      this.key = s;
    }
    this.practical = null;
    if (L.practical) { // светящаяся лампа в кадре: тёплый ореол вокруг абажура
      const pr = L.practical;
      const pl = new THREE.PointLight(new THREE.Color(pr.color), 0, 0, 2);
      pl.position.set(...pr.pos);
      const g = this._glowTexture(pr.color, null);
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: g.tex, color: new THREE.Color(pr.color), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
      sp.position.set(...pr.pos);
      sp.scale.setScalar(5);
      sp.userData.noDepth = true;
      this.root.add(pl, sp);
      this.practical = { light: pl, sprite: sp, spec: pr };
    }
    const f = L.fill || {};
    const fc = new THREE.Color(f.color || '#202020');
    this.fill = new THREE.HemisphereLight(fc, new THREE.Color(f.ground || fc.clone().multiplyScalar(0.35)), 0);
    this.root.add(this.fill);
    this.scene.background = new THREE.Color(L.bg || '#000000');
    // туман и цвет плёнки — у сцены свои (свет пресета) или общие (стиль)
    const fog = L.fog === undefined ? this.paper.fog : L.fog;
    this.scene.fog = fog ? new THREE.FogExp2(new THREE.Color(fog.color || '#808080'), fog.density ?? 0.005) : null;
    // цвет плёнки: стиль → пресет света (grade); grade_to — переход за кадр (grade_at — доли кадра, как ramp)
    const gr = { saturation: this.paper.saturation ?? 1, tint: this.paper.tint || '#ffffff', autochrome: this.paper.autochrome ?? 0, ...(L.grade || {}) };
    this.gradeFrom = { saturation: gr.saturation, tint: new THREE.Color(gr.tint), autochrome: gr.autochrome };
    this.gradeTo = L.grade_to ? { saturation: L.grade_to.saturation ?? gr.saturation, tint: new THREE.Color(L.grade_to.tint || gr.tint),
      autochrome: L.grade_to.autochrome ?? gr.autochrome } : null;
    this.gradeAt = L.grade_at || [0, 1];
    this._grade(0);
  }

  _grade(u) {
    const a = this.gradeFrom, b = this.gradeTo;
    const k = b ? smooth(...this.gradeAt, u) : 0;
    const U = this.grade.uniforms;
    U.saturation.value = b ? lerp(a.saturation, b.saturation, k) : a.saturation;
    U.tint.value.copy(a.tint);
    if (b) U.tint.value.lerp(b.tint, k);
    U.autochrome.value = b ? lerp(a.autochrome, b.autochrome, k) : a.autochrome;
  }

  // ирис немого кино: in: 'iris' — круг раскрывается из темноты; следующий кадр с ирисом — этот закрывается
  _iris(shot, t) {
    const D = 1.3;
    let r = 10;
    const ease3 = x => x * x * (3 - 2 * x);
    if (shot.in === 'iris') r = Math.min(r, t - shot.t0 < D ? 1.02 * ease3(clamp((t - shot.t0) / D, 0, 1)) : 10);
    const i = this.tl.shots.indexOf(shot);
    const next = this.tl.shots[i + 1];
    const out = shot.end && shot.end.iris_out ? shot.end.iris_out : (next && next.in === 'iris' ? D : 0);
    if (out && t > shot.t1 - out) r = Math.min(r, 1.02 * ease3(clamp((shot.t1 - t) / out, 0, 1)));
    const c = (shot.iris && shot.iris.center) || [0.5, 0.5];
    this.grade.uniforms.irisCenter.value.set(c[0], 1 - c[1]);
    return r;
  }

  // ---------------------------------------------------------------- кадр в момент t

  renderAt(t) {
    const tReal = t;
    // «ручная» частота немого кино (stage.fps_look, напр. 18): сцена движется рывками, плёнка (зерно, пыль) — каждый кадр
    if (this.paper.fps_look) t = Math.floor(t * this.paper.fps_look + 1e-6) / this.paper.fps_look;
    const shot = this.shotAt(t);
    if (shot !== this.shot) this._build(shot);
    const dur = Math.max(0.001, shot.t1 - shot.t0);
    const u = clamp((t - shot.t0) / dur, 0, 1);
    const lt = t - shot.t0;

    // элементы
    for (const it of Object.values(this.items)) this._updateElement(it, t, u, lt);

    // камера
    const cam = shot.camera;
    const e = ease(cam.ease, u);
    const pos = new THREE.Vector3(...lerp3(cam.from.pos, cam.to.pos, e));
    const look = new THREE.Vector3(...lerp3(cam.from.look, cam.to.look, e));
    this.camera.fov = lerp(cam.from.fov, cam.to.fov, e);
    this.camera.position.copy(pos);
    this.camera.up.set(0, 1, 0);
    this.camera.lookAt(look);
    const hand = cam.hand ?? 1;
    if (hand > 0) {
      const a = hand * (this.paper.hand ?? 1); // stage.hand стиля — сила «рук» для всех кадров
      this.camera.rotateY(wave(t, 'yaw', HAND_F) * 0.4 * DEG * a);
      this.camera.rotateX(wave(t, 'pitch', HAND_F) * 0.34 * DEG * a);
      this.camera.rotateZ(wave(t, 'roll', HAND_F) * 0.5 * DEG * a);
      this.camera.translateX(wave(t, 'tx', HAND_F) * 0.15 * a);
      this.camera.translateY(wave(t, 'ty', HAND_F) * 0.15 * a);
    }
    this.camera.updateProjectionMatrix();
    this.camera.updateMatrixWorld();

    // свет и экспозиция
    const k = this._lightK(shot, t, u, lt);
    this._updateLight(shot, t, u, lt, k);
    this.renderer.toneMappingExposure = this.debug ? 1 : this._exposure(shot, t);

    // фокус
    this._focus(shot, u);
    this._grade(u);
    this.grade.uniforms.iris.value = this._iris(shot, tReal);
    const fr = Math.floor(tReal * (this.tl.fps || 24));
    this.grade.uniforms.seed.value = (fr % 997) / 97.0;
    this.grade.uniforms.flicker.value = (this.paper.flicker || 0) * (wave(fr * 0.37, 'flick', [1.7, 2.9, 5.3]) * 0.5 + (((fr * 7919) % 13) / 13 - 0.5));
    const wv = (this.paper.weave || 0) * this.H / 1080; // кадр «гуляет» в фильмовом канале (пиксели)
    this.grade.uniforms.weave.value.set(wave(fr * 0.5, 'wx', [0.9, 1.7]) * wv * 0.4, wave(fr * 0.5, 'wy', [1.1, 2.3]) * wv);

    this.composer.render();
    this._composite(tReal);
    return this.out;
  }

  _updateElement(it, t, u, lt) {
    const { el, group } = it;
    let p = el.pos || [0, 0, 0];
    let r = rot3(el.rot);
    const mv = el.move;
    if (mv && mv.keys) { // маршрут: [[доля кадра, [x, y, z]], …] — вышел, постоял, ушёл
      const ks = mv.keys;
      p = ks[0][1];
      for (let i = 1; i < ks.length; i++) {
        if (u >= ks[i][0]) { p = ks[i][1]; continue; }
        if (u > ks[i - 1][0]) p = lerp3(ks[i - 1][1], ks[i][1], ease(mv.ease || 'inOut', (u - ks[i - 1][0]) / ((ks[i][0] - ks[i - 1][0]) || 1)));
        break;
      }
      if (mv.rot_to) r = lerp3(r, rot3(mv.rot_to), ease(mv.ease || 'inOut', (u - (mv.start ?? 0)) / (((mv.end ?? 1) - (mv.start ?? 0)) || 1)));
    } else if (mv) {
      const s0 = mv.start ?? 0, s1 = mv.end ?? 1;
      const k = ease(mv.ease || 'inOut', (u - s0) / ((s1 - s0) || 1));
      if (mv.to) p = lerp3(p, mv.to, k);
      if (mv.rot_to) r = lerp3(r, rot3(mv.rot_to), k);
    }
    if (el.fall) ({ p, r } = fallPose(el, p, r, u));
    let spin = null;
    if (el.spin) {
      spin = spinAngle(el.spin, lt, this.shot ? this.shot.t1 - this.shot.t0 : 1);
      const ax = { x: 0, y: 1, z: 2 }[el.spin.axis || 'y'];
      r = r.slice(); r[ax] += spin.ang;
    }
    const fx = el.fx || {};
    let dy = 0, rz = 0, sc = 1, dx = 0;
    const seed = el.id;
    if (fx.bob) dy += Math.abs(Math.sin(t * PI * (fx.bob_hz || 1.7) + (hashStr(seed) % 7))) * fx.bob;
    // шаг бумажной куклы: карточку ведут рукой — она покачивается с носка на пятку, не подпрыгивая
    if (fx.walk) rz += Math.sin(t * PI * (fx.walk_hz || 1.4) + (hashStr(seed) % 7)) * fx.walk;
    if (fx.jitter) rz += (wave(t * 2.5, seed + 'j', [1.1, 1.7, 2.9]) * fx.jitter * 0.45); // дрожь руки — мягче
    if (fx.sway) rz += Math.sin(t * 2 * PI * 0.32 + (hashStr(seed) % 5)) * fx.sway;
    if (fx.wobble) dx += Math.sin(t * 2 * PI * 3.2) * fx.wobble * 0.5;
    if (fx.breathe) sc += Math.sin(t * 2 * PI * 0.22) * fx.breathe;
    group.position.set(p[0] + dx, p[1] + dy, p[2]);
    group.rotation.set(r[0] * DEG, r[1] * DEG, (r[2] + rz) * DEG, 'YXZ');
    group.scale.setScalar(sc);
    if (it.prev) {
      const sw = (u >= (el.swap_at ?? 0));
      it.prev.visible = !sw; it.mesh.visible = sw;
    }
    // свечение (тонировка карточки или светящийся элемент)
    let gk = el.k ?? 1;
    if (el.k_to !== undefined) { const [a, b] = el.ramp || [0, 1]; gk = lerp(el.k ?? 1, el.k_to, smooth(a, b, u)); }
    if (fx.flicker) gk *= 1 - fx.flicker * 0.5 * (0.5 + 0.5 * wave(t * 3, seed + 'f', [1.3, 2.1, 3.7]));
    if (it.spec.draw === 'glow' && it.mesh) {
      it.mesh.material.color.setScalar(gk * 1.4);
      it.mesh.visible = gk > 0.01;
      if (it.light) it.light.intensity = gk * 60 * PI;
    }
    if (it.spec.draw === 'screen' && it.mesh) it.mesh.material.color.setScalar(0.55 * gk); // просвеченная бумага — не до белого
    if (it.spec.draw === 'title' && it.mesh) it.mesh.material.color.setScalar(gk);
    if (it.spec.draw === 'shape' && it.mesh) {
      it.mesh.material.opacity = clamp(gk, 0, 1);
      it.mesh.visible = gk > 0.005;
      const n = it.ghosts.length;  // шлейф: следы позади по ходу вращения, ярче — чем быстрее
      const ax = (el.spin && el.spin.axis) || 'y';
      const sp = spin ? spin.speed : 0;
      it.ghosts.forEach((g, i) => {
        g.rotation.set(0, 0, 0);
        g.rotation[ax] = -Math.sign(sp) * Math.min(Math.abs(sp) * (i + 1) / 48, 360 * (i + 1) / (n + 1)) * DEG;
        g.material.opacity = clamp(gk, 0, 1) * Math.pow(1 - (i + 1) / (n + 1), 1.5) * clamp(Math.abs(sp) / 360, 0, 1) * 0.8;
        g.visible = g.material.opacity > 0.004;
      });
    }
    if (it.trace) updateTrace(it.trace, el, t, u, clamp(gk, 0, 1));
    if (el.glow && it.mesh && it.mesh.material.emissive) {
      const g = el.glow;
      const gs = (g.k ?? 0.3) * smooth(g.start ?? 0, (g.start ?? 0) + 0.12, u);
      it.mesh.material.emissive.set(g.color || '#ffffff');
      it.mesh.material.emissiveMap = it.mesh.material.map;
      it.mesh.material.emissiveIntensity = gs;
    }
    if (it.points) {
      it.points.material.uniforms.time.value = t;
      if (it.points.material.uniforms.twinkle) it.points.material.uniforms.twinkle.value = fx.twinkle ?? 0.3;
    }
    if (it.parts && el.parts) {
      for (const [name, v] of Object.entries(el.parts)) {
        const pv = it.parts[name];
        if (!pv) continue;
        pv.rotation.z = this._keyed(v, u) * DEG;
      }
    }
  }

  _keyed(v, u) {
    if (!Array.isArray(v)) return v || 0;
    if (u <= v[0][0]) return v[0][1];
    for (let i = 1; i < v.length; i++) {
      if (u <= v[i][0]) return lerp(v[i - 1][1], v[i][1], ease('inOut', (u - v[i - 1][0]) / ((v[i][0] - v[i - 1][0]) || 1)));
    }
    return v[v.length - 1][1];
  }

  _lightK(shot, t, u, lt) {
    const L = shot.light;
    let k = L.k ?? 1;
    if (L.k_to !== undefined) { const [a, b] = L.ramp || [0, 1]; k = lerp(L.k ?? 1, L.k_to, smooth(a, b, u)); }
    const fx = L.fx || {};
    if (fx.heartbeat) { // тук-тук, пропуск, барабанная дробь
      const beat = 0.86, ph = (lt % beat) / beat, n = Math.floor(lt / beat);
      const skip = (hashStr('hb' + n) % 5) === 0;
      const pulse = Math.exp(-Math.pow((ph - 0.08) / 0.05, 2)) + 0.7 * Math.exp(-Math.pow((ph - 0.3) / 0.05, 2));
      k *= 1 - 0.55 * fx.heartbeat * 0.5 + (skip ? -0.25 : pulse * 0.55 * fx.heartbeat);
    }
    if (fx.breath) k *= 1 - 0.45 * fx.breath * Math.sin(PI * smooth(0.05, 0.7, u));
    return Math.max(0, k);
  }

  _updateLight(shot, t, u, lt, k) {
    const L = shot.light, key = L.key || {};
    let target = key.target || [0, 0, 0];
    if (L.target_to) target = lerp3(target, L.target_to, smooth(0, 1, u));
    let pos = key.pos || [0, 30, 30];
    const fx = L.fx || {};
    if (fx.swing) { // лампу задели: качание с затуханием
      const s = fx.swing * Math.sin(2 * PI * 0.55 * lt) * Math.exp(-lt / 7);
      target = [target[0] + s * 9, target[1], target[2] + s * 3];
      pos = [pos[0] + s * 0.6, pos[1], pos[2]];
    }
    this.key.position.set(...pos);
    this.key.target.position.set(...target);
    this.key.target.updateMatrixWorld();
    const d0 = Math.hypot(pos[0] - target[0], pos[1] - target[1], pos[2] - target[2]);
    let col = new THREE.Color(key.color || '#ffffff');
    if (L.warm) col = col.lerp(new THREE.Color('#ff9a4a'), L.warm);
    this.key.color.copy(col);
    if (this.key.isSpotLight) {
      this.key.intensity = (key.intensity ?? 1) * k * d0 * d0 * PI;
      let ang = key.angle || 50;
      if (L.angle_to) ang = lerp(ang, L.angle_to, smooth(0, 0.6, u));
      this.key.angle = ang * DEG;
    } else {
      this.key.intensity = (key.intensity ?? 1) * k * PI;
    }
    this.fill.intensity = ((L.fill || {}).intensity ?? 0.2) * Math.min(1, 0.35 + 0.65 * k) * PI;
    if (this.practical) {
      const pr = this.practical.spec;
      this.practical.light.intensity = (pr.intensity ?? 1) * k * 100 * PI;
      this.practical.sprite.material.color.set(pr.color).multiplyScalar((pr.glow ?? 1) * Math.min(1.2, k));
      this.practical.sprite.visible = k > 0.02;
    }
    if (this.debug) { this.fill.color.set('#ffffff'); this.fill.groundColor.set('#888888'); this.fill.intensity = 1.6 * PI; }
  }

  _exposure(shot, t) {
    let ex = 1;
    const lt = t - shot.t0;
    if (shot.in === 'fade') ex *= smooth(0, 1.6, lt);
    if (shot.in === 'dip') ex *= smooth(0, 0.6, lt);
    if (this.tl.fade_out) ex *= 1 - smooth(this.tl.duration - this.tl.fade_out, this.tl.duration, t); // конец фильма — в темноту
    const i = this.tl.shots.indexOf(shot);
    const next = this.tl.shots[i + 1];
    if (next && next.in === 'dip') ex *= 1 - smooth(next.t0 - 0.45, next.t0, t);
    if (shot.end && shot.end.light_off) {
      const off = shot.t1 - shot.end.light_off;
      ex *= 1 - smooth(off, off + 0.12, t) * (t < off + 0.05 ? 0.6 : 1);
    }
    return ex;
  }

  _point(ref) {
    if (Array.isArray(ref)) return new THREE.Vector3(...ref);
    const it = this.items[ref] || Object.values(this.items).find(x => x.el.id.endsWith(':' + ref));
    if (!it) return null;
    const p = new THREE.Vector3();
    if (it.points && !it.mesh) { it.group.getWorldPosition(p); return p.add(new THREE.Vector3(0, (it.h || 0) * 0.6, 0)); }
    if (!it.mesh || it.spec.draw === 'shape') { it.group.updateWorldMatrix(true, false); return it.group.getWorldPosition(p); }  // линия, фигура — их центр
    // точка на самой карточке (в её плоскости — и для повёрнутых и лежащих): 62% высоты — уровень лица
    const isFloor = it.spec.kind === 'floor';
    it.mesh.updateWorldMatrix(true, false);
    return it.mesh.localToWorld(p.set(0, isFloor ? 0 : (it.h || 0) * 0.62, 0));
  }

  _focus(shot, u) {
    const f = shot.focus || {};
    const fwd = new THREE.Vector3();
    this.camera.getWorldDirection(fwd);
    const dist = ref => {
      const p = ref !== undefined && this._point(ref);
      return p ? Math.max(2, p.sub(this.camera.position).dot(fwd)) : null;
    };
    let d = dist(f.on) ?? 50;
    if (f.to !== undefined) {
      const d2 = dist(f.to) ?? d;
      const [a, b] = f.at || [0.3, 0.7];
      d = lerp(d, d2, smooth(a, b, u));
    }
    let ap = f.f ?? 1.2;
    if (f.f_to !== undefined) ap = lerp(ap, f.f_to, smooth(0, 1, u));
    const k = this.H / 1920;
    this.dof.material.uniforms.focus.value = d;
    this.dof.material.uniforms.cocScale.value = this.debug ? 0 : 34 * ap * k;
    this.dof.material.uniforms.maxCoc.value = 30 * k;
  }

  // ---------------------------------------------------------------- субтитры поверх

  _sub() { return { y: 0.735, width: 0.82, size: 0.0285, ...(this.tl.subtitle_style || {}) }; }

  _subSize() { return Math.round(this.H * this._sub().size); }

  _composite(t) {
    const ctx = this.ctx;
    ctx.drawImage(this.renderer.domElement, 0, 0);
    const sub = this._sub().burn === false || !this.subtitles ? null : this.subAt(t); // burn: false — субтитры отдельно (.srt)
    if (!sub) return;
    const fs = this._subSize();
    const a = smooth(sub.t0, sub.t0 + 0.14, t) * (1 - smooth(sub.t1 - 0.14, sub.t1, t));
    if (a <= 0) return;
    ctx.save();
    ctx.globalAlpha = a;
    ctx.font = `${fs}px "Paper Serif", Georgia, serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const st = this._sub();
    const lines = wrap(ctx, sub.text, this.W * st.width);
    const lh = fs * 1.28;
    const cy = this.H * st.y - (lines.length - 1) * lh / 2;
    ctx.shadowColor = 'rgba(0,0,0,.9)';
    ctx.shadowBlur = fs * 0.45;
    ctx.fillStyle = '#f5ecdb';
    lines.forEach((ln, i) => { ctx.fillText(ln, this.W / 2, cy + i * lh); ctx.fillText(ln, this.W / 2, cy + i * lh); });
    ctx.restore();
  }

  subAt(t) {
    const s = this.tl.subtitles;
    let lo = 0, hi = s.length - 1, best = null;
    while (lo <= hi) {
      const m = (lo + hi) >> 1;
      if (s[m].t0 <= t) { best = s[m]; lo = m + 1; } else hi = m - 1;
    }
    return best && t <= best.t1 ? best : null;
  }
}

function wrap(ctx, text, maxW) {
  const words = text.split(/\s+/);
  const lines = [];
  let cur = '';
  for (const w of words) {
    const tryL = cur ? cur + ' ' + w : w;
    if (ctx.measureText(tryL).width > maxW && cur) { lines.push(cur); cur = w; } else cur = tryL;
  }
  if (cur) lines.push(cur);
  if (lines.length === 2 && lines[1].split(' ').length === 1 && lines[0].includes(' ')) { // без «вдовы» во второй строке
    const ws = lines[0].split(' ');
    lines[1] = ws.pop() + ' ' + lines[1];
    lines[0] = ws.join(' ');
  }
  return lines;
}
