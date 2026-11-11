#!/bin/bash
# Køres af Proxmox' first-boot hook (proxmox-first-boot) første gang en ny node starter.
# Hentes fra portalen, som indsætter sin egen URL i PORTAL_URL.
PORTAL_URL="__PORTAL_URL__"
LOG=/var/log/portal-first-boot.log
exec > >(tee -a "$LOG") 2>&1

report() {
    local ok="$1" message="$2"
    local body
    body=$(printf '{"ok": %s, "message": "%s"}' "$ok" "$(printf '%s' "$message" | tr -d '"\\\n\r' | tail -c 300)")
    for attempt in $(seq 1 60); do
        for mac in $MACS; do
            if curl -fsS -X POST -H "Content-Type: application/json" -d "$body" "$PORTAL_URL/api/baremetal/first-boot-done/$mac" >/dev/null 2>&1; then
                return 0
            fi
        done
        sleep 10
    done
}

fail() {
    echo "FEJL: $1"
    report false "$1"
    exit 1
}

# Alle fysiske MAC-adresser - portalen kender noden på PXE-netkortets MAC.
MACS=$(cat /sys/class/net/*/address 2>/dev/null | grep -v '^00:00:00:00:00:00$' | sort -u)

echo "==> Slår enterprise-repos fra (kræver subscription) og tilføjer no-subscription repo"
for file in /etc/apt/sources.list.d/pve-enterprise.sources /etc/apt/sources.list.d/ceph.sources; do
    if [[ -f "$file" ]] && ! grep -q '^Enabled:' "$file"; then
        sed -i '/^Types:/a Enabled: false' "$file"
    fi
done
for file in /etc/apt/sources.list.d/pve-enterprise.list /etc/apt/sources.list.d/ceph.list; do
    [[ -f "$file" ]] && sed -i 's/^deb /# deb /' "$file"
done

CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
cat > /etc/apt/sources.list.d/proxmox.sources <<EOF
Types: deb
URIs: http://download.proxmox.com/debian/pve
Suites: $CODENAME
Components: pve-no-subscription
Signed-By: /usr/share/keyrings/proxmox-archive-keyring.gpg
EOF

export DEBIAN_FRONTEND=noninteractive
apt-get update || fail "apt-get update fejlede (har noden internet/DNS?)"

INSTALL_CEPH=false
for mac in $MACS; do
    config=$(curl -fsS "$PORTAL_URL/api/baremetal/first-boot-config/$mac" 2>/dev/null) || continue
    if echo "$config" | grep -q '"install_ceph": *true'; then
        INSTALL_CEPH=true
    fi
    break
done

if [[ "$INSTALL_CEPH" == true ]]; then
    echo "==> Installerer Ceph-pakker"
    yes | pveceph install --repository no-subscription || fail "pveceph install fejlede"
    command -v ceph >/dev/null || fail "Ceph blev ikke installeret"
    report true "Klar (Ceph-pakker installeret)"
else
    report true "Klar"
fi
