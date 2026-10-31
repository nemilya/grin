# Deploying grin.nemilya.me

**English** · [Русский](README.ru.md) · the whole cycle (clone → build → live site) — [README](../README.md#full-cycle-from-a-clone-to-the-live-site)

As in mountain-rock: `make deploy` writes the built site into a folder on the server — that's all. It runs from
your own machine over ssh (rsync); a Claude Code cloud session can build the site but can't deploy it (no ssh).

## Once per machine

In `local.mk` (or `.env`) — the server folder the web server serves (an ssh alias from `~/.ssh/config` works):

```
DEPLOY = ssh://nemilya-me/var/www/grin
SITE_URL = https://grin.nemilya.me
```

## Every time — two steps

```bash
make media-pull     # 0) the media of media.rev (make site refuses to run without them)
make site           # 1) build the site → dist/  (look at it: make serve → http://127.0.0.1:8730/)
make deploy-dry     #    what would be uploaded — changes nothing
make deploy         # 2) upload; the ssh password is asked once
```

`make deploy` uploads **exactly the built site** — it doesn't rebuild it. If the site isn't built, or the narration,
texts, storyboards, assets, `site.json` or the scene (`stage/js`) changed after the build, it stops and asks for
`make site` first: the server gets what you have seen. In order:

1. connects to the server once (the password — here, in the console);
2. adds media (webp layers, timelines, video sound, posters), narration and resources — without deleting, so pages
   being viewed keep working;
3. writes the pages and deletes everything that is no longer in `dist/`.

The server folder must hold only this site: anything else in it is deleted.

## Cache

Links to styles, scripts, fonts, media and sound carry a `?v=<content hash>` stamp; the scene (stage.js and three.js)
lives in `assets/stage-<hash>/`: a changed file gets a new link. So they can be cached forever (`immutable`), and
pages for a minute: a new build shows up right away and never mixes with the old cache.

## If the address has no web server yet

Only if `grin.nemilya.me` serves nothing yet — a ready [`nginx.conf`](nginx.conf):

```bash
scp deploy/nginx.conf nemilya-me:/tmp/grin.conf
ssh nemilya-me
sudo mkdir -p /var/www/grin && sudo chown $USER: /var/www/grin
sudo cp /tmp/grin.conf /etc/nginx/sites-available/grin
sudo ln -s /etc/nginx/sites-available/grin /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d grin.nemilya.me      # https
```

(plus a DNS A record for `grin.nemilya.me` pointing at the server). The path in `nginx.conf` (`root`) is the same as in
`DEPLOY`. If another nginx config already serves the address, it's enough that its `root` points at the `DEPLOY`
folder; nginx usually knows the `m4a` (audio/mp4) and `webp` types (mime.types).

## Moving to another server

Set up nginx there as above, change `DEPLOY` (and DNS), `make deploy` — the site is fully contained in `dist/`,
nothing else lives on the server.
