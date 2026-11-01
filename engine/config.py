"""Paths, the OpenRouter key, stories (stories/<slug>/story.json)."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORIES = ROOT / 'stories'
STYLES = ROOT / 'styles'
DIRECTORS = ROOT / 'directors'
OUT = ROOT / 'out'  # renders: frames and films (not in git)
SITE = ROOT / 'site'  # site sources: styles, scripts, fonts, texts
DIST = ROOT / 'dist'  # the built site (make site; not in git)


def load_env() -> None:
    """OPENROUTER_API_KEY etc. from .env or local.mk (unless already in the environment). The key is never written anywhere."""
    for name in ('.env', 'local.mk'):
        f = ROOT / name
        if not f.exists():
            continue
        for line in f.read_text(encoding='utf8').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            for sep in (':=', '?=', '='):
                if sep in line:
                    k, v = line.split(sep, 1)
                    k, v = k.strip().removeprefix('export ').strip(), v.strip().strip('"\'')
                    if k and k.isidentifier() and k not in os.environ:
                        os.environ[k] = v
                    break


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf8'))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n', encoding='utf8')
    tmp.replace(path)


def story_dir(slug: str) -> Path:
    d = STORIES / slug
    if not (d / 'story.json').exists() or '/' in slug or slug.startswith('.'):
        raise KeyError(f'no story {slug}')
    return d


def text_dir(slug: str) -> Path:
    """Where the text, translation and voice live. A production ("base": another story) takes them from the base story,
    and keeps its own bible, storyboard, assets and build (story_dir)."""
    base = read_json(story_dir(slug) / 'story.json').get('base')
    return story_dir(base) if base else story_dir(slug)


def story(slug: str) -> dict:
    s = read_json(story_dir(slug) / 'story.json')
    if s.get('base'):  # a production: the base story's fields + its own on top (film — key by key)
        b = read_json(story_dir(s['base']) / 'story.json')
        b.pop('formats', None)
        s = {**b, **s, 'film': {**b.get('film', {}), **s.get('film', {})}}
    s['slug'] = slug
    return s


def stories() -> list[dict]:
    return [story(d.name) for d in sorted(STORIES.iterdir()) if (d / 'story.json').exists()]


def site_config() -> dict:
    """site.json: address, languages, author, stories and their video versions (make site)."""
    return read_json(ROOT / 'site.json', {}) or {}
