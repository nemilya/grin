// Захват кадров сцены (stage/) браузером: стоп-кадры раскадровки или ролик целиком.
//
//   node tools/capture.mjs stills [story] [--scale 0.5] [--shots s01a,s05g] [--at 0.5]
//        → out/<story>/stills/<кадр>.jpg + contact.jpg (лист всех кадров)
//   node tools/capture.mjs video  [story] [--scale 1] [--from 0] [--to 30] [--fps 24] [--tl demo] [--no-share] [--no-subs]
//        --no-subs — without burnt-in subtitles (YouTube: upload the .srt of make youtube) → …-nosubs.mp4
//        → out/<story>/<story>[-demo].mp4 + …-share.mp4 (облегчённая для соцсетей); звук — build/sound[-demo].wav
//   node tools/capture.mjs share <файл.mp4>   → <файл>-share.mp4
//
// Сервер статики — свой (корень репозитория), браузер — Playwright Chromium (видеокарта, если есть, иначе SwiftShader). Каждый кадр рисуется из времени t, поэтому любой отрезок можно перерисовать отдельно.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const mode = args[0] || 'stills';
const story = args[1] && !args[1].startsWith('--') ? args[1] : 'mate-in-3';
const opt = (name, def) => { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def; };

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json',
  '.png': 'image/png', '.webp': 'image/webp', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.wav': 'audio/wav', '.css': 'text/css' };

function serve() {
  return new Promise(resolve => {
    const srv = http.createServer((req, res) => {
      const p = path.join(ROOT, decodeURIComponent(new URL(req.url, 'http://x').pathname));
      if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'content-type': TYPES[path.extname(p)] || 'application/octet-stream', 'cache-control': 'no-store' });
      fs.createReadStream(p).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

function playwright() {
  try {
    return require('playwright');
  } catch {
    console.error('Нет playwright. Один раз в корне проекта:  make setup   (или: npm install && npx playwright install chromium)');
    process.exit(1);
  }
}

// Где рисовать WebGL. По умолчанию (auto) — пробуем видеокарту: новый headless-режим Chromium (в старом
// headless-shell GPU обычно нет), на macOS — ANGLE через Metal; если вышел программный рендер — перезапуск
// в SwiftShader (он работает везде, ≈ 1 с/кадр при 720×1280). CAPTURE_GL=gpu / cpu — задать режим явно.
const GPU_ARGS = ['--ignore-gpu-blocklist', '--enable-gpu', '--enable-gpu-rasterization',
  ...(process.platform === 'darwin' ? ['--use-angle=metal'] : [])];
const CPU_ARGS = ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'];
const SOFTWARE = /swiftshader|llvmpipe|softpipe|software|нет webgl/i;

async function renderer(browser) {
  const page = await browser.newPage();
  const r = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2');
    const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
    return gl ? (ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : 'нет WebGL2';
  });
  await page.close();
  return r;
}

// Браузер: Chromium Playwright'а (npx playwright install chromium), иначе — установленный Google Chrome / Edge
// (на macOS 13 новые Playwright свой Chromium уже не ставят).
async function start(chromium, args, gpu) {
  const tries = [...(gpu ? [{ channel: 'chromium' }] : []), {}, { channel: 'chrome' }, { channel: 'msedge' }];
  let last;
  for (const o of tries) {
    try {
      const b = await chromium.launch({ ...o, args });
      if (o.channel === 'chrome' || o.channel === 'msedge') console.log(`  браузер: установленный ${o.channel === 'chrome' ? 'Google Chrome' : 'Edge'}`);
      return b;
    } catch (e) { last = e; }
  }
  console.error('✗ не запустился ни Chromium Playwright, ни Google Chrome:', last.message.split('\n')[0]);
  console.error('  поставьте Google Chrome или выполните: npx playwright install chromium');
  process.exit(1);
}

async function launch() {
  const { chromium } = playwright();
  const mode = (process.env.CAPTURE_GL || 'auto').toLowerCase();
  if (mode !== 'cpu') {
    const browser = await start(chromium, GPU_ARGS, true);
    const gl = await renderer(browser);
    if (mode === 'gpu' || !SOFTWARE.test(gl)) return { browser, gl, mode: 'gpu' };
    await browser.close(); // видеокарты не нашлось — надёжный программный режим
  }
  const browser = await start(chromium, CPU_ARGS, false);
  return { browser, gl: await renderer(browser), mode: 'cpu' };
}

async function open(scale, samples) {
  const { browser, gl, mode } = await launch();
  console.log(`  WebGL: ${gl} — ${mode === 'gpu' ? 'видеокарта' : 'программный рендер (видеокарта не найдена)'}`);
  const srv = await serve();
  const page = await browser.newPage({ viewport: { width: 400, height: 400 } });
  page.on('console', m => { if ((m.type() === 'error' || m.type() === 'warning') && !/GL Driver Message/.test(m.text())) console.log('  [page]', m.text()); });
  page.on('pageerror', e => console.log('  [page error]', e.message));
  const tl = opt('tl', '');
  const url = `http://127.0.0.1:${srv.address().port}/stage/index.html?story=${story}&capture&scale=${scale}&samples=${samples}${args.includes('--debug') ? '&debug' : ''}${args.includes('--no-subs') ? '&nosubs' : ''}${tl ? '&tl=' + tl : ''}`;
  await page.goto(url);
  await page.waitForFunction(() => window.STAGE && window.STAGE.ready, null, { timeout: 120000 });
  const info = await page.evaluate(() => ({ duration: STAGE.duration, fps: STAGE.fps, w: STAGE.width, h: STAGE.height, shots: STAGE.shots }));
  console.log(`  кадр ${info.w}×${info.h}, ${info.duration.toFixed(1)} с`);
  return { browser, srv, page, info };
}

const frame = (page, t) => page.evaluate(t => STAGE.frame(t), t).then(d => Buffer.from(d.split(',')[1], 'base64'));

// Кодирование. На macOS — аппаратный энкодер Apple (h264_videotoolbox): медиаблок чипа, процессор почти не занят;
// иначе libx264. CAPTURE_COOL=1 (make … COOL=1) — без перегрева: ffmpeg с низким приоритетом и в 2 потока,
// пауза между кадрами (видеокарта не молотит без передышки). CAPTURE_ENCODER=x264 / videotoolbox — задать явно.
const COOL = ['1', 'true', 'yes'].includes(String(process.env.CAPTURE_COOL || '').toLowerCase()) || args.includes('--cool');
let _encoders = null;
function hwEncoder() {
  const want = (process.env.CAPTURE_ENCODER || 'auto').toLowerCase();
  if (want === 'x264') return false;
  if (_encoders === null) _encoders = spawnSync('ffmpeg', ['-hide_banner', '-encoders'], { encoding: 'utf8' }).stdout || '';
  const has = /h264_videotoolbox/.test(_encoders);
  return want === 'videotoolbox' ? has : has && process.platform === 'darwin';
}
function videoArgs({ w, h, master }) {
  const px = w * h;
  if (hwEncoder()) { // битрейт по площади кадра: мастер 1080×1920 ≈ 16 Мбит/с, версия для соцсетей ≈ 3,5 Мбит/с
    const rate = master ? Math.round(px / 2073600 * 16000) : 3500;
    return ['-c:v', 'h264_videotoolbox', '-profile:v', 'high', '-b:v', `${rate}k`, '-maxrate', `${Math.round(rate * 1.5)}k`,
      '-bufsize', `${rate * 2}k`, '-allow_sw', '1', '-pix_fmt', 'yuv420p'];
  }
  const x = master ? ['-preset', COOL ? 'medium' : 'slow', '-crf', '17'] : ['-preset', COOL ? 'medium' : 'slow', '-crf', '23',
    '-maxrate', '3500k', '-bufsize', '7000k'];
  return ['-c:v', 'libx264', '-profile:v', 'high', ...x, ...(COOL ? ['-threads', '2'] : []), '-pix_fmt', 'yuv420p'];
}
function ffmpeg(argv, opts) { // в режиме COOL — с низким приоритетом
  return COOL && process.platform !== 'win32' ? ['nice', ['-n', '15', 'ffmpeg', ...argv], opts] : ['ffmpeg', argv, opts];
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function stills() {
  const scale = parseFloat(opt('scale', '0.5'));
  const at = parseFloat(opt('at', '0.55'));
  const only = opt('shots', '') ? opt('shots').split(',') : null;
  const { browser, srv, page, info } = await open(scale, opt('samples', '40'));
  const dir = path.join(ROOT, 'out', story, (opt('tl', '') ? opt('tl') + '-' : '') + (args.includes('--debug') ? 'stills-debug' : 'stills'));
  fs.mkdirSync(dir, { recursive: true });
  const shots = info.shots.filter(s => !only || only.includes(s.id));
  const t0 = Date.now();
  for (const s of shots) {
    const t = s.t0 + (s.t1 - s.t0) * at;
    fs.writeFileSync(path.join(dir, `${s.id}.jpg`), await frame(page, t));
    process.stdout.write(`\r  ${s.id} (${shots.indexOf(s) + 1}/${shots.length})   `);
  }
  console.log(`\n✓ ${shots.length} кадров, ${((Date.now() - t0) / shots.length / 1000).toFixed(2)} с/кадр → ${path.relative(ROOT, dir)}`);
  await browser.close(); srv.close();
  if (!only || shots.length > 1) contact(dir, shots.map(s => s.id), info.w > info.h);
}

function contact(dir, ids, landscape = false) {
  // лист: 8 в ряд (горизонталь — 5), подпись — id кадра
  const cols = landscape ? 5 : 8, list = path.join(dir, 'list.txt');
  const tile = landscape ? '480:270' : '270:480';
  fs.writeFileSync(list, ids.map(i => `file '${i}.jpg'`).join('\n'));
  const rows = Math.ceil(ids.length / cols);
  const r = spawnSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', list,
    '-vf', `scale=${tile},drawtext=text='%{metadata\\:id}':x=8:y=8:fontsize=18:fontcolor=white,tile=${cols}x${rows}:padding=6:color=0x14110e`,
    '-frames:v', '1', path.join(dir, 'contact.jpg')], { stdio: 'inherit' });
  if (r.status === 0) console.log(`✓ лист → ${path.relative(ROOT, path.join(dir, 'contact.jpg'))}`);
}

async function video() {
  const scale = parseFloat(opt('scale', '1'));
  const { browser, srv, page, info } = await open(scale, opt('samples', '64'));
  const fps = parseFloat(opt('fps', String(info.fps || 24)));
  const from = parseFloat(opt('from', '0')), to = Math.min(info.duration, parseFloat(opt('to', String(info.duration))));
  const dir = path.join(ROOT, 'out', story);
  fs.mkdirSync(dir, { recursive: true });
  const tlName = opt('tl', '');
  const name = opt('out', (tlName ? `${story}-${tlName}` : story) + (from > 0 || to < info.duration ? `-${from}-${to}` : '')
    + (args.includes('--no-subs') ? '-nosubs' : '') + '.mp4');  // without burnt-in subtitles: for YouTube + .srt
  const voice = path.join(ROOT, 'stories', story, 'build', tlName ? `sound-${tlName}.wav` : 'sound.wav');
  const audio = fs.existsSync(voice) ? ['-ss', String(from), '-t', String(to - from), '-i', voice] : [];
  const enc = videoArgs({ w: info.w, h: info.h, master: true });
  console.log(`  кодек: ${enc[1]}${COOL ? ' · режим без перегрева (COOL)' : ''}`);
  const ff = spawn(...ffmpeg(['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', 'pipe:0',
    ...audio, ...enc, '-movflags', '+faststart',
    ...(audio.length ? ['-c:a', 'aac', '-b:a', '160k', '-shortest'] : []), path.join(dir, name)], { stdio: ['pipe', 'inherit', 'inherit'] }));
  const n = Math.round((to - from) * fps);
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    const buf = await frame(page, from + i / fps);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (COOL) await sleep(60);
    if (i % 24 === 0) {
      const el = (Date.now() - t0) / 1000, eta = el / (i + 1) * (n - i - 1);
      process.stdout.write(`\r  кадр ${i + 1}/${n}  ${(el / (i + 1)).toFixed(2)} с/кадр  осталось ~${Math.round(eta / 60)} мин   `);
    }
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  console.log(`\n✓ ${path.relative(ROOT, path.join(dir, name))}`);
  if (!args.includes('--no-share')) share(path.join(dir, name));
  await browser.close(); srv.close();
}

// Версия для соцсетей: короткая сторона 720 (720×1280 / 1280×720, не больше исходника), H.264 high, ≈ 3,5 Мбит/с, AAC 128k,
// moov в начале (faststart) — Reels / Shorts / TikTok / Telegram принимают без перекодирования; ≈ 25 МБ/мин.
function share(src) {
  const dst = src.replace(/\.mp4$/, '-share.mp4');
  const r = spawnSync(...ffmpeg(['-y', '-loglevel', 'error', '-i', src,
    '-vf', "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)':flags=lanczos", ...videoArgs({ master: false }),
    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-movflags', '+faststart', dst], { stdio: 'inherit' }));
  if (r.status) { console.error('✗ share: ffmpeg'); return; }
  const mb = n => (fs.statSync(n).size / 1048576).toFixed(1);
  console.log(`✓ для соцсетей → ${path.relative(ROOT, dst)} (${mb(dst)} МБ; мастер ${mb(src)} МБ)`);
}

const run = { video, stills, share: async () => share(path.resolve(args[1] || '')) }[mode] || stills;
run().catch(e => { console.error(e); process.exit(1); });
