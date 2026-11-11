#!/usr/bin/env bash
# Kører i Ubuntu live discovery-imaget: rapporterer diske og venter derefter på besked
# fra portalen om at genstarte ind i Proxmox installeren (så ingen skal trykke på tænd-knappen).
set -u

PORTAL_URL=$(tr ' ' '\n' </proc/cmdline | sed -n 's/^portal.server=//p' | head -n 1)
if [[ -z "$PORTAL_URL" ]]; then
     exit 1
fi

PORTAL_HOST=${PORTAL_URL#http://}
PORTAL_HOST=${PORTAL_HOST%%/*}
PORTAL_HOST=${PORTAL_HOST%%:*}
INTERFACE=$(ip route get "$PORTAL_HOST" | awk '{for (i = 1; i <= NF; i++) if ($i == "dev") {print $(i + 1); exit}}')
MAC=$(cat "/sys/class/net/${INTERFACE}/address")

DISKS_JSON=$(python3 - <<'PY'
import json
import subprocess

devices = json.loads(subprocess.check_output(["lsblk", "-b", "-d", "-J", "-o", "NAME,SIZE,MODEL,SERIAL,TYPE"], text=True))["blockdevices"]
disks = [
     {
          "name": device["name"],
          "size": f"{int(device['size']) // 1073741824}G",
          "model": (device.get("model") or "Generic Disk").strip(),
          "serial": (device.get("serial") or "").strip(),
     }
     for device in devices
     if device.get("type") == "disk"
]
print(json.dumps(disks))
PY
)

until curl --fail --silent --show-error -X POST "${PORTAL_URL}/api/baremetal/report-disks/${MAC}" \
     -H "Content-Type: application/json" \
     -d "$DISKS_JSON"; do
     sleep 5
done

echo "Diske rapporteret til portalen - venter på installationsbesked..."

# Sæt næste UEFI-boot til netværkskortet, så genstarten går til PXE uanset boot-rækkefølge.
set_pxe_bootnext() {
     command -v efibootmgr >/dev/null || return 0
     local mac_compact entry
     mac_compact=$(echo "$MAC" | tr -d ':' | tr '[:lower:]' '[:upper:]')
     entry=$(efibootmgr -v 2>/dev/null | grep -i "MAC(${mac_compact}" | grep -iv "IPv6" | head -n 1 | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\).*/\1/p')
     if [[ -z "$entry" ]]; then
          entry=$(efibootmgr 2>/dev/null | grep -iE "IPv4|PXE|Network" | grep -iv "IPv6" | head -n 1 | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\).*/\1/p')
     fi
     [[ -n "$entry" ]] && efibootmgr -n "$entry" >/dev/null 2>&1
     return 0
}

while true; do
     action=$(curl --fail --silent "${PORTAL_URL}/api/baremetal/next-action/${MAC}" 2>/dev/null || true)
     if echo "$action" | grep -q '"install"'; then
          echo "Portalen har startet installationen - genstarter til PXE..."
          set_pxe_bootnext
          sync
          reboot -f
     fi
     sleep 5
done
