cat << 'EOF' > ~/portal/storage/discovery/discovery-script.sh
#!/bin/bash

# Hent MAC-adresse fra primære netværkskort
MAC=$(ip link show | grep "link/ether" | head -n 1 | awk '{print $2}')

# Find automations-PC IP ud fra gateway / DHCP server
SERVER_IP=$(ip route show default | awk '{print $3}')

# Indsaml disk-informationer via lsblk i JSON format
DISKS_JSON=$(lsblk -b -d -J -o NAME,SIZE,MODEL | jq '[.blockdevices[] | select(.type=="disk") | {name: .name, size: (.size | tonumber / 1073741824 | floor | tostring + "G"), model: (.model // "Generic Disk")}]')

# Send POST request tilbage til FastAPI backend
curl -X POST "http://${SERVER_IP}:8000/api/baremetal/report-disks/${MAC}" \
     -H "Content-Type: application/json" \
     -d "$DISKS_JSON"

# Genstart/sluk maskinen efter rapportering
sleep 2
poweroff -f
EOF

chmod +x ~/portal/storage/discovery/discovery-script.sh
