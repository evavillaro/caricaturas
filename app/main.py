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

from . import config, fulfilment, imaging, scenes, storage

log = logging.getLogger("caricaturas")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=config.BRAND_NAME)
STATIC = Path(__file__).parent / "static"
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
        "CATEGORY": "",
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
async def category_page(category: str):
    cat = scenes.CATEGORIES.get(category)
    if not cat:
        raise HTTPException(404)
    return _page("index.html", CATEGORY=category, PAGE_TITLE=f"{cat['title']} · {config.BRAND_NAME}", H1=cat["title"], INTRO=cat["intro"])


@app.get("/api/scenes")
async def api_scenes(category: str = ""):
    return {"categories": [{"slug": k, **v} for k, v in scenes.CATEGORIES.items()], "scenes": scenes.scenes_for(category or None)}


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
    scene_data = scenes.SCENE_BY_ID.get(scene) or scenes.SCENE_BY_ID["clasica"]
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
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
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
