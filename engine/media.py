"""Media — pictures and narration — live in a second git repository (nemilya/grin-media) laid over this folder.

This repository holds the code and everything a film is made of as text: story texts, translations, bibles,
storyboards, manifests. Binary media (stories/**/*.webp|png|jpg|opus|wav…) are ignored here and tracked by the
media repository, whose git dir is `.media.git/` and whose work tree is this very folder: the files sit exactly
where the engine expects them, so nothing else in the engine knows about it.

`media.rev` (one line, committed here) pins the media commit this code commit was made with — like a submodule,
without the submodule ceremony. Any code commit can be reproduced: check it out, then `make media-pull`.

    python -m engine.media status            pinned / pulled / changed locally / not pushed
    python -m engine.media pull [--latest]   fetch and lay out media.rev (--latest: the tip of the media branch)
    python -m engine.media push [-m MSG]     commit changed media, push it, write and stage media.rev
    python -m engine.media check             exit 1 if the media of media.rev are not pulled (guards paid generation)

The media branch is named after the code branch (main → main, claude/x → claude/x); pushes that find the
branch moved are merged (git merge-tree — no work-tree merge, so files outside stories/ are never touched).
Only stories/ is ever written to disk; the media repository's own README and LICENSE stay in git.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import config

ROOT = config.ROOT  # tests point this elsewhere
REMOTE = 'https://github.com/nemilya/grin-media.git'  # MEDIA_REMOTE in local.mk / environment overrides
EXTS = {'.webp', '.png', '.jpg', '.jpeg', '.opus', '.wav', '.mp3', '.m4a'}
LOCAL_ONLY = (('assets', 'takes'), ('assets', 'raw'))  # earlier picture variants and pre-key sources stay local


class MediaError(RuntimeError):
    pass


def git_dir() -> Path:
    return ROOT / '.media.git'


def rev_file() -> Path:
    return ROOT / 'media.rev'


def remote_url() -> str:
    return os.environ.get('MEDIA_REMOTE') or REMOTE


def git(*args: str, input: str | None = None, check: bool = True) -> str:
    r = subprocess.run(['git', f'--git-dir={git_dir()}', f'--work-tree={ROOT}', *args], cwd=ROOT,
                       input=input, capture_output=True, text=True)
    if check and r.returncode:
        raise MediaError(f"git {' '.join(args[:3])}…: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def is_media(rel: str) -> bool:
    parts = rel.split('/')
    if len(parts) < 3 or parts[0] != 'stories' or Path(rel).suffix.lower() not in EXTS:
        return False
    return parts[2] != 'build' and tuple(parts[2:4]) not in LOCAL_ONLY


def media_files() -> list[str]:
    st = ROOT / 'stories'
    if not st.exists():
        return []
    return sorted(r for p in st.rglob('*') if p.is_file() and is_media(r := p.relative_to(ROOT).as_posix()))


def pinned() -> str | None:
    f = rev_file()
    return (f.read_text().strip() or None) if f.exists() else None


def head() -> str | None:
    if not git_dir().exists():
        return None
    return git('rev-parse', '-q', '--verify', 'HEAD^{commit}', check=False).strip() or None


def code_branch() -> str:
    r = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True)
    b = r.stdout.strip()
    return b if r.returncode == 0 and b and b != 'HEAD' else 'main'


def init() -> None:
    if git_dir().exists():
        return
    subprocess.run(['git', 'init', '-q', '--bare', str(git_dir())], check=True)
    git('config', 'core.bare', 'false')
    git('remote', 'add', 'origin', remote_url())
    if (ROOT / '.git').exists():  # the pre-push check of this repo (tools/hooks/pre-push)
        subprocess.run(['git', '-C', str(ROOT), 'config', 'core.hooksPath', 'tools/hooks'], check=False)


def _tree(rev: str) -> dict[str, str]:
    """Paths under stories/ in a media commit → blob ids."""
    out = git('ls-tree', '-r', '-z', rev, '--', 'stories/')
    return {line.split('\t', 1)[1]: line.split()[2] for line in out.split('\0') if line}


def _hashes(paths: list[str]) -> dict[str, str]:
    if not paths:
        return {}
    out = git('hash-object', '--no-filters', '--stdin-paths', input='\n'.join(paths) + '\n').split()
    return dict(zip(paths, out))


def changes() -> dict[str, list[str]]:
    """Local media vs the checked-out media commit: changed, new, deleted (paths under stories/)."""
    files = media_files()
    h = head()
    if not h:
        return {'changed': [], 'new': files, 'deleted': []}
    tracked = _tree(h)
    on_disk = set(files)
    known = [p for p in files if p in tracked]
    cur = _hashes(known)
    return {'changed': [p for p in known if cur[p] != tracked[p]],
            'new': [p for p in files if p not in tracked],
            'deleted': sorted(p for p in tracked if p not in on_disk and is_media(p))}


def _fetch(what: str, depth: int = 1) -> str:
    """Fetch a commit (sha) or a branch from the media remote; returns the commit id."""
    if len(what) == 40:  # a pinned commit: remember it came from the remote (status, pre-push)
        git('fetch', '-q', f'--depth={depth}', 'origin', what)
        git('update-ref', 'refs/remotes/origin/pulled', what)
        return what
    git('fetch', '-q', f'--depth={depth}', 'origin', f'+refs/heads/{what}:refs/remotes/origin/{what}')
    return git('rev-parse', f'refs/remotes/origin/{what}').strip()


def _apply(old: str | None, new: str, force: bool = False) -> int:
    """Make stories/ media on disk equal to commit `new` (coming from `old`); never touches other paths.
    Local edits that would be overwritten stop it (unless force) — they may be paid generations not pushed yet."""
    target = _tree(new)
    before = _tree(old) if old else {}
    on_disk = set(media_files())
    local = _hashes(sorted(on_disk & (set(target) | set(before))))
    dirty = {p for p, h in local.items() if h != before.get(p)}  # differs from what we had checked out
    write = [p for p, b in target.items() if local.get(p) != b]
    drop = [p for p in before if p not in target and p in on_disk]
    blocked = sorted(dirty & (set(write) | set(drop)))
    if blocked and not force:
        raise MediaError(f'{len(blocked)} local media files differ and are not pushed ({", ".join(blocked[:3])}…) — '
                         f'make media-push first (or pull with --force to discard them)')
    git('read-tree', new)
    if write:
        git('checkout-index', '-f', '-z', '--stdin', input='\0'.join(write) + '\0')
    for p in drop:
        (ROOT / p).unlink()
    git('update-index', '-q', '--refresh', check=False)
    git('update-ref', '--no-deref', 'HEAD', new)
    return len(write) + len(drop)


def pull(latest: bool = False, force: bool = False, log=print) -> str:
    init()
    rev = None if latest else pinned()
    new = _fetch(rev) if rev else _fetch(code_branch() if latest else 'main')
    n = _apply(head(), new, force=force)
    if latest and new != pinned():
        rev_file().write_text(new + '\n')
        log(f'media.rev → {new[:10]} (commit it)')
    log(f'✓ media {new[:10]}: {n} files updated, {len(_tree(new))} in total')
    return new


def push(message: str | None = None, log=print) -> str:
    init()
    ch = changes()
    paths = ch['changed'] + ch['new']
    if paths:
        git('add', '-f', '--pathspec-from-file=-', '--pathspec-file-nul', input='\0'.join(paths) + '\0')
    if ch['deleted']:
        git('rm', '-q', '--cached', '--pathspec-from-file=-', '--pathspec-file-nul', input='\0'.join(ch['deleted']) + '\0')
    if paths or ch['deleted']:
        stories = sorted({p.split('/')[1] for p in paths + ch['deleted']})
        msg = message or f"{', '.join(stories)}: {len(ch['new'])} new, {len(ch['changed'])} changed, {len(ch['deleted'])} deleted"
        git('commit', '-q', '--no-verify', '-m', msg)
    h = head()
    if not h:
        raise MediaError('nothing to push: no media yet')
    branch = code_branch()
    for _ in range(3):
        r = subprocess.run(['git', f'--git-dir={git_dir()}', 'push', '-q', 'origin', f'HEAD:refs/heads/{branch}'],
                           capture_output=True, text=True)
        if r.returncode == 0:
            break
        if 'rejected' not in r.stderr and 'fetch first' not in r.stderr and 'non-fast-forward' not in r.stderr:
            raise MediaError(f'push: {r.stderr.strip()}')
        theirs = _fetch(branch, depth=200)  # someone pushed media meanwhile: merge without touching the work tree
        m = subprocess.run(['git', f'--git-dir={git_dir()}', 'merge-tree', '--write-tree', h, theirs],
                           capture_output=True, text=True)
        if m.returncode:
            raise MediaError(f'media conflict with {branch} (the same files changed on both sides):\n{m.stdout.strip()}')
        tree = m.stdout.split()[0]
        merged = git('commit-tree', tree, '-p', h, '-p', theirs, '-m', f'Merge media of {branch}').strip()
        _apply(h, merged)
        h = merged
        log(f'· merged media pushed meanwhile to {branch}')
    else:
        raise MediaError('push kept being rejected')
    git('update-ref', f'refs/remotes/origin/{branch}', h)
    rev_file().write_text(h + '\n')
    if (ROOT / '.git').exists():
        subprocess.run(['git', '-C', str(ROOT), 'add', 'media.rev'], check=False)
    log(f"✓ media {h[:10]} → {branch}: {len(ch['new'])} new, {len(ch['changed'])} changed, {len(ch['deleted'])} deleted;"
        f" media.rev staged — commit it with the JSON")
    return h


def problem() -> str | None:
    """Why paid generation must not run now, or None. A file listed in the pinned media but absent on disk
    must be pulled, not regenerated: a fresh clone + `make assets` would otherwise redraw the whole film."""
    if os.environ.get('MEDIA_CHECK') == '0':
        return None
    rev = pinned()
    if not rev:
        return None
    h = head()
    if not h:
        return 'media not pulled: make media-pull'
    behind = h != rev and subprocess.run(['git', f'--git-dir={git_dir()}', 'merge-base', '--is-ancestor', rev, h],
                                         capture_output=True).returncode != 0  # local media newer than the pin — fine
    if behind:
        return f'media are at {h[:10]}, media.rev wants {rev[:10]}: make media-pull'
    return None


def check() -> None:
    p = problem()
    if p:
        sys.exit(f'✗ {p}  (MEDIA_CHECK=0 to override)')


def status(log=print) -> None:
    rev, h = pinned(), head()
    if not git_dir().exists():
        log(f"  media        not pulled (media.rev {rev[:10] if rev else '—'}): make media-pull")
        return
    ch = changes()
    on_remote = bool(h) and bool(git('branch', '-r', '--contains', h, check=False).strip())
    state = 'pulled' if h == rev else f'at {h[:10] if h else "—"}, media.rev {rev[:10] if rev else "—"}'
    todo = ', '.join(f'{len(v)} {k}' for k, v in ch.items() if v)
    log(f"  media        {state}; {len(media_files())} files" + (f'; local: {todo} — make media-push' if todo else '')
        + ('' if on_remote or not h else '; commit not pushed — make media-push'))


def prepush() -> int:
    """git pre-push hook: the pinned media commit must be on the media remote; warn about unpushed media."""
    if not git_dir().exists():
        return 0
    rev = pinned()
    if rev and not git('branch', '-r', '--contains', rev, check=False).strip():
        print(f'✗ media.rev {rev[:10]} is not on the media remote: make media-push  (git push --no-verify to skip)')
        return 1
    ch = changes()
    if any(ch.values()):
        n = sum(map(len, ch.values()))
        print(f'⚠ {n} media files changed locally and not pushed (make media-push) — in a cloud session they are lost'
              f' with the container')
    return 0


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog='python -m engine.media')
    ap.add_argument('cmd', choices=['status', 'pull', 'push', 'check', 'prepush'])
    ap.add_argument('--latest', action='store_true')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('-m', dest='message')
    a = ap.parse_args(argv)
    config.load_env()
    try:
        if a.cmd == 'status':
            status()
        elif a.cmd == 'pull':
            pull(latest=a.latest, force=a.force)
        elif a.cmd == 'push':
            push(a.message)
        elif a.cmd == 'check':
            check()
        elif a.cmd == 'prepush':
            sys.exit(prepush())
    except MediaError as e:
        sys.exit(f'✗ {e}')


if __name__ == '__main__':
    main()
