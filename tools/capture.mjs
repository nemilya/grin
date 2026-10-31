// Захват кадров сцены (stage/) браузером: стоп-кадры раскадровки или ролик целиком.
//
//   node tools/capture.mjs stills [story] [--scale 0.5] [--shots s01a,s05g] [--at 0.5]
//        → out/<story>/stills/<кадр>.jpg + contact.jpg (лист всех кадров)
//   node tools/capture.mjs video  [story] [--scale 1] [--from 0] [--to 30] [--fps 24] [--tl demo] [--no-share] [--subs]
//        a film has no burnt-in subtitles (YouTube: upload the .srt of make youtube); --subs — burn them in → …-subs.mp4
//        (Shorts, Reels, Telegram); stills show subtitles unless --no-subs
//        → out/<story>/<story>[-demo].mp4 + …-share.mp4 (облегчённая для соцсетей); звук — build/sound[-demo].wav
//   node tools/capture.mjs share <файл.mp4>   → <файл>-share.mp4
//   node tools/capture.mjs thumbnail <story> [--tl horizontal] [--shot s01a] …   → a YouTube thumbnail (see thumbnail())
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

async function open(scale, samples, subs = true) {
  const { browser, gl, mode } = await launch();
  console.log(`  WebGL: ${gl} — ${mode === 'gpu' ? 'видеокарта' : 'программный рендер (видеокарта не найдена)'}`);
  const srv = await serve();
  const page = await browser.newPage({ viewport: { width: 400, height: 400 } });
  page.on('console', m => { if ((m.type() === 'error' || m.type() === 'warning') && !/GL Driver Message/.test(m.text())) console.log('  [page]', m.text()); });
  page.on('pageerror', e => console.log('  [page error]', e.message));
  const tl = opt('tl', '');
  const url = `http://127.0.0.1:${srv.address().port}/stage/index.html?story=${story}&capture&scale=${scale}&samples=${samples}${args.includes('--debug') ? '&debug' : ''}${subs ? '' : '&nosubs'}${tl ? '&tl=' + tl : ''}`;
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
function videoArgs({ w, h, master, gentle = false }) {
  const px = w * h, cool = COOL || gentle;
  if (hwEncoder()) { // битрейт по площади кадра: мастер 1080×1920 ≈ 16 Мбит/с, версия для соцсетей ≈ 3,5 Мбит/с
    const rate = master ? Math.round(px / 2073600 * 16000) : 3500;
    return ['-c:v', 'h264_videotoolbox', '-profile:v', 'high', '-b:v', `${rate}k`, '-maxrate', `${Math.round(rate * 1.5)}k`,
      '-bufsize', `${rate * 2}k`, '-allow_sw', '1', '-pix_fmt', 'yuv420p'];
  }
  const x = master ? ['-preset', cool ? 'medium' : 'slow', '-crf', '17'] : ['-preset', cool ? 'medium' : 'slow', '-crf', '23',
    '-maxrate', '3500k', '-bufsize', '7000k'];
  return ['-c:v', 'libx264', '-profile:v', 'high', ...x, ...(cool ? ['-threads', '2'] : []), '-pix_fmt', 'yuv420p'];
}
function ffmpeg(argv, opts) { // в режиме COOL — с низким приоритетом
  return COOL && process.platform !== 'win32' ? ['nice', ['-n', '15', 'ffmpeg', ...argv], opts] : ['ffmpeg', argv, opts];
}
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function stills() {
  const scale = parseFloat(opt('scale', '0.5'));
  const at = parseFloat(opt('at', '0.55'));
  const only = opt('shots', '') ? opt('shots').split(',') : null;
  const { browser, srv, page, info } = await open(scale, opt('samples', '40'), !args.includes('--no-subs'));
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
  const subs = args.includes('--subs');  // a film has no burnt-in subtitles unless asked: YouTube takes the .srt of make youtube
  console.log(`  субтитры: ${subs ? 'вшиты в картинку (--subs)' : 'нет (отдельно — make youtube → .srt; вшить — SUBS=1)'}`);
  const { browser, srv, page, info } = await open(scale, opt('samples', '64'), subs);
  const fps = parseFloat(opt('fps', String(info.fps || 24)));
  const from = parseFloat(opt('from', '0')), to = Math.min(info.duration, parseFloat(opt('to', String(info.duration))));
  const dir = path.join(ROOT, 'out', story);
  fs.mkdirSync(dir, { recursive: true });
  const tlName = opt('tl', '');
  const name = opt('out', (tlName ? `${story}-${tlName}` : story) + (from > 0 || to < info.duration ? `-${from}-${to}` : '')
    + (subs ? '-subs' : '') + '.mp4');
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
  // Gentle by design — it runs right after a long render and must not spin the fans: the master is decoded by the
  // hardware decoder on a Mac (videotoolbox; elsewhere 2 threads), scaled in one thread (bicubic — at 720p it looks
  // the same as lanczos), encoded by the hardware encoder (or x264 in 2 threads), all at low priority (nice 15).
  const dst = src.replace(/\.mp4$/, '-share.mp4');
  const hw = hwEncoder();
  console.log(`  версия для соцсетей: 720p, ${hw ? 'аппаратное декодирование и кодирование' : 'x264 в 2 потока'}, низкий приоритет`);
  const argv = ['-y', '-hide_banner', '-loglevel', 'error', '-stats', ...(hw ? ['-hwaccel', 'videotoolbox'] : []), '-threads', '2',
    '-i', src, '-filter_threads', '1',
    '-vf', "scale='if(gt(iw,ih),-2,min(720,iw))':'if(gt(iw,ih),min(720,ih),-2)':flags=bicubic", ...videoArgs({ master: false, gentle: true }),
    '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-movflags', '+faststart', dst];
  const r = process.platform === 'win32' ? spawnSync('ffmpeg', argv, { stdio: 'inherit' })
    : spawnSync('nice', ['-n', '15', 'ffmpeg', ...argv], { stdio: 'inherit' });
  if (r.status) { console.error('✗ share: ffmpeg'); return; }
  const mb = n => (fs.statSync(n).size / 1048576).toFixed(1);
  console.log(`✓ для соцсетей → ${path.relative(ROOT, dst)} (${mb(dst)} МБ; мастер ${mb(src)} МБ)`);
}

// YouTube thumbnail: one shot without subtitles, 1280 px on the long side, with the title over it (site fonts).
//   node tools/capture.mjs thumbnail <story> [--tl horizontal] [--shot s01a] [--at 0.5] [--lang en] [--pos top|left|right]
//        [--title "…"] [--sub "…"] [--no-text]   → out/<story>/<story>[-tl]-thumb-<shot>.jpg (+ -raw.jpg, the clean frame)
// Defaults: the shot — the production's poster in site.json; the title, author and year — story.json; the line under
// them — the video's name in site.json.
async function thumbnail() {
  const readJSON = f => JSON.parse(fs.readFileSync(f, 'utf8'));
  const tlName = opt('tl', '');
  const tlFile = path.join(ROOT, 'stories', story, 'build', tlName ? `timeline-${tlName}.json` : 'timeline.json');
  if (!fs.existsSync(tlFile)) throw new Error(`нет ${path.relative(ROOT, tlFile)} — сначала make timeline`);
  const tl = readJSON(tlFile);
  let st = readJSON(path.join(ROOT, 'stories', story, 'story.json'));
  if (st.base) st = { ...readJSON(path.join(ROOT, 'stories', st.base, 'story.json')), ...st };
  const site = fs.existsSync(path.join(ROOT, 'site.json')) ? readJSON(path.join(ROOT, 'site.json')) : {};
  const video = (site.stories || []).flatMap(x => x.videos || []).find(v => v.production === story) || {};
  const lang = opt('lang', 'en');
  const pick = o => (o && typeof o === 'object' ? o[lang] || o.en || Object.values(o)[0] : o) || '';
  const shotId = opt('shot', (video.poster || [])[0]);
  const at = parseFloat(opt('at', String((video.poster || [])[0] === shotId && video.poster ? video.poster[1] : 0.5)));
  const scale = 1280 / Math.max(tl.width, tl.height);
  const { browser, srv, page, info } = await open(scale, opt('samples', '96'), false);
  const shot = info.shots.find(x => x.id === shotId);
  if (!shot) { await browser.close(); srv.close(); throw new Error(`нет кадра ${shotId}; есть: ${info.shots.map(x => x.id).join(' ')}`); }
  const raw = await frame(page, shot.t0 + (shot.t1 - shot.t0) * at);
  const base = path.join(ROOT, 'out', story, `${tlName ? `${story}-${tlName}` : story}-thumb-${shotId}`);
  fs.mkdirSync(path.dirname(base), { recursive: true });
  fs.writeFileSync(`${base}-raw.jpg`, raw);
  const data = (buf, type) => `data:${type};base64,${buf.toString('base64')}`;
  const font = (family, weight, style, file) => ['lat', 'cyr'].map(sub => {
    const f = path.join(ROOT, 'site', 'fonts', `${file}-${sub}.woff2`);
    return fs.existsSync(f) ? `@font-face { font-family: ${family}; font-weight: ${weight}; font-style: ${style};
      src: url(${data(fs.readFileSync(f), 'font/woff2')});${sub === 'cyr' ? ' unicode-range: U+0400-045F, U+0490-0491, U+2116;' : ''} }` : '';
  }).join('\n');
  const title = opt('title', pick(st.title)), by = [pick(st.author), st.year].filter(Boolean).join(' · ');
  const sub = opt('sub', pick(video.name));
  const pos = opt('pos', 'top');
  const box = { top: 'left: 0; right: 0; top: 7%; text-align: center',
                left: 'left: 5%; top: 9%; width: 55%', right: 'right: 4%; top: 12%; width: 42%; text-align: right' }[pos];
  const shade = { top: 'linear-gradient(180deg, rgba(0,0,0,.6) 0%, rgba(0,0,0,0) 45%)',
                  left: 'linear-gradient(90deg, rgba(0,0,0,.65) 0%, rgba(0,0,0,0) 60%)',
                  right: 'linear-gradient(270deg, rgba(0,0,0,.7) 0%, rgba(0,0,0,0) 60%)' }[pos];
  if (!box) throw new Error('--pos top | left | right');
  const k = info.w / 1280;  // text scales with the frame (vertical frames are 720 wide)
  const html = `<html><head><style>
    ${font('S', 600, 'normal', 'serif-600')} ${font('S', 400, 'italic', 'serif-400i')} ${font('G', 600, 'normal', 'golos-600')}
    html, body { margin: 0; width: ${info.w}px; height: ${info.h}px; overflow: hidden; background: #000; }
    .bg, .shade { position: absolute; inset: 0; } .bg { background: url(${data(raw, 'image/jpeg')}) center / cover; }
    .shade { background: ${shade}; }
    .t { position: absolute; ${box}; color: #f6ead2; text-shadow: 0 3px 18px rgba(0,0,0,.85), 0 1px 3px rgba(0,0,0,.9); }
    h1 { font: 600 ${Math.round(100 * k)}px/0.98 S; margin: 0; letter-spacing: -0.5px; }
    .by { font: 600 ${Math.round(30 * k)}px G; letter-spacing: .14em; text-transform: uppercase; color: #e8b45a; margin-top: ${Math.round(22 * k)}px; }
    .sub { font: italic 400 ${Math.round(34 * k)}px S; margin-top: ${Math.round(10 * k)}px; color: #f1e3c8; }
  </style></head><body><div class="bg"></div>${args.includes('--no-text') ? '' : `<div class="shade"></div>
    <div class="t"><h1>${title}</h1><div class="by">${by}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`}</body></html>`;
  const card = await browser.newPage({ viewport: { width: info.w, height: info.h } });
  await card.setContent(html, { waitUntil: 'load' });
  await card.evaluate(() => document.fonts.ready);
  await card.screenshot({ path: `${base}.jpg`, type: 'jpeg', quality: 92 });
  await browser.close(); srv.close();
  console.log(`✓ обложка → ${path.relative(ROOT, base)}.jpg (${info.w}×${info.h}; кадр ${shotId} @ ${at}; без текста — -raw.jpg)`);
}

const run = { video, stills, thumbnail, share: async () => share(path.resolve(args[1] || '')) }[mode] || stills;
run().catch(e => { console.error(e); process.exit(1); });
