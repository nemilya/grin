/* Общее для всех страниц: дневная/ночная схема (☀/☾). Выбор — на <html data-theme> и в localStorage;
 * до отрисовки его ставит строка в <head>; без выбора — как в системе. */
(() => {
  const root = document.documentElement;
  const store = {
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* приватный режим */ } },
  };
  const dark = () => root.dataset.theme === 'dark'
    || (!root.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  const btn = document.querySelector('.tools .theme');
  const paint = () => {
    if (!btn) return;
    btn.textContent = dark() ? '☀' : '☾';
    btn.title = btn.dataset[dark() ? 'day' : 'night'];
  };
  btn?.addEventListener('click', () => {
    root.dataset.theme = dark() ? 'light' : 'dark';
    store.set('theme', root.dataset.theme);
    paint();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', paint);
  paint();
})();
