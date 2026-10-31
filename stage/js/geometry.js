// Процедурная геометрия сцены («Отпавший Лист», docs/stories/leaf-story.md): супрематические фигуры, линии, которые
// рисуются во времени, вращение со шлейфом и падение карточки (лист). Всё — из времени кадра, без состояния.
//
//   фигура   draw: "shape", shape: disc | ring | rect | wedge | cross | burst (лучи от центра, гаснут к краю; rays — число),
//            size [w, h], color, width (кольцо, крест — доля; burst — ширина луча),
//            soft (0..1 — размытый край: уголь, огонь), add (сложение света); начало координат — центр фигуры
//   линия    draw: "trace", points [[x, y(, z)], …] (в единицах сцены от pos), smooth (кривая через точки), width,
//            color, dash [штрих, пробел], grow [a, b] — доли кадра: линия дорисовывается; wave {amp, freq, speed, fade [a, b]}
//            — дрожит, как струна (fade — амплитуда гаснет к нулю); soft (0..1 — мягкий край), add — сложение света
//            (светящаяся нить)
//   вращение spin {axis: x|y|z, speed, speed_to, ramp [a, b]} — градусы в секунду (разгон за ramp), trail: n — шлейф из n
//            следов: быстро вращающееся кольцо читается сферой
//   падение  fall {to [x, y, z], at [a, b], sway, swings, tumble, flutter, rot_to} — карточка падает из pos в to,
//            качаясь маятником (sway — размах вбок, tumble — наклон, flutter — кувырок вокруг x), садится в rot_to
import * as THREE from 'three';
import { depthMaterial } from './post.js';

const PI = Math.PI;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const lerp = (a, b, k) => a + (b - a) * k;
const smooth = (a, b, x) => { const k = clamp((x - a) / ((b - a) || 1e-6), 0, 1); return k * k * (3 - 2 * k); };

// ---------------------------------------------------------------- фигуры: холст → текстура (гладкий край, глубина по альфе)

export function shapeCanvas(spec) {
  const [w, h] = spec.size || [10, 10];
  const S = 1024 / Math.max(w, h);
  const pad = spec.soft ? Math.round(Math.min(w, h) * S * 0.25 * spec.soft) : 4;
  const c = document.createElement('canvas');
  c.width = Math.round(w * S) + pad * 2; c.height = Math.round(h * S) + pad * 2;
  const x = c.getContext('2d');
  x.translate(pad, pad);
  const W = c.width - pad * 2, H = c.height - pad * 2;
  x.fillStyle = x.strokeStyle = spec.color || '#c8281e';
  if (spec.soft) x.filter = `blur(${pad * 0.5}px)`;
  const lw = (spec.width ?? 0.08) * Math.min(W, H);
  switch (spec.shape) {
    case 'ring':
      x.lineWidth = lw;
      x.beginPath(); x.ellipse(W / 2, H / 2, (W - lw) / 2, (H - lw) / 2, 0, 0, 2 * PI); x.stroke();
      break;
    case 'rect': x.fillRect(0, 0, W, H); break;
    case 'wedge': x.beginPath(); x.moveTo(0, 0); x.lineTo(W, H / 2); x.lineTo(0, H); x.closePath(); x.fill(); break;
    case 'cross':
      x.fillRect(0, (H - lw) / 2, W, lw); x.fillRect((W - lw) / 2, 0, lw, H);
      break;
    case 'burst': {  // супрематическое солнце: тонкие лучи из центра, к краю гаснут
      const n = spec.rays || 24, R = Math.min(W, H) / 2, half = PI / n * (spec.width ?? 0.35);
      const c = new THREE.Color(spec.color || '#f2c14e');
      const rgba = a => `rgba(${Math.round(c.r * 255)},${Math.round(c.g * 255)},${Math.round(c.b * 255)},${a})`;
      const g = x.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, R);
      g.addColorStop(0, rgba(1)); g.addColorStop(0.45, rgba(0.7)); g.addColorStop(1, rgba(0));
      x.fillStyle = g;
      for (let i = 0; i < n; i++) {
        const a = i / n * 2 * PI, r = R * (i % 2 ? 0.78 : 1);  // лучи через один короче
        x.beginPath(); x.moveTo(W / 2, H / 2);
        x.lineTo(W / 2 + r * Math.cos(a - half), H / 2 + r * Math.sin(a - half));
        x.lineTo(W / 2 + r * Math.cos(a + half), H / 2 + r * Math.sin(a + half));
        x.closePath(); x.fill();
      }
      break;
    }
    default: x.beginPath(); x.ellipse(W / 2, H / 2, W / 2, H / 2, 0, 0, 2 * PI); x.fill();  // disc
  }
  c.userData = { pad: pad / S };
  return c;
}

// меш фигуры: плоскость с текстурой фигуры (центр — в начале координат), + шлейф (копии для вращения)
export function shapeMesh(spec, tex, padUnits, trail = 0) {
  const [w, h] = spec.size || [10, 10];
  const mk = () => {
    const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, alphaTest: 0.01, side: THREE.DoubleSide,
      depthWrite: !spec.add, blending: spec.add ? THREE.AdditiveBlending : THREE.NormalBlending, fog: false });
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w + 2 * padUnits, h + 2 * padUnits), mat);
    if (spec.add || spec.soft) mesh.userData.noDepth = true; else mesh.userData.depthMat = depthMaterial(tex);
    return mesh;
  };
  const mesh = mk();
  const ghosts = [];
  for (let i = 0; i < trail; i++) {
    const g = mk();
    g.userData.noDepth = true;
    g.material.depthWrite = false;
    ghosts.push(g);
  }
  return { mesh, ghosts, w, h };
}

// ---------------------------------------------------------------- линии: лента вдоль кривой, рост и пунктир — в шейдере

function curvePoints(pts, smoothIt) {
  const v = pts.map(p => new THREE.Vector3(p[0], p[1], p[2] || 0));
  if (!smoothIt || v.length < 3) return v;
  const curve = new THREE.CatmullRomCurve3(v, false, 'centripetal');
  const len = curve.getLength();
  return curve.getSpacedPoints(Math.max(16, Math.min(1200, Math.round(len * 6))));
}

const TRACE_VERT = `
  attribute float dist; attribute float side; attribute vec3 nrm;
  uniform float time; uniform float total; uniform vec4 wave;  // amp, freq (волн на длину), speed, —
  varying float vDist; varying float vSide;
  void main() {
    vDist = dist; vSide = side;
    float env = sin(3.14159 * clamp(dist / max(total, 1e-3), 0.0, 1.0));  // концы струны закреплены
    vec3 p = position + nrm * (wave.x * env * sin(6.28318 * (wave.y * dist / max(total, 1e-3)) - time * wave.z));
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }`;
const TRACE_FRAG = `
  uniform vec3 color; uniform float opacity; uniform float progress; uniform float total; uniform vec2 dash; uniform float soft;
  varying float vDist; varying float vSide;
  void main() {
    if (vDist > progress * total) discard;
    if (dash.x > 0.0 && mod(vDist, dash.x + dash.y) > dash.x) discard;
    float aa = fwidth(vSide) * 1.5;
    float a = 1.0 - smoothstep(1.0 - aa - soft, 1.0, abs(vSide));  // soft — к краю гаснет: светящаяся нить
    gl_FragColor = vec4(color, opacity * a);
  }`;

export function traceMesh(spec) {
  const P = curvePoints(spec.points || [[0, 0], [10, 0]], spec.smooth !== false);
  const n = P.length;
  const half = (spec.width ?? 0.3) / 2;
  const pos = new Float32Array(n * 6), nrm = new Float32Array(n * 6), dist = new Float32Array(n * 2), side = new Float32Array(n * 2);
  let d = 0;
  const t = new THREE.Vector3(), nv = new THREE.Vector3(), Z = new THREE.Vector3(0, 0, 1);
  for (let i = 0; i < n; i++) {
    if (i) d += P[i].distanceTo(P[i - 1]);
    t.subVectors(P[Math.min(n - 1, i + 1)], P[Math.max(0, i - 1)]).normalize();
    nv.crossVectors(Z, t).normalize();  // нормаль в плоскости линии (x, y)
    for (let s = 0; s < 2; s++) {
      const k = s ? -1 : 1, j = i * 2 + s;
      pos[j * 3] = P[i].x + nv.x * half * k; pos[j * 3 + 1] = P[i].y + nv.y * half * k; pos[j * 3 + 2] = P[i].z;
      nrm[j * 3] = nv.x; nrm[j * 3 + 1] = nv.y; nrm[j * 3 + 2] = 0;
      dist[j] = d; side[j] = k;
    }
  }
  const idx = [];
  for (let i = 0; i < n - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('nrm', new THREE.BufferAttribute(nrm, 3));
  geo.setAttribute('dist', new THREE.BufferAttribute(dist, 1));
  geo.setAttribute('side', new THREE.BufferAttribute(side, 1));
  geo.setIndex(idx);
  const w = spec.wave || {};
  const mat = new THREE.ShaderMaterial({
    uniforms: { color: { value: new THREE.Color(spec.color || '#141414') }, opacity: { value: 1 }, progress: { value: 1 },
      total: { value: d }, dash: { value: new THREE.Vector2(...(spec.dash || [0, 0])) }, time: { value: 0 }, soft: { value: spec.soft || 0 },
      wave: { value: new THREE.Vector4(w.amp || 0, w.freq ?? 1, w.speed ?? 8, 0) } },
    vertexShader: TRACE_VERT, fragmentShader: TRACE_FRAG,
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    blending: spec.add ? THREE.AdditiveBlending : THREE.NormalBlending,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.frustumCulled = false;
  mesh.userData.noDepth = true;  // тонкая линия: резкость — как у того, что за ней
  return { mesh, total: d };
}

export function updateTrace(mesh, el, t, u, gk) {
  const U = mesh.material.uniforms;
  U.progress.value = el.grow ? smooth(el.grow[0], el.grow[1], u) : 1;
  U.opacity.value = gk;
  U.time.value = t;
  const w = el.wave;
  if (w) U.wave.value.x = (w.amp || 0) * (w.fade ? 1 - smooth(w.fade[0], w.fade[1], u) : 1);
}

// ---------------------------------------------------------------- вращение: угол из скорости с разгоном (интеграл)

export function spinAngle(spin, lt, dur) {
  const s0 = spin.speed || 0, s1 = spin.speed_to ?? s0;
  const [a, b] = (spin.ramp || [0, 1]).map(x => x * dur);
  const T = Math.max(b - a, 1e-6);
  const x0 = Math.min(lt, a), x1 = clamp(lt - a, 0, T), x2 = Math.max(0, lt - b);
  const ang = s0 * x0 + s0 * x1 + (s1 - s0) * x1 * x1 / (2 * T) + s1 * x2;
  const speed = lt < a ? s0 : lt > b ? s1 : lerp(s0, s1, x1 / T);
  return { ang: (spin.phase || 0) + ang, speed };
}

// ---------------------------------------------------------------- падение листа: маятник, кувырок, мягкая посадка

export function fallPose(el, p0, r0, u) {
  const f = el.fall;
  const [a, b] = f.at || [0, 1];
  const k = clamp((u - a) / ((b - a) || 1e-6), 0, 1);
  const land = 1 - smooth(0.78, 1, k);          // у земли качание стихает
  const env = smooth(0, 0.12, k) * land;        // и не начинается рывком
  const ph = 2 * PI * (f.swings ?? 2.5) * k;
  const down = k < 0.85 ? k / 0.85 * 0.92 : 0.92 + 0.08 * smooth(0.85, 1, k);  // ровно, у колен — притормаживает
  const to = f.to || p0;
  const p = [lerp(p0[0], to[0], down) + (f.sway ?? 3) * Math.sin(ph) * env,
    lerp(p0[1], to[1], down) - Math.abs(Math.cos(ph)) * (f.dip ?? 0.6) * env,  // в крайних точках маятника лист «подвисает»
    lerp(p0[2], to[2], down)];
  const rt = f.rot_to || r0;
  const r = [lerp(r0[0], rt[0], smooth(0.6, 1, k)) + (f.flutter ?? 35) * Math.sin(ph * 2 + 0.7) * env,
    lerp(r0[1], rt[1], k) + (f.turn ?? 40) * Math.sin(ph * 0.5) * env,
    lerp(r0[2], rt[2], smooth(0.6, 1, k)) + (f.tumble ?? 30) * Math.cos(ph) * env];
  return { p, r };
}
