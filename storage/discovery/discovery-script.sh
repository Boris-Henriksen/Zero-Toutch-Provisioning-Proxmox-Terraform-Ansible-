#!/usr/bin/env bash
set -eu

PORTAL_URL=$(tr ' ' '\n' </proc/cmdline | sed -n 's/^portal.server=//p' | head -n 1)
if [[ -z "$PORTAL_URL" ]]; then
     exit 1
fi

PORTAL_HOST=${PORTAL_URL#http://}
PORTAL_HOST=${PORTAL_HOST%%/*}
INTERFACE=$(ip route get "$PORTAL_HOST" | awk '{for (index = 1; index <= NF; index++) if ($index == "dev") {print $(index + 1); exit}}')
MAC=$(cat "/sys/class/net/${INTERFACE}/address")

DISKS_JSON=$(python3 - <<'PY'
import json
import subprocess

devices = json.loads(subprocess.check_output(["lsblk", "-b", "-d", "-J", "-o", "NAME,SIZE,MODEL,TYPE"], text=True))["blockdevices"]
disks = [
     {
          "name": device["name"],
          "size": f"{int(device['size']) // 1073741824}G",
          "model": (device.get("model") or "Generic Disk").strip(),
     }
     for device in devices
     if device.get("type") == "disk"
]
print(json.dumps(disks))
PY
)

curl --fail --silent --show-error -X POST "${PORTAL_URL}/api/baremetal/report-disks/${MAC}" \
     -H "Content-Type: application/json" \
     -d "$DISKS_JSON"

poweroff -f
