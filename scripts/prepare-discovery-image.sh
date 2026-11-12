#!/usr/bin/env bash
# Udtrækker vmlinuz/initrd fra en Ubuntu Server "live" ISO til brug for
# discovery-boot (hardware-scan af bare-metal noder).
#
# Disse filer er binære install-media og ligger derfor IKKE i Git.
# Kør dette script én gang pr. installation med en selvvalgt Ubuntu Server ISO:
#
#   sudo ./scripts/prepare-discovery-image.sh /sti/til/ubuntu-22.04-live-server-amd64.iso
#
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Dette script skal køres som root (sudo)." >&2
    exit 1
fi

if [[ $# -ne 1 ]]; then
    echo "Brug: sudo $0 /sti/til/ubuntu-live-server-amd64.iso" >&2
    exit 1
fi

ISO_PATH="$1"
if [[ ! -f "$ISO_PATH" ]]; then
    echo "ISO-filen findes ikke: $ISO_PATH" >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DISCOVERY_DIR="$REPO_DIR/storage/discovery"
MOUNT_POINT="/tmp/mnt_discovery_iso"

mkdir -p "$DISCOVERY_DIR" "$MOUNT_POINT"

echo "==> Monterer $ISO_PATH ..."
mount -o loop,ro "$ISO_PATH" "$MOUNT_POINT"

cleanup() {
    umount "$MOUNT_POINT" 2>/dev/null || true
}
trap cleanup EXIT

if [[ ! -f "$MOUNT_POINT/casper/vmlinuz" || ! -f "$MOUNT_POINT/casper/initrd" ]]; then
    echo "Fejl: $ISO_PATH ser ikke ud til at være en Ubuntu Server 'live' ISO (mangler casper/vmlinuz eller casper/initrd)." >&2
    exit 1
fi

if ! file "$MOUNT_POINT/casper/vmlinuz" | grep -Eqi 'x86-64|x86_64|amd64'; then
    echo "Fejl: Discovery-image skal være amd64/x86-64. Den valgte ISO indeholder ikke en x86-64 kernel." >&2
    exit 1
fi

echo "==> Kopierer casper/vmlinuz og casper/initrd til $DISCOVERY_DIR ..."
cp "$MOUNT_POINT/casper/vmlinuz" "$DISCOVERY_DIR/vmlinuz"
cp "$MOUNT_POINT/casper/initrd" "$DISCOVERY_DIR/initrd"

# casper henter selve live-rootfs'et fra ISO'en via url= ved netboot.
# Hardlink frem for kopi (sparer ~3 GB) når ISO'en ligger på samme filsystem, f.eks. storage/isos/ubuntu/.
echo "==> Lægger ISO'en som $DISCOVERY_DIR/ubuntu-live.iso (bruges som rootfs via HTTP) ..."
if [[ ! "$ISO_PATH" -ef "$DISCOVERY_DIR/ubuntu-live.iso" ]]; then
    ln -f "$ISO_PATH" "$DISCOVERY_DIR/ubuntu-live.iso" 2>/dev/null || cp "$ISO_PATH" "$DISCOVERY_DIR/ubuntu-live.iso"
fi
chmod 644 "$DISCOVERY_DIR/vmlinuz" "$DISCOVERY_DIR/initrd" "$DISCOVERY_DIR/ubuntu-live.iso"

if [[ -f "$DISCOVERY_DIR/discovery-script.sh" ]]; then
    chmod +x "$DISCOVERY_DIR/discovery-script.sh"
fi

echo "==> Færdig. Discovery-image er klar i $DISCOVERY_DIR"
basename "$ISO_PATH" > "$DISCOVERY_DIR/source.txt"
