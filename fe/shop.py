"""Carrito → Stripe Checkout → pedido en Supabase → Gelato."""
import json
import secrets
import time

import httpx

from . import config, db


def _stripe():
    import stripe
    stripe.api_key = config.STRIPE_SECRET_KEY
    return stripe


def _as_dict(o):
    if isinstance(o, dict):
        return o
    for m in ("to_dict_recursive", "to_dict"):
        if hasattr(o, m):
            return getattr(o, m)()
    return dict(o)


def frame_label(f: str) -> str:
    return dict(config.FRAMES).get(f, f)


async def validate_items(raw: list[dict]) -> list[dict]:
    """Recalcula precios en servidor: nunca se fía del navegador."""
    items = []
    for it in raw[:20]:
        p = await db.product(str(it.get("slug", "")))
        if not p:
            continue
        size = str(it.get("size")); frame = str(it.get("frame"))
        if size not in {s[0] for s in config.sizes_for(p["kind"])} or frame not in {f[0] for f in config.frames_for(p["kind"])}:
            continue
        qty = max(1, min(10, int(it.get("qty") or 1)))
        eur = config.price_eur(p["kind"], size, frame)
        kind_name = "Lienzo" if p["kind"] == "lienzo" else "Lámina enmarcada"
        items.append({
            "slug": p["slug"], "title": p["title"], "kind": p["kind"], "size": size, "frame": frame, "qty": qty,
            "cents": eur * 100, "name": f"{p['title']} · {kind_name} {size} cm · {frame_label(frame)}",
            "image": next((i["url"] for i in (p.get("images") or []) if isinstance(i, dict) and i.get("kind") == "main"), None),
        })
    return items


async def create_checkout(raw_items: list[dict], email: str | None = None, discount: bool = False) -> str:
    items = await validate_items(raw_items)
    if not items:
        raise ValueError("carrito vacío")
    order_id = "FM" + time.strftime("%y%m%d") + secrets.token_hex(3).upper()
    amount = sum(i["cents"] * i["qty"] for i in items)
    await db.upsert("fe_orders", [{"id": order_id, "items": items, "amount_cents": amount, "status": "checkout"}])
    if not config.STRIPE_SECRET_KEY:
        await db.patch("fe_orders", "id", order_id, {"status": "paid_demo"})
        return f"{config.BASE_URL}/gracias?pedido={order_id}&demo=1"
    stripe = _stripe()
    params = dict(
        mode="payment",
        line_items=[{
            "price_data": {"currency": "eur", "unit_amount": i["cents"], "product_data": {"name": i["name"], **({"images": [i["image"]]} if i["image"] else {})}},
            "quantity": i["qty"],
        } for i in items],
        success_url=f"{config.BASE_URL}/gracias?pedido={order_id}&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{config.BASE_URL}/carrito",
        metadata={"order_id": order_id, "store": "fe"},
        client_reference_id=order_id,
        locale="es",
        shipping_address_collection={"allowed_countries": ["ES", "PT", "FR", "IT", "DE", "BE", "NL", "AT", "IE", "MX", "US", "CO", "AR", "CL", "PE"]},
        phone_number_collection={"enabled": True},
    )
    if email:
        params["customer_email"] = email
    if discount and config.STRIPE_COUPON:
        params["discounts"] = [{"coupon": config.STRIPE_COUPON}]
    else:
        params["allow_promotion_codes"] = True
    s = stripe.checkout.Session.create(**params)
    await db.patch("fe_orders", "id", order_id, {"stripe_session": s.id})
    return s.url


async def get_order(order_id: str) -> dict | None:
    rows = await db.get("fe_orders", {"select": "*", "id": f"eq.{order_id}"})
    return rows[0] if rows else None


async def mark_paid(session) -> dict | None:
    s = _as_dict(session)
    oid = (s.get("metadata") or {}).get("order_id") or s.get("client_reference_id")
    if not oid:
        return None
    o = await get_order(oid)
    if not o or o.get("status") not in ("checkout", None):
        return o
    det = s.get("customer_details") or {}
    ship = s.get("shipping_details") or (s.get("collected_information") or {}).get("shipping_details") or {}
    addr = ship.get("address") or {}
    shipping = {"name": ship.get("name") or det.get("name"), "line1": addr.get("line1"), "line2": addr.get("line2"), "city": addr.get("city"),
                "postcode": addr.get("postal_code"), "state": addr.get("state"), "country": addr.get("country"), "phone": det.get("phone")}
    await db.patch("fe_orders", "id", oid, {"status": "paid", "email": det.get("email"), "shipping": shipping, "amount_cents": s.get("amount_total") or o.get("amount_cents")})
    return await get_order(oid)


async def confirm(order_id: str, session_id: str) -> dict | None:
    o = await get_order(order_id)
    if not o or o.get("status") != "checkout" or not config.STRIPE_SECRET_KEY:
        return o
    s = _as_dict(_stripe().checkout.Session.retrieve(session_id))
    if s.get("payment_status") == "paid" and s.get("client_reference_id") == order_id:
        o = await mark_paid(s)
        await fulfil(order_id)
    return await get_order(order_id)


# --- Gelato -------------------------------------------------------------------------

async def gelato_uids() -> dict:
    if config.GELATO_UIDS_JSON:
        try:
            return json.loads(config.GELATO_UIDS_JSON)
        except Exception:
            pass
    return (await db.get_setting("gelato_uids")) or {}


def uid_key(kind: str, size: str, frame: str, orient: str) -> str:
    return f"{kind}:{size}:{frame}:{orient}"


async def fulfil(order_id: str) -> dict | None:
    o = await get_order(order_id)
    if not o or o.get("status") != "paid" or o.get("gelato_order"):
        return o
    if not config.GELATO_API_KEY:
        await db.patch("fe_orders", "id", order_id, {"status": "paid_pending_print", "gelato_order": "demo"})
        return await get_order(order_id)
    uids = await gelato_uids()
    ship = o.get("shipping") or {}
    lines, missing = [], []
    for n, it in enumerate(o["items"], 1):
        p = await db.product(it["slug"]) or {}
        k = uid_key(it["kind"], it["size"], it["frame"], p.get("orient", "h"))
        uid = uids.get(k)
        if not uid:
            missing.append(k); continue
        lines.append({"itemReferenceId": f"{order_id}-{n}", "productUid": uid, "quantity": it["qty"],
                      "files": [{"type": "default", "url": f"{config.BASE_URL}/api/print/{it['slug']}/{it['size']}/{it['frame']}.jpg"}]})
    if missing:
        await db.patch("fe_orders", "id", order_id, {"status": "print_error", "gelato_error": "sin UID de Gelato: " + ", ".join(missing)})
        return await get_order(order_id)
    name = (ship.get("name") or "Cliente").split(" ")
    payload = {
        "orderType": "order", "orderReferenceId": order_id, "customerReferenceId": o.get("email") or order_id, "currency": "EUR",
        "items": lines, "shipmentMethodUid": "normal",
        "shippingAddress": {"firstName": name[0], "lastName": " ".join(name[1:]) or "-", "addressLine1": ship.get("line1") or "",
                            "addressLine2": ship.get("line2") or "", "city": ship.get("city") or "", "postCode": ship.get("postcode") or "",
                            "state": ship.get("state") or "", "country": ship.get("country") or "ES", "email": o.get("email") or "", "phone": ship.get("phone") or ""},
    }
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(config.GELATO_ORDERS_URL, json=payload, headers={"X-API-KEY": config.GELATO_API_KEY})
    if r.status_code >= 300:
        await db.patch("fe_orders", "id", order_id, {"status": "print_error", "gelato_error": r.text[:800]})
    else:
        await db.patch("fe_orders", "id", order_id, {"status": "sent_to_print", "gelato_order": r.json().get("id")})
    return await get_order(order_id)


async def gelato(method: str, url: str, body: dict | None = None):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.request(method, url, json=body, headers={"X-API-KEY": config.GELATO_API_KEY})
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text[:2000]
