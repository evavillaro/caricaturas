"""Pago (Stripe Checkout) y producción (Gelato)."""
import time

import httpx

from . import config, mail, storage

P = config.PRICES_CENTS
PRODUCTS = {
    "digital": {"name": "Caricatura en archivo digital (alta resolución)", "cents": P["digital"], "ships": False, "type": "digital", "size": "Archivo"},
    "canvas_20x30": {"name": "Caricatura en lienzo 20x30 cm", "cents": P["canvas_20x30"], "ships": True, "mm": (200, 300), "bleed": 10, "type": "canvas", "size": "20x30 cm"},
    "canvas_30x40": {"name": "Caricatura en lienzo 30x40 cm", "cents": P["canvas_30x40"], "ships": True, "mm": (300, 400), "bleed": 10, "type": "canvas", "size": "30x40 cm"},
    "canvas_40x50": {"name": "Caricatura en lienzo 40x50 cm", "cents": P["canvas_40x50"], "ships": True, "mm": (400, 500), "bleed": 10, "type": "canvas", "size": "40x50 cm"},
    "canvas_50x70": {"name": "Caricatura en lienzo 50x70 cm", "cents": P["canvas_50x70"], "ships": True, "mm": (500, 700), "bleed": 10, "type": "canvas", "size": "50x70 cm"},
    "canvas_60x90": {"name": "Caricatura en lienzo 60x90 cm", "cents": P["canvas_60x90"], "ships": True, "mm": (600, 900), "bleed": 10, "type": "canvas", "size": "60x90 cm"},
    "canvas_80x120": {"name": "Caricatura en lienzo 80x120 cm", "cents": P["canvas_80x120"], "ships": True, "mm": (800, 1200), "bleed": 10, "type": "canvas", "size": "80x120 cm"},
    "poster_a4": {"name": "Caricatura en póster A4", "cents": P["poster_a4"], "ships": True, "mm": (210, 297), "bleed": 3, "type": "poster", "size": "A4"},
    "poster_a3": {"name": "Caricatura en póster A3", "cents": P["poster_a3"], "ships": True, "mm": (297, 420), "bleed": 3, "type": "poster", "size": "A3"},
    "poster_a2": {"name": "Caricatura en póster A2", "cents": P["poster_a2"], "ships": True, "mm": (420, 594), "bleed": 3, "type": "poster", "size": "A2"},
    "poster_a1": {"name": "Caricatura en póster A1", "cents": P["poster_a1"], "ships": True, "mm": (594, 841), "bleed": 3, "type": "poster", "size": "A1"},
    # compatibilidad con la primera versión
    "canvas": {"name": "Caricatura en lienzo 30x40 cm", "cents": P["canvas_30x40"], "ships": True, "mm": (300, 400), "bleed": 10, "alias": "canvas_30x40", "type": "canvas", "size": "30x40 cm"},
    "poster": {"name": "Caricatura en póster A3", "cents": P["poster_a3"], "ships": True, "mm": (297, 420), "bleed": 3, "alias": "poster_a3", "type": "poster", "size": "A3"},
}


def product_list() -> list[dict]:
    return [{"id": k, "type": v["type"], "size": v["size"], "name": v["name"], "cents": v["cents"]} for k, v in PRODUCTS.items() if "alias" not in v]


def gelato_uid(product: str) -> str:
    key = PRODUCTS[product].get("alias", product)
    return config.GELATO_PRODUCTS.get(key, "")


def stripe_client():
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def create_checkout(job_id: str, product: str) -> str:
    """Devuelve la URL de pago. En demo (sin Stripe) devuelve la página de éxito directamente."""
    p = PRODUCTS[product]
    storage.update_meta(job_id, product=product, status="checkout")
    storage.persist(job_id)
    if not config.PAYMENTS_ENABLED:
        storage.update_meta(job_id, paid=True, paid_at=time.time(), payment="demo", status="paid")
        return f"{config.BASE_URL}/gracias?job={job_id}&demo=1"
    stripe = stripe_client()
    params = dict(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": config.CURRENCY,
                "unit_amount": p["cents"],
                "product_data": {"name": p["name"], "images": [f"{config.BASE_URL}/api/preview/{job_id}.jpg"]},
            },
            "quantity": 1,
        }],
        success_url=f"{config.BASE_URL}/gracias?job={job_id}&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{config.BASE_URL}/?job={job_id}",
        metadata={"job_id": job_id, "product": product},
        client_reference_id=job_id,
        locale="es",
    )
    if p["ships"]:
        params["shipping_address_collection"] = {"allowed_countries": ["ES", "PT", "FR", "IT", "DE", "MX", "US"]}
        params["phone_number_collection"] = {"enabled": True}
    session = stripe.checkout.Session.create(**params)
    storage.update_meta(job_id, stripe_session=session.id)
    return session.url


def confirm_from_session(job_id: str, session_id: str) -> bool:
    """Comprueba en Stripe que la sesión está pagada (respaldo si el webhook no llega)."""
    if not config.PAYMENTS_ENABLED:
        return bool((storage.read_meta(job_id) or {}).get("paid"))
    stripe = stripe_client()
    s = _as_dict(stripe.checkout.Session.retrieve(session_id))
    if s.get("payment_status") != "paid" or s.get("client_reference_id") != job_id:
        return False
    mark_paid(job_id, s)
    return True


def _as_dict(obj) -> dict:
    """La librería de Stripe devuelve objetos que ya no se comportan como dict."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


def mark_paid(job_id: str, session) -> None:
    session = _as_dict(session)
    meta = storage.read_meta(job_id) or {}
    if meta.get("paid"):
        return
    details = session.get("customer_details") or {}
    ship = session.get("shipping_details") or (session.get("collected_information") or {}).get("shipping_details") or {}
    addr = ship.get("address") or {}
    storage.update_meta(
        job_id,
        paid=True,
        paid_at=time.time(),
        payment="stripe",
        status="paid",
        email=details.get("email"),
        shipping={
            "name": ship.get("name") or details.get("name"),
            "line1": addr.get("line1"),
            "line2": addr.get("line2"),
            "city": addr.get("city"),
            "postcode": addr.get("postal_code"),
            "state": addr.get("state"),
            "country": addr.get("country"),
            "phone": details.get("phone"),
        },
    )


async def fulfil(job_id: str) -> dict:
    """Tras el pago: lienzo/póster → pedido a Gelato; digital → nada que hacer (se descarga)."""
    meta = storage.read_meta(job_id) or {}
    if not meta.get("paid") or meta.get("gelato_order"):
        return meta
    product = meta.get("product")
    if product == "digital":
        return storage.update_meta(job_id, status="delivered")
    if not config.PRINT_ENABLED:
        return storage.update_meta(job_id, status="paid_pending_print", gelato_order="demo")
    uid = gelato_uid(product)
    ship = meta.get("shipping") or {}
    payload = {
        "orderType": "order",
        "orderReferenceId": job_id,
        "customerReferenceId": meta.get("email") or job_id,
        "currency": config.CURRENCY.upper(),
        "items": [{
            "itemReferenceId": f"{job_id}-1",
            "productUid": uid,
            "files": [{"type": "default", "url": f"{config.BASE_URL}/api/print-file/{job_id}.png"}],
            "quantity": 1,
        }],
        "shipmentMethodUid": "normal",
        "shippingAddress": {
            "firstName": (ship.get("name") or "Cliente").split(" ")[0],
            "lastName": " ".join((ship.get("name") or "Cliente").split(" ")[1:]) or "-",
            "addressLine1": ship.get("line1") or "",
            "addressLine2": ship.get("line2") or "",
            "city": ship.get("city") or "",
            "postCode": ship.get("postcode") or "",
            "state": ship.get("state") or "",
            "country": ship.get("country") or "ES",
            "email": meta.get("email") or "",
            "phone": ship.get("phone") or "",
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(config.GELATO_ORDERS_URL, json=payload, headers={"X-API-KEY": config.GELATO_API_KEY})
    if r.status_code >= 300:
        await mail.admin_alert(f"Gelato ha rechazado el pedido {job_id}", r.text[:800])
        return storage.update_meta(job_id, status="print_error", gelato_error=r.text[:500])
    data = r.json()
    return storage.update_meta(job_id, status="sent_to_print", gelato_order=data.get("id"), gelato_status=data.get("fulfillmentStatus"))


async def notify_once(job_id: str, key: str, coro_fn, *args):
    meta = storage.read_meta(job_id) or {}
    sent = dict(meta.get("emails") or {})
    if sent.get(key):
        return
    if await coro_fn(*args):
        sent[key] = True
        storage.update_meta(job_id, emails=sent)


async def notify_paid(job_id: str):
    meta = storage.read_meta(job_id) or {}
    if not meta.get("paid"):
        return
    p = PRODUCTS.get(meta.get("product") or "") or {}
    await notify_once(job_id, "confirmed", mail.order_confirmed, job_id, meta, p.get("name", "Caricatura"), p.get("cents", 0), not p.get("ships", True))


STATUS = {"shipped": "shipped", "delivered": "delivered", "canceled": "canceled", "cancelled": "canceled", "failed": "print_error",
          "in_production": "in_production", "printed": "in_production", "returned": "returned", "on_hold": "on_hold"}


async def gelato_event(ev: dict) -> dict:
    ref = ev.get("orderReferenceId") or ""
    if not ref or ref.startswith("FM"):
        return {"ignored": ref}
    try:
        meta = storage.read_meta(ref)
    except ValueError:
        return {"ignored": ref}
    if not meta:
        return {"unknown": ref}
    st = STATUS.get((ev.get("fulfillmentStatus") or "").lower())
    tracking = None
    for it in ev.get("items") or []:
        for f in it.get("fulfillments") or []:
            if f.get("trackingUrl") or f.get("trackingCode"):
                tracking = {"url": f.get("trackingUrl"), "code": f.get("trackingCode"), "carrier": f.get("shipmentMethodName")}
    if ev.get("trackingUrl") or ev.get("trackingCode"):
        tracking = {"url": ev.get("trackingUrl"), "code": ev.get("trackingCode"), "carrier": ev.get("shipmentMethodName")}
    ch = {}
    if st:
        ch["status"] = st; ch["gelato_status"] = ev.get("fulfillmentStatus")
    if tracking:
        ch["tracking"] = tracking
    if ch:
        meta = storage.update_meta(ref, **ch)
    t = meta.get("tracking") or {}
    if t.get("url"):
        await notify_once(ref, "shipped", mail.order_shipped, meta, t.get("url"), t.get("carrier"))
    if meta.get("status") == "delivered":
        await notify_once(ref, "delivered", mail.order_delivered, meta)
    if meta.get("status") in ("print_error", "canceled", "on_hold", "returned"):
        await mail.admin_alert(f"Pedido {ref}: {meta.get('status')}", str(ev)[:1500])
    return {"ok": True, "status": meta.get("status")}
