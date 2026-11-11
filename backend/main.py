from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Optional
import ipaddress
import json
import os
import re
import shutil
import subprocess
import threading
import time

import proxmox_cluster

# 1. Opret FastAPI app
app = FastAPI()

# 2. Definer Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ISO_DIR = STORAGE_DIR / "isos"
EXTRACTED_DIR = STORAGE_DIR / "extracted"
DISCOVERY_DIR = STORAGE_DIR / "discovery"
TFTP_DIR = STORAGE_DIR / "tftpboot"
DISCOVERY_ISO_NAME = "ubuntu-live.iso"
# 3. Opret mapper på disken
ISO_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
TFTP_DIR.mkdir(parents=True, exist_ok=True)

# 4. Mount statiske routes
app.mount("/proxmox/discovery", StaticFiles(directory=DISCOVERY_DIR), name="discovery")
app.mount("/proxmox/extracted", StaticFiles(directory=EXTRACTED_DIR), name="extracted")

dnsmasq_process = None


def normalize_mac(mac: str) -> str:
    compact_mac = mac.strip().lower().replace(":", "").replace("-", "")
    if len(compact_mac) != 12 or any(character not in "0123456789abcdef" for character in compact_mac):
        raise ValueError(f"Ugyldig MAC-adresse: {mac}")
    return ":".join(compact_mac[index:index + 2] for index in range(0, 12, 2))


def detect_interface_network(interface: str, required_leases: int) -> tuple[str, str, str, str, int]:
    """Returns the local address, netmask, DHCP range, and prefix of the PXE NIC."""
    result = subprocess.run(["ip", "-o", "-4", "addr", "show", "dev", interface], capture_output=True, text=True, check=False)
    match = re.search(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", result.stdout)
    if not match:
        raise HTTPException(status_code=400, detail=f"Kunne ikke finde en IPv4-adresse på interface '{interface}'. Er kablet sat i, og er interfacet korrekt?")
    network_interface = ipaddress.IPv4Interface(match.group(1))
    network = network_interface.network
    first_host = int(network.network_address) + 1
    last_host = int(network.broadcast_address) - 1
    server_address = int(network_interface.ip)
    default_route = subprocess.run(
        ["ip", "route", "show", "default", "dev", interface], capture_output=True, text=True, check=False
    ).stdout
    gateway_match = re.search(r"via (\d+\.\d+\.\d+\.\d+)", default_route)
    reserved_addresses = {server_address}
    if gateway_match:
        reserved_addresses.add(int(ipaddress.IPv4Address(gateway_match.group(1))))

    pool_candidates = []
    candidate_start = None
    for address in range(first_host, last_host + 2):
        if address <= last_host and address not in reserved_addresses:
            candidate_start = address if candidate_start is None else candidate_start
            continue
        if candidate_start is not None:
            pool_candidates.append((candidate_start, address - 1))
            candidate_start = None

    pool_candidates.sort(key=lambda candidate: (candidate[0] <= server_address, -candidate[1] + candidate[0]))
    pool_start, pool_end = next(
        (candidate for candidate in pool_candidates if candidate[1] - candidate[0] + 1 >= required_leases),
        (None, None),
    )
    if pool_start is None:
        raise HTTPException(status_code=400, detail=f"Interface '{interface}' har ikke nok ledige IPv4-adresser til DHCP.")

    return (
        str(network_interface.ip),
        str(network.netmask),
        str(ipaddress.IPv4Address(pool_start)),
        str(ipaddress.IPv4Address(pool_end)),
        network.prefixlen,
    )


def resolve_pxe_interface(interface: Optional[str]) -> str:
    if interface:
        return interface
    result = subprocess.run(["ip", "-o", "-4", "addr", "show", "scope", "global", "up"], capture_output=True, text=True, check=False)
    interfaces = list(dict.fromkeys(re.findall(r"^\d+:\s+([^\s:]+)", result.stdout, re.MULTILINE)))
    if len(interfaces) != 1:
        raise HTTPException(status_code=400, detail="Kunne ikke vælge PXE-interface automatisk. Angiv præcis ét aktivt IPv4-interface.")
    return interfaces[0]


# --- ISO Endpoint ---
@app.get("/api/proxmox/versions")
def list_proxmox_versions():
    iso_files = [f.name for f in ISO_DIR.glob("*.iso")]
    return {"status": "success", "versions": sorted(iso_files, reverse=True)}


# --- Step 1 Datamodeller & Endpoints ---
SESSION_DIR = Path(os.environ.get("PORTAL_SESSION_DIR", "/tmp/portal_pxe"))
SESSION_FILE = SESSION_DIR / "nodes.json"
SECRETS_FILE = SESSION_DIR / "secrets.json"
session_lock = threading.RLock()
cluster_thread: Optional[threading.Thread] = None
prepare_thread: Optional[threading.Thread] = None

INSTALLED_STATES = {"installed", "ready", "clustered", "ceph_ready"}
# Kun noder i disse tilstande må få installeren/svarfilen - alt andet (inkl. "error") booter lokal disk.
INSTALLABLE_STATES = {"waiting_install", "install_requested", "installing"}
READY_STATES = {"ready", "clustered", "ceph_ready"}
KEYBOARDS = {"de", "de-ch", "dk", "en-gb", "en-us", "es", "fi", "fr", "fr-be", "fr-ca", "fr-ch", "hu", "is", "it",
             "jp", "lt", "mk", "nl", "no", "pl", "pt", "pt-br", "se", "si", "tr"}
HOSTNAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
DOMAIN_RE = re.compile(r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
MAC_RE = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})")


class DisksInfo(BaseModel):
    name: str        # f.eks. "nvme0n1" eller "sda"
    size: str        # f.eks. "500G"
    model: str       # f.eks. "SAMSUNG MZQL2960"
    serial: str = ""


class BareMetalNode(BaseModel):
    hostname: str
    mac_address: str
    ip: str
    disk: str = "sda"
    enable_ceph: bool = False
    ceph_disks: List[str] = []
    discovered_disks: List[DisksInfo] = []


class Step1Data(BaseModel):
    interface: Optional[str] = None
    gateway: str = ""
    dns: str = ""
    root_password: str = ""
    selected_iso: str
    domain: str = "lab.local"
    mailto: str = "admin@lab.local"
    filesystem: str = "ext4"
    keyboard: str = "dk"
    country: str = "dk"
    timezone: str = "Europe/Copenhagen"
    create_cluster: bool = False
    cluster_name: str = "pve-cluster"
    ceph_pool: str = "ceph-vm"
    ceph_size: int = 3
    ceph_min_size: int = 2
    nodes: list[BareMetalNode]


class FirstBootResult(BaseModel):
    ok: bool
    message: str = ""


def load_session() -> Optional[dict]:
    with session_lock:
        if not SESSION_FILE.exists():
            return None
        with open(SESSION_FILE) as f:
            return json.load(f)


def save_session(data: dict):
    with session_lock:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        tmp_file = SESSION_FILE.with_suffix(".tmp")
        with open(tmp_file, "w") as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(SESSION_FILE)


def load_password() -> str:
    try:
        with open(SECRETS_FILE) as f:
            return json.load(f).get("root_password", "")
    except FileNotFoundError:
        return ""


def save_password(password: str):
    # Root password holdes ude af nodes.json (som er læsbar for alle) og gemmes med mode 0600.
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(SECRETS_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"root_password": password}, f)
    os.chmod(SECRETS_FILE, 0o600)


def find_node(session: dict, macs) -> Optional[dict]:
    wanted = {m.lower() for m in macs}
    return next((n for n in session.get("nodes", []) if n["mac_address"].lower() in wanted), None)


def node_for_request(session: dict, mac: str, request: Request) -> Optional[dict]:
    """Find noden via MAC, eller via klientens IP (hver node har fast IP via dhcp-host) hvis MAC mangler."""
    node = find_node(session, [mac]) if mac else None
    if not node and request.client:
        node = next((n for n in session.get("nodes", []) if n.get("ip") == request.client.host), None)
    return node


def update_node(mac: str, **fields) -> Optional[dict]:
    with session_lock:
        session = load_session()
        if not session:
            return None
        node = find_node(session, [mac])
        if node:
            node.update(fields)
            save_session(session)
        return node


def update_session(**fields):
    with session_lock:
        session = load_session()
        if session:
            session.update(fields)
            save_session(session)


def update_cluster(**fields):
    with session_lock:
        session = load_session()
        if not session:
            return
        cluster = session.setdefault("cluster", {})
        if "log" in fields:
            cluster.setdefault("log", []).append(f"{time.strftime('%H:%M:%S')} {fields.pop('log')}")
            cluster["log"] = cluster["log"][-50:]
        cluster.update(fields)
        save_session(session)


def server_url(session: dict) -> str:
    return f"http://{session['server_address']}:8000"


def auto_installer_dir(version: str) -> Path:
    return EXTRACTED_DIR / f"{version}-auto"


def prepare_proxmox_installer(iso_path: Path, version: str, answer_url: str):
    """Laver PXE-filer (vmlinuz, initrd.img, proxmox.iso) med svarfil-URL indbygget via proxmox-auto-install-assistant."""
    target = auto_installer_dir(version)
    marker = target / "answer-url.txt"
    if marker.exists() and marker.read_text().strip() == answer_url and all(
        (target / name).exists() for name in ("vmlinuz", "initrd.img", "proxmox.iso")
    ):
        return
    if not shutil.which("proxmox-auto-install-assistant") or not shutil.which("xorriso"):
        raise RuntimeError("proxmox-auto-install-assistant/xorriso mangler - kør install.sh igen.")

    # Arbejdsmappen skal ligge på disk - /tmp er ofte en lille tmpfs, og ISO'en kopieres undervejs.
    work_dir = EXTRACTED_DIR / f".{version}-work"
    shutil.rmtree(work_dir, ignore_errors=True)
    (work_dir / "out").mkdir(parents=True)
    try:
        result = subprocess.run(
            ["proxmox-auto-install-assistant", "prepare-iso", str(iso_path),
             "--fetch-from", "http", "--url", answer_url, "--pxe",
             "--output", str(work_dir / "out"), "--tmp", str(work_dir)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"prepare-iso fejlede: {(result.stderr or result.stdout).strip()[-500:]}")
        out = work_dir / "out"
        prepared_iso = next(out.glob("*.iso"), None)
        if not (out / "vmlinuz").exists() or not (out / "initrd.img").exists() or not prepared_iso:
            raise RuntimeError("prepare-iso lavede ikke vmlinuz/initrd.img/iso.")
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        shutil.move(str(out / "vmlinuz"), target / "vmlinuz")
        shutil.move(str(out / "initrd.img"), target / "initrd.img")
        shutil.move(str(prepared_iso), target / "proxmox.iso")
        for path in target.iterdir():
            path.chmod(0o644)
        marker.write_text(answer_url)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_prepare(iso_path: Path, version: str, answer_url: str):
    try:
        prepare_proxmox_installer(iso_path, version, answer_url)
        update_session(phase="installing", phase_message="Proxmox installer klar - noderne genstarter og installerer.")
    except Exception as error:
        update_session(phase="error", phase_message=f"Kunne ikke forberede Proxmox installer: {error}")


def run_cluster_build():
    session = load_session()
    password = load_password()
    update_cluster(status="running", message="Opretter cluster...", log="Starter cluster-opsætning")
    try:
        proxmox_cluster.build_cluster(
            session,
            password,
            log=lambda message: update_cluster(message=message, log=message),
            set_node_status=lambda mac, status, message: update_node(mac, status=status, status_message=message),
        )
        with_ceph = any(n.get("enable_ceph") for n in session["nodes"])
        update_cluster(status="done", message="Cluster og Ceph er klar." if with_ceph else "Cluster er klar.", log="Færdig")
    except Exception as error:
        update_cluster(status="error", message=f"Fejl: {error}", log=f"Fejl: {error}")


def maybe_start_cluster_build(force: bool = False):
    global cluster_thread
    with session_lock:
        session = load_session()
        if not session or not session.get("create_cluster"):
            return
        if cluster_thread and cluster_thread.is_alive():
            return
        if session.get("cluster", {}).get("status") in ("running", "done") and not force:
            return
        if not all(node.get("status") in READY_STATES for node in session["nodes"]):
            return
        update_cluster(status="running", message="Starter...")
        cluster_thread = threading.Thread(target=run_cluster_build, daemon=True)
        cluster_thread.start()


def validate_install(data: Step1Data, server_address: str, prefix_len: int, previous: dict):
    errors = []
    network = ipaddress.IPv4Interface(f"{server_address}/{prefix_len}").network
    if len(data.root_password) < 8:
        errors.append("Root password skal være mindst 8 tegn.")
    for label, value in (("Gateway", data.gateway), ("DNS", data.dns)):
        try:
            ipaddress.IPv4Address(value)
        except ValueError:
            errors.append(f"{label} er ikke en gyldig IPv4-adresse.")
    if not DOMAIN_RE.match(data.domain or ""):
        errors.append("Domæne skal være f.eks. 'lab.local'.")
    if "@" not in data.mailto:
        errors.append("Admin e-mail er ugyldig.")
    if data.filesystem not in ("ext4", "xfs", "zfs"):
        errors.append("Filsystem skal være ext4, xfs eller zfs.")
    if data.keyboard not in KEYBOARDS:
        errors.append(f"Ukendt tastaturlayout '{data.keyboard}'.")
    if not re.fullmatch(r"[a-z]{2}", data.country or ""):
        errors.append("Land skal være en 2-bogstavs kode, f.eks. 'dk'.")
    if not re.fullmatch(r"[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+)*", data.timezone or ""):
        errors.append("Tidszone skal være f.eks. 'Europe/Copenhagen'.")

    hostnames, ips = set(), set()
    for node in data.nodes:
        prev = previous.get(node.mac_address, {})
        disk_names = {d["name"] for d in prev.get("discovered_disks", [])}
        if not HOSTNAME_RE.match(node.hostname or ""):
            errors.append(f"{node.mac_address}: ugyldigt hostname '{node.hostname}' (kun a-z, 0-9 og '-').")
        if node.hostname in hostnames:
            errors.append(f"Hostname '{node.hostname}' er brugt flere gange.")
        hostnames.add(node.hostname)
        try:
            address = ipaddress.IPv4Address(node.ip)
            if address not in network or address in (network.network_address, network.broadcast_address):
                errors.append(f"{node.hostname}: IP {node.ip} skal ligge i PXE-netværket {network}.")
            if node.ip in (server_address, data.gateway):
                errors.append(f"{node.hostname}: IP {node.ip} er allerede brugt af automation-serveren/gateway.")
        except ValueError:
            errors.append(f"{node.hostname}: '{node.ip}' er ikke en gyldig IP.")
        if node.ip in ips:
            errors.append(f"IP {node.ip} er brugt flere gange.")
        ips.add(node.ip)
        if not disk_names:
            errors.append(f"{node.hostname}: discovery er ikke færdig for {node.mac_address}.")
        elif node.disk not in disk_names:
            errors.append(f"{node.hostname}: OS-disk '{node.disk}' blev ikke fundet ved discovery.")
        if node.enable_ceph:
            if not data.create_cluster:
                errors.append("Ceph kræver at 'Opret Cluster' er slået til.")
            if not node.ceph_disks:
                errors.append(f"{node.hostname}: vælg mindst én OSD-disk til Ceph.")
            if node.disk in node.ceph_disks:
                errors.append(f"{node.hostname}: OS-disken kan ikke også bruges som OSD-disk.")
            if len(set(node.ceph_disks)) != len(node.ceph_disks):
                errors.append(f"{node.hostname}: samme OSD-disk er valgt flere gange.")
            if disk_names and not set(node.ceph_disks) <= disk_names:
                errors.append(f"{node.hostname}: en OSD-disk blev ikke fundet ved discovery.")

    if data.create_cluster:
        if not re.fullmatch(r"[A-Za-z0-9-]{1,15}", data.cluster_name or ""):
            errors.append("Clusternavn må kun indeholde bogstaver, tal og '-' (max 15 tegn).")
        ceph_count = sum(1 for node in data.nodes if node.enable_ceph)
        if ceph_count:
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", data.ceph_pool or ""):
                errors.append("Ugyldigt Ceph pool-navn.")
            if not 1 <= data.ceph_size <= ceph_count:
                errors.append(f"Replika size ({data.ceph_size}) skal være mellem 1 og antal Ceph-noder ({ceph_count}).")
            if not 1 <= data.ceph_min_size <= data.ceph_size:
                errors.append("Replika min_size skal være mellem 1 og size.")
    if errors:
        raise HTTPException(status_code=400, detail="\n".join(errors))


@app.post("/api/baremetal/report-disks/{mac}")
def report_node_disks(mac: str, disks: List[DisksInfo]):
    """Endpoint kaldet af discovery-image for kun godkendte MAC-adresser"""
    with session_lock:
        session = load_session()
        if not session:
            raise HTTPException(status_code=400, detail="Ingen aktiv PXE-session fundet")
        node = find_node(session, [mac])
        if not node:
            raise HTTPException(status_code=403, detail="MAC-adresse ikke godkendt")
        node["discovered_disks"] = [d.model_dump() for d in disks]
        if node.get("status") not in INSTALLED_STATES:
            node["status"] = "discovered"
            node["status_message"] = f"{len(disks)} diske fundet - venter på installation"
        save_session(session)
    return {"status": "success", "message": "Diske opdateret"}


@app.get("/api/baremetal/next-action/{mac}")
def next_action(mac: str):
    """Discovery-imaget poller her efter disk-rapporten. 'install' = genstart ind i Proxmox installeren."""
    with session_lock:
        session = load_session()
        node = find_node(session, [mac]) if session else None
        if not node:
            return {"action": "wait"}
        if session.get("mode") == "install" and session.get("phase") == "installing" and node.get("status") in ("waiting_install", "install_requested"):
            node["status"] = "install_requested"
            node["status_message"] = "Genstarter til Proxmox installation"
            save_session(session)
            return {"action": "install"}
    return {"action": "wait"}


@app.get("/api/baremetal/nodes")
def get_current_nodes():
    session = load_session()
    if not session:
        return {"nodes": []}
    return {
        "nodes": session.get("nodes", []),
        "mode": session.get("mode"),
        "phase": session.get("phase"),
        "phase_message": session.get("phase_message", ""),
        "create_cluster": session.get("create_cluster", False),
        "cluster": session.get("cluster", {}),
    }


@app.post("/api/baremetal/start")
def start_baremetal_provisioning(data: Step1Data):
    global dnsmasq_process, prepare_thread
    try:
        data.interface = resolve_pxe_interface(data.interface)
        is_discovery = data.selected_iso == "discovery.iso"
        missing_boot_files = [name for name in ("ipxe.efi", "undionly.kpxe") if not (TFTP_DIR / name).exists()]
        if missing_boot_files:
            raise HTTPException(status_code=400, detail=f"PXE-bootfiler mangler i {TFTP_DIR}: {', '.join(missing_boot_files)}. Kør install.sh igen.")
        if is_discovery:
            if not all((DISCOVERY_DIR / name).exists() for name in ("vmlinuz", "initrd", DISCOVERY_ISO_NAME)):
                raise HTTPException(status_code=400, detail="Discovery-image mangler: kør prepare-discovery-image.sh først.")
            kernel_description = subprocess.run(
                ["file", str(DISCOVERY_DIR / "vmlinuz")], capture_output=True, text=True, check=False
            ).stdout.lower()
            if not any(architecture in kernel_description for architecture in ("x86-64", "x86_64", "amd64")):
                raise HTTPException(status_code=400, detail="Discovery-image er ikke amd64/x86-64. Brug en Ubuntu Server amd64 ISO.")
        else:
            iso_path = ISO_DIR / data.selected_iso
            if not iso_path.exists():
                raise HTTPException(status_code=404, detail=f"ISO filen {data.selected_iso} blev ikke fundet.")
            if prepare_thread and prepare_thread.is_alive():
                raise HTTPException(status_code=409, detail="Proxmox installeren er allerede ved at blive forberedt - vent lidt.")

        server_address, netmask, pool_start, pool_end, prefix_len = detect_interface_network(data.interface, len(data.nodes))

        for node in data.nodes:
            node.mac_address = normalize_mac(node.mac_address)
        previous_session = load_session() or {}
        previous = {n["mac_address"]: n for n in previous_session.get("nodes", [])}

        if not is_discovery:
            validate_install(data, server_address, prefix_len, previous)

        conf_lines = [
            # Bliv root, så TFTP kan læse filer under f.eks. /home/<bruger> (mode 0750).
            "user=root",
            f"interface={data.interface}",
            "bind-interfaces",
            f"dhcp-range={pool_start},{pool_end},{netmask},1h",
            "dhcp-ignore=tag:!known",
        ]
        if data.gateway:
            conf_lines.append(f"dhcp-option=option:router,{data.gateway}")
        if data.dns:
            conf_lines.append(f"dhcp-option=option:dns-server,{data.dns}")
        conf_lines.append("")

        session_nodes = []
        for index, node in enumerate(data.nodes):
            prev = previous.get(node.mac_address, {})
            if is_discovery:
                node.ip = str(ipaddress.IPv4Address(int(ipaddress.IPv4Address(pool_start)) + index))
            node_dict = node.model_dump()
            # Behold diske fundet ved discovery - frontend sender dem ikke med.
            node_dict["discovered_disks"] = prev.get("discovered_disks") or node_dict["discovered_disks"]
            if is_discovery:
                node_dict["status"] = "discovered" if node_dict["discovered_disks"] else "waiting_discovery"
                node_dict["status_message"] = "Diske fundet" if node_dict["discovered_disks"] else "Afventer discovery"
            else:
                node_dict["status"] = "waiting_install"
                node_dict["status_message"] = "Afventer genstart til installation"
            session_nodes.append(node_dict)
            conf_lines.append(f"dhcp-host={node.mac_address},{node.hostname},{node.ip},set:known")

        conf_lines.extend([
            "",
            "enable-tftp",
            f"tftp-root={TFTP_DIR}",
            # Undgå boot-loop: klienter der allerede kører iPXE (identificeret via DHCP user-class)
            # henter scriptet direkte over lokal HTTP og prøver derfor ikke net0 igen.
            "dhcp-userclass=set:ipxe,iPXE",
            # Option 93 (client-arch): 7/9 = UEFI x86-64, alt andet behandles som legacy BIOS.
            "dhcp-match=set:efi64,option:client-arch,7",
            "dhcp-match=set:efi64,option:client-arch,9",
            f"dhcp-boot=tag:ipxe,http://{server_address}:8000/auto-installer.ipxe",
            "dhcp-boot=tag:!ipxe,tag:efi64,ipxe.efi",
            "dhcp-boot=tag:!ipxe,tag:!efi64,undionly.kpxe"
        ])

        version_name = "discovery" if is_discovery else Path(data.selected_iso).stem
        session_data = data.model_dump(exclude={"root_password", "nodes"})
        session_data.update({
            "nodes": session_nodes,
            "network_prefix_length": prefix_len,
            "server_address": server_address,
            "mode": "discovery" if is_discovery else "install",
            "version": version_name,
            "phase": "discovery" if is_discovery else "preparing",
            "phase_message": "Discovery kører" if is_discovery else "Forbereder Proxmox installer (ca. 2 min første gang)...",
            "cluster": {"status": "pending" if data.create_cluster else "disabled", "message": "", "log": []},
        })

        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        save_session(session_data)
        if not is_discovery:
            save_password(data.root_password)

        if dnsmasq_process and dnsmasq_process.poll() is None:
            dnsmasq_process.terminate()
            dnsmasq_process.wait(timeout=10)

        with open(SESSION_DIR / "dnsmasq.conf", "w") as f:
            f.write("\n".join(conf_lines))

        # Log til fil i stedet for en pipe, der aldrig læses (fyldt pipe = dnsmasq hænger).
        dnsmasq_log = open(SESSION_DIR / "dnsmasq.log", "ab")
        dnsmasq_process = subprocess.Popen(
            ["sudo", "dnsmasq", "-C", str(SESSION_DIR / "dnsmasq.conf"), "-d"],
            stdout=dnsmasq_log,
            stderr=subprocess.STDOUT
        )
        dnsmasq_log.close()

        if not is_discovery:
            answer_url = f"http://{server_address}:8000/api/baremetal/answer"
            prepare_thread = threading.Thread(target=run_prepare, args=(iso_path, version_name, answer_url), daemon=True)
            prepare_thread.start()
            return {"status": "success", "message": f"Proxmox installation startet for {len(data.nodes)} node(r). Installeren forberedes nu - noder i discovery genstarter automatisk, slukkede noder skal blot tændes."}

        return {"status": "success", "message": f"PXE/DHCP startet for {len(data.nodes)} node(r) med discovery."}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/baremetal/stop")
def stop_baremetal():
    global dnsmasq_process
    if dnsmasq_process and dnsmasq_process.poll() is None:
        dnsmasq_process.terminate()
        dnsmasq_process = None
        return {"status": "stopped", "message": "PXE/DHCP stoppet - netværk er rent."}
    return {"status": "not_running"}


@app.get("/auto-installer.ipxe")
def get_ipxe_script(request: Request, mac: str = ""):
    host = request.headers.get("host", "").split(":")[0]
    if not host:
        raise HTTPException(status_code=400, detail="Mangler Host-header til iPXE-scriptet.")
    session = load_session()
    if not session:
        raise HTTPException(status_code=400, detail="Ingen aktiv PXE-session.")
    node = node_for_request(session, mac, request)

    if session.get("mode") == "discovery":
        # systemd.run kører uden shell, så pipe'en pakkes ind i bash -c. casper kræver boot=casper + url= til rootfs.
        ipxe_script = f"""#!ipxe

kernel http://{host}:8000/proxmox/discovery/vmlinuz initrd=initrd boot=casper ip=dhcp url=http://{host}:8000/proxmox/discovery/{DISCOVERY_ISO_NAME} cloud-config-url=/dev/null ds=nocloud portal.server=http://{host}:8000 systemd.run="/bin/bash -c 'curl -fsSL http://{host}:8000/proxmox/discovery/discovery-script.sh | bash'" quiet
initrd http://{host}:8000/proxmox/discovery/initrd
boot
"""
        return Response(content=ipxe_script, media_type="text/plain")

    # Allerede installeret, ukendt node, fejl - eller installeren har allerede hentet sin svarfil
    # (så webhook'en kan være gået tabt): boot lokal disk i stedet for at risikere geninstallation.
    if not node or node.get("status") not in INSTALLABLE_STATES or node.get("answer_served"):
        return Response(content="#!ipxe\necho Ingen installation til denne node - booter fra lokal disk\nsleep 3\nexit\n", media_type="text/plain")

    if session.get("phase") != "installing":
        retry_url = f"http://{host}:8000/auto-installer.ipxe?mac=${{netX/mac}}"
        return Response(
            content=f"#!ipxe\necho Venter paa at Proxmox installeren bliver klar...\nsleep 15\nchain {retry_url}\n",
            media_type="text/plain",
        )

    base = f"http://{host}:8000/proxmox/extracted/{session['version']}-auto"
    if node:
        update_node(node["mac_address"], status="installing", status_message="Henter Proxmox installer")
    # Parametre fra 'prepare-iso --pxe-loader ipxe'; ISO'en indlæses som ekstra initrd med navnet proxmox.iso.
    ipxe_script = f"""#!ipxe

kernel {base}/vmlinuz ramdisk_size=16777216 rw quiet initrd=initrd.img splash=silent proxmox-start-auto-installer
initrd {base}/initrd.img
initrd {base}/proxmox.iso proxmox.iso
boot
"""
    return Response(content=ipxe_script, media_type="text/plain")


def build_answer_toml(session: dict, node: dict, password: str) -> str:
    q = json.dumps  # JSON-strenge er gyldige TOML basic strings
    base_url = server_url(session)
    mac_compact = node["mac_address"].replace(":", "")
    disk_setup = f'filesystem = {q(session["filesystem"])}\ndisk-list = [{q(node["disk"])}]'
    if session["filesystem"] == "zfs":
        disk_setup += '\nzfs.raid = "raid0"'
    return f"""[global]
keyboard = {q(session["keyboard"])}
country = {q(session["country"])}
fqdn = {q(node["hostname"] + "." + session["domain"])}
mailto = {q(session["mailto"])}
timezone = {q(session["timezone"])}
root-password = {q(password)}

[network]
source = "from-answer"
cidr = {q(node["ip"] + "/" + str(session["network_prefix_length"]))}
gateway = {q(session["gateway"])}
dns = {q(session["dns"])}
filter.ID_NET_NAME_MAC = {q("*" + mac_compact)}

[disk-setup]
{disk_setup}

[post-installation-webhook]
url = {q(base_url + "/api/baremetal/installed")}

[first-boot]
source = "from-url"
ordering = "network-online"
url = {q(base_url + "/api/baremetal/first-boot.sh")}
"""


@app.post("/api/baremetal/answer")
async def get_answer_toml(request: Request):
    """Kaldes af Proxmox' auto-installer (HTTP POST med system-info inkl. MAC-adresser)."""
    try:
        system_info = await request.json()
    except Exception:
        system_info = {}
    macs = [iface.get("mac", "") for iface in system_info.get("network_interfaces", []) if isinstance(iface, dict)]
    session = load_session()
    node = find_node(session, macs) if session and session.get("mode") == "install" else None
    if not node:
        raise HTTPException(status_code=404, detail=f"Ingen node matcher MAC-adresserne {macs}")
    if node.get("status") not in INSTALLABLE_STATES:
        raise HTTPException(status_code=409, detail=f"{node['hostname']} skal ikke installeres (status: {node.get('status')}).")
    toml_content = build_answer_toml(session, node, load_password())
    update_node(node["mac_address"], status="installing", status_message="Installerer Proxmox...", answer_served=True)
    return Response(content=toml_content, media_type="text/plain")


@app.post("/api/baremetal/installed")
async def installation_finished(request: Request):
    """Proxmox' post-installation webhook."""
    payload = (await request.body()).decode(errors="replace").lower()
    session = load_session()
    node = find_node(session, set(MAC_RE.findall(payload))) if session else None
    if not node:
        raise HTTPException(status_code=404, detail="Ukendt node")
    update_node(node["mac_address"], status="installed", status_message="Proxmox installeret - første opstart")
    return {"status": "ok"}


@app.get("/api/baremetal/first-boot.sh")
def first_boot_script():
    session = load_session()
    if not session:
        raise HTTPException(status_code=400, detail="Ingen aktiv PXE-session.")
    script = (BASE_DIR / "backend" / "templates" / "first-boot.sh").read_text().replace("__PORTAL_URL__", server_url(session))
    return Response(content=script, media_type="text/plain")


@app.get("/api/baremetal/first-boot-config/{mac}")
def first_boot_config(mac: str):
    session = load_session()
    node = find_node(session, [mac]) if session else None
    if not node:
        raise HTTPException(status_code=404, detail="Ukendt node")
    return {"install_ceph": bool(session.get("create_cluster") and node.get("enable_ceph"))}


@app.post("/api/baremetal/first-boot-done/{mac}")
def first_boot_done(mac: str, result: FirstBootResult):
    if result.ok:
        node = update_node(mac, status="ready", status_message=result.message or "Klar")
    else:
        node = update_node(mac, status="error", status_message=f"First-boot fejlede: {result.message}")
    if not node:
        raise HTTPException(status_code=404, detail="Ukendt node")
    maybe_start_cluster_build()
    return {"status": "ok"}


@app.post("/api/baremetal/cluster/retry")
def retry_cluster():
    session = load_session()
    if not session or not session.get("create_cluster"):
        raise HTTPException(status_code=400, detail="Ingen cluster-opsætning i denne session.")
    if not all(node.get("status") in READY_STATES for node in session["nodes"]):
        raise HTTPException(status_code=400, detail="Alle noder skal være installeret og klar før cluster kan oprettes.")
    maybe_start_cluster_build(force=True)
    return {"status": "started", "message": "Cluster-opsætning startet igen."}


# --- Step 2 Datamodeller & Endpoints (Med SSH Keys support) ---
class VMInput(BaseModel):
    key: str
    name: str
    node: str
    cores: int
    sockets: int = 1
    memory: int
    disk: int

class RequestData(BaseModel):
    proxmox_api_ip: str
    subnet_prefix: str
    start_ip: int = 101
    ssh_keys: List[str] = []
    vms: list[VMInput]

@app.post("/api/generate")
def generate_config(data: RequestData):
    try:
        prepared_vms = []
        current_ip_host = data.start_ip

        for vm in data.vms:
            vm_dict = vm.model_dump()
            vm_dict["ip_host"] = str(current_ip_host)
            vm_dict["full_ip"] = f"{data.subnet_prefix}.{current_ip_host}"
            prepared_vms.append(vm_dict)
            current_ip_host += 1

        env = Environment(loader=FileSystemLoader("backend/templates"))
        template = env.get_template("cluster.tf.j2")
        rendered_tf = template.render(
            proxmox_api_ip=data.proxmox_api_ip,
            vms=prepared_vms,
            subnet_prefix=data.subnet_prefix,
            ssh_keys=data.ssh_keys
        )

        os.makedirs("terraform", exist_ok=True)
        os.makedirs("ansible/group_vars", exist_ok=True)

        with open("terraform/main.tf", "w") as f:
            f.write(rendered_tf)

        with open("ansible/group_vars/all.json", "w") as f:
            json.dump({
                "proxmox_api_ip": data.proxmox_api_ip,
                "subnet_prefix": data.subnet_prefix,
                "ssh_keys": data.ssh_keys,
                "vms": prepared_vms
            }, f, indent=2)

        return {"status": "success", "count": len(prepared_vms)}

    except Exception as e:
        print(f"Fejl under generering: {e}")
        raise HTTPException(status_code=500, detail=str(e))
