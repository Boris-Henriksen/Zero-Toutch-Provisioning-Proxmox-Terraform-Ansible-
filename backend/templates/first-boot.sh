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

# Blev noden afbrudt med "Slet og start forfra" mens den installerede? Så slettes den nye
# installation igen, og noden venter på en ny discovery og genstarter selv ind i den.
# Kun et eksplicit svar fra portalen udløser dette - er portalen nede, fortsættes normalt.
ABORT_MAC="" ABORT_DISK=""
for attempt in $(seq 1 6); do
    reached=false
    for mac in $MACS; do
        resp=$(curl -fsS --max-time 10 "$PORTAL_URL/api/baremetal/abort-check/$mac" 2>/dev/null) || continue
        reached=true
        if echo "$resp" | grep -q '"abort": *true'; then
            ABORT_MAC=$mac
            ABORT_DISK=$(echo "$resp" | sed -n 's/.*"disk": *"\([a-zA-Z0-9]*\)".*/\1/p')
            break
        fi
    done
    [[ "$reached" == true ]] && break
    sleep 5
done

if [[ -n "$ABORT_MAC" ]]; then
    cat > /run/portal-abort.sh <<ABORT
#!/bin/bash
MSG="
==================================================================
   Installationen blev afbrudt fra portalen ('Slet og start forfra').

   Proxmox er slettet fra disken igen. Noden venter på en ny discovery:
   start 'Discovery Mode' i portalen med MAC $ABORT_MAC,
   så genstarter noden selv og rapporterer sin hardware.

   Sluk IKKE maskinen.
==================================================================
"
while true; do
    printf '%s\n' "\$MSG" > /dev/tty1 2>/dev/null
    action=\$(curl -fsS --max-time 10 "$PORTAL_URL/api/baremetal/next-action/$ABORT_MAC" 2>/dev/null)
    if echo "\$action" | grep -q '"report"'; then
        printf '\nNy discovery fundet - genstarter til netværksboot...\n' > /dev/tty1 2>/dev/null
        sync
        reboot -f
    fi
    sleep 10
done
ABORT
    chmod +x /run/portal-abort.sh

    disk_dev="/dev/$ABORT_DISK"
    if [[ -z "$ABORT_DISK" || ! -b "$disk_dev" ]]; then
        # Fallback: disken som rodfilsystemet ligger på.
        disk_dev="/dev/$(lsblk -nso NAME,TYPE "$(findmnt -no SOURCE /)" 2>/dev/null | awk '$2 == "disk" {print $1}' | head -n 1)"
    fi
    echo "==> Afbrudt fra portalen - sletter installationen på $disk_dev"
    if [[ -b "$disk_dev" ]]; then
        lsblk -lnpo NAME,TYPE "$disk_dev" | awk '$2 == "part" {print $1}' | while read -r part; do
            wipefs -af "$part" >/dev/null 2>&1
        done
        wipefs -af "$disk_dev" >/dev/null 2>&1
        sectors=$(blockdev --getsz "$disk_dev" 2>/dev/null || echo 0)
        dd if=/dev/zero of="$disk_dev" bs=1M count=16 conv=fsync status=none 2>/dev/null
        if [[ "$sectors" -gt 65536 ]]; then
            dd if=/dev/zero of="$disk_dev" bs=512 seek=$((sectors - 32768)) count=32768 conv=fsync status=none 2>/dev/null
        fi
    fi
    # Næste boot: netværkskortet, så noden ender i discovery når den genstarter.
    if command -v efibootmgr >/dev/null; then
        entry=$(efibootmgr -v 2>/dev/null | grep -i "MAC($(echo "$ABORT_MAC" | tr -d ':' | tr '[:lower:]' '[:upper:]')" | grep -iv IPv6 | head -n 1 | sed -n 's/^Boot\([0-9A-Fa-f]\{4\}\).*/\1/p')
        [[ -n "$entry" ]] && efibootmgr -n "$entry" >/dev/null 2>&1
    fi
    sync
    # Vent i baggrunden (uden for first-boot servicen, så den ikke rammer en timeout).
    systemd-run --no-block --unit=portal-abort-wait /bin/bash /run/portal-abort.sh \
        || (setsid /bin/bash /run/portal-abort.sh >/dev/null 2>&1 &)
    exit 0
fi

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

# ISO'en kan være ældre end de nyeste rettelser (f.eks. kunne libpve-storage-perl 9.1.5 ikke læse
# Ceph 20's aes256k-nøgler). Opdatér alt før Ceph sættes op; ny kerne aktiveres ved næste genstart.
echo "==> Opdaterer alle pakker (apt full-upgrade)"
apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold full-upgrade \
    || fail "apt full-upgrade fejlede"

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
