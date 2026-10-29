"""Acceso a Supabase (REST + Storage) para la tienda de cuadros."""
import time

import httpx

from . import config, seed

URL = config.SUPABASE_URL
KEY = config.SUPABASE_KEY
ENABLED = bool(URL and KEY)

_cache = {"t": 0.0, "products": None}
CACHE_SECONDS = 120


def _h(json_body: bool = True) -> dict:
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


async def get(table: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{URL}/rest/v1/{table}", headers=_h(), params=params or {})
    r.raise_for_status()
    return r.json()


async def upsert(table: str, rows, on_conflict: str | None = None):
    if not rows:
        return
    h = _h(); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    params = {"on_conflict": on_conflict} if on_conflict else {}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{URL}/rest/v1/{table}", headers=h, params=params, json=rows)
    if r.status_code >= 300:
        raise RuntimeError(f"supabase {r.status_code}: {r.text[:300]}")


async def patch(table: str, key: str, value: str, data: dict):
    h = _h(); h["Prefer"] = "return=minimal"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.patch(f"{URL}/rest/v1/{table}", headers=h, params={key: f"eq.{value}"}, json=data)
    if r.status_code >= 300:
        raise RuntimeError(f"supabase {r.status_code}: {r.text[:300]}")


async def upload(path: str, data: bytes, content_type: str = "image/jpeg") -> str:
    h = {"apikey": KEY, "Authorization": f"Bearer {KEY}", "Content-Type": content_type, "x-upsert": "true"}
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.post(f"{URL}/storage/v1/object/{config.BUCKET}/{path}", headers=h, content=data)
    if r.status_code >= 300:
        raise RuntimeError(f"storage {r.status_code}: {r.text[:300]}")
    return public_url(path)


def public_url(path: str) -> str:
    return f"{URL}/storage/v1/object/public/{config.BUCKET}/{path}"


async def download(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.get(url)
    r.raise_for_status()
    return r.content


# --- catálogo -----------------------------------------------------------------

def _seed_products() -> list[dict]:
    return [dict(r, images=[], art_url=None, content={}) for r in seed.build_rows()]


async def products(force: bool = False) -> list[dict]:
    if not ENABLED:
        return _seed_products()
    if not force and _cache["products"] is not None and time.time() - _cache["t"] < CACHE_SECONDS:
        return _cache["products"]
    try:
        rows = await get("fe_products", {"select": "*", "active": "eq.true", "order": "sort.asc", "limit": "1000"})
    except Exception:
        rows = _cache["products"] or _seed_products()
    if not rows:
        rows = _seed_products()
    _cache.update(t=time.time(), products=rows)
    return rows


def invalidate():
    _cache["products"] = None


async def product(slug: str) -> dict | None:
    for p in await products():
        if p["slug"] == slug:
            return p
    return None


async def seed_catalog() -> int:
    rows = seed.build_rows()
    await upsert("fe_products", rows, on_conflict="slug")
    invalidate()
    return len(rows)


async def get_setting(key: str):
    try:
        rows = await get("fe_settings", {"select": "v", "k": f"eq.{key}"})
        return rows[0]["v"] if rows else None
    except Exception:
        return None


async def set_setting(key: str, value):
    await upsert("fe_settings", [{"k": key, "v": value}], on_conflict="k")
