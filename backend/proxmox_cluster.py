"""Opretter Proxmox-cluster og Ceph via Proxmox' REST API (ingen SSH/Ansible).

Køres i en baggrundstråd fra main.py, når alle noder har meldt at first-boot er færdig.
"""
import ipaddress
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Optional

# Proxmox bruger et selvsigneret certifikat lige efter installation.
_SSL_CONTEXT = ssl._create_unverified_context()


class ProxmoxError(Exception):
    pass


class ProxmoxAPI:
    def __init__(self, host: str, password: str, user: str = "root@pam"):
        self.base = f"https://{host}:8006/api2/json"
        self.host = host
        self.user = user
        self.password = password
        self.ticket: Optional[str] = None
        self.csrf: Optional[str] = None

    def _request(self, method: str, path: str, params: Optional[dict] = None, timeout: int = 120, auth: bool = True):
        url = self.base + path
        data = None
        if params:
            encoded = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if method == "GET":
                url += "?" + encoded
            else:
                data = encoded.encode()
        request = urllib.request.Request(url, data=data, method=method)
        if auth and self.ticket:
            request.add_header("Cookie", f"PVEAuthCookie={self.ticket}")
            if method != "GET":
                request.add_header("CSRFPreventionToken", self.csrf)
        try:
            with urllib.request.urlopen(request, context=_SSL_CONTEXT, timeout=timeout) as response:
                return json.loads(response.read() or b"{}").get("data")
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")
            raise ProxmoxError(f"{method} {path} på {self.host} fejlede ({error.code}): {error.reason} {body}".strip()) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as error:
            raise ProxmoxError(f"{method} {path} på {self.host}: {error}") from None

    def login(self):
        data = self._request("POST", "/access/ticket", {"username": self.user, "password": self.password}, auth=False)
        if not data or "ticket" not in data:
            raise ProxmoxError(f"Login på {self.host} fejlede")
        self.ticket = data["ticket"]
        self.csrf = data["CSRFPreventionToken"]

    def get(self, path, params=None, timeout=120):
        return self._request("GET", path, params, timeout)

    def post(self, path, params=None, timeout=300):
        return self._request("POST", path, params, timeout)

    def put(self, path, params=None, timeout=300):
        return self._request("PUT", path, params, timeout)

    def wait_task(self, node: str, upid, timeout: int = 1800):
        if not isinstance(upid, str) or not upid.startswith("UPID:"):
            return
        path = f"/nodes/{node}/tasks/{urllib.parse.quote(upid, safe='')}/status"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                status = self.get(path, timeout=30)
            except ProxmoxError:
                time.sleep(5)
                continue
            if status and status.get("status") == "stopped":
                if status.get("exitstatus") != "OK":
                    log = self.get(f"/nodes/{node}/tasks/{urllib.parse.quote(upid, safe='')}/log", {"limit": 20}) or []
                    tail = " | ".join(line.get("t", "") for line in log[-5:])
                    raise ProxmoxError(f"Task på {node} fejlede: {status.get('exitstatus')} {tail}")
                return
            time.sleep(3)
        raise ProxmoxError(f"Task på {node} tog for lang tid: {upid}")


def wait_for_api(host: str, password: str, timeout: int = 900) -> ProxmoxAPI:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        api = ProxmoxAPI(host, password)
        try:
            api.login()
            return api
        except ProxmoxError as error:
            last_error = error
            time.sleep(10)
    raise ProxmoxError(f"Proxmox API på {host} svarer ikke: {last_error}")


def ceph_public_network(nodes: list, prefix_length: int) -> str:
    return str(ipaddress.IPv4Interface(f"{nodes[0]['ip']}/{prefix_length}").network)


def build_cluster(session: dict, password: str, log: Callable[[str], None], set_node_status: Callable[[str, str, str], None]):
    nodes = session["nodes"]
    first = nodes[0]
    first_name = first["hostname"]

    log("Venter på at Proxmox API svarer på alle noder...")
    apis = {node["hostname"]: wait_for_api(node["ip"], password) for node in nodes}
    main_api = apis[first_name]

    # --- Proxmox cluster ---
    cluster_status = main_api.get("/cluster/status") or []
    if not any(entry.get("type") == "cluster" for entry in cluster_status):
        log(f"Opretter cluster '{session['cluster_name']}' på {first_name}...")
        upid = main_api.post("/cluster/config", {"clustername": session["cluster_name"]})
        main_api.wait_task(first_name, upid)
    set_node_status(first["mac_address"], "clustered", "I cluster")

    for node in nodes[1:]:
        members = {entry.get("name") for entry in (main_api.get("/cluster/status") or []) if entry.get("type") == "node"}
        if node["hostname"] not in members:
            log(f"Tilføjer {node['hostname']} til clusteret...")
            join_info = main_api.get("/cluster/config/join") or {}
            fingerprint = next(
                (entry.get("pve_fp") for entry in join_info.get("nodelist", []) if entry.get("name") == first_name),
                None,
            )
            if not fingerprint:
                raise ProxmoxError(f"Kunne ikke hente certifikat-fingerprint fra {first_name}")
            try:
                apis[node["hostname"]].post("/cluster/config/join", {
                    "hostname": first["ip"],
                    "password": password,
                    "fingerprint": fingerprint,
                    "link0": node["ip"],
                })
            except ProxmoxError as error:
                # pveproxy på den joinende node genstarter undervejs - forbindelsen kan blive afbrudt.
                log(f"(join-svar fra {node['hostname']}: {error})")

            deadline = time.time() + 600
            while time.time() < deadline:
                time.sleep(10)
                try:
                    members = {e.get("name") for e in (main_api.get("/cluster/status") or []) if e.get("type") == "node" and e.get("online")}
                except ProxmoxError:
                    continue
                if node["hostname"] in members:
                    break
            else:
                raise ProxmoxError(f"{node['hostname']} blev ikke online i clusteret")
        set_node_status(node["mac_address"], "clustered", "I cluster")

    # Ticket fra første node gælder i hele clusteret; /nodes/<navn>/... proxies til den rigtige node.
    main_api = wait_for_api(first["ip"], password)

    # --- Ceph ---
    ceph_nodes = [node for node in nodes if node.get("enable_ceph") and node.get("ceph_disks")]
    if not ceph_nodes:
        log("Cluster oprettet (ingen Ceph-noder valgt).")
        return

    c0 = ceph_nodes[0]["hostname"]
    network = ceph_public_network(nodes, session["network_prefix_length"])
    log(f"Initialiserer Ceph (public network {network})...")
    try:
        main_api.post(f"/nodes/{c0}/ceph/init", {"network": network})
    except ProxmoxError as error:
        if "already" not in str(error).lower() and "exist" not in str(error).lower():
            raise

    existing_mons = {mon.get("name") for mon in (main_api.get(f"/nodes/{c0}/ceph/mon") or [])}
    for node in ceph_nodes[:3]:
        name = node["hostname"]
        if name not in existing_mons:
            log(f"Opretter Ceph monitor på {name}...")
            main_api.wait_task(name, main_api.post(f"/nodes/{name}/ceph/mon/{name}"))
        try:
            log(f"Opretter Ceph manager på {name}...")
            main_api.wait_task(name, main_api.post(f"/nodes/{name}/ceph/mgr/{name}"))
        except ProxmoxError as error:
            if "already" not in str(error).lower() and "exist" not in str(error).lower():
                raise

    for node in ceph_nodes:
        name = node["hostname"]
        disks = main_api.get(f"/nodes/{name}/disks/list") or []
        serial_by_name = {d.get("name"): d.get("serial") for d in node.get("discovered_disks", [])}
        for disk_name in node["ceph_disks"]:
            # Find disken på Proxmox via serienummer hvis muligt (sdX-navne kan skifte mellem boots).
            wanted_serial = serial_by_name.get(disk_name)
            if wanted_serial:
                target = next((d for d in disks if d.get("serial") == wanted_serial), None)
                if not target:
                    # Gæt aldrig ud fra sdX-navnet når serienummeret er kendt - det kan ramme en forkert disk.
                    raise ProxmoxError(f"OSD-disk {disk_name} (serienr. {wanted_serial}) blev ikke fundet på {name}")
            else:
                target = next((d for d in disks if d.get("devpath") == f"/dev/{disk_name}"), None)
                if not target:
                    raise ProxmoxError(f"OSD-disk {disk_name} blev ikke fundet på {name}")
            osd_id = target.get("osdid")
            if osd_id is not None and int(osd_id) >= 0:
                log(f"{target['devpath']} på {name} er allerede en OSD - springer over.")
                continue
            log(f"Sletter og opretter OSD på {name}:{target['devpath']}...")
            main_api.wait_task(name, main_api.put(f"/nodes/{name}/disks/wipedisk", {"disk": target["devpath"]}))
            main_api.wait_task(name, main_api.post(f"/nodes/{name}/ceph/osd", {"dev": target["devpath"]}))

    pools = {pool.get("pool_name") for pool in (main_api.get(f"/nodes/{c0}/ceph/pool") or [])}
    if session["ceph_pool"] not in pools:
        log(f"Opretter Ceph pool '{session['ceph_pool']}' (size {session['ceph_size']}/{session['ceph_min_size']}) og tilføjer som storage...")
        main_api.wait_task(c0, main_api.post(f"/nodes/{c0}/ceph/pool", {
            "name": session["ceph_pool"],
            "size": session["ceph_size"],
            "min_size": session["ceph_min_size"],
            "application": "rbd",
            "pg_autoscale_mode": "on",
            "add_storages": 1,
        }))

    for node in ceph_nodes:
        set_node_status(node["mac_address"], "ceph_ready", "Cluster + Ceph klar")
    log("Cluster og Ceph er klar.")
