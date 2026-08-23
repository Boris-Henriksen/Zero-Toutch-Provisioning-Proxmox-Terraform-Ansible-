from fastapi import FastAPI, HTTPException, Response, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jinja2 import Environment, FileSystemLoader
from pathlib import Path
from typing import List, Optional
import json
import os
import re
import subprocess

# 1. Opret FastAPI app
app = FastAPI()

# 2. Definer Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ISO_DIR = STORAGE_DIR / "isos"
EXTRACTED_DIR = STORAGE_DIR / "extracted"
DISCOVERY_DIR = STORAGE_DIR / "discovery"
TFTP_DIR = STORAGE_DIR / "tftpboot"

# 3. Opret mapper på disken
ISO_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
TFTP_DIR.mkdir(parents=True, exist_ok=True)

# 4. Mount statiske routes
app.mount("/proxmox/discovery", StaticFiles(directory=DISCOVERY_DIR), name="discovery")
app.mount("/proxmox/extracted", StaticFiles(directory=EXTRACTED_DIR), name="extracted")

active_proxmox_version = None
dnsmasq_process = None


def normalize_mac(mac: str) -> str:
    compact_mac = mac.strip().lower().replace(":", "").replace("-", "")
    if len(compact_mac) != 12 or any(character not in "0123456789abcdef" for character in compact_mac):
        raise ValueError(f"Ugyldig MAC-adresse: {mac}")
    return ":".join(compact_mac[index:index + 2] for index in range(0, 12, 2))


def subnet_prefix_from_gateway(gateway: str) -> str:
    octets = gateway.strip().split(".")
    if len(octets) != 4 or not all(octet.isdigit() for octet in octets):
        raise ValueError(f"Ugyldig gateway-IP: {gateway}")
    return ".".join(octets[:3])


def detect_interface_subnet_prefix(interface: str) -> str:
    """Læser den faktisk konfigurerede IPv4 på NIC'et, så DHCP-poolen matcher det rigtige netværk."""
    result = subprocess.run(["ip", "-o", "-4", "addr", "show", "dev", interface], capture_output=True, text=True, check=False)
    match = re.search(r"inet (\d+\.\d+\.\d+)\.\d+/(\d+)", result.stdout)
    if not match:
        raise HTTPException(status_code=400, detail=f"Kunne ikke finde en IPv4-adresse på interface '{interface}'. Er kablet sat i, og er interfacet korrekt?")
    prefix, prefix_len = match.group(1), match.group(2)
    if prefix_len != "24":
        raise HTTPException(status_code=400, detail=f"Interface '{interface}' har et /{prefix_len}-netværk. Kun /24 understøttes i øjeblikket.")
    return prefix


# --- ISO Endpoint ---
@app.get("/api/proxmox/versions")
def list_proxmox_versions():
    iso_files = [f.name for f in ISO_DIR.glob("*.iso")]
    return {"status": "success", "versions": sorted(iso_files, reverse=True)}


# --- Step 1 Datamodeller & Endpoints ---
class DisksInfo(BaseModel):
    name: str        # f.eks. "nvme0n1" eller "sda"
    size: str        # f.eks. "500G"
    model: str       # f.eks. "SAMSUNG MZQL2960"

class BareMetalNode(BaseModel):
    hostname: str
    mac_address: str
    ip: str
    disk: str = "sda"
    enable_ceph: bool = False
    ceph_disks: List[str] = []
    discovered_disks: List[DisksInfo] = []

class Step1Data(BaseModel):
    interface: str = "eth0"
    gateway: str
    dns: str
    root_password: str
    selected_iso: str
    nodes: list[BareMetalNode]


@app.post("/api/baremetal/report-disks/{mac}")
def report_node_disks(mac: str, disks: List[DisksInfo]):
    """Endpoint kaldet af discovery-image for kun godkendte MAC-adresser"""
    try:
        nodes_file = Path("/tmp/portal_pxe/nodes.json")
        if not nodes_file.exists():
            raise HTTPException(status_code=400, detail="Ingen aktiv PXE-session fundet")

        with open(nodes_file, "r") as f:
            data = json.load(f)

        target_node = next((n for n in data["nodes"] if n["mac_address"].lower() == mac.lower()), None)
        if not target_node:
            raise HTTPException(status_code=403, detail="MAC-adresse ikke godkendt")

        target_node["discovered_disks"] = [d.model_dump() for d in disks]

        with open(nodes_file, "w") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "message": "Diske opdateret"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/baremetal/nodes")
def get_current_nodes():
    try:
        nodes_file = Path("/tmp/portal_pxe/nodes.json")
        if not nodes_file.exists():
            return {"nodes": []}
        with open(nodes_file, "r") as f:
            data = json.load(f)
        return {"nodes": data.get("nodes", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/baremetal/start")
def start_baremetal_provisioning(data: Step1Data):
    global dnsmasq_process, active_proxmox_version
    try:
        is_discovery = data.selected_iso == "discovery.iso"
        if is_discovery:
            if not (DISCOVERY_DIR / "vmlinuz").exists() or not (DISCOVERY_DIR / "initrd").exists():
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

        version_name = "discovery" if is_discovery else iso_path.stem
        target_extracted = EXTRACTED_DIR / version_name

        if not is_discovery and (not (target_extracted / "vmlinuz").exists() or not (target_extracted / "initrd.img").exists()):
            target_extracted.mkdir(parents=True, exist_ok=True)
            mount_point = Path("/tmp/mnt_iso")
            mount_point.mkdir(exist_ok=True)
            try:
                subprocess.run(["sudo", "mount", "-o", "loop", str(iso_path), str(mount_point)], check=True)
                subprocess.run(["sudo", "cp", str(mount_point / "boot" / "vmlinuz"), str(target_extracted / "vmlinuz")], check=True)
                subprocess.run(["sudo", "cp", str(mount_point / "boot" / "initrd.img"), str(target_extracted / "initrd.img")], check=True)
                subprocess.run(["sudo", "chmod", "-R", "755", str(target_extracted)], check=True)
            finally:
                subprocess.run(["sudo", "umount", str(mount_point)], check=False)

        active_proxmox_version = version_name

        if dnsmasq_process and dnsmasq_process.poll() is None:
            dnsmasq_process.terminate()

        subnet_prefix = detect_interface_subnet_prefix(data.interface)

        conf_lines = [
            f"interface={data.interface}",
            "bind-interfaces",
            f"dhcp-range={subnet_prefix}.200,{subnet_prefix}.250,255.255.255.0,1h",
            "dhcp-ignore=tag:!known\n"
        ]

        for index, node in enumerate(data.nodes):
            node.mac_address = normalize_mac(node.mac_address)
            if is_discovery:
                node.ip = f"{subnet_prefix}.{200 + index}"
            conf_lines.append(f"dhcp-host={node.mac_address},{node.hostname},{node.ip},set:known")

        conf_lines.extend([
            "\nenable-tftp",
            f"tftp-root={TFTP_DIR}",
            # Undgå boot-loop: klienter der allerede kører iPXE (identificeret via DHCP user-class)
            # skal videre til autoexec.ipxe i stedet for at hente ipxe.efi igen.
            "dhcp-userclass=set:ipxe,iPXE",
            "dhcp-boot=tag:ipxe,autoexec.ipxe",
            "dhcp-boot=tag:!ipxe,ipxe.efi"
        ])

        os.makedirs("/tmp/portal_pxe", exist_ok=True)
        with open("/tmp/portal_pxe/dnsmasq.conf", "w") as f:
            f.write("\n".join(conf_lines))

        with open("/tmp/portal_pxe/nodes.json", "w") as f:
            f.write(data.model_dump_json())

        dnsmasq_process = subprocess.Popen(
            ["sudo", "dnsmasq", "-C", "/tmp/portal_pxe/dnsmasq.conf", "-d"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        return {"status": "success", "message": f"PXE/DHCP startet for {len(data.nodes)} node(r) med {version_name}."}

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
def get_ipxe_script(request: Request):
    global active_proxmox_version
    host = request.headers.get("host", "10.20.10.2").split(":")[0]

    # Hvis "1. Start Discovery Mode" er valgt
    if active_proxmox_version == "discovery":
        ipxe_script = f"""#!ipxe

kernel http://{host}/proxmox/discovery/vmlinuz initrd=initrd ip=dhcp cloud-config-url=/dev/null ds=nocloud systemd.run="curl -s http://{host}/proxmox/discovery/discovery-script.sh | bash" quiet
initrd http://{host}/proxmox/discovery/initrd
boot
"""
        return Response(content=ipxe_script, media_type="text/plain")

    # Ellers boot den rigtige Proxmox Auto-Installer
    if not active_proxmox_version:
        raise HTTPException(status_code=400, detail="Ingen Proxmox version valgt.")

    ipxe_script = f"""#!ipxe

kernel http://{host}/proxmox/extracted/{active_proxmox_version}/vmlinuz initrd=initrd.img vga=788 boot=casper ro quiet proxmox-startauto-installer
initrd http://{host}/proxmox/extracted/{active_proxmox_version}/initrd.img
boot
"""
    return Response(content=ipxe_script, media_type="text/plain")

@app.get("/api/baremetal/answer/{mac}")
def get_answer_toml(mac: str):
    try:
        with open("/tmp/portal_pxe/nodes.json", "r") as f:
            data = json.load(f)

        target_node = next((n for n in data["nodes"] if n["mac_address"].lower() == mac.lower()), None)
        if not target_node:
            raise HTTPException(status_code=404, detail="Node ikke fundet")

        toml_content = f"""[global]
keyboard = "da"
country = "dk"
timezone = "Europe/Copenhagen"
root_password = "{data['root_password']}"
mailto = "admin@example.com"

[network]
source = "from-answer"
cidr = "{target_node['ip']}/24"
gateway = "{data['gateway']}"
dns = "{data['dns']}"

[disk-setup]
filesystem = "ext4"
disks = ["{target_node['disk']}"]
"""
        return Response(content=toml_content, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
