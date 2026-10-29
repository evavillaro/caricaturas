"""Tienda de cuadros religiosos modernos (Cuadros con Alma).

Arranque: uvicorn fe.main:app
"""
import asyncio
import io
import json
import logging
import re
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from . import art, config, content, db, seed, shop

log = logging.getLogger("fe")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=config.BRAND, docs_url=None, redoc_url=None)
from pathlib import Path
HERE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
T = Jinja2Templates(directory=HERE / "templates")

COLS = {c[0]: {"slug": c[0], "title": c[1], "group": c[2], "h1": c[3], "intro": c[4]} for c in seed.COLLECTIONS}
MENU = {}
for c in seed.COLLECTIONS:
    MENU.setdefault(c[2], []).append(COLS[c[0]])


def eur(n) -> str:
    n = float(n)
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s.replace(",00", "") + " €"


T.env.filters["eur"] = eur


def ctx(request: Request, **kw) -> dict:
    base = {
        "request": request, "brand": config.BRAND, "tagline": config.TAGLINE, "menu": MENU, "base_url": config.BASE_URL, "email": config.CONTACT_EMAIL,
        "discount": config.WELCOME_DISCOUNT_PCT, "year": time.strftime("%Y"),
        "ids": {"ga4": config.GA4_ID, "gads": config.GADS_ID, "gads_label": config.GADS_LABEL, "meta": config.META_PIXEL_ID,
                "clarity": config.CLARITY_ID, "pinterest": config.PINTEREST_TAG_ID},
    }
    base.update(kw)
    return base


def card(p: dict) -> dict:
    imgs = p.get("images") or []
    main = next((i["url"] for i in imgs if i.get("kind") == "main"), None)
    room = next((i["url"] for i in imgs if i.get("kind") == "room"), None)
    return {**p, "img": main, "img2": room, "from_price": config.min_price(p["kind"])}


async def reviews_for(slug: str | None = None, limit: int = 30) -> list[dict]:
    if not db.ENABLED:
        return []
    params = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
    if slug:
        params["product_slug"] = f"eq.{slug}"
    try:
        return await db.get("fe_reviews", params)
    except Exception:
        return []


# --- páginas -------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    prods = await db.products()
    best = [card(p) for p in prods if p.get("bestseller")][:20]
    hero = next((i["url"] for p in prods if p.get("bestseller") for i in (p.get("images") or []) if i.get("kind") == "room"), None)
    revs = await reviews_for(limit=20)
    return T.TemplateResponse(request, "home.html", ctx(request, best=best, hero=hero, reviews=revs, title=f"{config.BRAND} · {config.TAGLINE} · Cuadros religiosos modernos",
                                                 description="Cuadros religiosos modernos en lienzo y láminas enmarcadas: arte cristiano y católico en tonos neutros para casas modernas. Envío gratis."))


@app.get("/coleccion/{slug}", response_class=HTMLResponse)
async def collection(request: Request, slug: str, orden: str = ""):
    c = COLS.get(slug)
    if not c:
        raise HTTPException(404)
    prods = [card(p) for p in await db.products() if slug == "todos" or slug in (p.get("collections") or [])]
    if orden == "precio":
        prods.sort(key=lambda p: p["from_price"])
    return T.TemplateResponse(request, "collection.html", ctx(request, c=c, products=prods, title=f"{c['h1']} · {config.BRAND}", description=c["intro"]))


@app.get("/cuadro/{slug}", response_class=HTMLResponse)
async def product_page(request: Request, slug: str):
    p = await db.product(slug)
    if not p:
        raise HTTPException(404)
    p = card(p)
    sizes = [{"key": s[0], "label": f"{s[0]} cm" if p["orient"] == "v" else f"{s[0].split('x')[1]}x{s[0].split('x')[0]} cm"} for s in config.sizes_for(p["kind"])]
    frames = [{"key": f[0], "label": f[1]} for f in config.frames_for(p["kind"])]
    prices = {f"{s['key']}|{f['key']}": config.price_eur(p["kind"], s["key"], f["key"]) for s in sizes for f in frames}
    c = p.get("content") or {}
    if not c.get("intro"):
        c = content.fallback(p)
    related = [card(x) for x in await db.products() if x["slug"] != slug and x.get("theme") == p.get("theme")][:3]
    if len(related) < 3:
        related += [card(x) for x in await db.products() if x.get("bestseller") and x["slug"] != slug and x not in related][: 3 - len(related)]
    revs = await reviews_for(slug)
    return T.TemplateResponse(request, "product.html", ctx(request, p=p, sizes=sizes, frames=frames, prices=json.dumps(prices), c=c, related=related, reviews=revs,
                                                    title=f"{p['title']} · Cuadro religioso moderno · {config.BRAND}", description=(c.get("intro") or "")[:155],
                                                    og_image=p.get("img")))


@app.get("/carrito", response_class=HTMLResponse)
async def cart_page(request: Request):
    return T.TemplateResponse(request, "cart.html", ctx(request, title=f"Carrito · {config.BRAND}"))


@app.get("/gracias", response_class=HTMLResponse)
async def thanks(request: Request, pedido: str = "", session_id: str = ""):
    o = None
    if pedido and db.ENABLED:
        try:
            o = await (shop.confirm(pedido, session_id) if session_id else shop.get_order(pedido))
        except Exception as e:
            log.warning("confirm %s: %s", pedido, e)
    return T.TemplateResponse(request, "thanks.html", ctx(request, o=o, title=f"Gracias · {config.BRAND}"))


@app.get("/encuentra-tu-cuadro", response_class=HTMLResponse)
async def quiz(request: Request):
    prods = [card(p) for p in await db.products()]
    slim = [{"slug": p["slug"], "title": p["title"], "img": p["img"], "theme": p["theme"], "palette": p["palette"], "orient": p["orient"],
             "collections": p.get("collections") or [], "from_price": p["from_price"], "best": p.get("bestseller")} for p in prods]
    return T.TemplateResponse(request, "quiz.html", ctx(request, products=json.dumps(slim), title=f"¿Cuál es tu cuadro? · {config.BRAND}"))


PAGES = {
    "preguntas-frecuentes": "Preguntas frecuentes", "nuestra-historia": "Nuestra historia", "envios": "Política de envíos",
    "devoluciones": "Devoluciones y cambios", "privacidad": "Política de privacidad", "aviso-legal": "Aviso legal",
    "condiciones": "Condiciones de venta", "contacto": "Ayuda y contacto",
}


@app.get("/p/{page}", response_class=HTMLResponse)
async def static_page(request: Request, page: str):
    if page not in PAGES:
        raise HTTPException(404)
    return T.TemplateResponse(request, f"pages/{page}.html", ctx(request, page_title=PAGES[page], title=f"{PAGES[page]} · {config.BRAND}"))


# --- API ---------------------------------------------------------------------------

@app.get("/api/products")
async def api_products():
    return [{"slug": p["slug"], "title": p["title"], "kind": p["kind"], "img": card(p)["img"]} for p in await db.products()]


@app.post("/api/checkout")
async def api_checkout(request: Request):
    body = await request.json()
    try:
        url = await shop.create_checkout(body.get("items") or [], email=(body.get("email") or None), discount=bool(body.get("discount")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"url": url}


@app.post("/api/subscribe")
async def api_subscribe(request: Request):
    body = await request.json()
    email = str(body.get("email") or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "email no válido")
    if db.ENABLED:
        await db.upsert("fe_subscribers", [{"email": email, "source": str(body.get("source") or "popup")[:40]}], on_conflict="email")
    return {"ok": True, "code": "BIENVENIDA15"}


@app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    stripe = shop._stripe()
    try:
        ev = stripe.Webhook.construct_event(payload, sig, config.STRIPE_WEBHOOK_SECRET) if config.STRIPE_WEBHOOK_SECRET else json.loads(payload)
    except Exception:
        raise HTTPException(400, "firma no válida")
    ev = shop._as_dict(ev)
    if ev.get("type") == "checkout.session.completed":
        s = ev["data"]["object"]
        if (s.get("metadata") or {}).get("store") == "fe":
            o = await shop.mark_paid(s)
            if o:
                await shop.fulfil(o["id"])
    return {"ok": True}


@app.post("/api/gelato/webhook")
async def gelato_webhook(request: Request, key: str = ""):
    if not config.env("GELATO_WEBHOOK_KEY") or key != config.env("GELATO_WEBHOOK_KEY"):
        raise HTTPException(403)
    ev = await request.json()
    return await shop.gelato_event(ev)


@app.get("/api/print/{slug}/{size}/{frame}.jpg")
async def print_png(slug: str, size: str, frame: str):
    """Archivo de impresión para Gelato, generado al vuelo desde el original y cacheado en Storage."""
    p = await db.product(slug)
    if not p or not p.get("art_url"):
        raise HTTPException(404)
    path = f"{slug}/print-{size}-{frame}.jpg"
    url = db.public_url(path)
    async with httpx.AsyncClient(timeout=30) as c:
        h = await c.head(url)
    if h.status_code == 200:
        return RedirectResponse(url)
    src = Image.open(io.BytesIO(await db.download(p["art_url"]))).convert("RGB")
    data = await asyncio.to_thread(art.print_file, src, p["kind"], size, frame)
    await db.upload(path, data, "image/jpeg")
    return Response(data, media_type="image/jpeg")


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return f"User-agent: *\nDisallow: /admin\nDisallow: /api\nSitemap: {config.BASE_URL}/sitemap.xml\n"


@app.get("/sitemap.xml")
async def sitemap():
    urls = [f"{config.BASE_URL}/"] + [f"{config.BASE_URL}/coleccion/{c}" for c in COLS] + [f"{config.BASE_URL}/cuadro/{p['slug']}" for p in await db.products()]
    urls += [f"{config.BASE_URL}/p/{k}" for k in PAGES] + [f"{config.BASE_URL}/encuentra-tu-cuadro"]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    return Response(xml, media_type="application/xml")


# --- admin ---------------------------------------------------------------------------

def _auth(token: str):
    if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
        raise HTTPException(403)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, token: str = ""):
    _auth(token)
    return T.TemplateResponse(request, "admin.html", ctx(request, token=token, rooms=list(art.ROOM_TEMPLATES)))


@app.get("/admin/status")
async def admin_status(token: str = ""):
    _auth(token)
    prods = await db.products(force=True)
    rooms = await db.get_setting("rooms") or {}
    uids = await shop.gelato_uids()
    return {"supabase": db.ENABLED, "openai": bool(config.OPENAI_API_KEY), "stripe": bool(config.STRIPE_SECRET_KEY), "gelato": bool(config.GELATO_API_KEY),
            "products": len(prods), "with_art": sum(1 for p in prods if p.get("art_url")), "with_content": sum(1 for p in prods if (p.get("content") or {}).get("intro")),
            "rooms": sorted(rooms), "gelato_uids": len(uids), "bg_running": _bg["running"], "bg_done": _bg["done"], "bg_errors": _bg["errors"][-3:]}


@app.post("/admin/seed")
async def admin_seed(token: str = ""):
    _auth(token)
    return {"products": await db.seed_catalog()}


async def _load_rooms() -> dict:
    rooms = await db.get_setting("rooms") or {}
    out = {}
    changed = False
    for k, v in rooms.items():
        try:
            data = await db.download(v["url"])
            if not v["url"].startswith(db.URL):
                v["url"] = await db.upload(f"_rooms/{k}.png", data, "image/png"); changed = True
            out[k] = (Image.open(io.BytesIO(data)).convert("RGB"), v)
        except Exception:
            pass
    if changed:
        await db.set_setting("rooms", rooms)
    return out


@app.post("/admin/room")
async def admin_room(key: str, token: str = ""):
    """Genera (IA) una plantilla de estancia con el hueco verde y la guarda."""
    _auth(token)
    if key not in art.ROOM_TEMPLATES:
        raise HTTPException(400)
    img = await art.generate_room(key)
    quad, mask = art.detect_green(img)
    if not quad:
        raise HTTPException(422, "No se detecta el hueco verde; vuelve a pulsar")
    info = {"quad": quad, "size": img.size}
    if key == "sofa_tallas":
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        info["sofa"] = [min(xs), max(ys) + 4, max(xs), max(ys) + 40]
        img = art.clean_green(img, mask)
    url = await db.upload(f"_rooms/{key}.png", _png(img), "image/png")
    info["url"] = url
    rooms = await db.get_setting("rooms") or {}
    rooms[key] = info
    await db.set_setting("rooms", rooms)
    prev = await db.upload(f"_rooms/{key}-preview.jpg", art.jpeg(img, max_side=900))
    return {"ok": True, "preview": prev + f"?t={int(time.time())}", "info": info}


def _png(img) -> bytes:
    b = io.BytesIO(); img.save(b, format="PNG"); return b.getvalue()


async def build_images(p: dict, a: Image.Image, rooms: dict) -> list[dict]:
    """Todas las fotos de la ficha, en el orden de la referencia."""
    slug = p["slug"]; kind = p["kind"]; o = p["orient"]
    out = []
    t = int(time.time())

    async def up(name, img, kindtag, frame=None):
        url = await db.upload(f"{slug}/{name}.jpg", art.jpeg(img, 85, 1800))
        out.append({"url": f"{url}?v={t}", "kind": kindtag, **({"frame": frame} if frame else {})})

    main_frame = "natural"
    await up("main", await asyncio.to_thread(art.on_wall, a, main_frame, kind), "main", main_frame)
    room_keys = [k for k in rooms if k.endswith("_" + o)]
    for i, rk in enumerate(room_keys[:2]):
        tpl, info = rooms[rk]
        img = await asyncio.to_thread(art.in_room, tpl, info["quad"], a, main_frame, kind)
        await up(f"room{i+1}", img, "room")
        if i == 0:
            await up("closeup", await asyncio.to_thread(art.close_up, a), "detail")
    await up("frames", await asyncio.to_thread(art.frame_swatches, a, kind), "frames")
    sofa = rooms.get("sofa_tallas")
    await up("sizes", await asyncio.to_thread(art.sizes_chart, a, kind, sofa[0] if sofa else None, sofa[1] if sofa else None), "sizes")
    for f, _ in config.frames_for(kind):
        if f == main_frame:
            continue
        await up(f"frame-{f}", await asyncio.to_thread(art.on_wall, a, f, kind), "variant", f)
    for rk in room_keys[2:]:
        tpl, info = rooms[rk]
        await up(f"room-{rk}", await asyncio.to_thread(art.in_room, tpl, info["quad"], a, main_frame, kind), "room")
    return out


@app.post("/admin/art")
async def admin_art(token: str = "", limit: int = 2, slug: str = "", redo: bool = False):
    """Genera el diseño (IA) y todas las fotos de los productos que faltan."""
    _auth(token)
    prods = await db.products(force=True)
    todo = [p for p in prods if (p["slug"] == slug) or (not slug and (redo or not p.get("art_url")))][:limit]
    rooms = await _load_rooms()
    done = []
    for p in todo:
        try:
            a = await art.generate_art(p)
            art_url = await db.upload(f"{p['slug']}/art.jpg", art.jpeg(a, 96))
            imgs = await build_images(p, a, rooms)
            await db.patch("fe_products", "slug", p["slug"], {"art_url": art_url, "images": imgs})
            done.append({"slug": p["slug"], "main": imgs[0]["url"]})
        except Exception as e:
            log.exception("art %s", p["slug"])
            done.append({"slug": p["slug"], "error": str(e)[:300]})
    db.invalidate()
    left = sum(1 for p in await db.products(force=True) if not p.get("art_url"))
    return {"done": done, "left": left}


@app.post("/admin/remock")
async def admin_remock(token: str = "", limit: int = 10, offset: int = 0):
    """Rehace solo las fotos (sin coste de IA) a partir del diseño guardado."""
    _auth(token)
    prods = [p for p in await db.products(force=True) if p.get("art_url")][offset:offset + limit]
    rooms = await _load_rooms()
    done = []
    for p in prods:
        a = Image.open(io.BytesIO(await db.download(p["art_url"]))).convert("RGB")
        imgs = await build_images(p, a, rooms)
        await db.patch("fe_products", "slug", p["slug"], {"images": imgs})
        done.append(p["slug"])
    db.invalidate()
    return {"done": done}


@app.post("/admin/content")
async def admin_content(token: str = "", limit: int = 8, redo: bool = False):
    _auth(token)
    prods = [p for p in await db.products(force=True) if redo or not (p.get("content") or {}).get("intro")][:limit]
    res = await asyncio.gather(*[content.generate(p) for p in prods], return_exceptions=True)
    done = []
    for p, c in zip(prods, res):
        if isinstance(c, Exception):
            done.append({"slug": p["slug"], "error": str(c)[:200]}); continue
        await db.patch("fe_products", "slug", p["slug"], {"content": c})
        done.append(p["slug"])
    db.invalidate()
    left = sum(1 for p in await db.products(force=True) if not (p.get("content") or {}).get("intro"))
    return {"done": done, "left": left}


@app.api_route("/admin/gelato", methods=["GET", "POST"])
async def admin_gelato(request: Request, url: str, token: str = ""):
    """Proxy para explorar el catálogo de Gelato con la clave del servidor."""
    _auth(token)
    if not url.startswith("https://product.gelatoapis.com/") and not url.startswith("https://order.gelatoapis.com/"):
        raise HTTPException(400)
    body = await request.json() if request.method == "POST" else None
    code, data = await shop.gelato(request.method, url, body)
    return JSONResponse({"status": code, "data": data})


@app.post("/admin/gelato-uids")
async def admin_set_uids(request: Request, token: str = ""):
    _auth(token)
    uids = await request.json()
    await db.set_setting("gelato_uids", uids)
    return {"saved": len(uids)}


@app.get("/admin/orders")
async def admin_orders(token: str = ""):
    _auth(token)
    return await db.get("fe_orders", {"select": "*", "order": "created_at.desc", "limit": "100"})


@app.post("/admin/stripe-coupon")
async def admin_coupon(token: str = ""):
    """Crea (una vez) el cupón del 15 % y el código BIENVENIDA15 para la tienda de cuadros."""
    _auth(token)
    stripe = shop._stripe()
    existing = shop._as_dict(stripe.PromotionCode.list(code="BIENVENIDA15", limit=1))
    if existing.get("data"):
        return {"ok": True, "promotion_code": existing["data"][0]["id"], "existing": True}
    c = stripe.Coupon.create(percent_off=config.WELCOME_DISCOUNT_PCT, duration="once", name=f"Bienvenida {config.BRAND}")
    pc = stripe.PromotionCode.create(coupon=c.id, code="BIENVENIDA15", restrictions={"first_time_transaction": True})
    return {"ok": True, "coupon": c.id, "promotion_code": pc.id}


_bg = {"running": False, "done": 0, "errors": []}


@app.post("/admin/art-bg")
async def admin_art_bg(token: str = "", workers: int = 3):
    """Genera en el servidor todos los diseños que faltan, 3 a la vez (no hace falta la pestaña abierta)."""
    _auth(token)
    if _bg["running"]:
        return {"already_running": True, "done": _bg["done"], "errors": _bg["errors"][-5:]}
    queue = [p for p in await db.products(force=True) if not p.get("art_url")]
    rooms = await _load_rooms()

    async def one(p):
        try:
            a = await art.generate_art(p)
            art_url = await db.upload(f"{p['slug']}/art.jpg", art.jpeg(a, 96))
            imgs = await build_images(p, a, rooms)
            await db.patch("fe_products", "slug", p["slug"], {"art_url": art_url, "images": imgs})
            _bg["done"] += 1
        except Exception as e:  # noqa: BLE001
            log.exception("art %s", p["slug"]); _bg["errors"].append({"slug": p["slug"], "error": str(e)[:200]})

    async def worker():
        while queue:
            await one(queue.pop(0))

    async def run():
        _bg.update(running=True, done=0, errors=[])
        try:
            await asyncio.gather(*[worker() for _ in range(max(1, min(workers, 4)))])
        finally:
            _bg["running"] = False; db.invalidate()

    asyncio.create_task(run())
    return {"started": True, "pending": len(queue)}


@app.post("/admin/gelato-auto")
async def admin_gelato_auto(token: str = ""):
    """Busca en Gelato el UID de cada combinación tipo/tamaño/marco/orientación y los guarda."""
    _auth(token)
    base = "https://product.gelatoapis.com/v3/catalogs"
    uids, missing = {}, []
    color = {"natural": "natural-wood", "dark": "dark-wood", "black": "black", "gold": "gold", "white": "white"}
    for kind in ("lienzo", "lamina"):
        for size, a, b in config.sizes_for(kind):
            for orient in ("h", "v"):
                w, h = (b, a) if orient == "h" else (a, b)
                for frame, _ in config.frames_for(kind):
                    if kind == "lienzo" and frame == "none":
                        cat, flt = "canvas", {"CanvasFormat": [f"{w}x{h}-mm", f"{h}x{w}-mm"], "Orientation": ["hor" if orient == "h" else "ver"]}
                        pick = lambda u: "wood-fsc-2-cm" in u
                    elif kind == "lienzo":
                        cat, flt = "framed-canvas", {"CanvasFormat": [f"{w}x{h}-mm", f"{h}x{w}-mm"], "Orientation": ["hor" if orient == "h" else "ver"], "FrameColor": [color[frame]]}
                        pick = lambda u: "wood-fsc-2-cm" in u
                    else:
                        cat, flt = "mounted-framed-posters", {"PaperFormat": [f"{a}x{b}-mm"], "Orientation": ["hor" if orient == "h" else "ver"], "FrameColor": [color[frame]]}
                        pick = lambda u: "200-gsm-uncoated" in u and ("frm_wood" in u or frame == "gold")
                    code, data = await shop.gelato("POST", f"{base}/{cat}/products:search", {"attributeFilters": flt, "limit": 100})
                    cands = [p["productUid"] for p in (data.get("products") or [])] if code == 200 and isinstance(data, dict) else []
                    good = [u for u in cands if pick(u)] or cands
                    k = shop.uid_key(kind, size, frame, orient)
                    if good:
                        uids[k] = good[0]
                    else:
                        missing.append(k)
    await db.set_setting("gelato_uids", uids)
    return {"saved": len(uids), "missing": missing}


@app.post("/admin/test-email")
async def admin_test_email(token: str = "", to: str = ""):
    _auth(token)
    from . import mail
    demo = {"id": "FM-PRUEBA", "email": to or mail.ADMIN, "shipping": {"name": "Eva"},
            "items": [{"name": "El Buen Pastor · Lienzo 30x45 cm · Madera clara", "qty": 1, "cents": 10900}]}
    ok = await mail.order_confirmed(demo)
    return {"smtp": mail.ENABLED, "sent": ok, "to": demo["email"]}
