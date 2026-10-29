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

import httpx

from . import config

JOBS = config.DATA_DIR / "jobs"

# --- Copia persistente en Supabase de los pedidos (el disco de Render se borra al reiniciar) ---
SB_URL = config.env("SUPABASE_URL").rstrip("/")
SB_KEY = config.env("SUPABASE_SERVICE_KEY") or config.env("SUPABASE_KEY")
SB_ON = bool(SB_URL and SB_KEY)
BUCKET = "car-orders"


def _h(ct: str = "application/json") -> dict:
    return {"apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}", "Content-Type": ct}


def _sb_save(job_id: str, meta: dict) -> None:
    if not SB_ON:
        return
    try:
        h = _h(); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
        httpx.post(f"{SB_URL}/rest/v1/car_orders", headers=h, json=[{"job_id": job_id, "meta": meta, "updated_at": "now()"}], timeout=20)
    except Exception:
        pass


def _sb_load(job_id: str) -> dict | None:
    if not SB_ON:
        return None
    try:
        r = httpx.get(f"{SB_URL}/rest/v1/car_orders", headers=_h(), params={"job_id": f"eq.{job_id}", "select": "meta"}, timeout=20)
        rows = r.json() if r.status_code == 200 else []
        return rows[0]["meta"] if rows else None
    except Exception:
        return None


def persist(job_id: str) -> None:
    """Al iniciar el pago: sube la caricatura y la vista previa y marca el pedido como persistente."""
    if not SB_ON:
        return
    d = job_dir(job_id)
    for name, ct in (("result.png", "image/png"), ("preview.jpg", "image/jpeg")):
        f = d / name
        if f.exists():
            try:
                h = _h(ct); h["x-upsert"] = "true"
                httpx.post(f"{SB_URL}/storage/v1/object/{BUCKET}/{job_id}/{name}", headers=h, content=f.read_bytes(), timeout=120)
            except Exception:
                pass
    update_meta(job_id, persist=True)


def backup(job_id: str) -> None:
    """Copia de seguridad inmediata tras generar: si Render cambia de instancia (despliegue,
    reinicio), la vista previa y el pago siguen funcionando. No marca el pedido como persistente."""
    if not SB_ON:
        return
    d = job_dir(job_id)
    for name, ct in (("preview.jpg", "image/jpeg"), ("result.png", "image/png")):
        f = d / name
        if f.exists():
            try:
                h = _h(ct); h["x-upsert"] = "true"
                httpx.post(f"{SB_URL}/storage/v1/object/{BUCKET}/{job_id}/{name}", headers=h, content=f.read_bytes(), timeout=120)
            except Exception:
                pass
    meta = read_meta(job_id)
    if meta:
        _sb_save(job_id, meta)


UNPAID_KEEP_DAYS = 2
_last_sb_cleanup = 0.0


def sb_cleanup(force: bool = False) -> int:
    """Borra de Supabase las pruebas NO pagadas de más de 2 días (fila + archivos).
    Nunca toca pedidos pagados. Se ejecuta como mucho cada 6 h."""
    global _last_sb_cleanup
    if not SB_ON or (not force and time.time() - _last_sb_cleanup < 6 * 3600):
        return 0
    _last_sb_cleanup = time.time()
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=UNPAID_KEEP_DAYS)).isoformat()
    removed = 0
    try:
        r = httpx.get(f"{SB_URL}/rest/v1/car_orders", headers=_h(), timeout=30,
                      params={"select": "job_id,meta", "updated_at": f"lt.{cutoff}", "limit": "1000"})
        rows = r.json() if r.status_code == 200 else []
        old = [x["job_id"] for x in rows if not (x.get("meta") or {}).get("paid") and not (x.get("meta") or {}).get("gelato_order")]
        for i in range(0, len(old), 100):
            chunk = old[i:i + 100]
            httpx.request("DELETE", f"{SB_URL}/storage/v1/object/{BUCKET}", headers=_h(), timeout=60,
                          json={"prefixes": [f"{j}/{n}" for j in chunk for n in ("preview.jpg", "result.png")]})
            ids = ",".join(f'"{j}"' for j in chunk)
            httpx.request("DELETE", f"{SB_URL}/rest/v1/car_orders", headers=_h(), params={"job_id": f"in.({ids})"}, timeout=30)
            removed += len(chunk)
    except Exception:
        pass
    return removed


def ensure_file(job_id: str, name: str) -> Path:
    """Devuelve la ruta local del archivo; si el disco se borró, lo recupera de Supabase."""
    p = job_dir(job_id) / name
    if p.exists() or not SB_ON:
        return p
    try:
        r = httpx.get(f"{SB_URL}/storage/v1/object/{BUCKET}/{job_id}/{name}", headers=_h(), timeout=120)
        if r.status_code == 200:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
    except Exception:
        pass
    return p


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
        meta = _sb_load(job_id)
        if meta is None:
            return None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        return meta
    return json.loads(p.read_text())


def write_meta(job_id: str, meta: dict) -> None:
    p = job_dir(job_id) / "meta.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    tmp.replace(p)
    if meta.get("persist"):
        _sb_save(job_id, meta)


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
