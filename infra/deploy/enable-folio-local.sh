#!/usr/bin/env bash
# Publish Verso Folio at https://folio.local on the LAN. Run once, as root:
#   sudo bash infra/deploy/enable-folio-local.sh [LAN_IP]
#
# 1. Appends a folio.local site to the shared Caddy (/srv/docker/infrastructure/Caddyfile),
#    edited in place so the container's single-file bind mount sees it. Backed up first,
#    validated inside the running proxy, and restored automatically if validation fails.
# 2. Installs folio-mdns.service, publishing folio.local over mDNS like the other LAN apps.
set -euo pipefail

CADDYFILE=/srv/docker/infrastructure/Caddyfile
PROXY=reverse-proxy
LAN_IP="${1:-$(hostname -I | tr ' ' '\n' | grep -m1 '^192\.168\.')}"

[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
[[ -n "$LAN_IP" ]] || { echo "Could not detect the LAN IP; pass it as the first argument." >&2; exit 1; }

if grep -q "folio.local" "$CADDYFILE"; then
  echo "Caddy already has a folio.local site; leaving it unchanged."
else
  backup="$CADDYFILE.bak-$(date +%Y%m%d-%H%M%S)-before-folio"
  cp -p "$CADDYFILE" "$backup"
  cat >> "$CADDYFILE" <<'SITE'

http://folio.local {
 redir https://folio.local{uri} permanent
}

https://folio.local {
 tls internal
 encode zstd gzip
 @outside not remote_ip 127.0.0.0/8 ::1 192.168.68.0/24 100.64.0.0/10
 respond @outside "LAN access only" 403
 header Strict-Transport-Security "max-age=31536000"
 request_body {
  max_size 210MB
 }
 @backend path /api/*
 handle @backend {
  reverse_proxy folio-api:8000 {
   transport http {
    dial_timeout 5s
    response_header_timeout 300s
   }
  }
 }
 handle {
  reverse_proxy folio-web:8080
 }
}
SITE
  if ! docker exec "$PROXY" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null; then
    cat "$backup" > "$CADDYFILE"   # in place: keeps the bind-mounted inode
    echo "Caddy rejected the new config; restored $backup." >&2
    exit 1
  fi
  docker exec "$PROXY" caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
  echo "Caddy now serves https://folio.local (backup: $backup)."
fi

cat > /etc/systemd/system/folio-mdns.service <<UNIT
[Unit]
Description=Publish folio.local over mDNS (Verso Folio)
After=network-online.target avahi-daemon.service
Wants=network-online.target avahi-daemon.service

[Service]
ExecStart=/usr/bin/avahi-publish -a -R folio.local ${LAN_IP}
Restart=on-failure
RestartSec=10
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now folio-mdns.service
echo "folio.local -> ${LAN_IP} published over mDNS."
echo "Open https://folio.local (trust the local CA from https://verso.local/verso-local-ca.crt if your browser warns)."
