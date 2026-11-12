#!/usr/bin/env bash
# Kører i Ubuntu live discovery-imaget: rapporterer diske og venter derefter på besked fra portalen.
# Når installationen startes, gøres den valgte OS-disk ikke-bootbar, næste boot sættes til PXE,
# og noden genstarter ind i Proxmox installeren (så ingen skal trykke på tænd-knappen).
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
IP=$(ip -4 -o addr show dev "$INTERFACE" | awk '{print $4}' | head -n 1)

# Statusskærm på en egen konsol (vt9), så live-imagets egne beskeder ikke skjuler den.
STATUS_FILE=/run/portal-status
show_status() {
     {
          echo "=================================================================="
          echo "   Zero-Touch Proxmox Provisioning"
          echo "=================================================================="
          echo
          echo "   MAC: $MAC    IP: ${IP:-ukendt}    Portal: $PORTAL_HOST"
          echo
          printf '   %s\n' "$@"
          echo
          echo "=================================================================="
     } >"$STATUS_FILE"
     cat "$STATUS_FILE" >/dev/console 2>/dev/null
}

start_status_screen() {
     command -v openvt >/dev/null || return 0
     openvt -c 9 -f -s -- bash -c "setterm --blank 0 --cursor off 2>/dev/null; while :; do clear; cat '$STATUS_FILE'; sleep 2; done" 2>/dev/null
}

show_status "Scanner hardware og rapporterer diske til portalen..."
start_status_screen

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

DISK_COUNT=$(python3 -c 'import json, sys; print(len(json.loads(sys.argv[1])))' "$DISKS_JSON")

report_disks() {
     until curl --fail --silent --show-error -X POST "${PORTAL_URL}/api/baremetal/report-disks/${MAC}" \
          -H "Content-Type: application/json" \
          -d "$DISKS_JSON"; do
          sleep 5
     done
     show_status \
          "OK  Hardware rapporteret til portalen ($DISK_COUNT diske fundet)." \
          "" \
          "Venter på at Proxmox-installationen bliver startet." \
          "" \
          "Gør konfigurationen færdig i portalen og tryk" \
          "'Start Proxmox Auto-Installation'." \
          "Noden genstarter derefter selv og installerer Proxmox." \
          "" \
          "Sluk IKKE maskinen."
}
report_disks

# efibootmgr er ikke med i live-imaget - installér mens vi venter.
if ! command -v efibootmgr >/dev/null; then
     DEBIAN_FRONTEND=noninteractive timeout 300 apt-get install -y -q efibootmgr >/dev/null 2>&1 \
          || { timeout 300 apt-get update -q >/dev/null 2>&1 \
               && DEBIAN_FRONTEND=noninteractive timeout 300 apt-get install -y -q efibootmgr >/dev/null 2>&1; } \
          || echo "efibootmgr kunne ikke installeres - stoler på at den slettede disk får firmwaren til at netværksboote."
fi

# Gør den valgte OS-disk ikke-bootbar, så firmwaren ikke starter det gamle system
# (Windows/Ubuntu/gammel Proxmox) men går videre til netværksboot. Disken slettes alligevel af installationen.
wipe_os_disk() {
     local disk=$1 dev sectors
     [[ "$disk" =~ ^[a-zA-Z0-9]+$ ]] || return 0
     dev="/dev/$disk"
     [[ -b "$dev" && "$(lsblk -dno TYPE "$dev" 2>/dev/null)" == "disk" ]] || return 0
     lsblk -lnpo NAME,TYPE "$dev" | awk '$2 == "part" {print $1}' | while read -r part; do
          wipefs -af "$part" >/dev/null 2>&1
     done
     wipefs -af "$dev" >/dev/null 2>&1
     sectors=$(blockdev --getsz "$dev" 2>/dev/null || echo 0)
     dd if=/dev/zero of="$dev" bs=1M count=16 conv=fsync status=none 2>/dev/null
     # GPT har en backup-kopi i slutningen af disken.
     if [[ "$sectors" -gt 65536 ]]; then
          dd if=/dev/zero of="$dev" bs=512 seek=$((sectors - 32768)) count=32768 conv=fsync status=none 2>/dev/null
     fi
}

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

last_action=""
while true; do
     action=$(curl --fail --silent "${PORTAL_URL}/api/baremetal/next-action/${MAC}" 2>/dev/null || true)
     if echo "$action" | grep -q '"install"'; then
          disk=$(ACTION_JSON="$action" python3 -c 'import json, os; print(json.loads(os.environ["ACTION_JSON"]).get("disk", ""))')
          show_status \
               "Installationen er startet fra portalen." \
               "" \
               "Forbereder disken ${disk:-?} og genstarter til netværksboot (PXE)..." \
               "Proxmox installeres automatisk efter genstarten."
          wipe_os_disk "$disk"
          set_pxe_bootnext
          sync
          sleep 3
          reboot -f
     elif echo "$action" | grep -q '"report"'; then
          report_disks
     elif echo "$action" | grep -q '"reset"' && [[ "$last_action" != "reset" ]]; then
          show_status \
               "Portalen er blevet nulstillet - installationen er stoppet." \
               "" \
               "Noden venter på en ny discovery." \
               "Start 'Discovery Mode' i portalen med denne nodes MAC-adresse," \
               "så rapporterer noden sin hardware igen af sig selv." \
               "" \
               "Sluk IKKE maskinen."
     fi
     [[ -n "$action" ]] && last_action=$(echo "$action" | sed -n 's/.*"action": *"\([a-z]*\)".*/\1/p')
     sleep 5
done
