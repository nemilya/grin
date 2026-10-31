/* Видео в браузере, без mp4: сцена (stage.js, WebGL) рисует кадр по таймлайну в момент t, время берётся
 * из звука (<audio> — голос, фон, музыка). Вертикаль на телефоне и узком/портретном экране, горизонталь —
 * на широком; переключатель ⇄ (позиция сохраняется). Разрешение и число лучей фокуса — по экрану:
 * сцена считается во время просмотра. Место просмотра запоминается (localStorage). */
(() => {
  const D = JSON.parse(document.getElementById('data').textContent);
  const $ = (s) => document.querySelector(s);
  const audio = $('#audio'), frame = $('#frame'), poster = $('#poster'), big = $('#big'), loading = $('#loading');
  const pp = $('#pp'), seek = $('#seek'), cur = $('#cur'), cc = $('#cc'), orBtn = $('#or'), fsBtn = $('#fs');
  const watch = $('#watch');
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* приватный режим */ } },
  };
  const coarse = matchMedia('(pointer: coarse)').matches;
  const narrow = () => matchMedia('(orientation: portrait), (max-width: 760px)').matches;
  const q = new URLSearchParams(location.search);
  const pick = () => ((narrow() && D.formats.vertical) || !D.formats.horizontal ? 'vertical' : 'horizontal');
  let orient = q.get('o') && D.formats[q.get('o')] ? q.get('o') : pick();
  let stage = null, building = null, subtitles = store.get('subtitles', true);

  const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  function layout() {
    const f = D.formats[orient];
    frame.style.aspectRatio = `${f.width} / ${f.height}`;
    watch.dataset.orient = orient;
    poster.src = f.poster || '';
    poster.hidden = !f.poster;
  }
  layout();

  function webgl() {
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
  }

  // сцена текущей ориентации: таймлайн → Stage (разрешение под экран) → загрузка слоёв
  async function makeStage() {
    if (!webgl()) { loading.hidden = false; loading.textContent = D.ui.no_webgl; throw new Error('webgl'); }
    const f = D.formats[orient];
    const tl = await fetch(f.timeline).then((r) => r.json());
    const box = frame.getBoundingClientRect();
    const dpr = Math.min(devicePixelRatio || 1, coarse ? 1.5 : 2);
    const want = Math.max(box.height, box.width * f.height / f.width) * dpr;
    let scale = Math.min(1, Math.max(0.3, want / f.height));
    if (coarse) scale = Math.min(scale, 0.5);
    while (!window.Stage) await new Promise((r) => addEventListener('stage-ready', r, { once: true }));
    loading.hidden = false;
    const s = new window.Stage(tl, { base: D.base, scale, samples: coarse ? 18 : 30,
      onProgress: (n, all) => { $('#pct').textContent = `${Math.round((n / all) * 100)}%`; } });
    await s.load();
    s.subtitles = subtitles;
    s.out.className = 'scene';
    frame.querySelector('canvas.scene')?.remove();
    frame.prepend(s.out);
    loading.hidden = true;
    stage = s;
    draw();
    return s;
  }
  const ensure = () => (building ??= makeStage().finally(() => { building = null; }));

  let raf = 0;
  function draw() {
    if (!stage) return;
    const t = audio.currentTime;
    stage.renderAt(Math.min(t, D.duration - 0.01));
    if (!seeking) seek.value = t;
    cur.textContent = clock(t);
  }
  const loop = () => { draw(); raf = audio.paused ? 0 : requestAnimationFrame(loop); };

  async function play() {
    big.hidden = true;
    poster.hidden = true;
    if (!stage) await ensure();
    try { await audio.play(); } catch { big.hidden = false; }
  }
  const toggle = () => (audio.paused ? play() : audio.pause());
  big.onclick = play;
  pp.onclick = toggle;
  frame.addEventListener('click', (ev) => { if (ev.target !== big && !big.contains(ev.target) && stage) toggle(); });
  audio.addEventListener('play', () => { pp.textContent = '❚❚'; pp.setAttribute('aria-label', D.ui.pause); watch.classList.add('playing'); if (!raf) loop(); });
  audio.addEventListener('pause', () => { pp.textContent = '▶'; pp.setAttribute('aria-label', D.ui.play); watch.classList.remove('playing'); store.set(`video:${D.key}`, audio.currentTime); });
  audio.addEventListener('seeked', draw);
  audio.addEventListener('ended', () => { store.set(`video:${D.key}`, 0); big.hidden = false; });
  setInterval(() => { if (!audio.paused) store.set(`video:${D.key}`, audio.currentTime); }, 5000);

  let seeking = false;
  seek.addEventListener('input', () => { seeking = true; cur.textContent = clock(+seek.value); });
  seek.addEventListener('change', async () => {
    seeking = false;
    audio.currentTime = +seek.value;
    if (!stage) { big.hidden = true; poster.hidden = true; await ensure(); }
    draw();
  });

  const paintCC = () => { cc.classList.toggle('on', subtitles); cc.setAttribute('aria-pressed', subtitles); };
  paintCC();
  cc.onclick = () => { subtitles = !subtitles; store.set('subtitles', subtitles); if (stage) { stage.subtitles = subtitles; draw(); } paintCC(); };

  orBtn?.addEventListener('click', async () => {
    orient = orient === 'vertical' ? 'horizontal' : 'vertical';
    const was = !audio.paused;
    audio.pause();
    stage = null;
    frame.querySelector('canvas.scene')?.remove();
    layout();
    try { history.replaceState(null, '', `?o=${orient}`); } catch { /* */ }
    if (was || audio.currentTime > 0) { poster.hidden = true; big.hidden = true; await ensure(); if (was) play(); }
  });

  fsBtn.onclick = () => {
    const el = watch;
    if (document.fullscreenElement) document.exitFullscreen();
    else (el.requestFullscreen || el.webkitRequestFullscreen)?.call(el).catch?.(() => {});
  };
  document.addEventListener('fullscreenchange', () => watch.classList.toggle('full', !!document.fullscreenElement));

  document.addEventListener('keydown', (ev) => {
    if (ev.target.closest('input, select, textarea') || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const k = ev.key.toLowerCase();
    if (k === ' ' || k === 'k') { ev.preventDefault(); toggle(); }
    else if (k === 'arrowright') { ev.preventDefault(); audio.currentTime = Math.min(D.duration, audio.currentTime + 5); }
    else if (k === 'arrowleft') { ev.preventDefault(); audio.currentTime = Math.max(0, audio.currentTime - 5); }
    else if (k === 'c') cc.click();
    else if (k === 'f') fsBtn.click();
  });

  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: D.title, artist: D.author, album: D.name });
    navigator.mediaSession.setActionHandler('play', play);
    navigator.mediaSession.setActionHandler('pause', () => audio.pause());
  }

  // продолжить с места, где остановились
  const t0 = store.get(`video:${D.key}`, 0);
  if (t0 > 2 && t0 < D.duration - 5) {
    audio.addEventListener('loadedmetadata', () => { audio.currentTime = t0; seek.value = t0; cur.textContent = clock(t0); }, { once: true });
  }
})();
