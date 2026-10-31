# Деплой сайта grin.nemilya.me

[English](README.md) · **Русский** · полный цикл (клон → сборка → сайт) — [README.ru.md](../README.ru.md#полный-цикл-от-клона-до-сайта)

Как в mountain-rock: `make deploy` записывает собранный сайт в папку на сервере — и всё.

## Один раз

В `local.mk` (или `.env`) — папка на сервере, которую раздаёт веб-сервер (ssh-алиас из `~/.ssh/config` подходит):

```
DEPLOY = ssh://nemilya-me/var/www/grin
SITE_URL = https://grin.nemilya.me
```

## Каждый раз — два шага

```bash
make media-pull     # 0) медиа той версии, что в media.rev (без них make site не запустится)
make site           # 1) собрать сайт → dist/  (посмотреть: make serve → http://127.0.0.1:8730/)
make deploy-dry     #    что уйдёт на сервер — ничего не меняет
make deploy         # 2) залить; пароль ssh спросят один раз
```

`make deploy` заливает **ровно собранный сайт** — не пересобирает его. Если сайт не собран или после сборки
поменялись озвучка, текст, раскадровки, ассеты, `site.json` или сцена (`stage/js`), он остановится и попросит
сначала `make site`: на сервер уходит то, что вы видели. По порядку:

1. подключается к серверу один раз (пароль — здесь, в консоли);
2. дописывает медиа (слои webp, таймлайны, звук видео, постеры), озвучку и ресурсы — без удаления, старые страницы
   продолжают работать;
3. записывает страницы и удаляет всё, чего больше нет в `dist/`.

В папке на сервере должен лежать только этот сайт: лишние файлы в ней удаляются.

## Кеш

Ссылки на стили, скрипты, шрифты, медиа и звук — со штампом `?v=<хеш содержимого>`, сцена (stage.js и three.js) —
в папке `assets/stage-<хеш>/`: поменялся файл — поменялась ссылка. Поэтому их можно кешировать навсегда
(`immutable`), а страницы — минуту: новая сборка видна сразу и не смешивается со старым кешем.

## Если для адреса ещё нет веб-сервера

Только если `grin.nemilya.me` ещё ничего не раздаёт — готовый [`nginx.conf`](nginx.conf):

```bash
scp deploy/nginx.conf nemilya-me:/tmp/grin.conf
ssh nemilya-me
sudo mkdir -p /var/www/grin && sudo chown $USER: /var/www/grin
sudo cp /tmp/grin.conf /etc/nginx/sites-available/grin
sudo ln -s /etc/nginx/sites-available/grin /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d grin.nemilya.me      # https
```

(и A-запись `grin.nemilya.me` в DNS на IP сервера). Путь в `nginx.conf` (`root`) — тот же, что в `DEPLOY`.

Если адрес уже раздаёт другой конфиг nginx — достаточно, чтобы его `root` указывал на папку из `DEPLOY`;
типы `m4a` (audio/mp4) и `webp` nginx обычно знает (mime.types).
