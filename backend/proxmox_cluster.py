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


def verify_storage_active(apis: dict, nodes: list, storage: str, log: Callable[[str], None], timeout: int = 120):
    """Ceph kan være sund selvom Proxmox' storage-lag ikke kan bruge poolen (f.eks. gammel libpve-storage-perl)."""
    log(f"Tjekker at storage '{storage}' er aktiv på alle noder...")
    pending = {node["hostname"] for node in nodes}
    errors = {}
    deadline = time.time() + timeout
    while pending and time.time() < deadline:
        for name in sorted(pending):
            try:
                status = apis[name].get(f"/nodes/{name}/storage/{storage}/status", timeout=30) or {}
                if status.get("active"):
                    pending.discard(name)
                    continue
                errors[name] = "storage er ikke aktiv"
            except ProxmoxError as error:
                errors[name] = str(error)[-200:]
        if pending:
            time.sleep(10)
    if pending:
        details = "; ".join(f"{name}: {errors.get(name, 'ukendt')}" for name in sorted(pending))
        raise ProxmoxError(f"Ceph er oprettet, men storage '{storage}' er ikke aktiv på {details}. "
                           "Tjek 'pvesm status' og at libpve-storage-perl er opdateret på noden.")


def ceph_public_network(nodes: list, prefix_length: int) -> str:
    return str(ipaddress.IPv4Interface(f"{nodes[0]['ip']}/{prefix_length}").network)


def wait_for_quorum(api: ProxmoxAPI, node_name: str, log: Callable[[str], None], timeout: int = 180):
    """Et nyt cluster (eller lige efter et join) har ikke quorum med det samme - joins før det fejler."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status = api.get("/cluster/status", timeout=30) or []
            if any(e.get("type") == "cluster" and e.get("quorate") for e in status):
                return
        except ProxmoxError:
            pass
        time.sleep(5)
    raise ProxmoxError(f"Clusteret på {node_name} fik ikke quorum inden for {timeout} sekunder")


def online_members(api: ProxmoxAPI) -> set:
    return {e.get("name") for e in (api.get("/cluster/status", timeout=30) or []) if e.get("type") == "node" and e.get("online")}


def join_node(main_api: ProxmoxAPI, node_api: ProxmoxAPI, first: dict, node: dict, password: str,
              log: Callable[[str], None], attempts: int = 3):
    """Join via noden's API og følg join-tasken, så en fejl vises med Proxmox' egen besked."""
    name = node["hostname"]
    last_error = ""
    for attempt in range(1, attempts + 1):
        log(f"Tilføjer {name} til clusteret (forsøg {attempt}/{attempts})...")
        join_info = main_api.get("/cluster/config/join") or {}
        fingerprint = next(
            (e.get("pve_fp") for e in join_info.get("nodelist", []) if e.get("name") == first["hostname"]),
            None,
        )
        if not fingerprint:
            raise ProxmoxError(f"Kunne ikke hente certifikat-fingerprint fra {first['hostname']}")

        upid = None
        try:
            upid = node_api.post("/cluster/config/join", {
                "hostname": first["ip"],
                "password": password,
                "fingerprint": fingerprint,
                "link0": node["ip"],
            })
        except ProxmoxError as error:
            # pveproxy på den joinende node genstarter undervejs - forbindelsen kan blive afbrudt.
            log(f"(join-svar fra {name}: {error})")
            if "already" in str(error).lower() or "exists" in str(error).lower():
                raise ProxmoxError(f"{name} kan ikke joine: {error}") from None

        deadline = time.time() + 600
        while time.time() < deadline:
            time.sleep(10)
            try:
                if name in online_members(main_api):
                    log(f"{name} er med i clusteret")
                    return
            except ProxmoxError:
                pass
            if not isinstance(upid, str):
                continue
            # Efter et (delvist) join skifter nodens auth-nøgle - log ind igen hvis billetten er ugyldig.
            task_path = f"/nodes/{name}/tasks/{urllib.parse.quote(upid, safe='')}"
            try:
                status = node_api.get(task_path + "/status", timeout=30)
            except ProxmoxError:
                try:
                    node_api.login()
                    status = node_api.get(task_path + "/status", timeout=30)
                except ProxmoxError:
                    continue
            if status and status.get("status") == "stopped" and status.get("exitstatus") != "OK":
                try:
                    task_log = node_api.get(task_path + "/log", {"limit": 50}) or []
                    tail = " | ".join(line.get("t", "") for line in task_log[-6:] if line.get("t"))
                except ProxmoxError:
                    tail = ""
                last_error = f"{status.get('exitstatus')} {tail}".strip()
                log(f"Join af {name} fejlede: {last_error}")
                break
        else:
            last_error = "noden blev ikke online i clusteret inden for 10 minutter"
            log(f"Join af {name}: {last_error}")
        if attempt < attempts:
            time.sleep(20)
            wait_for_quorum(main_api, first["hostname"], log)
    raise ProxmoxError(f"{name} kunne ikke joine clusteret: {last_error}")


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
    wait_for_quorum(main_api, first_name, log)
    set_node_status(first["mac_address"], "clustered", "I cluster")

    for node in nodes[1:]:
        members = {entry.get("name") for entry in (main_api.get("/cluster/status") or []) if entry.get("type") == "node"}
        if node["hostname"] not in members:
            join_node(main_api, apis[node["hostname"]], first, node, password, log)
            wait_for_quorum(main_api, first_name, log)
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

    verify_storage_active(apis, nodes, session["ceph_pool"], log)

    for node in ceph_nodes:
        set_node_status(node["mac_address"], "ceph_ready", "Cluster + Ceph klar")
    log("Cluster og Ceph er klar.")
