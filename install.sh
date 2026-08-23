#!/usr/bin/env bash
#
# install.sh - Installerer og konfigurerer Infrastruktur Portal (backend + frontend)
# på en frisk Debian/Ubuntu (arm64/amd64) maskine.
#
# Formålet: kildekoden ligger i Git, og denne fil sørger for at installere alle
# afhængigheder (Python, Node, dnsmasq, ipxe, nginx), bygge frontend, og sætte
# services op via systemd - så portalen kan genskabes 1:1 på en ny maskine med:
#
#   git clone <repo> && cd <repo> && sudo ./install.sh
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Dette script skal køres som root, f.eks: sudo ./install.sh" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$REPO_DIR/backend"
FRONTEND_DIR="$REPO_DIR/frontend"
FRONTEND_DEPLOY_DIR="/var/www/portal"
STORAGE_DIR="$REPO_DIR/storage"
VENV_DIR="$REPO_DIR/venv"
SERVICE_NAME="portal-backend"
BACKEND_PORT=8000

echo "==> Installerer i: $REPO_DIR"

echo "==> [1/8] Installerer systempakker (apt)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    python3 \
    python3-venv \
    python3-pip \
    nodejs \
    npm \
    dnsmasq \
    ipxe \
    nginx \
    curl \
    ca-certificates

echo "==> [2/8] Opretter Python virtualenv og installerer backend-afhængigheder..."
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

echo "==> [3/8] Bygger frontend (npm ci + vite build)..."
if [[ -f "$FRONTEND_DIR/package-lock.json" ]]; then
    npm ci --prefix "$FRONTEND_DIR"
else
    npm install --prefix "$FRONTEND_DIR"
fi
npm run build --prefix "$FRONTEND_DIR"

echo "==>     Installerer frontend i ${FRONTEND_DEPLOY_DIR}..."
rm -rf "$FRONTEND_DEPLOY_DIR"
install -d -o root -g www-data -m 0755 "$FRONTEND_DEPLOY_DIR"
cp -a "$FRONTEND_DIR/dist/." "$FRONTEND_DEPLOY_DIR/"
chown -R root:www-data "$FRONTEND_DEPLOY_DIR"
find "$FRONTEND_DEPLOY_DIR" -type d -exec chmod 0755 {} +
find "$FRONTEND_DEPLOY_DIR" -type f -exec chmod 0644 {} +

echo "==> [4/8] Opretter storage-mapper og PXE-boot filer..."
mkdir -p "$STORAGE_DIR/isos" "$STORAGE_DIR/extracted" "$STORAGE_DIR/discovery" "$STORAGE_DIR/tftpboot"

if [[ ! -f "$STORAGE_DIR/tftpboot/ipxe.efi" ]]; then
    cp /usr/lib/ipxe/ipxe.efi "$STORAGE_DIR/tftpboot/ipxe.efi"
fi

if [[ ! -f "$STORAGE_DIR/tftpboot/autoexec.ipxe" || "$(head -n 1 "$STORAGE_DIR/tftpboot/autoexec.ipxe" 2>/dev/null)" == "cat << 'EOF'" ]]; then
    cat << 'EOF' > "$STORAGE_DIR/tftpboot/autoexec.ipxe"
#!ipxe
dhcp
chain http://${next-server}:8000/auto-installer.ipxe
EOF
fi

if [[ -f "$STORAGE_DIR/discovery/discovery-script.sh" ]]; then
    chmod +x "$STORAGE_DIR/discovery/discovery-script.sh"
fi

if [[ ! -f "$STORAGE_DIR/discovery/vmlinuz" || ! -f "$STORAGE_DIR/discovery/initrd" ]]; then
    echo "    NB: storage/discovery/vmlinuz + initrd mangler."
    echo "    Kør 'sudo ./scripts/prepare-discovery-image.sh /sti/til/ubuntu-live-server.iso' for at generere dem."
fi

echo "==> [5/8] Deaktiverer system-dnsmasq (portalen starter selv sin egen dnsmasq-proces)..."
systemctl disable --now dnsmasq >/dev/null 2>&1 || true

echo "==> [6/8] Installerer systemd-service for backend..."
cat << EOF > "/etc/systemd/system/${SERVICE_NAME}.service"
[Unit]
Description=Infrastruktur Portal - FastAPI backend
After=network.target

[Service]
Type=simple
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_DIR}/bin/uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${BACKEND_PORT}
Restart=on-failure
RestartSec=2
# Backend'en udfører privilegerede operationer (mount af ISO'er, tftp/dhcp via
# dnsmasq), og kører derfor som root - ligesom den oprindeligt blev udviklet til.
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "==> [7/8] Konfigurerer nginx (serverer frontend + proxy til backend)..."
cat << EOF > /etc/nginx/sites-available/portal
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    root ${FRONTEND_DEPLOY_DIR};
    index index.html;

    location / {
        try_files \$uri /index.html;
    }

    location ~ ^/(api/|proxmox/|auto-installer\.ipxe) {
        proxy_pass http://127.0.0.1:${BACKEND_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/portal /etc/nginx/sites-enabled/portal
nginx -t
systemctl enable --now nginx
systemctl reload nginx

echo "==> [8/8] Status..."
systemctl --no-pager --lines=0 status "${SERVICE_NAME}" || true
systemctl --no-pager --lines=0 status nginx || true

echo ""
echo "==================================================================="
echo " Installation færdig."
echo " Portal:  http://<server-ip>/"
echo " Backend: http://<server-ip>:${BACKEND_PORT}/ (proxy'et via nginx på port 80)"
echo ""
echo " Læg Proxmox ISO-filer i:   ${STORAGE_DIR}/isos/"
echo " Discovery boot-image:      sudo ./scripts/prepare-discovery-image.sh <iso>"
echo ""
echo " Se logs med: journalctl -u ${SERVICE_NAME} -f"
echo "==================================================================="
