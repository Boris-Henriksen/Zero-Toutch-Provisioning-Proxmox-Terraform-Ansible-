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
4. Opretter `storage/{isos/proxmox,isos/ubuntu,extracted,discovery,tftpboot}` og kopierer `ipxe.efi`
   (UEFI) og `undionly.kpxe` (legacy BIOS) fra apt-pakken `ipxe`. dnsmasq vælger
   automatisk den rigtige ud fra klientens arkitektur (DHCP option 93).
5. Deaktiverer systemets `dnsmasq.service` (portalen starter sin egen dnsmasq-proces
   pr. PXE-session).
6. Installerer og starter en systemd-service (`portal-backend.service`) der kører
   `uvicorn main:app` på port 8000.
7. Konfigurerer nginx til at servere frontend'en på port 80 og proxy'e
   `/api/`, `/proxmox/` og `/auto-installer.ipxe` videre til backend'en (uden
   størrelsesgrænse på uploads, så ISO-filer kan uploades fra setup-siden).

Efter installation er portalen tilgængelig på `http://<server-ip>/`.

## Efter installation

Åbn portalen. Mangler der ISO-filer, starter den på en **setup-side** (kan senere åbnes
via knappen *Setup / ISO-filer*). For hver fil kan man trække den ind / vælge den, eller
indsætte et download-link, så serveren selv henter den. En progress bar viser fremskridtet.

- **Proxmox VE ISO** gemmes i `storage/isos/proxmox/` - kun ISO'er herfra vises i
  portalens dropdown.
- **Ubuntu Server amd64 live ISO** gemmes i `storage/isos/ubuntu/`, hvorefter serveren
  automatisk kører `scripts/prepare-discovery-image.sh` (udpakker kernel/initrd og
  hardlinker ISO'en til `storage/discovery/ubuntu-live.iso`, som live-systemet henter sit
  rootfs fra over HTTP - kræver ~4 GB RAM på noden). ARM64 ISO'er afvises.

Filer kan stadig lægges ind manuelt (Proxmox i `storage/isos/proxmox/`, Ubuntu via
`sudo ./scripts/prepare-discovery-image.sh /sti/til/ubuntu-live-server-amd64.iso`).
ISO'er fra det gamle layout (direkte i `storage/isos/`) flyttes automatisk.

## Sådan virker provisioneringen (Step 1)

1. **Discovery:** Indtast nodernes MAC-adresser og tryk *Start Discovery*. Noderne PXE-booter
   Ubuntu live, rapporterer deres diske og venter (status vises på nodens skærm).
2. **Udfyld** hostname, statisk IP og OS-disk pr. node, samt de fælles felter (gateway, DNS,
   root password, domæne, e-mail, filsystem, samt tastatur/land/tidszone via søgbare dropdowns).
   Sæt evt. flueben i **Opret Cluster?** og vælg under hver node om den skal bruges i Ceph og
   hvilke OSD-diske (de slettes). *Start Proxmox Auto-Installation* er låst indtil alle noder
   har rapporteret klar, og manglende felter markeres med rødt når der trykkes.
3. **Start Proxmox Auto-Installation:** Portalen bygger en PXE-version af Proxmox ISO'en med
   `proxmox-auto-install-assistant prepare-iso --pxe` (ca. 2 min første gang, caches i
   `storage/extracted/<iso>-auto/`). Formularen låses (åbnes igen hvis en node fejler).
   Noder i discovery gør den valgte OS-disk ikke-bootbar, sætter næste boot til netværk
   (`efibootmgr`) og genstarter ind i installeren; slukkede noder skal blot tændes og
   PXE-bootes. Installeren henter sin svarfil fra `POST /api/baremetal/answer` (matcher på MAC).
   Fremskridt for hver node vises i boksen *Installationsstatus*.
4. Efter installationen melder noden sig via Proxmox' post-installation webhook og kører et
   **first-boot script** (`backend/templates/first-boot.sh`), der skifter til
   no-subscription repo, kører `apt full-upgrade` (så f.eks. `libpve-storage-perl` kan læse
   Ceph 20's nøgler) og installerer Ceph-pakkerne på Ceph-noder. Noderne PXE-booter
   ikke ind i installeren igen. PXE/DHCP stoppes automatisk når alle noder er installeret.
5. **Cluster & Ceph** oprettes automatisk via Proxmox' REST API (`backend/proxmox_cluster.py`)
   når alle noder er klar: cluster, join (venter på quorum og prøver igen ved fejl), Ceph init
   (public network beregnes ud fra nodernes IP/netmaske), monitorer/managers, OSD'er, pool og
   RBD-storage - som til sidst tjekkes aktiv på alle noder. Fejler noget, kan det køres igen
   fra UI'et (allerede oprettede dele springes over).

**Slet konfiguration og start forfra** stopper PXE/DHCP, sletter al konfiguration og afbryder
igangværende installationer: noder i discovery venter på en ny discovery, og noder der allerede
har skrevet Proxmox til disken sletter det igen ved første opstart (registreres i
`storage/aborted-nodes.json`). Færdige noder glemmes og kan rediscoveres ved at PXE-boote dem.

Session-data ligger i `/tmp/portal_pxe/` (`nodes.json`, `dnsmasq.log`); root password
gemmes separat i `secrets.json` med mode 0600.

**Frontend-ændringer:** nginx serverer en kopi i `/var/www/portal`, så efter
`npm run build` i `frontend/` skal den kopieres: `cp -a frontend/dist/. /var/www/portal/`
(eller kør `sudo ./install.sh` igen). Backend-ændringer kræver
`sudo systemctl restart portal-backend`.

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
