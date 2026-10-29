"""Caricaturas personalizadas: sube una foto, ve tu caricatura, paga, la recibes.

Rutas:
  GET  /                      landing + flujo
  POST /api/generate          foto → caricatura (preview con marca de agua)
  GET  /api/preview/{job}.jpg preview con marca de agua
  POST /api/checkout          crea el pago (Stripe) y devuelve la URL
  POST /api/stripe/webhook    confirmación de pago → producción
  GET  /gracias               página de éxito (respaldo: confirma el pago y produce)
  GET  /api/download/{job}.png archivo final (solo si pagado)
  GET  /api/print-file/{job}.png archivo de impresión para Gelato (solo si pagado)
  GET  /admin/orders          listado de pedidos (ADMIN_TOKEN)
"""
import asyncio
import json
import io
import logging
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from . import catalog, config, fulfilment, imaging, scenes, storage

log = logging.getLogger("caricaturas")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=config.BRAND_NAME)
STATIC = Path(__file__).parent / "static"
EXAMPLES = config.DATA_DIR / "examples"
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse("/static/favicon.ico", 301)


app.mount("/static", StaticFiles(directory=STATIC), name="static")

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
_sem = asyncio.Semaphore(3)  # generaciones simultáneas


@app.on_event("startup")
async def _startup():
    storage.JOBS.mkdir(parents=True, exist_ok=True)
    n = storage.cleanup()
    log.info("arranque: demo=%s pagos=%s impresion=%s, %d trabajos caducados borrados",
             config.DEMO_MODE, config.PAYMENTS_ENABLED, config.PRINT_ENABLED, n)


def _eur(cents: int) -> str:
    return f"{cents/100:.2f}".replace(".", ",") + " €"


def _page(name: str, **extra: str) -> HTMLResponse:
    html = (STATIC / name).read_text(encoding="utf-8")
    base = config.PRICE_CANVAS_20x30_CENTS
    before = round(base / (1 - config.DISCOUNT_PCT / 100)) if config.DISCOUNT_PCT else base
    repl = {
        "BRAND": config.BRAND_NAME,
        "PHONE": config.PHONE,
        "EMAIL": config.CONTACT_EMAIL,
        "DISCOUNT": str(config.DISCOUNT_PCT),
        "PRICE_FROM": _eur(base),
        "PRICE_BEFORE": _eur(before),
        "PRICE_CANVAS_20x30": _eur(config.PRICE_CANVAS_20x30_CENTS),
        "PRICE_CANVAS_30x40": _eur(config.PRICE_CANVAS_30x40_CENTS),
        "PRICE_CANVAS_40x50": _eur(config.PRICE_CANVAS_40x50_CENTS),
        "PRICE_POSTER_A4": _eur(config.PRICE_POSTER_A4_CENTS),
        "PRICE_POSTER_A3": _eur(config.PRICE_POSTER_A3_CENTS),
        "PRICE_DIGITAL": _eur(config.PRICE_DIGITAL_CENTS),
        "DEMO": "true" if config.DEMO_MODE else "false",
        "WHATSAPP": config.WHATSAPP,
        "CATEGORY": "",
        "SCENE_ID": "", "SCENE_NAME": "", "SCENE_DESC": "", "SCENE_HTML": "",
        "GA4_ID": config.env("GA4_ID"), "GADS_ID": config.env("GADS_ID"), "GADS_LABEL": config.env("GADS_LABEL"), "META_PIXEL_ID": config.env("META_PIXEL_ID"), "CLARITY_ID": config.env("CLARITY_ID"), "PINTEREST_TAG_ID": config.env("PINTEREST_TAG_ID"),
        "PAGE_TITLE": f"{config.BRAND_NAME} · Caricatura personalizada desde una foto, en lienzo",
        "H1": "Caricatura personalizada a partir de una foto",
        "INTRO": "Tu idea. Tu foto. Un regalo personal. Elige la escena, sube la foto y mira tu caricatura antes de pagar.",
        "HEAD_EXTRA": f'<link rel="canonical" href="{config.BASE_URL}/">',
    }
    repl.update(extra)
    for k, v in repl.items():
        html = html.replace("{{" + k + "}}", v)
    return HTMLResponse(html)


@app.middleware("http")
async def canonical_host(request: Request, call_next):
    """Si entran por *.onrender.com, redirige al dominio propio (salvo webhooks, API y admin)."""
    host = request.headers.get("host", ""); path = request.url.path
    if request.headers.get("x-forwarded-proto") == "http" and not host.startswith(("localhost", "127.")):
        q = ("?" + request.url.query) if request.url.query else ""
        return RedirectResponse(f"https://{host}{path}{q}", status_code=301)
    if host.endswith(".onrender.com") and config.BASE_URL.startswith("https://") and ".onrender.com" not in config.BASE_URL \
            and not path.startswith(("/api/", "/admin", "/static/")):
        q = ("?" + request.url.query) if request.url.query else ""
        return RedirectResponse(config.BASE_URL + path + q, status_code=301)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def home():
    return _page("index.html")


@app.get("/regalos/{category}", response_class=HTMLResponse)
@app.get("/coleccion/{category}", response_class=HTMLResponse)
async def category_page(category: str):
    _, cols = await catalog.get_catalog()
    cat = next((c for c in cols if c["slug"] == category), None)
    if not cat:
        raise HTTPException(404)
    return _page("index.html", CATEGORY=category, HEAD_EXTRA=f'<link rel="canonical" href="{config.BASE_URL}/coleccion/{category}">', PAGE_TITLE=f"{cat['h1'] or cat['title']} · {config.BRAND_NAME}", H1=cat["h1"] or cat["title"], INTRO=cat.get("intro") or "")


@app.get("/p/{slug}", response_class=HTMLResponse)
async def product_page(slug: str):
    s = await catalog.get_product(slug)
    if not s:
        raise HTTPException(404)
    import html as _h
    url = f"{config.BASE_URL}/p/{s['slug']}"
    ld = json.dumps({"@context": "https://schema.org", "@type": "Product", "name": s["title"], "description": s.get("short_desc") or "",
                     "image": (s.get("images") or [s.get("image_url")])[:6], "brand": {"@type": "Brand", "name": config.BRAND_NAME}, "sku": s["slug"],
                     "offers": {"@type": "AggregateOffer", "priceCurrency": "EUR", "lowPrice": config.PRICE_DIGITAL_CENTS / 100,
                                "highPrice": max(v["cents"] for v in fulfilment.PRODUCTS.values()) / 100, "availability": "https://schema.org/InStock", "url": url}},
                    ensure_ascii=False).replace("</", "<\\/")
    head = f'<link rel="canonical" href="{url}"><meta property="og:title" content="{_h.escape(s["title"])}"><meta property="og:image" content="{_h.escape(s.get("image_url") or "")}"><script type="application/ld+json">{ld}</script>'
    return _page("producto.html", HEAD_EXTRA=head, SCENE_ID=s["slug"], SCENE_NAME=s["title"], SCENE_DESC=s.get("short_desc") or "", SCENE_HTML=s.get("description_html") or "", PAGE_TITLE=f"{s['title']} · {config.BRAND_NAME}")


@app.get("/api/scenes")
async def api_scenes(category: str = "", group: str = ""):
    prods, cols = await catalog.get_catalog()
    items = [p for p in prods if (not category or category in (p.get("collections") or []) or category == "todas" or (category == "bestsellers" and p.get("bestseller"))) and (not group or p.get("group") == group)]
    return {
        "groups": [{"slug": k, "name": v} for k, v in scenes.GROUPS],
        "categories": [{"slug": c["slug"], "name": c["title"], "title": c.get("h1") or c["title"], "intro": c.get("intro") or ""} for c in cols if c["slug"] != "todas"],
        "scenes": [{"id": p["slug"], "name": p["title"], "group": p.get("group") or "el", "categories": p.get("collections") or [], "desc": p.get("short_desc") or "", "image": p.get("image_url"), "images": p.get("images") or [], "bestseller": p.get("bestseller", False)} for p in items],
        "products": fulfilment.product_list(),
        "discount": config.DISCOUNT_PCT,
        "whatsapp": config.WHATSAPP,
        "total": len(prods),
    }


@app.get("/api/example/{scene_id}.jpg")
async def api_example(scene_id: str):
    """Imagen de ejemplo de una escena: la del catálogo (Supabase) o la generada en /admin/ejemplos."""
    s = await catalog.get_product(scene_id)
    if s and s.get("image_url"):
        return RedirectResponse(s["image_url"], status_code=302)
    p = EXAMPLES / f"{scene_id}.jpg"
    if not p.exists():
        p = STATIC / "examples" / f"{scene_id}.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml")
async def sitemap():
    prods, cols = await catalog.get_catalog()
    urls = [f"{config.BASE_URL}/"] + [f"{config.BASE_URL}/coleccion/{c['slug']}" for c in cols] + [f"{config.BASE_URL}/p/{p['slug']}" for p in prods]
    body = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    return Response(body, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    return Response(f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /api/\nSitemap: {config.BASE_URL}/sitemap.xml\n", media_type="text/plain")


def _admin(token: str):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)


@app.post("/admin/import")
async def admin_import(token: str = "", start: int = 0, limit: int = 50):
    """Adapta productos del catálogo polaco a España y los guarda en Supabase."""
    _admin(token)
    await catalog.ensure_collections()
    return await catalog.import_from_polish(start, limit)


@app.post("/admin/generate-images")
async def admin_generate_images(token: str = "", limit: int = 10, before_after: bool = True, redo: bool = False, slugs: str = ""):
    """Genera la imagen de catálogo (y mockups) de los productos que aún no la tienen."""
    _admin(token)
    if not catalog.ENABLED:
        raise HTTPException(400, "Supabase no configurado")
    params = {"select": "slug,title,group,scene_prompt,short_desc,images", "active": "eq.true", "order": "sort.asc", "limit": str(limit)}
    if slugs:
        params["slug"] = f"in.({slugs})"
    if not redo:
        params["image_url"] = "is.null"
    rows = await catalog._get("car_products", params)
    if redo:  # rehacer solo las que no tienen antes/después (5 imágenes)
        rows = [x for x in rows if len(x.get("images") or []) < 5]
    done, errors = [], []
    for r in rows:
        try:
            base = f"{catalog.SUPABASE_URL}/storage/v1/object/public/caricaturas/{r['slug']}"
            import httpx as _hx
            async with _hx.AsyncClient(timeout=20) as c:
                already = (await c.head(f"{base}/poster.jpg")).status_code == 200
            if already and not before_after:  # ya generada: solo falta apuntar la fila
                urls = {k: f"{base}/{k}.jpg" for k in ("main", "wall", "brick", "poster")}
                urls["art"] = urls["main"]
            else:
                prompt = r["scene_prompt"] or r["short_desc"]
                async with _sem:
                    if before_after:
                        faces = await catalog.list_faces()
                        if (r.get("group") or "el") == "pareja":
                            f1 = catalog.pick_face(faces, "ella", r.get("title") or "", r["slug"])
                            f2 = catalog.pick_face(faces, "el", r.get("title") or "", r["slug"] + "x")
                            photo = [await catalog.face_image(f1), await catalog.face_image(f2)] if f1 and f2 else await imaging.generate_photo(prompt)
                        else:
                            face = catalog.pick_face(faces, r.get("group") or "el", r.get("title") or "", r["slug"])
                            photo = await catalog.face_image(face) if face else await imaging.generate_photo(prompt)
                        art = await imaging.generate(photo, "", prompt, "", quality=config.env("CATALOG_IMAGE_QUALITY", "medium"))
                    else:
                        photo = None
                        art = await imaging.generate_from_text(prompt)
                mocks = imaging.make_mockups(art, photo)
                if photo is not None:
                    for i, pimg in enumerate(photo if isinstance(photo, list) else [photo]):
                        pj = pimg.copy(); pj.thumbnail((600, 600))
                        mocks["photo" if i == 0 else f"photo{i+1}"] = imaging._jpeg(pj, 85)
                urls = {}
                for k, data in mocks.items():
                    urls[k] = await catalog.upload_image(f"{r['slug']}/{k}.jpg", data)
            imgs = [urls["main"], urls.get("art", urls["main"]), urls["wall"], urls["brick"], urls["poster"]]
            await catalog._patch("car_products", "slug", r["slug"], {"image_url": urls["main"], "images": imgs, "updated_at": "now()"})
            done.append(r["slug"])
        except Exception as e:  # noqa: BLE001
            errors.append({"slug": r["slug"], "error": str(e)[:200]})
    catalog._cache["t"] = 0
    return {"generated": done, "errors": errors, "remaining_hint": "repite la llamada hasta que generated venga vacío"}


@app.post("/admin/make-faces")
async def admin_make_faces(token: str = "", per_band: int = 3):
    """Genera el banco de caras: por género y franja de edad, per_band fotos (24 en total con 2)."""
    _admin(token)
    existing = set(await catalog.list_faces())
    made, errors = [], []
    for gender in ("mujer", "hombre"):
        for age in catalog.AGE_BANDS:
            for n in range(1, per_band + 1):
                name = f"{gender}-{age}-{n}.jpg"
                if name in existing:
                    continue
                try:
                    async with _sem:
                        img = await imaging.generate_photo("", gender, age)
                    img.thumbnail((900, 900))
                    await catalog.upload_image(f"_faces/{name}", imaging._jpeg(img, 88))
                    made.append(name)
                except Exception as e:  # noqa: BLE001
                    errors.append({"face": name, "error": str(e)[:200]})
    catalog._faces_cache.clear()
    return {"made": made, "errors": errors, "total": len(await catalog.list_faces())}


@app.post("/admin/make-template")
async def admin_make_template(token: str = ""):
    """Genera con IA la plantilla fotorrealista (lienzo verde + móvil azul), detecta la geometría y la guarda en Supabase."""
    _admin(token)
    tpl = await imaging.generate_template()
    geo = imaging.detect_template(tpl)
    buf = io.BytesIO(); tpl.save(buf, format="PNG")
    await catalog.upload_image("_template/template.png", buf.getvalue(), "image/png")
    import json as _json
    await catalog.upload_image("_template/geometry.json", _json.dumps(geo).encode(), "application/json")
    imaging._TPL_CACHE.clear()
    # vista previa con una imagen cualquiera
    sample = Image.new("RGB", (900, 1200), (210, 140, 90)); ImageDraw_ = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).ImageDraw
    photo = Image.new("RGB", (600, 600), (90, 140, 200))
    prev = imaging.compose_with_template(tpl, geo, sample, photo)
    pb = io.BytesIO(); prev.save(pb, format="JPEG", quality=85)
    url = await catalog.upload_image("_template/preview.jpg", pb.getvalue())
    return {"geometry": geo, "preview": url + f"?t={int(asyncio.get_event_loop().time())}", "template": url.replace("preview.jpg", "template.png")}


@app.post("/admin/dedupe-titles")
async def admin_dedupe(token: str = ""):
    _admin(token)
    return await catalog.dedupe_titles()


@app.get("/admin/models")
async def admin_models(token: str = ""):
    """Lista los modelos de OpenAI disponibles para esta clave y prueba el de texto configurado."""
    _admin(token)
    import httpx as _hx
    async with _hx.AsyncClient(timeout=60) as c:
        r = await c.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"})
        models = sorted(m["id"] for m in r.json().get("data", [])) if r.status_code == 200 else [f"error {r.status_code}: {r.text[:200]}"]
        t = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json={"model": catalog.OPENAI_TEXT_MODEL, "messages": [{"role": "user", "content": "Responde solo: ok"}]})
    return {"text_model": catalog.OPENAI_TEXT_MODEL, "test_status": t.status_code, "test_body": t.text[:400], "models": [m for m in models if "gpt" in m or "o" in m[:2]]}


_bg = {"running": False, "done": 0, "errors": [], "started": None}


async def _bg_worker(token: str, queue: list):
    while queue:
        slug = queue.pop(0)
        try:
            r = await admin_generate_images(token=token, limit=1, slugs=slug)
            _bg["done"] += len(r["generated"]); _bg["errors"] += r["errors"]
        except Exception as e:  # noqa: BLE001
            _bg["errors"].append({"slug": slug, "error": str(e)[:200]})


@app.post("/admin/generate-bg")
async def admin_generate_bg(token: str = "", workers: int = 3):
    """Genera en el servidor (no depende de tener la pestaña abierta), 3 a la vez."""
    _admin(token)
    if _bg["running"]:
        return {"already_running": True, **{k: v for k, v in _bg.items() if k != "errors"}, "errors": len(_bg["errors"])}
    rows = await catalog._get("car_products", {"select": "slug", "active": "eq.true", "image_url": "is.null", "order": "sort.asc", "limit": "5000"})
    queue = [r["slug"] for r in rows]

    async def run():
        _bg.update(running=True, done=0, errors=[], started=time.time())
        try:
            await asyncio.gather(*[_bg_worker(token, queue) for _ in range(max(1, min(workers, 3)))])
        finally:
            _bg["running"] = False
            catalog._cache["t"] = 0

    asyncio.create_task(run())
    return {"started": True, "pending": len(queue)}


_rooms_bg = {"running": False, "done": 0, "errors": []}


def _room_shots(art_bytes: bytes) -> dict:
    from . import rooms
    art = Image.open(io.BytesIO(art_bytes)).convert("RGB")
    out = {}
    for name in rooms.ROOMS:
        tpl = rooms.room(name)
        quad, _ = rooms.detect_green(tpl)
        img = rooms.in_room(tpl, quad, art, "none", "lienzo")
        out[name] = imaging._jpeg(img, 86)
    return out


@app.post("/admin/room-mockups")
async def admin_room_mockups(token: str = "", workers: int = 3, redo: bool = False):
    """Añade a cada producto 2 fotos del cuadro colgado en una estancia (sin coste de IA)."""
    _admin(token)
    if _rooms_bg["running"]:
        return {"already_running": True, "done": _rooms_bg["done"], "errors": _rooms_bg["errors"][-3:]}
    rows = await catalog._get("car_products", {"select": "slug,images", "image_url": "not.is.null", "limit": "5000"})
    queue = [r for r in rows if redo or not any("room-" in u for u in (r.get("images") or []))]
    import httpx as _hx

    async def one(r):
        base = f"{catalog.SUPABASE_URL}/storage/v1/object/public/caricaturas/{r['slug']}"
        try:
            async with _hx.AsyncClient(timeout=60) as c:
                art = (await c.get(f"{base}/art.jpg")).content
            shots = await asyncio.to_thread(_room_shots, art)
            urls = [await catalog.upload_image(f"{r['slug']}/room-{k}.jpg", v) for k, v in shots.items()]
            imgs = [u for u in (r.get("images") or []) if "room-" not in u]
            imgs = imgs[:1] + urls[:1] + imgs[1:2] + urls[1:] + imgs[2:]
            await catalog._patch("car_products", "slug", r["slug"], {"images": imgs})
            _rooms_bg["done"] += 1
        except Exception as e:  # noqa: BLE001
            _rooms_bg["errors"].append({"slug": r["slug"], "error": str(e)[:200]})

    async def worker():
        while queue:
            await one(queue.pop(0))

    async def run():
        _rooms_bg.update(running=True, done=0, errors=[])
        try:
            await asyncio.gather(*[worker() for _ in range(max(1, min(workers, 4)))])
        finally:
            _rooms_bg["running"] = False; catalog._cache["t"] = 0

    asyncio.create_task(run())
    return {"started": True, "pending": len(queue)}


_main_bg = {"running": False, "done": 0, "errors": []}


@app.post("/admin/remake-main")
async def admin_remake_main(token: str = "", workers: int = 3):
    """Rehace la foto principal (lienzo + móvil + "tu foto") de todos los productos, sin IA."""
    _admin(token)
    if _main_bg["running"]:
        return {"already_running": True, "done": _main_bg["done"]}
    rows = await catalog._get("car_products", {"select": "slug,group", "image_url": "not.is.null", "limit": "5000"})
    queue = list(rows)
    import httpx as _hx

    async def one(r):
        base = f"{catalog.SUPABASE_URL}/storage/v1/object/public/caricaturas/{r['slug']}"
        try:
            async with _hx.AsyncClient(timeout=60) as c:
                art = Image.open(io.BytesIO((await c.get(f"{base}/art.jpg")).content)).convert("RGB")
                photos = [Image.open(io.BytesIO((await c.get(f"{base}/photo.jpg")).content)).convert("RGB")]
                r2 = await c.get(f"{base}/photo2.jpg")
                if r2.status_code == 200 and r2.headers.get("content-type", "").startswith("image"):
                    photos.append(Image.open(io.BytesIO(r2.content)).convert("RGB"))
            img = await asyncio.to_thread(imaging.compose_main, art, photos if len(photos) > 1 else photos[0])
            await catalog.upload_image(f"{r['slug']}/main.jpg", imaging._jpeg(img, 86))
            _main_bg["done"] += 1
        except Exception as e:  # noqa: BLE001
            _main_bg["errors"].append({"slug": r["slug"], "error": str(e)[:200]})

    async def worker():
        while queue:
            await one(queue.pop(0))

    async def run():
        _main_bg.update(running=True, done=0, errors=[])
        try:
            await asyncio.gather(*[worker() for _ in range(max(1, min(workers, 4)))])
        finally:
            _main_bg["running"] = False

    asyncio.create_task(run())
    return {"started": True, "pending": len(queue)}


@app.get("/admin/catalog-status")
async def admin_catalog_status(token: str = ""):
    _admin(token)
    if not catalog.ENABLED:
        return {"supabase": False}
    total = await catalog._get("car_products", {"select": "slug", "limit": "5000"})
    with_img = await catalog._get("car_products", {"select": "slug", "image_url": "not.is.null", "limit": "5000"})
    return {"supabase": True, "products": len(total), "with_image": len(with_img), "source_total": 436, "bg_running": _bg["running"], "bg_errors": _bg["errors"][-5:], "rooms_running": _rooms_bg["running"], "rooms_done": _rooms_bg["done"], "rooms_errors": _rooms_bg["errors"][-3:], "main_running": _main_bg["running"], "main_done": _main_bg["done"], "main_errors": _main_bg["errors"][-3:]}


@app.get("/admin/catalogo", response_class=HTMLResponse)
async def admin_catalog_page(token: str = ""):
    _admin(token)
    return _page("admin-catalogo.html")


@app.get("/admin/ejemplos", response_class=HTMLResponse)
async def admin_examples_page(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    return _page("admin-ejemplos.html")


@app.post("/admin/example")
async def admin_example(photo: UploadFile = File(...), scene: str = Form(...), dedication: str = Form(""), token: str = Form("")):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    s = scenes.SCENE_BY_ID.get(scene)
    if not s:
        raise HTTPException(404)
    img = imaging.load_and_normalize(await photo.read())
    async with _sem:
        result = await imaging.generate(img, "", s["prompt"], dedication)
    if dedication:
        result = imaging.add_dedication(result, dedication)
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    result.save(EXAMPLES / f"{scene}.png", format="PNG")
    web = result.copy(); web.thumbnail((1200, 1200)); web.save(EXAMPLES / f"{scene}.jpg", format="JPEG", quality=88)
    return {"url": f"/api/example/{scene}.jpg?t={int(asyncio.get_event_loop().time())}", "file": f"{scene}.png"}


@app.get("/admin/examples.zip")
async def admin_examples_zip(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(EXAMPLES.glob("*")) if EXAMPLES.exists() else []:
            z.write(p, p.name)
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="ejemplos.zip"'})


@app.get("/gracias", response_class=HTMLResponse)
async def gracias(job: str = Query(...), session_id: str = "", demo: str = ""):
    meta = storage.read_meta(job)
    if not meta:
        raise HTTPException(404, "Este pedido ya no existe.")
    if not meta.get("paid") and session_id:
        try:
            fulfilment.confirm_from_session(job, session_id)
        except Exception as e:  # noqa: BLE001
            log.warning("confirmación Stripe falló: %s", e)
    meta = storage.read_meta(job) or {}
    if meta.get("paid"):
        await fulfilment.fulfil(job)
        await fulfilment.notify_paid(job)
    return _page("gracias.html")


@app.get("/api/config")
async def api_config():
    return {
        "brand": config.BRAND_NAME,
        "demo": config.DEMO_MODE,
        "payments": config.PAYMENTS_ENABLED,
        "print": config.PRINT_ENABLED,
        "prices": {k: v["cents"] for k, v in fulfilment.PRODUCTS.items()},
    }


FREE_TRIES = 3          # pruebas gratis por diseño y persona (IP) cada 24 h
FREE_TRIES_DAY = 8      # tope total por IP y día, para cortar abusos
_TRIES: dict[str, list[tuple[float, str]]] = {}


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "")).split(",")[0].strip()


@app.post("/api/generate")
async def api_generate(request: Request, photo: UploadFile = File(...), notes: str = Form(""), scene: str = Form("clasica"), dedication: str = Form("")):
    import time as _t
    ip = _client_ip(request); now = _t.time()
    hist = [h for h in _TRIES.get(ip, []) if now - h[0] < 86400]
    if sum(1 for h in hist if h[1] == scene) >= FREE_TRIES:
        raise HTTPException(429, "Has usado las 3 pruebas gratuitas de este diseño. Si quieres otra, escríbenos a hola@caricaturea.com.")
    if len(hist) >= FREE_TRIES_DAY:
        raise HTTPException(429, "Has llegado al máximo de pruebas gratuitas de hoy. Escríbenos a hola@caricaturea.com y te ayudamos.")
    hist.append((now, scene)); _TRIES[ip] = hist
    prod = await catalog.get_product(scene)
    if prod:
        scene_data = {"id": prod["slug"], "prompt": prod.get("scene_prompt") or prod.get("short_desc") or ""}
    else:
        s = scenes.SCENE_BY_ID.get(scene) or scenes.SCENE_BY_ID["clasica"]
        scene_data = {"id": s["id"], "prompt": s["prompt"]}
    dedication = " ".join(dedication.split())[:60]
    storage.cleanup()
    data = await photo.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "La foto pesa más de 12 MB. Prueba con otra o hazle una captura.")
    try:
        img = imaging.load_and_normalize(data)
    except Exception:
        raise HTTPException(400, "No he podido leer la imagen. Sube un JPG, PNG o HEIC convertido a JPG.")
    if min(img.size) < 400:
        raise HTTPException(400, "La foto es muy pequeña: necesitamos al menos 400 px de lado para ver bien la cara.")
    job_id, d = storage.create_job()
    storage.update_meta(job_id, status="generating", notes=notes[:300], scene=scene_data["id"], dedication=dedication)
    try:
        async with _sem:
            result = await imaging.generate(img, notes, scene_data["prompt"], dedication)
        if dedication:
            result = imaging.add_dedication(result, dedication)
    except Exception as e:  # noqa: BLE001
        log.exception("generación falló")
        storage.update_meta(job_id, status="error", error=str(e)[:300])
        raise HTTPException(502, "La caricatura no ha salido. No se te ha cobrado nada; prueba otra vez con otra foto.")
    result.save(d / "result.png", format="PNG")
    (d / "preview.jpg").write_bytes(imaging.make_preview(result))
    storage.update_meta(job_id, status="previewed", width=result.width, height=result.height)
    await asyncio.to_thread(storage.backup, job_id)
    # La foto original no se guarda: solo se usa para generar.
    return {"job_id": job_id, "preview_url": f"/api/preview/{job_id}.jpg", "demo": config.DEMO_MODE}


@app.get("/api/preview/{job_id}.jpg")
async def api_preview(job_id: str):
    try:
        p = storage.ensure_file(job_id, "preview.jpg")
    except ValueError:
        raise HTTPException(404)
    if not p.exists():
        raise HTTPException(404, "Esta vista previa ha caducado.")
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})


@app.post("/api/checkout")
async def api_checkout(request: Request):
    body = await request.json()
    job_id = body.get("job_id", "")
    product = body.get("product", "canvas")
    if product not in fulfilment.PRODUCTS:
        raise HTTPException(400, "Producto desconocido.")
    meta = storage.read_meta(job_id)
    if not meta or not (storage.job_dir(job_id) / "result.png").exists():
        raise HTTPException(404, "La caricatura ha caducado. Vuelve a subir la foto.")
    try:
        url = fulfilment.create_checkout(job_id, product)
    except Exception as e:  # noqa: BLE001
        log.exception("checkout falló")
        raise HTTPException(502, f"No se ha podido iniciar el pago: {str(e)[:120]}")
    return {"url": url}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    if not config.PAYMENTS_ENABLED:
        return JSONResponse({"ok": False, "reason": "stripe desactivado"})
    payload = await request.body()
    stripe = fulfilment.stripe_client()
    try:
        if config.STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, stripe_signature, config.STRIPE_WEBHOOK_SECRET)
        else:
            import json
            event = json.loads(payload)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"firma inválida: {e}")
    event = fulfilment._as_dict(event)
    if event["type"] == "checkout.session.completed":
        session = fulfilment._as_dict(event["data"]["object"])
        job_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("job_id")
        if job_id and storage.read_meta(job_id):
            fulfilment.mark_paid(job_id, session)
            await fulfilment.fulfil(job_id)
            await fulfilment.notify_paid(job_id)
    return {"ok": True}


def _paid_result(job_id: str) -> Path:
    meta = storage.read_meta(job_id)
    if not meta or not meta.get("paid"):
        raise HTTPException(403, "Este archivo solo está disponible tras el pago.")
    p = storage.ensure_file(job_id, "result.png")
    if not p.exists():
        raise HTTPException(404, "El archivo ya ha caducado.")
    return p


@app.get("/api/download/{job_id}.png")
async def api_download(job_id: str):
    p = _paid_result(job_id)
    data = imaging.prepare_digital_file(Image.open(p))
    return Response(data, media_type="image/png", headers={"Content-Disposition": f'attachment; filename="caricatura-{job_id[:6]}.png"'})


@app.get("/api/print-file/{job_id}.png")
async def api_print_file(job_id: str):
    p = _paid_result(job_id)
    meta = storage.read_meta(job_id) or {}
    prod = fulfilment.PRODUCTS.get(meta.get("product") or "canvas_30x40") or fulfilment.PRODUCTS["canvas_30x40"]
    mm = prod.get("mm", (300, 400))
    data = imaging.prepare_print_file(Image.open(p), mm[0], mm[1], prod.get("bleed", 10))
    return Response(data, media_type="image/png")


@app.get("/api/reviews")
async def api_reviews():
    if not catalog.ENABLED:
        return {"reviews": []}
    rows = await catalog._get("car_reviews", {"select": "name,rating,body,product,verified,created_at,photo_url", "approved": "eq.true", "order": "created_at.desc", "limit": "100"})
    return {"reviews": rows}


@app.post("/api/reviews")
async def api_review_create(name: str = Form(...), body: str = Form(...), rating: int = Form(5), product: str = Form(""), job: str = Form(""),
                            photo: UploadFile | None = File(None)):
    name = name.strip()[:60]; body = body.strip()[:1500]; rating = max(1, min(5, rating))
    if not name or len(body) < 3:
        raise HTTPException(400, "Faltan datos")
    job = job[:40]
    verified = False
    if job:
        try:
            verified = bool((storage.read_meta(job) or {}).get("paid"))
        except ValueError:
            verified = False
    photo_url = None
    if photo is not None and photo.filename:
        data = await photo.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(400, "La foto es demasiado grande")
        try:
            im = Image.open(io.BytesIO(data)); im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((1400, 1400))
            import secrets as _s
            photo_url = await catalog.upload_image(f"_reviews/{_s.token_hex(8)}.jpg", imaging._jpeg(im, 85))
        except Exception:
            raise HTTPException(400, "No se ha podido leer la foto")
    row = {"name": name, "rating": rating, "body": body, "product": product.strip()[:120] or None, "job_id": job or None, "verified": verified, "photo_url": photo_url}
    await catalog._upsert("car_reviews", [row])
    from . import mail
    await mail.admin_alert("Nueva reseña para revisar", f"{name} ({rating}★): {body}{' [con foto]' if photo_url else ''}\n\nApruébala en {config.BASE_URL}/admin/reviews?token={config.ADMIN_TOKEN}")
    return {"ok": True}


@app.get("/admin/reviews", response_class=HTMLResponse)
async def admin_reviews(token: str = ""):
    _admin(token)
    rows = await catalog._get("car_reviews", {"select": "*", "order": "created_at.desc", "limit": "200"})
    import html as _h
    trs = "".join(f"<tr><td>{r['created_at'][:10]}</td><td>{_h.escape(r['name'])}</td><td>{'★'*r['rating']}</td><td>{_h.escape(r['body'])}{f'<br><img src="{r["photo_url"]}" style="max-width:160px">' if r.get('photo_url') else ''}</td><td>{'✓' if r['verified'] else ''}</td>"
                  f"<td>{'publicada' if r['approved'] else 'pendiente'}</td><td><button onclick=\"act({r['id']},{str(not r['approved']).lower()})\">{'Ocultar' if r['approved'] else 'Publicar'}</button></td></tr>" for r in rows)
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><title>Reseñas</title><body style="font-family:sans-serif;padding:20px"><h2>Reseñas</h2>
<table border=1 cellpadding=6 style="border-collapse:collapse"><tr><th>Fecha</th><th>Nombre</th><th>Nota</th><th>Texto</th><th>Verif.</th><th>Estado</th><th></th></tr>{trs}</table>
<script>async function act(id,ap){{await fetch('/admin/reviews/'+id+'?token={token}&approved='+ap,{{method:'POST'}});location.reload();}}</script>""")


@app.post("/admin/reviews/{rid}")
async def admin_review_set(rid: int, token: str = "", approved: bool = True):
    _admin(token)
    await catalog._patch("car_reviews", "id", str(rid), {"approved": approved})
    return {"ok": True}


@app.post("/api/gelato/webhook")
async def gelato_webhook(request: Request, key: str = ""):
    if not config.env("GELATO_WEBHOOK_KEY") or key != config.env("GELATO_WEBHOOK_KEY"):
        raise HTTPException(403)
    return await fulfilment.gelato_event(await request.json())


@app.post("/admin/test-email")
async def admin_test_email(token: str = "", to: str = ""):
    _admin(token)
    from . import mail
    ok = await mail.send(to or mail.ADMIN, "Prueba de email de Caricaturea", ["Si te llega esto, los emails de pedidos funcionan."])
    return {"smtp": mail.ENABLED, "sent": ok}


@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    meta = storage.read_meta(job_id)
    if not meta:
        raise HTTPException(404)
    out = {k: meta.get(k) for k in ("status", "paid", "product", "gelato_order", "gelato_status")}
    prod = fulfilment.PRODUCTS.get(meta.get("product") or "")
    out["amount"] = (prod["cents"] / 100) if prod else None
    return out


@app.get("/admin/orders")
async def admin_orders(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    return storage.list_jobs()


@app.get("/salud")
async def salud():
    return {"ok": True, "demo": config.DEMO_MODE}
