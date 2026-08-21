# Infrastruktur Portal

FastAPI-backend + Vite-frontend til zero-touch bare-metal provisioning (PXE/dnsmasq)
af Proxmox-noder, samt generering af Terraform/Ansible-config til VM'er.

Kun kildekoden ligger i dette repository. Alle binære/genererede filer (Python venv,
node_modules, ISO'er, udpakkede boot-images, ipxe.efi m.m.) hentes eller bygges af
`install.sh` ved installation - se `.gitignore`.

## Installation på en ny maskine (Debian/Ubuntu, arm64 eller amd64)

```bash
git clone <repo-url> portal
cd portal
sudo ./install.sh
```

`install.sh` gør følgende:

1. Installerer systempakker: `python3`, `nodejs`/`npm`, `dnsmasq`, `ipxe`, `nginx`.
2. Opretter et Python virtualenv (`venv/`) og installerer `backend/requirements.txt`.
3. Bygger frontend (`npm ci && npm run build` i `frontend/`).
4. Opretter `storage/{isos,extracted,discovery,tftpboot}` og kopierer `ipxe.efi`
   fra apt-pakken `ipxe`.
5. Deaktiverer systemets `dnsmasq.service` (portalen starter sin egen dnsmasq-proces
   pr. PXE-session).
6. Installerer og starter en systemd-service (`portal-backend.service`) der kører
   `uvicorn main:app` på port 8000.
7. Konfigurerer nginx til at servere frontend'en på port 80 og proxy'e
   `/api/`, `/proxmox/` og `/auto-installer.ipxe` videre til backend'en.

Efter installation er portalen tilgængelig på `http://<server-ip>/`.

## Efter installation

- Læg Proxmox ISO-filer i `storage/isos/` (de bliver automatisk listet i UI'et).
- Generér discovery boot-image (bruges til hardware-scan af nye noder):

  ```bash
  sudo ./scripts/prepare-discovery-image.sh /sti/til/ubuntu-live-server-amd64.iso
  ```

## Nyttige kommandoer

```bash
journalctl -u portal-backend -f   # backend-logs
systemctl status portal-backend
systemctl status nginx
```

## Sikkerhedsnote

`portal-backend.service` kører som `root`, fordi backend'en selv udfører
privilegerede operationer (mount af ISO-filer, samt DHCP/TFTP via `dnsmasq`
på port 67/69). Portalen bør derfor kun eksponeres på et internt/administrativt
netværk.
