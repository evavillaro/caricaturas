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
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps

from . import art, config, content, db, seed, shop

log = logging.getLogger("fe")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title=config.BRAND, docs_url=None, redoc_url=None)
from pathlib import Path
HERE = Path(__file__).parent
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse("/static/favicon.ico", 301)


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


@app.middleware("http")
async def canonical_host(request: Request, call_next):
    """Si entran por *.onrender.com, redirige al dominio propio (salvo webhooks y admin)."""
    host = request.headers.get("host", "")
    path = request.url.path
    if request.headers.get("x-forwarded-proto") == "http" and not host.startswith(("localhost", "127.")):
        q = ("?" + request.url.query) if request.url.query else ""
        return RedirectResponse(f"https://{host}{path}{q}", status_code=301)
    if host.endswith(".onrender.com") and config.BASE_URL.startswith("https://") and ".onrender.com" not in config.BASE_URL \
            and not path.startswith(("/api/", "/admin", "/static/")):
        q = ("?" + request.url.query) if request.url.query else ""
        return RedirectResponse(config.BASE_URL + path + q, status_code=301)
    return await call_next(request)


def ld(obj) -> str:
    """JSON-LD seguro para incrustar en <script>."""
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def site_jsonld() -> str:
    org = {"@type": "Organization", "@id": f"{config.BASE_URL}/#org", "name": config.BRAND, "url": f"{config.BASE_URL}/",
           "logo": f"{config.BASE_URL}/static/icon-512.png", "email": config.CONTACT_EMAIL, "legalName": "Comartinvi S.L.",
           "description": "Tienda online de cuadros religiosos modernos: arte cristiano y católico contemporáneo en lienzo y lámina enmarcada, impreso bajo pedido en España.",
           "areaServed": ["ES", "EU", "US"], "knowsLanguage": "es"}
    web = {"@type": "WebSite", "@id": f"{config.BASE_URL}/#web", "name": config.BRAND, "alternateName": f"{config.BRAND} · {config.TAGLINE}",
           "url": f"{config.BASE_URL}/", "inLanguage": "es-ES", "publisher": {"@id": f"{config.BASE_URL}/#org"}}
    return ld({"@context": "https://schema.org", "@graph": [org, web]})


def crumbs(*items) -> str:
    """BreadcrumbList: items = (nombre, ruta)."""
    els = [{"@type": "ListItem", "position": i + 1, "name": n, "item": f"{config.BASE_URL}{u}"} for i, (n, u) in enumerate((("Inicio", "/"),) + items)]
    return ld({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": els})


def faq_ld(pairs) -> str:
    return ld({"@context": "https://schema.org", "@type": "FAQPage",
               "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in pairs]})


def ctx(request: Request, **kw) -> dict:
    base = {
        "request": request, "brand": config.BRAND, "tagline": config.TAGLINE, "menu": MENU, "base_url": config.BASE_URL, "email": config.CONTACT_EMAIL,
        "discount": config.WELCOME_DISCOUNT_PCT, "year": time.strftime("%Y"), "site_jsonld": site_jsonld(),
        "ids": {"ga4": config.GA4_ID, "gads": config.GADS_ID, "gads_label": config.GADS_LABEL, "meta": config.META_PIXEL_ID,
                "clarity": config.CLARITY_ID, "pinterest": config.PINTEREST_TAG_ID},
    }
    base.update(kw)
    return base


def card(p: dict) -> dict:
    imgs = p.get("images") or []
    mi = next((i for i in imgs if i.get("kind") == "main"), None)
    ro = next((i for i in imgs if i.get("kind") == "room"), None)
    sm = lambda i: (i.get("thumb") or i["url"]) if i else None
    return {**p, "img": sm(mi), "img2": sm(ro), "img_full": mi["url"] if mi else None, "img2_md": (ro.get("md") or ro["url"]) if ro else None, "from_price": config.min_price(p["kind"])}


async def reviews_for(slug: str | None = None, limit: int = 30) -> list[dict]:
    if not db.ENABLED:
        return []
    params = {"select": "*", "approved": "eq.true", "order": "created_at.desc", "limit": str(limit)}
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
    hero_i = next((i for p in prods if p.get("bestseller") for i in (p.get("images") or []) if i.get("kind") == "room"), None)
    hero = (hero_i.get("md") or hero_i["url"]) if hero_i else None
    revs = await reviews_for(limit=20)
    return T.TemplateResponse(request, "home.html", ctx(request, best=best, hero=hero, reviews=revs, title=f"{config.BRAND} · {config.TAGLINE} · Cuadros religiosos modernos", og_image=hero_i["url"] if hero_i else None,
                                                 description="Cuadros religiosos modernos en lienzo y láminas enmarcadas: arte cristiano y católico en tonos neutros para casas modernas. Envío gratis."))


@app.get("/coleccion/{slug}", response_class=HTMLResponse)
async def collection(request: Request, slug: str, orden: str = ""):
    c = COLS.get(slug)
    if not c:
        raise HTTPException(404)
    prods = [card(p) for p in await db.products() if slug == "todos" or slug in (p.get("collections") or [])]
    if orden == "precio":
        prods.sort(key=lambda p: p["from_price"])
    items = ld({"@context": "https://schema.org", "@type": "ItemList", "name": c["h1"], "numberOfItems": len(prods),
                "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": f"{config.BASE_URL}/cuadro/{p['slug']}", "name": p["title"]} for i, p in enumerate(prods)]})
    desc = f"{c['h1']}: {c['intro']} {len(prods)} diseños en lienzo y lámina enmarcada, desde {min((p['from_price'] for p in prods), default=0)} €. Envío gratis a la Península y Baleares."
    return T.TemplateResponse(request, "collection.html", ctx(request, c=c, products=prods, title=f"{c['h1']} · {config.BRAND}", description=desc[:300],
                                                       og_image=next((i["url"] for i in (prods[0].get("images") or []) if i.get("kind") == "room"), prods[0]["img_full"]) if prods else None,
                                                       extra_jsonld=[items, crumbs((c["title"], f"/coleccion/{slug}"))]))


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
    url = f"{config.BASE_URL}/cuadro/{p['slug']}"
    shipping = {"@type": "OfferShippingDetails", "shippingRate": {"@type": "MonetaryAmount", "value": 0, "currency": "EUR"},
                "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "ES"},
                "deliveryTime": {"@type": "ShippingDeliveryTime", "handlingTime": {"@type": "QuantitativeValue", "minValue": 2, "maxValue": 3, "unitCode": "DAY"},
                                 "transitTime": {"@type": "QuantitativeValue", "minValue": 3, "maxValue": 5, "unitCode": "DAY"}}}
    returns = {"@type": "MerchantReturnPolicy", "applicableCountry": "ES", "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
               "merchantReturnDays": 14, "returnMethod": "https://schema.org/ReturnByMail", "returnFees": "https://schema.org/ReturnShippingFees",
               "merchantReturnLink": f"{config.BASE_URL}/p/devoluciones"}
    prod = {"@context": "https://schema.org", "@type": "Product", "@id": f"{url}#product", "name": p["title"], "description": c.get("intro") or "",
            "image": [i["url"] for i in (p.get("images") or [])][:6], "brand": {"@type": "Brand", "name": config.BRAND}, "sku": p["slug"],
            "category": "Hogar y jardín > Decoración > Arte > Cuadros", "material": "Lienzo" if p["kind"] == "lienzo" else "Papel mate con marco",
            "url": url, "inLanguage": "es-ES",
            "additionalProperty": [{"@type": "PropertyValue", "name": k, "value": v} for k, v in
                                   (("Tema", c.get("subject")), ("Estilo", c.get("style")), ("Paleta", c.get("palette")), ("Versículo", f"{p.get('verse')} ({p.get('verse_ref')})" if p.get("verse") else None)) if v],
            "offers": {"@type": "AggregateOffer", "priceCurrency": "EUR", "lowPrice": p["from_price"], "highPrice": max(prices.values()), "offerCount": len(prices),
                       "availability": "https://schema.org/InStock", "itemCondition": "https://schema.org/NewCondition", "url": url,
                       "seller": {"@id": f"{config.BASE_URL}/#org"}, "shippingDetails": shipping, "hasMerchantReturnPolicy": returns}}
    if revs:
        prod["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": round(sum(r.get("rating") or 5 for r in revs) / len(revs), 1), "reviewCount": len(revs)}
        prod["review"] = [{"@type": "Review", "author": {"@type": "Person", "name": r.get("name") or "Cliente"}, "datePublished": (r.get("created_at") or "")[:10],
                           "reviewBody": r.get("body") or "", "reviewRating": {"@type": "Rating", "ratingValue": r.get("rating") or 5}} for r in revs[:5]]
    col = next((COLS[x] for x in (p.get("collections") or []) if x in COLS and COLS[x]["group"] == "Por tema"), COLS.get("todos"))
    extra = [ld(prod), crumbs((col["title"], f"/coleccion/{col['slug']}"), (p["title"], f"/cuadro/{p['slug']}"))]
    if c.get("faq"):
        extra.append(faq_ld([(f["q"], f["a"]) for f in c["faq"] if f.get("q") and f.get("a")]))
    return T.TemplateResponse(request, "product.html", ctx(request, extra_jsonld=extra, og_type="product", p=p, sizes=sizes, frames=frames, prices=json.dumps(prices), c=c, related=related, reviews=revs,
                                                    title=f"{p['title']} · Cuadro religioso moderno · {config.BRAND}", description=(c.get("intro") or "")[:155],
                                                    og_image=p.get("img_full")))


@app.get("/carrito", response_class=HTMLResponse)
async def cart_page(request: Request):
    return T.TemplateResponse(request, "cart.html", ctx(request, title=f"Carrito · {config.BRAND}", noindex=True))


@app.get("/gracias", response_class=HTMLResponse)
async def thanks(request: Request, pedido: str = "", session_id: str = ""):
    o = None
    if pedido and db.ENABLED:
        try:
            o = await (shop.confirm(pedido, session_id) if session_id else shop.get_order(pedido))
        except Exception as e:
            log.warning("confirm %s: %s", pedido, e)
    return T.TemplateResponse(request, "thanks.html", ctx(request, o=o, title=f"Gracias · {config.BRAND}", noindex=True))


@app.get("/encuentra-tu-cuadro", response_class=HTMLResponse)
async def quiz(request: Request):
    prods = [card(p) for p in await db.products()]
    slim = [{"slug": p["slug"], "title": p["title"], "img": p["img"], "theme": p["theme"], "palette": p["palette"], "orient": p["orient"],
             "collections": p.get("collections") or [], "from_price": p["from_price"], "best": p.get("bestseller")} for p in prods]
    return T.TemplateResponse(request, "quiz.html", ctx(request, products=json.dumps(slim), title=f"¿Cuál es tu cuadro? · {config.BRAND}",
                                                 description="Responde 4 preguntas y te recomendamos el cuadro religioso moderno que mejor encaja con tu casa y tu fe."))


PAGES = {
    "preguntas-frecuentes": "Preguntas frecuentes", "nuestra-historia": "Nuestra historia", "envios": "Política de envíos",
    "devoluciones": "Devoluciones y cambios", "privacidad": "Política de privacidad", "aviso-legal": "Aviso legal",
    "condiciones": "Condiciones de venta", "contacto": "Ayuda y contacto",
}


PAGE_DESC = {
    "preguntas-frecuentes": "Tamaños, marcos, plazos de entrega, envío gratis, devoluciones y pago de los cuadros religiosos de Cuadros con Alma.",
    "nuestra-historia": "Dos hermanas de Barcelona que no encontraban arte religioso moderno para su casa y decidieron crearlo.",
    "envios": "Envío gratis a la Península y Baleares en 5-8 días laborables. También enviamos a Europa y Estados Unidos.",
    "devoluciones": "Derecho de desistimiento de 14 días y reposición sin coste si tu cuadro llega dañado.",
    "contacto": "Escríbenos para tamaños a medida, dudas sobre tu pedido o cualquier pregunta sobre nuestros cuadros.",
}


@app.get("/p/{page}", response_class=HTMLResponse)
async def static_page(request: Request, page: str):
    if page not in PAGES:
        raise HTTPException(404)
    extra = [crumbs((PAGES[page], f"/p/{page}"))]
    if page == "preguntas-frecuentes":
        html = T.get_template("pages/preguntas-frecuentes.html").render(ctx(request, page_title=PAGES[page]))
        strip = lambda x: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", x)).strip()
        extra.append(faq_ld([(strip(q), strip(a)) for q, a in re.findall(r'<p class="faq-q">(.*?)</p><p>(.*?)</p>', html, re.S)]))
    return T.TemplateResponse(request, f"pages/{page}.html", ctx(request, page_title=PAGES[page], title=f"{PAGES[page]} · {config.BRAND}", extra_jsonld=extra,
                                                                description=PAGE_DESC.get(page)))


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
    block = "Disallow: /admin\nDisallow: /api/\nDisallow: /carrito\nDisallow: /gracias\n"
    ai = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User",
          "Google-Extended", "Applebot-Extended", "Bingbot", "meta-externalagent", "CCBot"]
    out = "User-agent: *\nAllow: /\n" + block + "\n"
    out += "# Asistentes de IA: bienvenidos (resumen en /llms.txt)\n" + "".join(f"User-agent: {b}\n" for b in ai) + "Allow: /\n" + block
    return out + f"\nSitemap: {config.BASE_URL}/sitemap.xml\n"


@app.get("/sitemap.xml")
async def sitemap():
    from xml.sax.saxutils import escape as x
    prods = await db.products()
    last = max(((p.get("updated_at") or "")[:10] for p in prods), default="")
    def u(loc, mod="", imgs=()):
        im = "".join(f"<image:image><image:loc>{x(i)}</image:loc></image:image>" for i in imgs)
        return f"<url><loc>{x(loc)}</loc>{f'<lastmod>{mod}</lastmod>' if mod else ''}{im}</url>"
    parts = [u(f"{config.BASE_URL}/", last)] + [u(f"{config.BASE_URL}/coleccion/{c}", last) for c in COLS]
    parts += [u(f"{config.BASE_URL}/cuadro/{p['slug']}", (p.get("updated_at") or "")[:10], [i["url"] for i in (p.get("images") or [])][:5]) for p in prods]
    parts += [u(f"{config.BASE_URL}/p/{k}") for k in PAGES] + [u(f"{config.BASE_URL}/encuentra-tu-cuadro"), u(f"{config.BASE_URL}/llms.txt", last)]
    xml = ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
           'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">' + "".join(parts) + "</urlset>")
    return Response(xml, media_type="application/xml")


@app.get("/llms.txt", response_class=PlainTextResponse)
async def llms_txt():
    """Resumen en texto para asistentes de IA (ChatGPT, Claude, Perplexity…)."""
    B = config.BASE_URL
    prods = await db.products()
    lines = [f"# {config.BRAND}", "",
             f"> {config.BRAND} ({config.TAGLINE.lower()}) es una tienda online española de cuadros religiosos modernos: arte cristiano y católico "
             "contemporáneo en tonos neutros, pensado para casas actuales. Cada diseño es original e incluye un versículo o una oración. "
             "Se imprime bajo pedido en España y llega montado, listo para colgar.", "",
             "## Datos clave",
             f"- Productos: lienzo (sin marco desde {config.min_price('lienzo')} €, o con marco flotante de madera) y lámina enmarcada con metacrilato (desde {config.min_price('lamina')} €). Precios con IVA.",
             "- Tamaños: lienzo 30x45, 40x60, 50x75 y 60x90 cm; lámina 30x40, 45x60, 50x70 y 60x90 cm. Tamaños a medida bajo consulta.",
             "- Envío: gratis a la Península y Baleares, entrega en 5-8 días laborables. También envía al resto de Europa y a Estados Unidos.",
             "- Devoluciones: desistimiento legal de 14 días; si el cuadro llega dañado se repone sin coste.",
             "- Pago: tarjeta, Apple Pay y Google Pay (Stripe). {config.WELCOME_DISCOUNT_PCT} % de descuento en el primer pedido al suscribirse.",
             f"- Contacto: {config.CONTACT_EMAIL}. Empresa: Comartinvi S.L., Barcelona (España).",
             "- Ideal para regalar en: bodas, primera comunión, bautizo, confirmación, inauguración de casa, Navidad, Día de la Madre.", "",
             "## Colecciones"]
    lines += [f"- [{c['h1']}]({B}/coleccion/{c['slug']}): {c['intro']}" for c in COLS.values()]
    lines += ["", "## Cuadros"]
    for p in prods:
        c = card(p)
        v = f" Versículo: «{p['verse']}» ({p.get('verse_ref')})." if p.get("verse") else ""
        intro = ((p.get("content") or {}).get("intro") or "").strip()
        lines.append(f"- [{p['title']}]({B}/cuadro/{p['slug']}): desde {c['from_price']} €. {intro[:220]}{v}")
    lines += ["", "## Más información",
              f"- [Preguntas frecuentes]({B}/p/preguntas-frecuentes)", f"- [Envíos]({B}/p/envios)", f"- [Devoluciones]({B}/p/devoluciones)",
              f"- [Nuestra historia]({B}/p/nuestra-historia)", f"- [¿Cuál es tu cuadro? (test)]({B}/encuentra-tu-cuadro)"]
    return "\n".join(lines) + "\n"


# --- reseñas -------------------------------------------------------------------------

@app.post("/api/reviews")
async def api_review_create(name: str = Form(...), body: str = Form(...), rating: int = Form(5), slug: str = Form(""), pedido: str = Form(""),
                            photo: UploadFile | None = File(None)):
    name = name.strip()[:60]; body = body.strip()[:1500]; rating = max(1, min(5, rating))
    if not name or len(body) < 3:
        raise HTTPException(400, "Faltan datos")
    verified = False
    if pedido:
        o = await shop.get_order(pedido[:40])
        verified = bool(o and str(o.get("status", "")).startswith(("paid", "in_", "ship", "deliver", "fulfil", "sent")))
    photo_url = None
    if photo is not None and photo.filename:
        data = await photo.read()
        if len(data) > 15 * 1024 * 1024:
            raise HTTPException(400, "La foto es demasiado grande")
        try:
            im = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
            import secrets as _s
            photo_url = await db.upload(f"_reviews/{_s.token_hex(8)}.jpg", art.jpeg(im, max_side=1400))
        except Exception:
            raise HTTPException(400, "No se ha podido leer la foto")
    await db.upsert("fe_reviews", [{"name": name, "rating": rating, "body": body, "product_slug": slug[:120] or None,
                                    "order_id": pedido[:40] or None, "verified": verified, "photo_url": photo_url}])
    from . import mail
    await mail.admin_alert("Nueva reseña para revisar", f"{name} ({rating}★) {slug}: {body}{' [con foto]' if photo_url else ''}\n\nApruébala en {config.BASE_URL}/admin/reviews?token={config.ADMIN_TOKEN}")
    return {"ok": True}


@app.get("/admin/reviews", response_class=HTMLResponse)
async def admin_reviews(token: str = ""):
    _auth(token)
    import html as _h
    rows = await db.get("fe_reviews", {"select": "*", "order": "created_at.desc", "limit": "200"})
    tr = "".join(f"""<tr><td>{r['created_at'][:10]}</td><td>{_h.escape(r['name'])}</td><td>{'★'*r['rating']}</td><td>{_h.escape(r.get('product_slug') or '')}</td>
<td>{_h.escape(r['body'])}{f'<br><img src="{r["photo_url"]}" style="max-width:160px">' if r.get('photo_url') else ''}</td><td>{'✔ verificada' if r.get('verified') else ''}</td>
<td>{'<b>publicada</b>' if r.get('approved') else 'pendiente'}<br><a href="/admin/reviews/{r['id']}?token={token}&approved=1">Publicar</a> · <a href="/admin/reviews/{r['id']}?token={token}&approved=0">Ocultar</a></td></tr>""" for r in rows)
    return f"<meta name=viewport content='width=device-width'><h2>Reseñas</h2><table border=1 cellpadding=6 style='border-collapse:collapse;font-family:sans-serif'>{tr}</table>"


@app.get("/admin/reviews/{rid}")
async def admin_review_set(rid: str, token: str = "", approved: int = 1):
    _auth(token)
    await db.patch("fe_reviews", "id", rid, {"approved": bool(approved)})
    return RedirectResponse(f"/admin/reviews?token={token}", 303)


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


THUMB_W, MD_W = 600, 1200


async def _web_versions(slug: str, name: str, img: Image.Image, v) -> tuple[str, str]:
    """Sube la miniatura (600 px) y la versión de galería (1200 px) en WebP."""
    th = await db.upload(f"{slug}/web/{name}-{THUMB_W}.webp", await asyncio.to_thread(art.webp, img, THUMB_W, 78), "image/webp")
    md = await db.upload(f"{slug}/web/{name}-{MD_W}.webp", await asyncio.to_thread(art.webp, img, MD_W, 82), "image/webp")
    return f"{th}?v={v}", f"{md}?v={v}"


THUMBS = {"running": False, "done": 0, "total": 0, "errors": []}


async def _thumbs_job(force: bool):
    THUMBS.update(running=True, done=0, errors=[])
    try:
        prods = [p for p in await db.products(force=True) if p.get("images")]
        THUMBS["total"] = len(prods)
        sem = asyncio.Semaphore(4)

        async def one(im: dict, slug: str):
            if im.get("thumb") and im.get("md") and not force:
                return im
            async with sem:
                base = im["url"].split("?")[0]
                name = base.rsplit("/", 1)[1].rsplit(".", 1)[0]
                v = im["url"].split("v=")[1] if "v=" in im["url"] else int(time.time())
                img = Image.open(io.BytesIO(await db.download(base))).convert("RGB")
                th, md = await _web_versions(slug, name, img, v)
                return {**im, "thumb": th, "md": md}

        for p in prods:
            try:
                imgs = await asyncio.gather(*(one(dict(i), p["slug"]) for i in p["images"]))
                if imgs != p["images"]:
                    await db.patch("fe_products", "slug", p["slug"], {"images": list(imgs)})
            except Exception as e:
                log.exception("thumbs %s", p["slug"])
                THUMBS["errors"].append(f"{p['slug']}: {str(e)[:150]}")
            THUMBS["done"] += 1
        db.invalidate()
    finally:
        THUMBS["running"] = False


@app.post("/admin/thumbs")
async def admin_thumbs(token: str = "", force: bool = False):
    """Crea en segundo plano las versiones ligeras (WebP) de todas las fotos existentes."""
    _auth(token)
    if not THUMBS["running"]:
        asyncio.create_task(_thumbs_job(force))
    return THUMBS


@app.get("/admin/thumbs")
async def admin_thumbs_status(token: str = ""):
    _auth(token)
    return THUMBS


async def build_images(p: dict, a: Image.Image, rooms: dict) -> list[dict]:
    """Todas las fotos de la ficha, en el orden de la referencia."""
    slug = p["slug"]; kind = p["kind"]; o = p["orient"]
    out = []
    t = int(time.time())

    async def up(name, img, kindtag, frame=None):
        url = await db.upload(f"{slug}/{name}.jpg", art.jpeg(img, 85, 1800))
        th, md = await _web_versions(slug, name, img, t)
        out.append({"url": f"{url}?v={t}", "thumb": th, "md": md, "kind": kindtag, **({"frame": frame} if frame else {})})

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
    name = f"Bienvenida {config.BRAND}"
    coupons = shop._as_dict(stripe.Coupon.list(limit=100)).get("data") or []
    c = next((x for x in coupons if x.get("name") == name and x.get("valid")), None)
    cid = c["id"] if c else stripe.Coupon.create(percent_off=config.WELCOME_DISCOUNT_PCT, duration="once", name=name).id
    try:
        pc = stripe.PromotionCode.create(promotion={"type": "coupon", "coupon": cid}, code="BIENVENIDA15", restrictions={"first_time_transaction": True})
    except Exception:
        pc = stripe.PromotionCode.create(coupon=cid, code="BIENVENIDA15", restrictions={"first_time_transaction": True})
    c = type("C", (), {"id": cid})
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
