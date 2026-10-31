// Бумага: фактура (цвет/рельеф), заглушки ассетов до генерации и процедурные карточки
// (звёзды-проколы, экран теней, лист с «10», шахматная вырезка, бумажный «?», свечение).
// Всё детерминировано (seed) — кадр N всегда одинаковый.
import * as THREE from 'three';

export function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function hashStr(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) h = Math.imul(h ^ str.charCodeAt(i), 16777619);
  return h >>> 0;
}

function canvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

// ---------------------------------------------------------------- фактура бумаги

let _paper = null;
// Рельеф волокон: шум + короткие волокна → normal map; общий для всех карточек.
export function paperTextures() {
  if (_paper) return _paper;
  const N = 512, r = rng(7);
  const hgt = new Float32Array(N * N);
  // крупная зернистость картона
  for (let o = 0; o < 4; o++) {
    const step = 64 >> o, amp = 0.5 / (o + 1);
    const g = [];
    const gn = N / step + 1;
    for (let i = 0; i < gn * gn; i++) g.push(r());
    for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
      const gx = x / step, gy = y / step, x0 = Math.floor(gx), y0 = Math.floor(gy);
      const fx = gx - x0, fy = gy - y0, sx = fx * fx * (3 - 2 * fx), sy = fy * fy * (3 - 2 * fy);
      const at = (i, j) => g[((j % (gn - 1)) * gn) + (i % (gn - 1))];
      const v = at(x0, y0) * (1 - sx) * (1 - sy) + at(x0 + 1, y0) * sx * (1 - sy) + at(x0, y0 + 1) * (1 - sx) * sy + at(x0 + 1, y0 + 1) * sx * sy;
      hgt[y * N + x] += v * amp;
    }
  }
  // волокна
  for (let k = 0; k < 2600; k++) {
    let x = r() * N, y = r() * N;
    const a = r() * Math.PI, len = 6 + r() * 22, d = (r() - 0.5) * 0.35;
    for (let s = 0; s < len; s++) {
      const xi = ((Math.round(x) % N) + N) % N, yi = ((Math.round(y) % N) + N) % N;
      hgt[yi * N + xi] += d;
      x += Math.cos(a); y += Math.sin(a);
    }
  }
  const nc = canvas(N, N), nctx = nc.getContext('2d'), nimg = nctx.createImageData(N, N);
  const cc = canvas(N, N), cctx = cc.getContext('2d'), cimg = cctx.createImageData(N, N);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const h = (i, j) => hgt[(((j + N) % N) * N) + ((i + N) % N)];
    const dx = (h(x + 1, y) - h(x - 1, y)) * 2.2, dy = (h(x, y + 1) - h(x, y - 1)) * 2.2;
    const l = Math.hypot(dx, dy, 1), i = (y * N + x) * 4;
    nimg.data[i] = (-dx / l * 0.5 + 0.5) * 255;
    nimg.data[i + 1] = (dy / l * 0.5 + 0.5) * 255;
    nimg.data[i + 2] = (1 / l * 0.5 + 0.5) * 255;
    nimg.data[i + 3] = 255;
    const v = 236 + (hgt[y * N + x] - 0.5) * 30;
    cimg.data[i] = v + 4; cimg.data[i + 1] = v; cimg.data[i + 2] = v - 8; cimg.data[i + 3] = 255;
  }
  nctx.putImageData(nimg, 0, 0);
  cctx.putImageData(cimg, 0, 0);
  const normal = new THREE.CanvasTexture(nc);
  normal.wrapS = normal.wrapT = THREE.RepeatWrapping;
  const grain = new THREE.CanvasTexture(cc);
  grain.wrapS = grain.wrapT = THREE.RepeatWrapping;
  grain.colorSpace = THREE.SRGBColorSpace;
  _paper = { normal, grain, canvas: cc };
  return _paper;
}

// ---------------------------------------------------------------- заглушки

const PX = 40; // пикселей на сантиметр заглушки

function shade(hex, k) {
  const c = new THREE.Color(hex || '#888888');
  c.multiplyScalar(k);
  return '#' + c.getHexString();
}

function cutPath(ctx, draw, w, h, border) {
  // белая кромка «ножниц»: обводка той же формы толще + заливка
  ctx.save();
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#f4efe4';
  ctx.lineWidth = border * 2;
  draw(ctx, w, h); ctx.stroke();
  ctx.fillStyle = '#f4efe4';
  draw(ctx, w, h); ctx.fill();
  ctx.restore();
}

function figure(ctx, w, h, facing, seated) {
  ctx.beginPath();
  const cx = w / 2, head = Math.min(w, h) * (seated ? 0.17 : 0.13);
  const hy = head * 1.25;
  ctx.ellipse(cx + (facing === 'left' ? -head * 0.15 : facing === 'right' ? head * 0.15 : 0), hy, head * 0.82, head, 0, 0, Math.PI * 2);
  const top = hy + head * 0.95;
  if (seated) {
    const dir = facing === 'left' ? -1 : 1;
    ctx.moveTo(cx - w * 0.2, top);
    ctx.lineTo(cx + w * 0.2, top);
    ctx.lineTo(cx + w * 0.22, h * 0.62);
    ctx.lineTo(cx + dir * w * 0.45, h * 0.62);
    ctx.lineTo(cx + dir * w * 0.45, h * 0.99);
    ctx.lineTo(cx + dir * w * 0.3, h * 0.99);
    ctx.lineTo(cx + dir * w * 0.3, h * 0.74);
    ctx.lineTo(cx - w * 0.24, h * 0.74);
    ctx.lineTo(cx - w * 0.22, top);
  } else {
    ctx.moveTo(cx - w * 0.2, top);
    ctx.lineTo(cx + w * 0.2, top);
    ctx.lineTo(cx + w * 0.3, h * 0.66);
    ctx.lineTo(cx + w * 0.16, h * 0.99);
    ctx.lineTo(cx - w * 0.16, h * 0.99);
    ctx.lineTo(cx - w * 0.3, h * 0.66);
  }
  ctx.closePath();
}

function label(ctx, w, h, text, color) {
  ctx.save();
  ctx.fillStyle = color;
  const fs = Math.max(11, Math.min(26, w / 12));
  ctx.font = `600 ${fs}px Georgia, serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'bottom';
  const words = String(text).split(/\s+/);
  const lines = [];
  let cur = '';
  for (const wd of words) {
    if (ctx.measureText(cur + ' ' + wd).width > w * 0.86 && cur) { lines.push(cur); cur = wd; } else cur = cur ? cur + ' ' + wd : wd;
  }
  lines.push(cur);
  lines.slice(-3).reverse().forEach((ln, i) => ctx.fillText(ln, w / 2, h - 10 - i * fs * 1.15));
  ctx.restore();
}

// Заглушка ассета: силуэт / прямоугольник с подписью — видно композицию до генерации картинок.
export function placeholder(key, spec) {
  const hcm = spec.size ? spec.size[1] : (spec.h || 10);
  const wcm = spec.size ? spec.size[0] : hcm * (spec.aspect || 1);
  const scale = Math.min(PX, 1600 / Math.max(wcm, hcm));
  const w = Math.max(16, Math.round(wcm * scale)), h = Math.max(16, Math.round(hcm * scale));
  const c = canvas(w, h), ctx = c.getContext('2d');
  const color = spec.color || '#9a8f80';
  const isFigure = /^(doctor|patient|woman-baby|girl|schoolgirl|lady|old-woman|wife|yard-keeper|stranger)\//.test(key);
  const kind = spec.kind;
  if (kind === 'backdrop' || kind === 'floor') {
    ctx.fillStyle = shade(color, kind === 'floor' ? 0.55 : 0.75);
    ctx.fillRect(0, 0, w, h);
    ctx.globalAlpha = 0.18;
    ctx.fillStyle = '#000';
    for (let x = 0; x < w; x += 22) ctx.fillRect(x, 0, 9, h);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = 'rgba(255,240,220,.35)'; ctx.lineWidth = 3;
    ctx.strokeRect(6, 6, w - 12, h - 12);
    label(ctx, w, h, spec.label || key, 'rgba(255,245,230,.75)');
  } else {
    const border = Math.max(3, Math.min(w * 0.025, h * 0.06)); // от меньшей стороны: длинные граунд-ряды тоже
    const pad = border * 1.6;
    ctx.translate(pad, pad);
    const iw = w - pad * 2, ih = h - pad * 2;
    const draw = isFigure && !/head|hands|arm-|in-bed|in-hammock|on-bench/.test(key)
      ? (x, ww, hh) => figure(x, ww, hh, spec.facing, /seated|at-window/.test(key))
      : (x, ww, hh) => { x.beginPath(); x.roundRect(0, 0, Math.max(1, ww), Math.max(1, hh), Math.max(0, Math.min(ww, hh) * 0.12)); };
    if (kind !== 'silhouette') cutPath(ctx, draw, iw, ih, border);
    ctx.fillStyle = kind === 'silhouette' ? '#050505' : color;
    draw(ctx, iw, ih); ctx.fill();
    ctx.globalAlpha = 0.25; ctx.fillStyle = '#000';
    for (let y = 0; y < ih; y += 7) { ctx.fillRect(0, y, iw, 1); }
    ctx.globalAlpha = 1;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    if (kind !== 'silhouette') label(ctx, w, h, spec.label || key, 'rgba(255,250,240,.9)');
  }
  if (spec.hole) { // окно / дверной проём — насквозь
    const [x0, y0, x1, y1] = spec.hole;
    ctx.clearRect(x0 * w, (1 - y1) * h, (x1 - x0) * w, (y1 - y0) * h);
  }
  return c;
}

// ---------------------------------------------------------------- процедурные карточки

function sheet(spec) {
  const w = 720, h = Math.round(720 / (spec.aspect || 0.72));
  const c = canvas(w, h), ctx = c.getContext('2d');
  const r = rng(hashStr(spec.text + (spec.crumbs ? 'c' : '')));
  ctx.fillStyle = '#f2ece0'; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(120,140,170,.25)'; ctx.lineWidth = 2;
  for (let y = 120; y < h; y += 46) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  if (spec.text) {
    // карандаш: графит, неровный нажим
    ctx.save();
    ctx.translate(w * 0.5, h * 0.52);
    ctx.rotate(-0.06);
    ctx.font = `italic 300px Georgia, "Times New Roman", serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (let k = 0; k < 7; k++) {
      ctx.fillStyle = `rgba(60,60,66,${0.12 + r() * 0.1})`;
      ctx.fillText(spec.text, (r() - 0.5) * 6, (r() - 0.5) * 6);
    }
    ctx.restore();
  }
  if (spec.crumbs) {
    ctx.fillStyle = 'rgba(80,80,90,.10)';
    ctx.fillRect(w * 0.22, h * 0.32, w * 0.56, h * 0.4); // след стёртого
    for (let k = 0; k < 90; k++) {
      ctx.fillStyle = `rgba(${170 + r() * 40},${120 + r() * 30},${120 + r() * 30},.9)`;
      ctx.beginPath(); ctx.ellipse(w * (0.2 + r() * 0.6), h * (0.3 + r() * 0.5), 3 + r() * 6, 2 + r() * 3, r() * 3, 0, 7); ctx.fill();
    }
  }
  return c;
}

const PIECES = { K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙', k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };

function chess(spec) {
  const w = 900, h = Math.round(900 / (spec.aspect || 0.78));
  const c = canvas(w, h), ctx = c.getContext('2d');
  ctx.fillStyle = '#ebe2cf'; ctx.fillRect(0, 0, w, h);
  // неровный край вырезки
  ctx.globalCompositeOperation = 'destination-in';
  ctx.beginPath();
  const r = rng(11);
  ctx.moveTo(8, 8);
  for (let x = 8; x < w - 8; x += 30) ctx.lineTo(x, 6 + r() * 6);
  for (let y = 8; y < h - 8; y += 30) ctx.lineTo(w - 6 - r() * 6, y);
  for (let x = w - 8; x > 8; x -= 30) ctx.lineTo(x, h - 6 - r() * 6);
  for (let y = h - 8; y > 8; y -= 30) ctx.lineTo(6 + r() * 6, y);
  ctx.closePath(); ctx.fill();
  ctx.globalCompositeOperation = 'source-over';
  const cap = spec.caption || ['LEIPZIG', 'International Tournament', 'Mate in three moves'];
  ctx.fillStyle = '#1d1a16'; ctx.textAlign = 'center';
  ctx.font = '600 64px Georgia, serif'; ctx.fillText(cap[0], w / 2, 92);
  ctx.font = 'italic 38px Georgia, serif'; ctx.fillText(cap[1] || '', w / 2, 140);
  const S = 680, x0 = (w - S) / 2, y0 = 175, q = S / 8;
  ctx.strokeStyle = '#1d1a16'; ctx.lineWidth = 5; ctx.strokeRect(x0, y0, S, S);
  for (let i = 0; i < 8; i++) for (let j = 0; j < 8; j++) {
    if ((i + j) % 2 === 1) { // тёмные поля — штриховка, как в журнальной диаграмме
      ctx.save(); ctx.beginPath(); ctx.rect(x0 + i * q, y0 + j * q, q, q); ctx.clip();
      ctx.strokeStyle = '#3a342c'; ctx.lineWidth = 2;
      for (let d = -q; d < q * 2; d += 8) { ctx.beginPath(); ctx.moveTo(x0 + i * q + d, y0 + j * q); ctx.lineTo(x0 + i * q + d - q, y0 + j * q + q); ctx.stroke(); }
      ctx.restore();
    }
  }
  const fen = (spec.fen || '6k1/5ppp/8/8/8/8/5PPP/3R2K1').split(' ')[0];
  ctx.font = `${q * 0.82}px "DejaVu Sans", "Segoe UI Symbol", "Apple Symbols", "Noto Sans Symbols2", serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  fen.split('/').forEach((row, j) => {
    let i = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) { i += +ch; continue; }
      const cx = x0 + i * q + q / 2, cy = y0 + j * q + q / 2 + q * 0.04;
      ctx.fillStyle = '#f5efe2'; ctx.beginPath(); ctx.arc(cx, cy, q * 0.34, 0, 7); ctx.fill();
      ctx.fillStyle = '#14110e'; ctx.fillText(PIECES[ch] || '?', cx, cy);
      i++;
    }
  });
  ctx.font = 'italic 36px Georgia, serif'; ctx.fillStyle = '#1d1a16';
  ctx.fillText(cap[2] || '', w / 2, y0 + S + 52);
  return c;
}

function question(spec) {
  const w = 600, h = Math.round(600 / (spec.aspect || 0.6));
  const c = canvas(w, h), ctx = c.getContext('2d');
  ctx.font = `bold ${h * 0.95}px Georgia, serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 26; ctx.strokeText('?', w / 2, h * 0.54);
  ctx.fillStyle = spec.color || '#efe6d2'; ctx.fillText('?', w / 2, h * 0.54);
  ctx.globalAlpha = 0.25; ctx.strokeStyle = '#8a7a60'; ctx.lineWidth = 3; ctx.strokeText('?', w / 2, h * 0.54);
  return c;
}

function screenTex(spec) {
  const w = 1024, h = Math.round(1024 * spec.size[1] / spec.size[0]);
  const c = canvas(w, h), ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(w / 2, h * 0.55, 10, w / 2, h * 0.55, w * 0.7);
  g.addColorStop(0, spec.color || '#f3dcb4'); g.addColorStop(1, shade(spec.color || '#f3dcb4', 0.35));
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  const p = paperTextures().canvas;
  ctx.globalAlpha = 0.5; ctx.globalCompositeOperation = 'multiply';
  for (let x = 0; x < w; x += 512) for (let y = 0; y < h; y += 512) ctx.drawImage(p, x, y);
  return c;
}

function glowTex(spec) {
  const N = 256, c = canvas(N, N), ctx = c.getContext('2d');
  const col = new THREE.Color(spec.color || '#ffcf8a');
  if (spec.size && spec.size[0] !== spec.size[1] && spec.size[0] > 1) { // дверной проём — ровный свет с мягким краем
    ctx.fillStyle = '#' + col.getHexString(); ctx.fillRect(0, 0, N, N);
    return c;
  }
  const g = ctx.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
  g.addColorStop(0, '#ffffff'); g.addColorStop(0.25, '#' + col.getHexString()); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, N, N);
  return c;
}

// интертитр немого кино: тёмная карточка, двойная рамка с уголками, текст кремовым шрифтом сцены.
// spec.text — текст (big — крупно: номер главы), spec.attr — подпись (эпиграф), spec.lines — заглавие [автор, название]
// интертитр русского авангарда 1918 (look: suprematist): белое поле, супрематические фигуры, рубленый шрифт
// заглавными, строки лесенкой с наклоном; у глав — огромная цифра и своя композиция из красного и чёрного
function suprematistCard(spec) {
  const w = 1920, h = Math.round(1920 * (spec.size ? spec.size[1] / spec.size[0] : 9 / 16));
  const c = canvas(w, h), x = c.getContext('2d');
  const RED = '#c8281e', BLACK = '#151413', PAPER = '#f3efe4', GREEN = '#2f8f4e';  // зелёный — по элементу на карточку: лист
  x.fillStyle = PAPER; x.fillRect(0, 0, w, h);
  const sans = px => `600 ${px}px "Stage Sans", "Golos Text", Arial, sans-serif`;
  const rect = (cx, cy, rw, rh, deg, col) => { x.save(); x.translate(cx, cy); x.rotate(deg * Math.PI / 180); x.fillStyle = col; x.fillRect(-rw / 2, -rh / 2, rw, rh); x.restore(); };
  const disc = (cx, cy, r, col) => { x.fillStyle = col; x.beginPath(); x.arc(cx, cy, r, 0, 2 * Math.PI); x.fill(); };
  const text = (s, cx, cy, px, deg, col, align = 'left', track = 0) => {
    x.save(); x.translate(cx, cy); x.rotate(deg * Math.PI / 180); x.font = sans(px); x.fillStyle = col;
    x.textAlign = align; x.textBaseline = 'alphabetic';
    if (x.letterSpacing !== undefined) x.letterSpacing = `${track}px`;
    x.fillText(s, 0, 0); x.restore();
  };
  const u = Math.min(w, h), tall = h > w;  // размеры — от меньшей стороны; вертикаль — своя раскладка
  if (spec.lines) { // заглавная: автор (красный, в разрядку), название лесенкой, чёрный квадрат и красный круг
    if (tall) { rect(w * 0.66, h * 0.17, u * 0.5, u * 0.5, 12, GREEN); disc(w * 0.22, h * 0.86, u * 0.14, RED); rect(w * 0.5, h * 0.75, w * 1.1, u * 0.012, -6, BLACK); }
    else { rect(w * 0.86, h * 0.3, u * 0.42, u * 0.42, 12, GREEN); disc(w * 0.9, h * 0.8, u * 0.11, RED); rect(w * 0.4, h * 0.88, w * 0.7, u * 0.012, -6, BLACK); }
    const words = (spec.lines[1] || '').toUpperCase().split(/\s+/);
    const lim = Math.max(15, ...words.map(wd => wd.length)), rows = [];  // строки лесенкой — по длине (≤ 15 знаков)
    for (const wd of words) { if (rows.length && (rows[rows.length - 1] + ' ' + wd).length <= lim) rows[rows.length - 1] += ' ' + wd; else rows.push(wd); }
    const x0 = w * 0.08, top = tall ? h * 0.47 : h * 0.4, maxW = (tall ? 0.84 : 0.6) * w - rows.length * u * 0.05;
    let px = u * (tall ? 0.16 : 0.15);
    x.font = sans(px);
    px *= Math.min(1, maxW / Math.max(...rows.map(r => x.measureText(r).width), 1));
    text((spec.lines[0] || '').toUpperCase(), x0, top - px * 1.15, u * 0.045, -6, RED, 'left', u * 0.012);
    rows.forEach((r, i) => text(r, x0 + i * u * 0.05, top + i * px * 1.12, px, -6, BLACK));
    return c;
  }
  if (spec.big) { // глава: огромная цифра; композиция — своя для каждой главы
    const n = (spec.text || '').length;
    const comp = [
      () => { rect(w * 0.5, h * 0.55, Math.hypot(w, h) * 1.1, u * 0.07, tall ? -60 : -18, RED); disc(w * 0.78, h * 0.25, u * 0.09, GREEN); },
      () => { rect(w * (tall ? 0.55 : 0.7), h * (tall ? 0.3 : 0.5), u * 0.55, u * 0.55, -10, RED); rect(w * 0.4, h * (tall ? 0.72 : 0.8), w * 0.6, u * 0.03, 4, GREEN); },
      () => { disc(w * (tall ? 0.5 : 0.68), h * (tall ? 0.36 : 0.48), u * 0.3, RED); rect(w * 0.5, h * 0.5, Math.hypot(w, h), u * 0.015, tall ? -62 : -30, BLACK);
        rect(w * 0.18, h * 0.18, u * 0.12, u * 0.12, 20, GREEN); },
    ][(n - 1) % 3];
    comp();
    text(spec.text || '', w * (tall ? 0.5 : 0.42), h * (tall ? 0.62 : 0.78), u * 0.62, -6, BLACK, 'center');
    return c;
  }
  const words = (spec.text || '').split(/\s+/), lines = [];
  const px = h * 0.05, maxW = w * 0.62;
  x.font = sans(px);
  let cur = '';
  for (const wd of words) { const t = cur ? cur + ' ' + wd : wd; if (x.measureText(t).width > maxW && cur) { lines.push(cur); cur = wd; } else cur = t; }
  if (cur) lines.push(cur);
  rect(w * 0.08, h * 0.5, h * 0.02, h * 0.6, 0, RED);
  lines.forEach((ln, i) => text(ln, w * 0.12, h * 0.5 + (i - lines.length / 2 + 0.8) * px * 1.4, px, 0, BLACK));
  return c;
}

function titleCard(spec) {
  if (spec.look === 'suprematist') return suprematistCard(spec);
  const w = 1920, h = Math.round(1920 * (spec.size ? spec.size[1] / spec.size[0] : 9 / 16));
  const c = canvas(w, h), ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, w * 0.62);
  g.addColorStop(0, '#1c1914'); g.addColorStop(1, '#070605');
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  const ink = '#e9dfc8';
  ctx.strokeStyle = ink; ctx.fillStyle = ink;
  const m = h * 0.07, m2 = m + 14;
  ctx.lineWidth = 4; ctx.strokeRect(m, m, w - 2 * m, h - 2 * m);
  ctx.lineWidth = 1.5; ctx.strokeRect(m2, m2, w - 2 * m2, h - 2 * m2);
  for (const [x, y] of [[m, m], [w - m, m], [m, h - m], [w - m, h - m]]) { // уголки: ромб и завиток
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4);
    ctx.fillRect(-11, -11, 22, 22);
    ctx.restore();
  }
  const rule = (y, half) => { ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(w / 2 - half, y); ctx.lineTo(w / 2 + half, y); ctx.stroke();
    ctx.save(); ctx.translate(w / 2, y); ctx.rotate(Math.PI / 4); ctx.fillRect(-7, -7, 14, 14); ctx.restore(); };
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  const font = (px, it) => `${it ? 'italic ' : ''}${px}px "Paper Serif", Georgia, serif`;
  if (spec.lines) { // заглавная карточка: автор, линейка, название
    ctx.font = font(h * 0.055); ctx.fillText(spec.lines[0] || '', w / 2, h * 0.36);
    rule(h * 0.45, w * 0.12);
    let px = h * 0.1;
    ctx.font = font(px);
    px *= Math.min(1, w * 0.74 / Math.max(1, ctx.measureText(spec.lines[1] || '').width)); // длинное название — мельче, в рамку
    ctx.font = font(px); ctx.fillText(spec.lines[1] || '', w / 2, h * 0.57);
    return c;
  }
  if (spec.big) {
    ctx.font = font(h * 0.3); ctx.fillText(spec.text || '', w / 2, h * 0.5);
    rule(h * 0.72, w * 0.08);
    return c;
  }
  const px = h * 0.052, lh = px * 1.45, maxW = w * 0.66;
  ctx.font = font(px, true);
  const words = (spec.text || '').split(/\s+/), lines = [];
  let cur = '';
  for (const wd of words) { const t = cur ? cur + ' ' + wd : wd; if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = wd; } else cur = t; }
  if (cur) lines.push(cur);
  const total = lines.length * lh + (spec.attr ? lh * 1.6 : 0);
  let y = h / 2 - total / 2 + lh / 2;
  for (const ln of lines) { ctx.fillText(ln, w / 2, y); y += lh; }
  if (spec.attr) {
    ctx.font = font(px * 0.82); ctx.textAlign = 'right';
    ctx.fillText(spec.attr, w / 2 + maxW / 2, y + lh * 0.6);
  }
  return c;
}

export function procedural(spec) {
  switch (spec.draw) {
    case 'title': return titleCard(spec);
    case 'sheet': return sheet(spec);
    case 'chess': return chess(spec);
    case 'question': return question(spec);
    case 'screen': return screenTex(spec);
    case 'glow': return glowTex(spec);
    case 'shape': case 'trace': return canvas(2, 2);  // рисует сцена (geometry.js)
    case 'stars': { const c = canvas(8, 8); const x = c.getContext('2d'); x.fillStyle = '#020203'; x.fillRect(0, 0, 8, 8); return c; }
    default: return null;
  }
}
