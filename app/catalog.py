"""Catálogo de productos en Supabase (tablas car_products / car_collections y
bucket 'caricaturas'). Si Supabase no está configurado, se usa el catálogo
fijo de scenes.py.

También contiene el importador: toma data/polaco.json (436 productos de la
tienda de referencia), los adapta a España con OpenAI y los guarda en Supabase.
"""
import asyncio
import json
import logging
import re
import time
import unicodedata
from pathlib import Path

import httpx

from . import config, scenes

log = logging.getLogger("caricaturas.catalog")

SUPABASE_URL = config.env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = config.env("SUPABASE_SERVICE_KEY") or config.env("SUPABASE_KEY")
ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
OPENAI_TEXT_MODEL = config.env("OPENAI_TEXT_MODEL", "gpt-6.1-terra")

_cache = {"t": 0, "products": None, "collections": None}
CACHE_SECONDS = 300

DEFAULT_COLLECTIONS = [
    ("todas", "Todas las caricaturas", "Caricatura a partir de una foto, a tu medida", "Elige el diseño, sube la foto y mira el resultado antes de pagar."),
    ("regalo-para-hombre", "Regalo de cumpleaños para hombre", "Caricatura personalizada: regalo de cumpleaños para hombre", "Motero, futbolero, jefe, cazador, chef… la escena que le define, con su cara."),
    ("regalo-para-mujer", "Regalo de cumpleaños para mujer", "Caricatura personalizada: regalo de cumpleaños para mujer", "Glamour, alfombra roja, vino, bici con flores, su profesión… elige la escena y sube su foto."),
    ("18-cumpleanos", "18 cumpleaños", "Regalo para 18 cumpleaños: caricatura desde una foto", "La mayoría de edad merece un cuadro. Con el 18 bien grande."),
    ("40-cumpleanos", "40 cumpleaños", "Regalo para 40 cumpleaños: caricatura desde una foto", "Para los 40, con el número en el cuadro."),
    ("50-cumpleanos", "50 cumpleaños", "Regalo para 50 cumpleaños: caricatura desde una foto", "Medio siglo bien llevado, en lienzo."),
    ("60-cumpleanos", "60 cumpleaños", "Regalo para 60 cumpleaños: caricatura desde una foto", "Para los 60 y la jubilación."),
    ("boda", "Regalo de boda", "Caricatura de novios: regalo de boda original", "Los novios en su escena. Un regalo de boda que se cuelga."),
    ("aniversario", "Aniversario de boda", "Caricatura de pareja para aniversario", "La pareja de siempre, con los años juntos en el cuadro."),
    ("profesiones", "Profesiones y aficiones", "Caricatura con su profesión o su afición", "Médica, profe, mecánico, enfermera, bombero, runner… cientos de escenas."),
    ("futbol", "Fans del fútbol", "Caricatura para fan de un equipo de fútbol", "Con los colores de su equipo y el estadio detrás."),
    ("mascotas", "Mascotas", "Caricatura de tu perro o tu gato", "Tu mascota como realeza o como protagonista."),
    ("familia", "Familia", "Caricatura de familia desde una foto", "Toda la familia en un cuadro."),
    ("bestsellers", "Los más vendidos", "Las caricaturas más pedidas", "Los diseños que más regalan nuestros clientes."),
]


def _headers(json_body: bool = True) -> dict:
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if json_body:
        h["Content-Type"] = "application/json"
    return h


async def _get(path: str, params: dict | None = None):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=_headers(), params=params or {})
    r.raise_for_status()
    return r.json()


async def _upsert(table: str, rows: list[dict]):
    if not rows:
        return
    h = _headers(); h["Prefer"] = "resolution=merge-duplicates,return=minimal"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=rows)
    if r.status_code >= 300:
        raise RuntimeError(f"supabase {r.status_code}: {r.text[:300]}")


async def _patch(table: str, key: str, value: str, data: dict):
    h = _headers(); h["Prefer"] = "return=minimal"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{table}", headers=h, params={key: f"eq.{value}"}, json=data)
    if r.status_code >= 300:
        raise RuntimeError(f"supabase {r.status_code}: {r.text[:300]}")


async def upload_image(path: str, data: bytes, content_type: str = "image/jpeg") -> str:
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": content_type, "x-upsert": "true"}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/caricaturas/{path}", headers=h, content=data)
    if r.status_code >= 300:
        raise RuntimeError(f"storage {r.status_code}: {r.text[:300]}")
    return f"{SUPABASE_URL}/storage/v1/object/public/caricaturas/{path}"


# --- lectura ----------------------------------------------------------------

def _fallback_products() -> list[dict]:
    out = []
    for s in scenes.SCENES:
        d = scenes.SCENE_BY_ID[s[0]]
        out.append({"slug": d["id"], "title": d["name"], "group": d["group"], "collections": d["categories"], "tags": [], "short_desc": d["desc"], "scene_prompt": d["prompt"], "description_html": f"<p>{d['desc']}</p>", "image_url": None, "images": [], "bestseller": False})
    return out


async def get_catalog(force: bool = False) -> tuple[list[dict], list[dict]]:
    if not ENABLED:
        return _fallback_products(), [{"slug": k, "title": v["name"], "h1": v["title"], "intro": v["intro"]} for k, v in scenes.CATEGORIES.items()]
    if not force and _cache["products"] is not None and time.time() - _cache["t"] < CACHE_SECONDS:
        return _cache["products"], _cache["collections"]
    try:
        prods = await _get("car_products", {"select": "slug,title,group,collections,tags,short_desc,scene_prompt,description_html,image_url,images,bestseller,sort", "active": "eq.true", "order": "sort.asc,created_at.desc", "limit": "2000"})
        cols = await _get("car_collections", {"select": "slug,title,h1,intro,sort", "order": "sort.asc"})
        if not prods:
            prods = _fallback_products()
        if not cols:
            cols = [{"slug": s, "title": t, "h1": h, "intro": i} for s, t, h, i in DEFAULT_COLLECTIONS]
        _cache.update(t=time.time(), products=prods, collections=cols)
        return prods, cols
    except Exception as e:  # noqa: BLE001
        log.warning("supabase no disponible: %s", e)
        if _cache["products"] is not None:
            return _cache["products"], _cache["collections"]
        return _fallback_products(), [{"slug": s, "title": t, "h1": h, "intro": i} for s, t, h, i in DEFAULT_COLLECTIONS]


async def get_product(slug: str) -> dict | None:
    prods, _ = await get_catalog()
    for p in prods:
        if p["slug"] == slug:
            return p
    return None


# --- importador -------------------------------------------------------------

def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:80]


ADAPT_PROMPT = """Eres el responsable de catálogo de una tienda española de caricaturas personalizadas a partir de una foto (impresas en lienzo o póster, o archivo digital). Te doy un producto de una tienda polaca equivalente (título, etiquetas y descripción en polaco). Adáptalo al mercado de España (y público hispano en general):
- Traduce y adapta, no copies literal. Cambia referencias locales polacas por españolas equivalentes: clubes polacos → "fan del Real Madrid", "fan del Barça", "fan del Atlético", "fan del Athletic", "fan del Betis", "fan del Sevilla", "fan del Valencia" (sin escudos ni logotipos; se rota entre ellos si hay varios productos de fútbol), aerolíneas polacas → "piloto de aerolínea" / "azafata", Wisła etc. Mantén la ocasión (18, 25, 30, 40, 50, 60 cumpleaños, boda, aniversario, jubilación), el género y la profesión o afición.
- Devuelve SOLO un JSON con estas claves:
  title: título de producto SEO en español (máx. 90 caracteres), estilo "Caricatura personalizada para [X]: regalo de [ocasión]".
  slug: slug ascii corto (máx. 60 chars) a partir del título.
  group: uno de "ella" (regalo para mujer), "el" (regalo para hombre), "pareja", "familia" (familia, niños o mascotas).
  collections: lista de slugs entre: regalo-para-hombre, regalo-para-mujer, 18-cumpleanos, 40-cumpleanos, 50-cumpleanos, 60-cumpleanos, boda, aniversario, profesiones, futbol, mascotas, familia (las que apliquen, 1 a 4).
  tags: 4-8 etiquetas cortas en español (ocasión, persona, profesión/afición).
  short_desc: una frase de 12-20 palabras que describa la escena (lo que se ve en el cuadro).
  description_html: descripción de producto en HTML sencillo (2 párrafos <p> y una lista <ul> de 3-4 usos/ventajas), 900-1300 caracteres, SEO natural en español de España, sin hablar de "panel" ni de "revisiones": nuestro flujo es "subes la foto, ves la caricatura en 1-2 minutos y pagas solo si te gusta". Menciona lienzo listo para colgar, póster o archivo digital, envío gratis en España, posibilidad de añadir un número y una dedicatoria.
  scene_prompt: instrucción en español para el generador de imagen con TODO lo que debe aparecer en la escena (ropa, objetos, fondo, número grande de edad si la ocasión lo tiene, ambiente), 40-80 palabras, sin marcas ni logotipos reales, sin texto escrito salvo un número de edad.
Producto polaco:
"""


async def _openai_json(prompt: str) -> dict:
    body = {"model": OPENAI_TEXT_MODEL, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"openai {r.status_code}: {r.text[:300]}")
    return json.loads(r.json()["choices"][0]["message"]["content"])


async def import_from_polish(start: int = 0, limit: int = 50, concurrency: int = 4) -> dict:
    """Adapta productos polacos (data/polaco.json) y los guarda en Supabase."""
    if not ENABLED or not config.OPENAI_API_KEY:
        raise RuntimeError("Hacen falta SUPABASE_URL, SUPABASE_SERVICE_KEY y OPENAI_API_KEY")
    src = json.loads((Path(__file__).parent.parent / "data" / "polaco.json").read_text(encoding="utf-8"))
    batch = src[start:start + limit]
    existing = {r["source_handle"] for r in await _get("car_products", {"select": "source_handle", "limit": "5000"})}
    todo = [p for p in batch if p["handle"] not in existing]
    sem = asyncio.Semaphore(concurrency)
    results, errors = [], []
    used_slugs = {r["slug"] for r in await _get("car_products", {"select": "slug", "limit": "5000"})}

    async def one(p, i):
        async with sem:
            try:
                d = await _openai_json(ADAPT_PROMPT + json.dumps({"title": p["title"], "tags": p["tags"], "description": p["body"][:1800]}, ensure_ascii=False))
                slug = slugify(d.get("slug") or d["title"])
                base = slug; n = 2
                while slug in used_slugs:
                    slug = f"{base}-{n}"; n += 1
                used_slugs.add(slug)
                row = {
                    "slug": slug, "title": d["title"][:120], "group": d.get("group") if d.get("group") in ("ella", "el", "pareja", "familia") else "el",
                    "collections": [c for c in d.get("collections", []) if isinstance(c, str)][:4], "tags": [t for t in d.get("tags", []) if isinstance(t, str)][:8],
                    "short_desc": d.get("short_desc", "")[:220], "description_html": d.get("description_html", ""), "scene_prompt": d.get("scene_prompt", "")[:900],
                    "source_handle": p["handle"], "source_title": p["title"], "source_tags": p["tags"], "source_image": p["image"],
                    "bestseller": "bestseller" in p["tags"], "sort": start + i, "updated_at": "now()",
                }
                results.append(row)
            except Exception as e:  # noqa: BLE001
                errors.append({"handle": p["handle"], "error": str(e)[:200]})

    await asyncio.gather(*(one(p, i) for i, p in enumerate(todo)))
    for i in range(0, len(results), 50):
        await _upsert("car_products", results[i:i + 50])
    _cache["t"] = 0
    return {"requested": len(batch), "skipped_existing": len(batch) - len(todo), "imported": len(results), "errors": errors}


DEDUPE_PROMPT = """Eres responsable de catálogo de una tienda española de caricaturas personalizadas. Estos productos comparten el MISMO título aunque la escena de cada uno es distinta. Reescribe cada uno para que el título sea único y describa su escena (p. ej. "Caricatura personalizada para mujer: regalo de 40 cumpleaños con tarta y champán", "...: 40 cumpleaños en descapotable rosa"). Si son fans del mismo club de fútbol, reparte los clubes entre ellos (Real Madrid, FC Barcelona, Atlético de Madrid, Athletic Club, Real Betis, Sevilla FC, Valencia CF, Real Sociedad; sin escudos ni logotipos) y adapta los colores de la ropa en scene_prompt, short_desc, tags y description_html (blanco → azulgrana / rojiblanco / verdiblanco, etc.).
Devuelve SOLO JSON: {"items":[{"slug": "...", "title": "...", "short_desc": "...", "tags": [...], "scene_prompt": "...", "description_html": "..."}]} manteniendo el slug de cada producto y la misma longitud/estilo de description_html (puedes copiarla ajustando solo lo que cambie).
Productos:
"""


async def dedupe_titles() -> dict:
    rows = await _get("car_products", {"select": "slug,title,short_desc,tags,scene_prompt,description_html", "limit": "5000"})
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["title"].strip().lower(), []).append(r)
    dups = [g for g in groups.values() if len(g) > 1]
    updated, errors = 0, []
    for g in dups:
        try:
            d = await _openai_json(DEDUPE_PROMPT + json.dumps(g, ensure_ascii=False))
            items = d.get("items", [])
            valid = {r["slug"] for r in g}
            out = []
            for it in items:
                if it.get("slug") in valid and it.get("title"):
                    out.append({"slug": it["slug"], "title": it["title"][:120], "short_desc": (it.get("short_desc") or "")[:220], "tags": [t for t in it.get("tags", []) if isinstance(t, str)][:8], "scene_prompt": (it.get("scene_prompt") or "")[:900], "description_html": it.get("description_html") or "", "updated_at": "now()"})
            # no dejar vacíos
            out = [o for o in out if o["scene_prompt"] and o["description_html"]]
            await _upsert("car_products", out)
            updated += len(out)
        except Exception as e:  # noqa: BLE001
            errors.append(str(e)[:200])
    _cache["t"] = 0
    return {"groups": len(dups), "updated": updated, "errors": errors}


async def ensure_collections():
    rows = [{"slug": s, "title": t, "h1": h, "intro": i, "sort": n} for n, (s, t, h, i) in enumerate(DEFAULT_COLLECTIONS)]
    await _upsert("car_collections", rows)
    _cache["t"] = 0


# --- banco de caras (fotos sintéticas reutilizadas entre productos) -------------
AGE_BANDS = (18, 25, 30, 40, 50, 60)
_faces_cache: dict = {}


async def list_faces() -> list[str]:
    """Rutas de las caras disponibles en el bucket (_faces/<genero>-<edad>-<n>.jpg)."""
    if "v" in _faces_cache and time.time() - _faces_cache.get("t", 0) < 300:
        return _faces_cache["v"]
    h = _headers()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{SUPABASE_URL}/storage/v1/object/list/caricaturas", headers=h, json={"prefix": "_faces", "limit": 500})
    names = [o["name"] for o in r.json()] if r.status_code == 200 else []
    _faces_cache.update(v=names, t=time.time())
    return names


def pick_face(names: list[str], group: str, title: str, slug: str) -> str | None:
    gender = "mujer" if group in ("ella",) else "hombre"
    m = re.search(r"\b(18|25|30|40|50|60)\b", title)
    age = int(m.group(1)) if m else AGE_BANDS[sum(map(ord, slug)) % len(AGE_BANDS)]
    cands = [n for n in names if n.startswith(f"{gender}-{age}-")] or [n for n in names if n.startswith(f"{gender}-")] or names
    if not cands:
        return None
    return cands[sum(map(ord, slug)) % len(cands)]


async def face_image(name: str):
    from PIL import Image as _I
    import io as _io
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{SUPABASE_URL}/storage/v1/object/public/caricaturas/_faces/{name}")
    r.raise_for_status()
    return _I.open(_io.BytesIO(r.content)).convert("RGB")
