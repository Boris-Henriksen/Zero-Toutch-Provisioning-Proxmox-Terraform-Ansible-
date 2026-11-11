# Infrastruktur Portal

FastAPI-backend + Vite-frontend til zero-touch bare-metal provisioning (PXE/dnsmasq)
af Proxmox-noder, samt generering af Terraform/Ansible-config til VM'er.

Kun kildekoden ligger i dette repository. ISO'er og genererede boot-images ligger
ikke i Git - se `.gitignore`. De skal tilføjes eller genereres på hver ny maskine.

## Installation på en ny maskine (Debian/Ubuntu, arm64 eller amd64)

```bash
git clone <repo-url> portal
cd portal
sudo ./install.sh
```

`install.sh` gør følgende:

1. Installerer systempakker: `python3`, `nodejs`/`npm`, `dnsmasq`, `ipxe`, `nginx`, `xorriso`
   samt `proxmox-auto-install-assistant` (hentes fra Proxmox' pakkearkiv og SHA256-verificeres).
2. Opretter et Python virtualenv (`venv/`) og installerer `backend/requirements.txt`.
3. Bygger frontend (`npm ci && npm run build` i `frontend/`).
4. Opretter `storage/{isos,extracted,discovery,tftpboot}` og kopierer `ipxe.efi`
   (UEFI) og `undionly.kpxe` (legacy BIOS) fra apt-pakken `ipxe`. dnsmasq vælger
   automatisk den rigtige ud fra klientens arkitektur (DHCP option 93).
5. Deaktiverer systemets `dnsmasq.service` (portalen starter sin egen dnsmasq-proces
   pr. PXE-session).
6. Installerer og starter en systemd-service (`portal-backend.service`) der kører
   `uvicorn main:app` på port 8000.
7. Konfigurerer nginx til at servere frontend'en på port 80 og proxy'e
   `/api/`, `/proxmox/` og `/auto-installer.ipxe` videre til backend'en.

Efter installation er portalen tilgængelig på `http://<server-ip>/`.

## Efter installation

- Kopiér en Proxmox ISO til `storage/isos/` (den bliver automatisk listet i UI'et).
- Hent en Ubuntu Server **amd64/x86-64** live ISO, og generér discovery boot-image
   (bruges til hardware-scan af nye noder):

  ```bash
  sudo ./scripts/prepare-discovery-image.sh /sti/til/ubuntu-live-server-amd64.iso
  ```

   ARM64 ISO'er kan ikke bruges til de x86-64 bare-metal-servere og bliver afvist
   af scriptet. ISO'en kopieres også til `storage/discovery/ubuntu-live.iso`, da
   live-systemet henter sit rootfs derfra over HTTP (kræver ~4 GB RAM på noden).

## Sådan virker provisioneringen (Step 1)

1. **Discovery:** Indtast nodernes MAC-adresser og tryk *Start Discovery*. Noderne PXE-booter
   Ubuntu live, rapporterer deres diske og bliver derefter tændt og venter.
2. **Udfyld** hostname, statisk IP og OS-disk pr. node, samt de fælles felter (gateway, DNS,
   root password, domæne, e-mail, filsystem). Sæt evt. flueben i **Opret Cluster?** og vælg
   under hver node om den skal bruges i Ceph og hvilke OSD-diske (de slettes).
3. **Start Proxmox Auto-Installation:** Portalen bygger en PXE-version af Proxmox ISO'en med
   `proxmox-auto-install-assistant prepare-iso --pxe` (ca. 2 min første gang, caches i
   `storage/extracted/<iso>-auto/`). Noder i discovery genstarter selv ind i installeren;
   slukkede noder skal blot tændes. Installeren henter sin svarfil fra
   `POST /api/baremetal/answer` (matcher på MAC).
4. Efter installationen melder noden sig via Proxmox' post-installation webhook og kører et
   **first-boot script** (`backend/templates/first-boot.sh`), der skifter til
   no-subscription repo og installerer Ceph-pakkerne på Ceph-noder. Noderne PXE-booter
   ikke ind i installeren igen.
5. **Cluster & Ceph** oprettes automatisk via Proxmox' REST API (`backend/proxmox_cluster.py`)
   når alle noder er klar: cluster, join, Ceph init (public network beregnes ud fra
   nodernes IP/netmaske), monitorer/managers, OSD'er, pool og RBD-storage. Fejler noget,
   kan det køres igen fra UI'et (allerede oprettede dele springes over).

Session-data ligger i `/tmp/portal_pxe/` (`nodes.json`, `dnsmasq.log`); root password
gemmes separat i `secrets.json` med mode 0600.

## Nyttige kommandoer

```bash
journalctl -u portal-backend -f   # backend-logs
sudo cat /tmp/portal_pxe/dnsmasq.log   # DHCP/TFTP-log for PXE
systemctl status portal-backend
systemctl status nginx
```

## Sikkerhedsnote

`portal-backend.service` kører som `root`, fordi backend'en selv udfører
privilegerede operationer (mount af ISO-filer, samt DHCP/TFTP via `dnsmasq`
på port 67/69). Portalen bør derfor kun eksponeres på et internt/administrativt
netværk.
