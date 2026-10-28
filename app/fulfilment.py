"""Pago (Stripe Checkout) y producción (Gelato)."""
import time

import httpx

from . import config, storage

PRODUCTS = {
    "canvas": {"name": "Caricatura en lienzo 30x40 cm", "cents": config.PRICE_CANVAS_CENTS, "ships": True},
    "poster": {"name": "Caricatura en póster A3 (29,7x42 cm)", "cents": config.PRICE_POSTER_CENTS, "ships": True},
    "digital": {"name": "Caricatura en archivo digital (alta resolución)", "cents": config.PRICE_DIGITAL_CENTS, "ships": False},
}


def stripe_client():
    import stripe

    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def create_checkout(job_id: str, product: str) -> str:
    """Devuelve la URL de pago. En demo (sin Stripe) devuelve la página de éxito directamente."""
    p = PRODUCTS[product]
    storage.update_meta(job_id, product=product, status="checkout")
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
    s = stripe.checkout.Session.retrieve(session_id, expand=["shipping_details"])
    if s.get("payment_status") != "paid" or s.get("client_reference_id") != job_id:
        return False
    mark_paid(job_id, s)
    return True


def mark_paid(job_id: str, session) -> None:
    meta = storage.read_meta(job_id) or {}
    if meta.get("paid"):
        return
    details = session.get("customer_details") or {}
    ship = session.get("shipping_details") or session.get("collected_information", {}).get("shipping_details") or {}
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
    uid = config.GELATO_PRODUCT_CANVAS if product == "canvas" else config.GELATO_PRODUCT_POSTER
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
        return storage.update_meta(job_id, status="print_error", gelato_error=r.text[:500])
    data = r.json()
    return storage.update_meta(job_id, status="sent_to_print", gelato_order=data.get("id"), gelato_status=data.get("fulfillmentStatus"))
