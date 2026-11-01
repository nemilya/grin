"""Deploy: the built site dist/ → a folder on the server, rsync over ssh.

    DEPLOY = ssh://nemilya-me/var/www/grin      (local.mk or .env; or host:/path, or a local folder)
    SITE_URL = https://grin.nemilya.me          (optional; defaults to site.json → url)

Two steps: 1) build the site (make site) and look at it (make serve); 2) make deploy uploads exactly that
build — it doesn't rebuild. If anything changed after the build (narration, text, storyboard, assets,
site.json, the stage), deploy refuses: what goes to the server is what was seen. Media and resources first (no deletion),
then pages with --delete: a new page never links to sound that isn't uploaded yet. All steps share one
ssh connection (ControlMaster): a password, if needed, is asked once.
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
NO_PASSWORD = ('The server asked for a password and there is nowhere to type it. Run  make deploy  in a terminal '
               '(the password is asked once) or install an ssh key:  ssh-copy-id {host}')


class DeployError(RuntimeError):
    pass


def target() -> str:
    """DEPLOY as rsync expects it: ssh://host/path → host:/path; host:/path and a local folder — as is."""
    value = (os.environ.get('DEPLOY') or '').strip().rstrip('/')
    if not value:
        raise DeployError('No server address. Add to local.mk:  DEPLOY = ssh://nemilya-me/var/www/grin')
    m = re.match(r'^s?sh://([^/]+)(/.*)$', value)
    return f'{m.group(1)}:{m.group(2)}' if m else value


def remote(dest: str) -> tuple[str, str] | None:
    """(host, path) for host:/path; None — a local folder."""
    host, sep, path = dest.partition(':')
    return (host, path) if sep and '/' not in host and len(host) > 1 else None


def site_state() -> str:
    """none — not built; stale — something changed after the build; fresh — ready to upload."""
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
    """One ssh connection for all steps. interactive=False (admin): don't ask for a password, give advice right away."""

    def __init__(self, host: str | None, interactive: bool):
        self.host, self.interactive = host, interactive
        # /tmp: the socket path must be short (macOS — ~104 chars)
        self.dir = tempfile.mkdtemp(prefix='grin-ssh-', dir='/tmp') if host else None
        self.opts = (['-o', 'ControlMaster=auto', '-o', f'ControlPath={self.dir}/%C', '-o', 'ControlPersist=120']
                     + ([] if interactive else ['-o', 'BatchMode=yes'])) if host else []

    def run(self, *cmd: str) -> None:
        r = subprocess.run(['ssh', *self.opts, self.host, *cmd], capture_output=not self.interactive, text=True)
        if r.returncode:
            err = (r.stderr or '').strip()
            if not self.interactive and ('Permission denied' in err or 'password' in err.lower()):
                raise DeployError(NO_PASSWORD.format(host=self.host))
            raise DeployError(f'ssh {self.host}: {err or "code " + str(r.returncode)}')

    def rsync_args(self) -> list[str]:
        return ['-e', 'ssh ' + ' '.join(self.opts)] if self.host else []

    def close(self) -> None:
        if self.host:
            subprocess.run(['ssh', *self.opts, '-O', 'exit', self.host], capture_output=True)
            shutil.rmtree(self.dir, ignore_errors=True)


def _rsync(args: list[str], say) -> int:
    """rsync printing the changes; → how many files were sent / deleted."""
    if not shutil.which('rsync'):
        raise DeployError('No rsync: install it (brew install rsync / apt install rsync)')
    say('$ ' + ' '.join(a for a in args if not a.startswith('ssh -o')))
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    changed = 0
    for line in proc.stdout:
        line = line.rstrip()
        if line[:2] in ('<f', '>f', '*d') or line.startswith('*deleting'):
            changed += 1
            say('  ' + line)
        elif line and line[:1] not in ('c', '.'):  # rsync's own messages and errors
            say('  ' + line)
    if proc.wait():
        raise DeployError(f'rsync exited with code {proc.returncode}')
    return changed


def deploy(dry: bool = False, say=print, interactive: bool = True) -> dict:
    """Upload the built site as is. dry — only show what would change."""
    state = site_state()
    if state != 'fresh':
        why = ('The site is not built yet' if state == 'none' else
               'The site is stale: narration, text, storyboard, assets, site.json or the stage changed after the build')
        if not dry:
            raise DeployError(why + '. Build it first: make site, look at it (make serve) — then upload.')
        say('⚠ ' + why + ' — make site')
    dest = target()
    where = remote(dest)
    src = f'{config.DIST}/'
    sent = {'media': 0, 'pages': 0}
    ssh = Ssh(where[0] if where else None, interactive)
    try:
        if where:
            say(f'Connecting to {where[0]}' + (' (if it asks for a password, type it here, once)' if interactive else ''))
            ssh.run('mkdir', '-p', where[1])
        elif not dry:
            Path(dest).mkdir(parents=True, exist_ok=True)
        flags = RSYNC + ssh.rsync_args() + (['--dry-run'] if dry else [])
        # 1) media (layers, timelines, sound), narration, resources — no deletion: old pages keep working
        sent['media'] = _rsync(flags + ['--exclude', '*.html', src, f'{dest}/'], say)
        # 2) pages; everything no longer in dist/ is deleted
        sent['pages'] = _rsync(flags + ['--delete', src, f'{dest}/'], say)
    finally:
        ssh.close()
    say(('Dry run: would change' if dry else 'Uploaded') + f" files: sound and resources {sent['media']}, pages {sent['pages']}")
    url = os.environ.get('SITE_URL') or config.site_config().get('url')
    if not dry and url:
        say(f'Site: {url}')
    return sent


if __name__ == '__main__':
    import sys
    config.load_env()
    try:
        deploy(dry='--dry' in sys.argv)
    except DeployError as e:
        print(f'✗ {e}')
        sys.exit(1)
