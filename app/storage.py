"""Almacenamiento temporal en disco, sin base de datos.

Cada trabajo (job) es una carpeta DATA_DIR/jobs/<id>/ con:
  original.<ext>   foto subida (se borra al generar la caricatura)
  result.png       caricatura en alta resolución
  preview.jpg      caricatura con marca de agua, tamaño web
  meta.json        estado, producto elegido, datos de pedido
Todo caduca: UPLOAD_TTL_HOURS si no se paga, PAID_TTL_DAYS si se paga.
"""
import json
import secrets
import shutil
import time
from pathlib import Path

from . import config

JOBS = config.DATA_DIR / "jobs"


def new_job_id() -> str:
    return secrets.token_urlsafe(16)


def job_dir(job_id: str) -> Path:
    if not job_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in job_id):
        raise ValueError("job id inválido")
    return JOBS / job_id


def create_job() -> tuple[str, Path]:
    job_id = new_job_id()
    d = job_dir(job_id)
    d.mkdir(parents=True, exist_ok=False)
    write_meta(job_id, {"created": time.time(), "status": "new", "paid": False})
    return job_id, d


def read_meta(job_id: str) -> dict | None:
    p = job_dir(job_id) / "meta.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def write_meta(job_id: str, meta: dict) -> None:
    p = job_dir(job_id) / "meta.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    tmp.replace(p)


def update_meta(job_id: str, **changes) -> dict:
    meta = read_meta(job_id) or {}
    meta.update(changes)
    write_meta(job_id, meta)
    return meta


def delete_job(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)


def cleanup() -> int:
    """Borra trabajos caducados. Se llama al arrancar y en cada subida."""
    if not JOBS.exists():
        return 0
    now = time.time()
    removed = 0
    for d in JOBS.iterdir():
        meta_path = d / "meta.json"
        try:
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        except Exception:
            meta = {}
        created = meta.get("created", d.stat().st_mtime)
        ttl = config.PAID_TTL_DAYS * 86400 if meta.get("paid") else config.UPLOAD_TTL_HOURS * 3600
        if now - created > ttl:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed


def list_jobs() -> list[dict]:
    out = []
    if not JOBS.exists():
        return out
    for d in sorted(JOBS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        meta = read_meta(d.name) or {}
        meta["job_id"] = d.name
        out.append(meta)
    return out
