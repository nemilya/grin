/* Админка (только просмотр): /api/stories, /api/story?slug=… (tools/admin.py). */
(() => {
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const st = (s) => `<span class="st ${esc(s)}">${esc(s)}</span>`;
  let current = null, tab = 'overview';

  async function load() {
    const list = await fetch('/api/stories').then((r) => r.json());
    $('#stories').innerHTML = list.map((s) => `<a href="#${s.slug}" data-slug="${s.slug}">${esc(s.title.ru || s.slug)}
      <small>${esc(s.slug)}${s.base ? ` · постановка (${esc(s.style)})` : ` · ${esc(s.style)}`}</small>
      <small>${s.timeline.shots ?? '?'} кадров · ${s.timeline.duration ? mmss(s.timeline.duration) : '—'} · ассеты ${Object.entries(s.assets).map(([k, v]) => `${k} ${v}`).join(', ')}</small></a>`).join('');
    route();
  }
  addEventListener('hashchange', route);
  async function route() {
    const [slug, t] = location.hash.slice(1).split('/');
    if (t) tab = t;
    document.querySelectorAll('#stories a').forEach((a) => a.classList.toggle('on', a.dataset.slug === slug));
    if (!slug) return;
    if (!current || current.slug !== slug) {
      $('#main').innerHTML = '<p class="empty">Загрузка…</p>';
      current = await fetch(`/api/story?slug=${encodeURIComponent(slug)}`).then((r) => r.json());
    }
    render();
  }

  const card = (c, title, desc) => `<div class="card">
    ${c.file ? `<div class="img" data-zoom="${esc(c.file)}" data-prompt="${esc(c.prompt)}"><img src="${esc(c.file)}" loading="lazy" alt=""></div>`
    : `<div class="img none">${c.status === 'procedural' ? 'процедурная' : 'нет картинки'}</div>`}
    <div class="k">${esc(title)}</div><div class="d">${esc(desc || '')}</div>
    <div class="meta">${st(c.status)}<span>${c.w ? `${c.w}×${c.h}` : ''}${c.cost ? ` · $${c.cost}` : ''}</span></div></div>`;

  const TABS = {
    overview: 'Обзор', characters: 'Герои и листы', sets: 'Декорации и предметы', shots: 'Раскадровка',
    voicing: 'Озвучка', style: 'Стиль и режиссёр',
  };
  function render() {
    const d = current;
    if (d.error) { $('#main').innerHTML = `<p class="err">${esc(d.error)}</p>`; return; }
    const s = d.story;
    const tabs = Object.entries(TABS).filter(([k]) => k !== 'voicing' || d.voicings.length)
      .map(([k, v]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${v}</button>`).join('');
    let body = '';
    if (tab === 'overview') {
      const t = d.timeline;
      body = `<div class="kv">
        <b>Название</b><span>${esc(s.title?.ru)} / ${esc(s.title?.en)}</span>
        <b>База</b><span>${esc(s.base || '— (своя история)')}</span>
        <b>Стиль</b><span>${esc(s.film?.style)}</span>
        <b>Формат</b><span>${s.film?.width}×${s.film?.height}${Object.keys(s.formats || {}).map((f) => ` · ${esc(f)}`).join('')}</span>
        <b>Озвучки</b><span>${esc(JSON.stringify(s.film?.voicings || s.film?.voicing))}</span>
        <b>Таймлайн</b><span>${t.duration ? mmss(t.duration) : ''} · время: ${esc(t.timing)}</span>
        <b>Ассеты</b><span>потрачено $${(d.cost || 0).toFixed(2)}</span></div>
        ${(t.errors || []).map((x) => `<p class="err">✗ ${esc(x)}</p>`).join('')}
        ${(t.warnings || []).map((x) => `<p class="warn">· ${esc(x)}</p>`).join('')}
        <h3>Мир</h3><p>${esc(d.world)}</p>`;
    } else if (tab === 'characters') {
      body = d.characters.map((c) => `<div class="char"><div class="head">${card(c.sheet, `refs/${c.id}`, '')}
        <div><h3 style="margin-top:0">${esc(c.name)}</h3><p class="look">${esc(c.look)}</p></div></div>
        <div class="cards">${c.poses.map((p) => card(p, `${c.id}/${p.id}`, p.desc)).join('')}</div></div>`).join('');
    } else if (tab === 'sets') {
      body = d.sets.map((x) => `<h3>${esc(x.name)} · <code>${esc(x.id)}</code> · свет ${esc(x.light)}</h3><p class="sub">${esc(x.look)}</p>
        <div class="cards">${x.pieces.map((p) => card(p, `${x.id}/${p.id}${p.key !== `${x.id}/${p.id}` ? ` → ${p.key}` : ''}`, `${p.kind} · ${JSON.stringify(p.pos || '')} · ${p.desc}`)).join('')}</div>`).join('')
        + `<h3>Предметы</h3><div class="cards">${d.props.map((p) => card(p, `prop/${p.id}`, p.desc)).join('')}</div>`;
    } else if (tab === 'shots') {
      const land = s.film?.width > s.film?.height ? ' land' : '';
      let scene = '';
      body = `<p class="sub">Стоп-кадры — из out/${esc(d.slug)}/stills (<code>node tools/capture.mjs stills ${esc(d.slug)} --scale 0.3</code>).</p><div class="shots">`
        + d.shots.map((x) => {
          const h = x.scene !== scene ? `</div><h3>${esc(x.scene)} · ${esc(x.title)}</h3><div class="shots">` : '';
          scene = x.scene;
          return `${h}<div class="shot${land}">${x.still ? `<div class="img" data-zoom="${esc(x.still)}" data-prompt="${esc(x.cards.join('\n'))}"><img src="${esc(x.still)}" loading="lazy" alt=""></div>` : '<div class="img none">нет стоп-кадра</div>'}
            <b>${esc(x.id)}</b> <span class="t">${mmss(x.t0)} · ${esc(x.at)} · ${esc(x.cam)} · ${esc(x.set)}</span>
            <div class="note">${esc(x.note)}</div></div>`;
        }).join('') + '</div>';
    } else if (tab === 'voicing') {
      body = d.voicings.map((v) => `<h3>${esc(v.name)} · ${esc(v.lang)} · ${esc(v.voice)} · ${(v.duration / 60).toFixed(1)} мин · $${v.cost}</h3>
        <table><tr><th>абзац</th><th>статус</th><th>оценка</th><th>длит.</th><th>текст / распознано</th><th>звук</th></tr>
        ${v.items.map((it) => `<tr><td>${esc(it.id)}</td><td>${st(it.status)}${it.takes > 1 ? ` <small>${it.takes} дубля</small>` : ''}</td>
          <td>${it.score ?? ''}</td><td>${it.dur ? it.dur.toFixed(1) : ''}</td>
          <td class="txt">${esc(it.text)}${it.manner ? `<div class="tr">манера: ${esc(it.manner)}</div>` : ''}${it.transcript && it.score < 0.97 ? `<div class="tr">распознано: ${esc(it.transcript)}</div>` : ''}</td>
          <td>${it.audio ? `<audio controls preload="none" src="${esc(it.audio)}"></audio>` : ''}</td></tr>`).join('')}</table>`).join('');
    } else if (tab === 'style') {
      body = `<h3>Стиль · ${esc(s.film?.style)}</h3><pre>${esc(JSON.stringify(d.style, null, 1))}</pre>`
        + (d.director ? `<h3>Режиссёр</h3><pre>${esc(JSON.stringify(d.director, null, 1))}</pre>` : '<p class="sub">Режиссёра нет — умолчания движка (бумажный театр).</p>');
    }
    $('#main').innerHTML = `<h2>${esc(s.title?.ru)} <small class="sub">${esc(d.slug)}</small></h2><div class="tabs">${tabs}</div>${body}`;
  }

  document.addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-tab]');
    if (b) { tab = b.dataset.tab; history.replaceState(null, '', `#${current.slug}/${tab}`); render(); return; }
    const z = ev.target.closest('[data-zoom]');
    const box = $('#zoom');
    if (z) { $('img', box).src = z.dataset.zoom; $('pre', box).textContent = z.dataset.prompt || ''; box.hidden = false; return; }
    if (ev.target.closest('#zoom')) box.hidden = true;
  });
  addEventListener('keydown', (ev) => { if (ev.key === 'Escape') $('#zoom').hidden = true; });
  load();
})();
