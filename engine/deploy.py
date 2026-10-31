"""Деплой: собранный сайт dist/ → папка на сервере, rsync по ssh (как в coloring-book и nemilya/math).

    DEPLOY = ssh://nemilya-me/var/www/grin      (local.mk или .env; или host:/path, или локальная папка)
    SITE_URL = https://grin.nemilya.me          (необязательно; по умолчанию — site.json → url)

Два шага: 1) собрать сайт (make site) и посмотреть (make serve); 2) make deploy заливает ровно эту
сборку — не пересобирает. Если после сборки что-то поменялось (озвучка, текст, раскадровка, ассеты,
site.json, сцена), деплой откажется: на сервер уходит то, что видели. Сначала медиа и ресурсы (без удаления),
потом страницы с --delete: новая страница никогда не ссылается на ещё не залитый звук. Все шаги — одно
ssh-соединение (ControlMaster): пароль, если нужен, спросят один раз.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config

RSYNC = ['rsync', '-rlptz', '--itemize-changes', '--exclude', '.DS_Store', '--exclude', '.build.json']
NO_PASSWORD = ('Сервер спросил пароль, а ввести его некуда. Запустите в консоли  make deploy  '
               '(пароль спросят один раз) или поставьте ssh-ключ:  ssh-copy-id {host}')


class DeployError(RuntimeError):
    pass


def target() -> str:
    """DEPLOY как его ждёт rsync: ssh://host/path → host:/path; host:/path и локальная папка — как есть."""
    value = (os.environ.get('DEPLOY') or '').strip().rstrip('/')
    if not value:
        raise DeployError('Нет адреса сервера. Добавьте в local.mk:  DEPLOY = ssh://nemilya-me/var/www/grin')
    m = re.match(r'^s?sh://([^/]+)(/.*)$', value)
    return f'{m.group(1)}:{m.group(2)}' if m else value


def remote(dest: str) -> tuple[str, str] | None:
    """(host, path) для host:/path; None — локальная папка."""
    host, sep, path = dest.partition(':')
    return (host, path) if sep and '/' not in host and len(host) > 1 else None


def site_state() -> str:
    """none — не собран; stale — после сборки что-то менялось; fresh — можно заливать."""
    built_f = config.DIST / '.build.json'
    if not built_f.exists() or not (config.DIST / 'index.html').exists():
        return 'none'
    built = built_f.stat().st_mtime
    cfg = config.site_config()
    sources = [config.ROOT / 'site.json', config.SITE, config.ROOT / 'stage' / 'js', config.ROOT / 'engine' / 'sound.py']
    for item in cfg.get('stories') or []:
        d = config.STORIES / item['story']
        sources += [d / 'story.json', d / 'prepared', d / 'overrides']
        sources += [d / 'voicings' / vid for vid in (item.get('voicings') or {}).values() if vid]
        for v in item.get('videos') or []:
            p = config.STORIES / v['production']
            sources += [p / 'story.json', p / 'bible.json', p / 'assets' / 'assets.json',
                        *p.glob('storyboard*.json')]
    changed = 0.0
    for s in sources:
        if s.is_file():
            changed = max(changed, s.stat().st_mtime)
        elif s.is_dir():
            changed = max([changed] + [f.stat().st_mtime for f in s.rglob('*') if f.is_file()])
    return 'stale' if changed > built else 'fresh'


class Ssh:
    """Одно ssh-соединение на все шаги. interactive=False (админка): пароль не спрашивать, сразу совет."""

    def __init__(self, host: str | None, interactive: bool):
        self.host, self.interactive = host, interactive
        # /tmp: путь к сокету должен быть коротким (macOS — ~104 знака)
        self.dir = tempfile.mkdtemp(prefix='grin-ssh-', dir='/tmp') if host else None
        self.opts = (['-o', 'ControlMaster=auto', '-o', f'ControlPath={self.dir}/%C', '-o', 'ControlPersist=120']
                     + ([] if interactive else ['-o', 'BatchMode=yes'])) if host else []

    def run(self, *cmd: str) -> None:
        r = subprocess.run(['ssh', *self.opts, self.host, *cmd], capture_output=not self.interactive, text=True)
        if r.returncode:
            err = (r.stderr or '').strip()
            if not self.interactive and ('Permission denied' in err or 'password' in err.lower()):
                raise DeployError(NO_PASSWORD.format(host=self.host))
            raise DeployError(f'ssh {self.host}: {err or "код " + str(r.returncode)}')

    def rsync_args(self) -> list[str]:
        return ['-e', 'ssh ' + ' '.join(self.opts)] if self.host else []

    def close(self) -> None:
        if self.host:
            subprocess.run(['ssh', *self.opts, '-O', 'exit', self.host], capture_output=True)
            shutil.rmtree(self.dir, ignore_errors=True)


def _rsync(args: list[str], say) -> int:
    """rsync с выводом изменений; → сколько файлов отправлено / удалено."""
    if not shutil.which('rsync'):
        raise DeployError('Нет rsync: поставьте его (brew install rsync / apt install rsync)')
    say('$ ' + ' '.join(a for a in args if not a.startswith('ssh -o')))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    changed = 0
    for line in proc.stdout:
        line = line.rstrip()
        if line[:2] in ('<f', '>f', '*d') or line.startswith('*deleting'):
            changed += 1
            say('  ' + line)
        elif line and line[:1] not in ('c', '.'):  # сообщения и ошибки самого rsync
            say('  ' + line)
    if proc.wait():
        raise DeployError(f'rsync завершился с кодом {proc.returncode}')
    return changed


def deploy(dry: bool = False, say=print, interactive: bool = True) -> dict:
    """Залить собранный сайт как есть. dry — только показать, что изменится."""
    state = site_state()
    if state != 'fresh':
        why = ('Сайт ещё не собран' if state == 'none' else
               'Сайт устарел: после сборки менялись озвучка, текст, раскадровка, ассеты, site.json или сцена')
        if not dry:
            raise DeployError(why + '. Сначала соберите: make site, посмотрите (make serve) — и заливайте.')
        say('⚠ ' + why + ' — make site')
    dest = target()
    where = remote(dest)
    src = f'{config.DIST}/'
    sent = {'media': 0, 'pages': 0}
    ssh = Ssh(where[0] if where else None, interactive)
    try:
        if where:
            say(f'Подключаемся к {where[0]}' + (' (если спросит пароль — введите его здесь, один раз)' if interactive else ''))
            ssh.run('mkdir', '-p', where[1])
        elif not dry:
            Path(dest).mkdir(parents=True, exist_ok=True)
        flags = RSYNC + ssh.rsync_args() + (['--dry-run'] if dry else [])
        # 1) медиа (слои, таймлайны, звук), озвучка, ресурсы — без удаления: старые страницы продолжают работать
        sent['media'] = _rsync(flags + ['--exclude', '*.html', src, f'{dest}/'], say)
        # 2) страницы; всё, чего больше нет в dist/, удаляется
        sent['pages'] = _rsync(flags + ['--delete', src, f'{dest}/'], say)
    finally:
        ssh.close()
    say(('Проверка: изменится' if dry else 'Залито') + f" файлов: звук и ресурсы {sent['media']}, страницы {sent['pages']}")
    url = os.environ.get('SITE_URL') or config.site_config().get('url')
    if not dry and url:
        say(f'Сайт: {url}')
    return sent


if __name__ == '__main__':
    import sys
    config.load_env()
    try:
        deploy(dry='--dry' in sys.argv)
    except DeployError as e:
        print(f'✗ {e}')
        sys.exit(1)
