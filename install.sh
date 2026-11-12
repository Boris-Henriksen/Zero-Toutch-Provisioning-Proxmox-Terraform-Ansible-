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
    ca-certificates \
    xorriso \
    file

echo "==>     Installerer proxmox-auto-install-assistant (bygger Proxmox PXE-installer med svarfil-URL)..."
if ! command -v proxmox-auto-install-assistant >/dev/null; then
    # Hentes over http, da https til download.proxmox.com kan blive opsnappet af netværksfiltre.
    # Pakken verificeres mod SHA256 i Proxmox' pakkeindeks.
    PVE_REPO="http://download.proxmox.com/debian/pve"
    PKG_INFO=$(curl -fsSL "$PVE_REPO/dists/trixie/pve-no-subscription/binary-amd64/Packages.gz" | gunzip \
        | awk '/^Package: proxmox-auto-install-assistant$/{p=1} p&&/^$/{p=0} p')
    PKG_FILE=$(echo "$PKG_INFO" | sed -n 's/^Filename: //p' | tail -n 1)
    PKG_SHA=$(echo "$PKG_INFO" | sed -n 's/^SHA256: //p' | tail -n 1)
    TMP_DEB=$(mktemp --suffix=.deb)
    curl -fsSL -o "$TMP_DEB" "$PVE_REPO/$PKG_FILE"
    echo "$PKG_SHA  $TMP_DEB" | sha256sum -c -
    chmod 0644 "$TMP_DEB"
    apt-get install -y "$TMP_DEB"
    rm -f "$TMP_DEB"
fi

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
# Giv build-output tilbage til repo-ejeren, så senere 'npm run build' uden sudo virker.
chown -R "$(stat -c '%U:%G' "$REPO_DIR")" "$FRONTEND_DIR/dist" "$FRONTEND_DIR/node_modules"

echo "==>     Installerer frontend i ${FRONTEND_DEPLOY_DIR}..."
rm -rf "$FRONTEND_DEPLOY_DIR"
install -d -o root -g www-data -m 0755 "$FRONTEND_DEPLOY_DIR"
cp -a "$FRONTEND_DIR/dist/." "$FRONTEND_DEPLOY_DIR/"
chown -R root:www-data "$FRONTEND_DEPLOY_DIR"
find "$FRONTEND_DEPLOY_DIR" -type d -exec chmod 0755 {} +
find "$FRONTEND_DEPLOY_DIR" -type f -exec chmod 0644 {} +

echo "==> [4/8] Opretter storage-mapper og PXE-boot filer..."
mkdir -p "$STORAGE_DIR/isos/proxmox" "$STORAGE_DIR/isos/ubuntu" "$STORAGE_DIR/extracted" "$STORAGE_DIR/discovery" "$STORAGE_DIR/tftpboot"

# Fuld ipxe.efi (egne NIC-drivere): snponly.efi deler netkortet med firmwarens
# netværksstack og modtager på nogle maskiner aldrig DHCP-svar ("Configuring net0").
install -m 0644 /usr/lib/ipxe/ipxe.efi "$STORAGE_DIR/tftpboot/ipxe.efi"
# Legacy BIOS-klienter (f.eks. Dell i "BIOS boot mode") kan ikke køre ipxe.efi.
install -m 0644 /usr/lib/ipxe/undionly.kpxe "$STORAGE_DIR/tftpboot/undionly.kpxe"

cat << 'EOF' > "$STORAGE_DIR/tftpboot/autoexec.ipxe"
#!ipxe
# Genbrug firmwarens DHCP-lease hvis det findes, ellers lav DHCP paa alle interfaces.
isset ${net0/ip} && ifopen net0 && goto boot ||
dhcp && goto boot ||
echo DHCP fejlede - aabner iPXE shell
shell

:boot
chain http://${next-server}:8000/auto-installer.ipxe?mac=${netX/mac} || shell
EOF

if [[ -f "$STORAGE_DIR/discovery/discovery-script.sh" ]]; then
    chmod +x "$STORAGE_DIR/discovery/discovery-script.sh"
fi

if [[ ! -f "$STORAGE_DIR/discovery/vmlinuz" || ! -f "$STORAGE_DIR/discovery/initrd" || ! -f "$STORAGE_DIR/discovery/ubuntu-live.iso" ]]; then
    echo "    NB: Discovery-image mangler - upload en Ubuntu Server live ISO på portalens setup-side."
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
systemctl enable "${SERVICE_NAME}"
# restart (ikke kun --now), så en ny kørsel af install.sh også indlæser opdateret kode.
systemctl restart "${SERVICE_NAME}"

echo "==> [7/8] Konfigurerer nginx (serverer frontend + proxy til backend)..."
cat << EOF > /etc/nginx/sites-available/portal
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    # ISO-filer (flere GB) uploades via setup-siden.
    client_max_body_size 0;

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
        # Stream store uploads direkte til backend i stedet for at buffre dem på disk.
        proxy_request_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
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
echo " Åbn portalen og upload/download Proxmox- og Ubuntu-ISO'en på setup-siden."
echo " (Manuelt: Proxmox i ${STORAGE_DIR}/isos/proxmox/, Ubuntu via scripts/prepare-discovery-image.sh)"
echo ""
echo " Se logs med: journalctl -u ${SERVICE_NAME} -f"
echo "==================================================================="
