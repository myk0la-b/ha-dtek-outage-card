#!/usr/bin/env bash
# Deploy the DTEK scraper on the home Raspberry Pi (rpi).
# Runs the pure-HTTP scraper via systemd timer; writes state.json into HA's www dir.
#
#   ./install_pi.sh            # copy + setup (idempotent)
#
# Requires: env RPI=host (default: rpi), HA config at /srv/homeassistant/config.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/../.." && pwd)"   # проєкт = deploy/pi/ на два вгору
RPI="${RPI:-rpi}"
DEST=/srv/dtek-outage

echo "==> syncing project to $RPI:$DEST"
ssh "$RPI" "sudo mkdir -p $DEST && sudo chown \$(id -un) $DEST"
rsync -a --delete \
  --exclude venv --exclude __pycache__ --exclude out --exclude .git \
  "$SRC/scraper/dtek_scraper.py" "$SRC/scraper/requirements.txt" "$RPI:$DEST/"
# cookie-файл опціональний (тільки 'теплий' старт з візід-кукою) — сесія самовідновлюється сама
[ -f "$SRC/scraper/cookies.dtek.json" ] && scp "$SRC/scraper/cookies.dtek.json" "$RPI:$DEST/cookies.dtek.json"

echo "==> python venv + deps"
ssh "$RPI" "test -d $DEST/venv || python3 -m venv $DEST/venv; $DEST/venv/bin/pip -q install -U pip curl_cffi"

echo "==> HA www dir"
ssh "$RPI" "sudo mkdir -p /srv/homeassistant/config/www/dtek_outage && sudo chmod 777 /srv/homeassistant/config/www/dtek_outage"

echo "==> systemd unit"
scp "$SRC/deploy/pi/dtek-scraper.service" "$SRC/deploy/pi/dtek-scraper.timer" "$RPI:/tmp/"
ssh "$RPI" "sudo mv /tmp/dtek-scraper.{service,timer} /etc/systemd/system/ && \
  sudo systemctl daemon-reload && sudo systemctl enable --now dtek-scraper.timer"

echo "==> first run"
ssh "$RPI" "sudo systemctl start dtek-scraper.service; sleep 2; tail -2 /var/log/dtek-scraper.log || true"
echo "done. timer: systemctl list-timers dtek-scraper.timer on rpi"
