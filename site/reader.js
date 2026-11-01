/* Reading with narration: a section's text is split into pages by screen height (no scrolling), the sentence
 * and word being heard are highlighted, the page turns after the voice. A click on a word — listen from it.
 * The timing marks are in <script id="data">: paragraphs → sentences [a, b, t0, t1] and words [a, b, t0, t1]
 * (offsets in the paragraph text, seconds in the section's mp3). */
(() => {
  const D = JSON.parse(document.getElementById('data').textContent);
  const $ = (s) => document.querySelector(s);
  const reader = $('.reader');
  const audio = $('#audio'), pageEl = $('#page'), pp = $('#pp'), seek = $('#seek'), cur = $('#cur');
  const speedBtn = $('#speed'), followBtn = $('#follow');
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
  };
  // book progress — one bookmark per book (chapter and second), the chapters listened to, the maximum per chapter.
  // The bookmark moves only while listening: opening another chapter without listening doesn't touch it.
  const bookKey = `book:${D.book}/${D.lang}`;
  const progress = () => ({ cur: null, done: {}, max: {}, ...store.get(bookKey, {}) });
  let listening = false;
  try { Object.keys(localStorage).filter((k) => k.startsWith('pos:')).forEach((k) => localStorage.removeItem(k)); } catch { /* the old format — a position per chapter */ }
  function saveProgress(ended = false) {
    const p = progress(), t = Math.round(audio.currentTime);
    p.max[D.id] = Math.max(p.max[D.id] || 0, ended ? Math.round(D.duration) : t);
    if (ended || t >= D.duration * 0.97) p.done[D.id] = true;
    p.cur = ended ? (D.nextId ? { s: D.nextId, t: 0, at: Date.now() } : null) : { s: D.id, t, at: Date.now() };
    store.set(bookKey, p);
  }

  // ---------------------------------------------------------------- text → sentences and words
  const words = [], sents = [], blocks = [];
  D.paragraphs.forEach((p, pi) => {
    const el = document.getElementById(p.id);
    const text = el.textContent;
    const frag = document.createDocumentFragment();
    let pos = 0, wi = 0;
    for (const [sa, sb, st0, st1] of p.sentences) {
      if (sa > pos) frag.append(text.slice(pos, sa));
      const sEl = document.createElement('span');
      sEl.className = 's';
      sents.push({ el: sEl, t0: st0, t1: st1, pi });
      let q = sa;
      while (wi < p.words.length && p.words[wi][1] <= sb) {
        const [a, b, t0, t1] = p.words[wi++];
        if (a < sa) continue;
        if (a > q) sEl.append(text.slice(q, a));
        const w = document.createElement('span');
        w.className = 'w';
        w.textContent = text.slice(a, b);
        w.dataset.i = words.length;
        words.push({ el: w, t0, t1, pi });
        sEl.append(w);
        q = b;
      }
      if (sb > q) sEl.append(text.slice(q, sb));
      frag.append(sEl);
      pos = sb;
    }
    if (pos < text.length) frag.append(text.slice(pos));
    el.textContent = '';
    el.append(frag);
    blocks.push({ el, t0: p.t0, t1: p.t1 });
  });

  // ---------------------------------------------------------------- pages by screen height
  let pages = [], pageNo = 0, follow = true;
  function paginate() {
    const keep = blocks[pages[pageNo]?.[0]]?.el;
    blocks.forEach((b) => { b.el.hidden = false; });
    pageEl.classList.remove('overflow');
    // the chapter picture — only on the first page (a phone: a strip at the top, a wide screen: a spread,
    // the text column narrower). Paragraph heights are measured in both layouts: the first page and the rest.
    const measure = (first) => {
      reader.classList.toggle('first', first);
      return [pageEl.clientHeight, blocks.map((b) => {
        const cs = getComputedStyle(b.el);
        return b.el.getBoundingClientRect().height + parseFloat(cs.marginTop) + parseFloat(cs.marginBottom);
      })];
    };
    const [H, hs] = measure(false);
    const [H0, hs0] = reader.classList.contains('has-art') ? measure(true) : [H, hs];
    pages = [];
    let start = 0, acc = 0;
    hs.forEach((_, i) => {
      const h = pages.length ? hs[i] : hs0[i];
      // a heading is not left alone on a page: the next paragraph goes with it (if it doesn't fit, the page scrolls)
      // (except the first page with a picture: the picture and the chapter heading are like a title page)
      const lone = i - start === 1 && /^H[12]$/.test(blocks[start].el.tagName) && !(pages.length === 0 && hs0 !== hs);
      if (i > start && !lone && acc + h > (pages.length ? H : H0)) { pages.push([start, i - 1]); start = i; acc = 0; }
      acc += h;
    });
    pages.push([start, blocks.length - 1]);
    const idx = keep ? blocks.findIndex((b) => b.el === keep) : 0;
    show(pageOf(Math.max(idx, 0)), false);
  }
  const pageOf = (bi) => Math.max(0, pages.findIndex(([a, b]) => bi >= a && bi <= b));
  function show(n, user = true) {
    pageNo = Math.min(Math.max(n, 0), pages.length - 1);
    reader.classList.toggle('first', pageNo === 0);
    const [a, b] = pages[pageNo];
    blocks.forEach((x, i) => { x.el.hidden = i < a || i > b; });
    pageEl.scrollTop = 0;
    pageEl.classList.toggle('overflow', pageEl.scrollHeight > pageEl.clientHeight + 2);
    pnum.textContent = `${D.ui.page} ${pageNo + 1} / ${pages.length}`;
    prevP.disabled = pageNo === 0;
    nextP.disabled = pageNo === pages.length - 1;
    if (user && !audio.paused && activeBlock() !== null && pageOf(activeBlock()) !== pageNo) setFollow(false);
    // paging by hand without listening — the address holds the start of the page's first sentence
    if (user && audio.paused) { const first = sents.find((x) => x.pi >= a && x.pi <= b); if (first) placeInUrl(first.t0); }
  }

  // page buttons in the row under the text
  const pager = $('.pager'), pnum = $('#pnum');
  const box = document.createElement('span');
  box.className = 'pages';
  const prevP = Object.assign(document.createElement('button'), { textContent: '‹', title: 'PgUp' });
  const nextP = Object.assign(document.createElement('button'), { textContent: '›', title: 'PgDn' });
  pnum.replaceWith(box);
  box.append(prevP, pnum, nextP);
  prevP.onclick = () => show(pageNo - 1);
  nextP.onclick = () => show(pageNo + 1);

  // ---------------------------------------------------------------- highlighting after the voice
  const find = (list, t) => { // the last element with t0 <= t (an 80 ms margin: mp3 seeking is imprecise, ~26 ms)
    let lo = 0, hi = list.length - 1, r = -1;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (list[m].t0 <= t + 0.08) { r = m; lo = m + 1; } else hi = m - 1; }
    return r;
  };
  let onW = null, onS = null;
  const activeBlock = () => (onS ? onS.pi : null);
  function tick() {
    const t = audio.currentTime;
    const si = find(sents, t), wi = find(words, t);
    const s = si >= 0 ? sents[si] : null;
    const w = wi >= 0 ? words[wi] : null; // the marker doesn't go out in pauses — it stays on the last word until the next
    if (s !== onS) { onS?.el.classList.remove('on'); s?.el.classList.add('on'); onS = s; if (s && !audio.paused) placeInUrl(s.t0); }
    if (w !== onW) { onW?.el.classList.remove('on'); w?.el.classList.add('on'); onW = w; }
    if (s && follow) {
      const pn = pageOf(s.pi);
      if (pn !== pageNo) show(pn, false);
      if (pageEl.classList.contains('overflow')) {
        const r = s.el.getBoundingClientRect(), R = pageEl.getBoundingClientRect();
        if (r.bottom > R.bottom - 8 || r.top < R.top) pageEl.scrollTop += r.top - R.top - R.height * 0.25;
      }
    }
    if (!seeking) seek.value = t;
    cur.textContent = clock(t);
  }
  const clock = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  function setFollow(on) {
    follow = on;
    followBtn.hidden = on;
    if (on) tick();
  }
  followBtn.onclick = () => setFollow(true);

  let raf = 0;
  const loop = () => { tick(); raf = audio.paused ? 0 : requestAnimationFrame(loop); };
  audio.addEventListener('play', () => { pp.textContent = '❚❚'; pp.setAttribute('aria-label', D.ui.pause); hint(false); if (!raf) loop(); });
  audio.addEventListener('pause', () => { pp.textContent = '▶'; pp.setAttribute('aria-label', D.ui.play); if (listening && !audio.ended) saveProgress(); if (onS) placeInUrl(onS.t0); });
  audio.addEventListener('playing', () => { listening = true; saveProgress(); });
  audio.addEventListener('seeked', () => { if (listening) saveProgress(); tick(); if (onS) placeInUrl(onS.t0); });
  audio.addEventListener('seeked', tick);
  audio.addEventListener('ended', () => {
    saveProgress(true);
    if (D.next) setTimeout(() => { location.href = `${D.next}#play`; }, 1500);
  });
  setInterval(() => { if (!audio.paused) saveProgress(); }, 5000);

  // the "tap to listen" hint: a pulse at the button until ▶ has been pressed on the page (and if the browser
  // didn't allow continuing automatically); the book's first listener also gets a label with text
  const tip = document.createElement('span');
  tip.className = 'pp-tip';
  tip.textContent = D.ui.tap_to_listen;
  function hint(on) {
    pp.classList.toggle('hint', on);
    if (on && !progress().cur && !Object.keys(progress().done).length) pp.after(tip);
    else tip.remove();
  }
  const play = () => audio.play().catch(() => hint(true));
  pp.onclick = () => (audio.paused ? (setFollow(true), play()) : audio.pause());
  let seeking = false;
  seek.addEventListener('input', () => { seeking = true; cur.textContent = clock(+seek.value); });
  seek.addEventListener('change', () => { seeking = false; audio.currentTime = +seek.value; setFollow(true); });
  pageEl.addEventListener('click', (ev) => {
    const w = ev.target.closest('.w');
    if (!w || getSelection().toString()) return;
    audio.currentTime = words[+w.dataset.i].t0;
    setFollow(true);
    play();
  });

  // the place in the address: /ru/ch01/#t=588.4 — the link can be copied and shared, it opens the same page
  function placeInUrl(t) {
    try { history.replaceState(null, '', `#t=${t.toFixed(1)}`); } catch { /* file:// etc. */ }
  }
  const shareBtn = $('#share');
  shareBtn?.addEventListener('click', async () => {
    const t = onS ? onS.t0 : audio.currentTime;
    placeInUrl(t);
    const url = location.href, title = `${D.bookTitle} — ${D.title}`;
    if (navigator.share && matchMedia('(pointer: coarse)').matches) {
      try { await navigator.share({ title, url }); } catch { /* cancelled */ }
      return;
    }
    try { await navigator.clipboard.writeText(url); } catch { prompt(D.ui.copy_link, url); return; }
    shareBtn.dataset.tip = D.ui.copied;
    shareBtn.classList.add('tip');
    setTimeout(() => shareBtn.classList.remove('tip'), 1600);
  });

  // the language switch: the same paragraph in another language
  document.querySelectorAll('.langs a').forEach((a) => a.addEventListener('click', () => {
    if (a.classList.contains('on') || !/\/[\w-]+\/$/.test(a.getAttribute('href'))) return;
    const pi = onS ? onS.pi : (pages[pageNo] ? pages[pageNo][0] : 0);
    a.href = a.href.split('#')[0] + `#p=${D.paragraphs[pi].id}`;
  }));

  // speed
  const speeds = [1, 1.15, 1.3, 1.5, 0.85];
  let sp = store.get('speed', 1);
  const setSpeed = (v) => { sp = v; audio.playbackRate = v; speedBtn.textContent = `${v}×`; store.set('speed', v); };
  setSpeed(speeds.includes(sp) ? sp : 1);
  speedBtn.onclick = () => setSpeed(speeds[(speeds.indexOf(sp) + 1) % speeds.length]);

  // keys and swipes
  const jumpSent = (d) => {
    const i = Math.min(Math.max(find(sents, audio.currentTime) + d, 0), sents.length - 1);
    audio.currentTime = sents[i].t0;
    setFollow(true);
  };
  document.addEventListener('keydown', (ev) => {
    if (ev.target.closest('input, select, textarea') || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    const k = ev.key;
    if (k === ' ' || k === 'k') { ev.preventDefault(); pp.click(); }
    else if (k === 'ArrowRight') { ev.preventDefault(); jumpSent(1); }
    else if (k === 'ArrowLeft') { ev.preventDefault(); jumpSent(-1); }
    else if (k === 'PageDown' || k === 'ArrowDown') { ev.preventDefault(); show(pageNo + 1); }
    else if (k === 'PageUp' || k === 'ArrowUp') { ev.preventDefault(); show(pageNo - 1); }
  });
  let tx = null;
  pageEl.addEventListener('touchstart', (ev) => { tx = ev.touches[0].clientX; }, { passive: true });
  pageEl.addEventListener('touchend', (ev) => {
    if (tx === null) return;
    const dx = ev.changedTouches[0].clientX - tx;
    tx = null;
    if (Math.abs(dx) > 60) show(pageNo + (dx < 0 ? 1 : -1));
  });

  // the lock screen / headset
  if ('mediaSession' in navigator) {
    navigator.mediaSession.metadata = new MediaMetadata({ title: D.title, artist: D.author, album: D.bookTitle });
    const ms = navigator.mediaSession;
    ms.setActionHandler('play', play);
    ms.setActionHandler('pause', () => audio.pause());
    ms.setActionHandler('seekbackward', () => { audio.currentTime -= 10; });
    ms.setActionHandler('seekforward', () => { audio.currentTime += 10; });
    try { ms.setActionHandler('previoustrack', () => jumpSent(-1)); ms.setActionHandler('nexttrack', () => jumpSent(1)); } catch { /* */ }
  }

  // start: pages, the saved place; #play — continue (coming from the previous chapter)
  let rt = 0;
  addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(paginate, 120); });
  const begin = () => {
    paginate();
    const m = /t=([\d.]+)/.exec(location.hash);
    // #p=<paragraph> — came from another language: the same paragraph (paragraph ids are shared by the languages)
    const pm = /p=([\w-]+)/.exec(location.hash);
    const pp = pm ? D.paragraphs.find((x) => x.id === pm[1]) : null;
    // our own bookmark — continue; otherwise (another chapter or finished) — from the start
    const cur = progress().cur;
    const t = m ? +m[1] : pp ? (pp.sentences[0]?.[2] ?? pp.t0) : (cur && cur.s === D.id ? cur.t : 0);
    if (t > 0 && t < D.duration - 1) { audio.currentTime = t; }
    tick();
    if (/play/.test(location.hash)) play(); else hint(true);
  };
  (document.fonts?.ready ?? Promise.resolve()).then(begin);
})();
