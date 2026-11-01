/* Shared by all pages: the day/night scheme (☀/☾). The choice lives on <html data-theme> and in localStorage;
 * a line in <head> sets it before rendering; with no choice — follow the system. */
(() => {
  const root = document.documentElement;
  const store = {
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
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
