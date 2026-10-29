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
import io
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import catalog, config, fulfilment, imaging, scenes, storage

log = logging.getLogger("caricaturas")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=config.BRAND_NAME)
STATIC = Path(__file__).parent / "static"
EXAMPLES = config.DATA_DIR / "examples"
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
        "PAGE_TITLE": f"{config.BRAND_NAME} · Caricatura personalizada desde una foto, en lienzo",
        "H1": "Caricatura personalizada a partir de una foto",
        "INTRO": "Tu idea. Tu foto. Un regalo personal. Elige la escena, sube la foto y mira tu caricatura antes de pagar.",
    }
    repl.update(extra)
    for k, v in repl.items():
        html = html.replace("{{" + k + "}}", v)
    return HTMLResponse(html)


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
    return _page("index.html", CATEGORY=category, PAGE_TITLE=f"{cat['h1'] or cat['title']} · {config.BRAND_NAME}", H1=cat["h1"] or cat["title"], INTRO=cat.get("intro") or "")


@app.get("/p/{slug}", response_class=HTMLResponse)
async def product_page(slug: str):
    s = await catalog.get_product(slug)
    if not s:
        raise HTTPException(404)
    return _page("producto.html", SCENE_ID=s["slug"], SCENE_NAME=s["title"], SCENE_DESC=s.get("short_desc") or "", SCENE_HTML=s.get("description_html") or "", PAGE_TITLE=f"{s['title']} · {config.BRAND_NAME}")


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
async def admin_generate_images(token: str = "", limit: int = 10):
    """Genera la imagen de catálogo (y mockups) de los productos que aún no la tienen."""
    _admin(token)
    if not catalog.ENABLED:
        raise HTTPException(400, "Supabase no configurado")
    rows = await catalog._get("car_products", {"select": "slug,scene_prompt,short_desc", "image_url": "is.null", "active": "eq.true", "order": "sort.asc", "limit": str(limit)})
    done, errors = [], []
    for r in rows:
        try:
            async with _sem:
                art = await imaging.generate_from_text(r["scene_prompt"] or r["short_desc"])
            mocks = imaging.make_mockups(art)
            urls = {}
            for k, data in mocks.items():
                urls[k] = await catalog.upload_image(f"{r['slug']}/{k}.jpg", data)
            await catalog._upsert("car_products", [{"slug": r["slug"], "image_url": urls["main"], "images": [urls["main"], urls["wall"], urls["brick"], urls["poster"]], "updated_at": "now()"}])
            done.append(r["slug"])
        except Exception as e:  # noqa: BLE001
            errors.append({"slug": r["slug"], "error": str(e)[:200]})
    catalog._cache["t"] = 0
    return {"generated": done, "errors": errors, "remaining_hint": "repite la llamada hasta que generated venga vacío"}


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


@app.get("/admin/catalog-status")
async def admin_catalog_status(token: str = ""):
    _admin(token)
    if not catalog.ENABLED:
        return {"supabase": False}
    total = await catalog._get("car_products", {"select": "slug", "limit": "5000"})
    with_img = await catalog._get("car_products", {"select": "slug", "image_url": "not.is.null", "limit": "5000"})
    return {"supabase": True, "products": len(total), "with_image": len(with_img), "source_total": 436}


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


@app.post("/api/generate")
async def api_generate(photo: UploadFile = File(...), notes: str = Form(""), scene: str = Form("clasica"), dedication: str = Form("")):
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
    # La foto original no se guarda: solo se usa para generar.
    return {"job_id": job_id, "preview_url": f"/api/preview/{job_id}.jpg", "demo": config.DEMO_MODE}


@app.get("/api/preview/{job_id}.jpg")
async def api_preview(job_id: str):
    try:
        p = storage.job_dir(job_id) / "preview.jpg"
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
    return {"ok": True}


def _paid_result(job_id: str) -> Path:
    meta = storage.read_meta(job_id)
    if not meta or not meta.get("paid"):
        raise HTTPException(403, "Este archivo solo está disponible tras el pago.")
    p = storage.job_dir(job_id) / "result.png"
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


@app.get("/api/status/{job_id}")
async def api_status(job_id: str):
    meta = storage.read_meta(job_id)
    if not meta:
        raise HTTPException(404)
    return {k: meta.get(k) for k in ("status", "paid", "product", "gelato_order", "gelato_status")}


@app.get("/admin/orders")
async def admin_orders(token: str = ""):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)
    return storage.list_jobs()


@app.get("/salud")
async def salud():
    return {"ok": True, "demo": config.DEMO_MODE}
