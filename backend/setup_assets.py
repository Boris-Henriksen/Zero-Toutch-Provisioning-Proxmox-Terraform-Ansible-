"""Setup-siden: hent Proxmox- og Ubuntu-ISO'er via upload eller download-link,
læg dem i de rigtige mapper og forbered discovery-imaget automatisk."""
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
ISO_DIR = STORAGE_DIR / "isos"
PROXMOX_ISO_DIR = ISO_DIR / "proxmox"
UBUNTU_ISO_DIR = ISO_DIR / "ubuntu"
DISCOVERY_DIR = STORAGE_DIR / "discovery"
DISCOVERY_ISO = DISCOVERY_DIR / "ubuntu-live.iso"
DISCOVERY_SOURCE = DISCOVERY_DIR / "source.txt"
PREPARE_SCRIPT = BASE_DIR / "scripts" / "prepare-discovery-image.sh"

TARGET_DIRS = {"proxmox": PROXMOX_ISO_DIR, "ubuntu": UBUNTU_ISO_DIR}
FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,200}\.iso$")
ACTIVE_STAGES = {"downloading", "uploading", "verifying", "preparing"}
CHUNK = 1 << 20

router = APIRouter()
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def migrate_isos():
    """Opret undermapperne og flyt ISO'er der ligger direkte i storage/isos (gammelt layout)."""
    for directory in TARGET_DIRS.values():
        directory.mkdir(parents=True, exist_ok=True)
    for iso in ISO_DIR.glob("*.iso"):
        name = iso.name.lower()
        target = PROXMOX_ISO_DIR if name.startswith("proxmox") else UBUNTU_ISO_DIR if "ubuntu" in name else None
        if target and not (target / iso.name).exists():
            iso.rename(target / iso.name)


def discovery_ready() -> bool:
    return all((DISCOVERY_DIR / name).exists() for name in ("vmlinuz", "initrd", DISCOVERY_ISO.name))


def discovery_source() -> str:
    if not discovery_ready():
        return ""
    if DISCOVERY_SOURCE.exists():
        return DISCOVERY_SOURCE.read_text().strip()
    # Ældre opsætning uden source.txt: find ISO'en i ubuntu-mappen via hardlink (samme inode).
    inode = DISCOVERY_ISO.stat().st_ino
    match = next((f.name for f in UBUNTU_ISO_DIR.glob("*.iso") if f.stat().st_ino == inode), None)
    return match or DISCOVERY_ISO.name


def is_iso9660(path: Path) -> bool:
    with open(path, "rb") as f:
        f.seek(32769)
        return f.read(5) == b"CD001"


def safe_filename(name: str) -> str:
    name = Path(urllib.parse.unquote(name or "")).name.strip()
    name = re.sub(r"[^A-Za-z0-9._+-]", "_", name)
    if not FILENAME_RE.match(name):
        raise HTTPException(status_code=400, detail=f"Ugyldigt filnavn '{name}' - filen skal være en .iso.")
    return name


def check_kind(kind: str) -> Path:
    if kind not in TARGET_DIRS:
        raise HTTPException(status_code=400, detail="Ukendt filtype - skal være 'proxmox' eller 'ubuntu'.")
    return TARGET_DIRS[kind]


def check_space(directory: Path, needed: int):
    free = shutil.disk_usage(directory).free
    if needed and free < needed + (1 << 30):
        raise RuntimeError(f"Ikke nok diskplads: {needed / 1e9:.1f} GB skal bruges, kun {free / 1e9:.1f} GB ledig.")


def new_job(kind: str, filename: str, source: str) -> dict:
    with jobs_lock:
        if any(j["kind"] == kind and j["stage"] in ACTIVE_STAGES for j in jobs.values()):
            raise HTTPException(status_code=409, detail="Der kører allerede en upload/download for denne fil - vent til den er færdig.")
        job = {
            "id": uuid.uuid4().hex[:12], "kind": kind, "filename": filename, "source": source,
            "stage": "uploading" if source == "upload" else "downloading",
            "done": 0, "total": 0, "rate": 0.0, "message": "", "started": time.time(),
            "_last": (time.monotonic(), 0),
        }
        jobs[job["id"]] = job
        # Behold kun de seneste jobs.
        for old in sorted(jobs.values(), key=lambda j: j["started"])[:-20]:
            jobs.pop(old["id"], None)
    return job


def update_job(job: dict, **fields):
    with jobs_lock:
        job.update(fields)


def add_progress(job: dict, size: int):
    with jobs_lock:
        job["done"] += size
        now = time.monotonic()
        last_t, last_done = job["_last"]
        if now - last_t >= 1:
            rate = (job["done"] - last_done) / (now - last_t)
            job["rate"] = rate if not job["rate"] else 0.7 * job["rate"] + 0.3 * rate
            job["_last"] = (now, job["done"])


def prepare_discovery(iso: Path):
    result = subprocess.run(["bash", str(PREPARE_SCRIPT), str(iso)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        output = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError("Klargøring af discovery-image fejlede: " + " | ".join(output[-3:]))
    DISCOVERY_SOURCE.write_text(iso.name)


def finalize(job: dict, part: Path, final: Path):
    """Tjek at filen er en ISO, flyt den på plads og forbered evt. discovery-imaget."""
    moved = False
    try:
        update_job(job, stage="verifying", message="Tjekker ISO-filen...")
        if not is_iso9660(part):
            raise RuntimeError("Filen er ikke en gyldig ISO (ISO 9660).")
        if final.exists():
            raise RuntimeError(f"{final.name} findes allerede.")
        part.replace(final)
        moved = True
        final.chmod(0o644)
        if job["kind"] == "ubuntu":
            update_job(job, stage="preparing", message="Udpakker kernel/initrd og klargør discovery-image...")
            prepare_discovery(final)
            update_job(job, stage="done", message=f"{final.name} er klar som discovery-image.")
        else:
            update_job(job, stage="done", message=f"{final.name} er klar og kan vælges i portalen.")
    except Exception as error:
        part.unlink(missing_ok=True)
        # En ISO der ikke kunne bruges som discovery-image fjernes igen, så den ikke blokerer et nyt forsøg.
        if moved and job["kind"] == "ubuntu" and not (DISCOVERY_ISO.exists() and final.samefile(DISCOVERY_ISO)):
            final.unlink(missing_ok=True)
        update_job(job, stage="error", message=str(error))


def run_download(job: dict, url: str):
    target_dir = TARGET_DIRS[job["kind"]]
    part: Optional[Path] = None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "infrastruktur-portal/1.0"})
        with urllib.request.urlopen(request, timeout=60) as resp:
            # Filnavn fra Content-Disposition, ellers fra den endelige URL (efter redirects).
            disposition = resp.headers.get("Content-Disposition", "")
            match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
            raw_name = match.group(1) if match else urllib.parse.urlparse(resp.geturl()).path
            try:
                filename = safe_filename(raw_name)
            except HTTPException as error:
                raise RuntimeError(f"Linket peger ikke på en .iso-fil ({error.detail})") from None
            final = target_dir / filename
            if final.exists():
                raise RuntimeError(f"{filename} findes allerede.")
            total = int(resp.headers.get("Content-Length") or 0)
            check_space(target_dir, total)
            update_job(job, filename=filename, total=total, message="Henter...")
            part = target_dir / f".{filename}.part"
            with open(part, "wb") as out:
                while chunk := resp.read(CHUNK):
                    out.write(chunk)
                    add_progress(job, len(chunk))
            if total and job["done"] != total:
                raise RuntimeError("Download blev afbrudt før filen var færdig.")
        finalize(job, part, final)
    except Exception as error:
        if part:
            part.unlink(missing_ok=True)
        message = error.reason if isinstance(error, urllib.error.URLError) and not isinstance(error, urllib.error.HTTPError) else error
        update_job(job, stage="error", message=f"Download fejlede: {message}")


class DownloadRequest(BaseModel):
    kind: str
    url: str


@router.get("/api/setup/status")
def setup_status():
    migrate_isos()
    proxmox = sorted(f.name for f in PROXMOX_ISO_DIR.glob("*.iso"))
    ubuntu = sorted(f.name for f in UBUNTU_ISO_DIR.glob("*.iso"))
    with jobs_lock:
        job_list = [{k: v for k, v in j.items() if not k.startswith("_")}
                    for j in sorted(jobs.values(), key=lambda j: j["started"], reverse=True)]
    return {
        "proxmox_isos": proxmox,
        "ubuntu_isos": ubuntu,
        "discovery_ready": discovery_ready(),
        "discovery_source": discovery_source(),
        "ready": bool(proxmox) and discovery_ready(),
        "jobs": job_list,
    }


@router.post("/api/setup/download")
def start_download(req: DownloadRequest):
    check_kind(req.kind)
    url = req.url.strip()
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Download-linket skal starte med http:// eller https://")
    guess = Path(urllib.parse.urlparse(url).path).name or "ukendt.iso"
    job = new_job(req.kind, guess, "download")
    threading.Thread(target=run_download, args=(job, url), daemon=True).start()
    return {"job_id": job["id"]}


@router.put("/api/setup/upload/{kind}")
async def upload_file(kind: str, request: Request, filename: str):
    target_dir = check_kind(kind)
    filename = safe_filename(filename)
    final = target_dir / filename
    if final.exists():
        raise HTTPException(status_code=409, detail=f"{filename} findes allerede.")
    total = int(request.headers.get("content-length") or 0)
    try:
        check_space(target_dir, total)
    except RuntimeError as error:
        raise HTTPException(status_code=507, detail=str(error)) from None
    job = new_job(kind, filename, "upload")
    update_job(job, total=total, message="Uploader...")
    part = target_dir / f".{filename}.part"
    try:
        with open(part, "wb") as out:
            async for chunk in request.stream():
                out.write(chunk)
                add_progress(job, len(chunk))
        if total and job["done"] != total:
            raise RuntimeError("Upload blev afbrudt før filen var færdig.")
    except Exception as error:
        part.unlink(missing_ok=True)
        update_job(job, stage="error", message=f"Upload fejlede: {error or 'forbindelsen blev afbrudt'}")
        raise HTTPException(status_code=400, detail=job["message"]) from None
    # Tjek og klargøring kan tage minutter - kør i baggrunden og lad siden polle status.
    threading.Thread(target=finalize, args=(job, part, final), daemon=True).start()
    return {"job_id": job["id"]}
