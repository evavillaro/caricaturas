"""Emails al cliente (estado del pedido) por SMTP, con el buzón de DonDominio.

Variables: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM, ADMIN_EMAIL.
Sin SMTP configurado no se envía nada (se registra en el log).
"""
import asyncio
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from . import config

log = logging.getLogger("fe.mail")

HOST = config.env("SMTP_HOST"); PORT = int(config.env("SMTP_PORT", "587") or 587)
USER = config.env("SMTP_USER"); PASS = config.env("SMTP_PASS")
FROM = config.env("SMTP_FROM") or (formataddr((config.BRAND, USER)) if USER else "")
ADMIN = config.env("ADMIN_EMAIL", "hola@comartinvi.com")
ENABLED = bool(HOST and USER and PASS)


def _eur(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",") + " €"


def _send_sync(to: str, subject: str, html_body: str, text_body: str):
    msg = EmailMessage()
    msg["From"] = FROM; msg["To"] = to; msg["Subject"] = subject
    msg["Reply-To"] = config.CONTACT_EMAIL if "@" in config.CONTACT_EMAIL else USER
    msg["Message-ID"] = make_msgid(domain=(USER.split("@")[-1] if "@" in USER else None))
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    ctx = ssl.create_default_context()
    if PORT == 465:
        with smtplib.SMTP_SSL(HOST, PORT, context=ctx, timeout=30) as s:
            s.login(USER, PASS); s.send_message(msg)
    else:
        with smtplib.SMTP(HOST, PORT, timeout=30) as s:
            s.starttls(context=ctx); s.login(USER, PASS); s.send_message(msg)


async def send(to: str | None, subject: str, paragraphs: list[str], button: tuple[str, str] | None = None, items: list[dict] | None = None):
    if not to:
        return False
    if not ENABLED:
        log.info("SMTP sin configurar; no se envía '%s' a %s", subject, to)
        return False
    rows = ""
    if items:
        rows = "".join(
            f'<tr><td style="padding:8px 0;border-bottom:1px solid #eee">{html.escape(i["name"])} × {i["qty"]}</td>'
            f'<td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right">{_eur(i["cents"] * i["qty"])}</td></tr>'
            for i in items)
        rows = f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin:16px 0">{rows}</table>'
    btn = f'<p style="margin:24px 0"><a href="{button[1]}" style="background:#1d1b19;color:#fff;padding:12px 22px;text-decoration:none;display:inline-block">{html.escape(button[0])}</a></p>' if button else ""
    body = "".join(f'<p style="margin:0 0 14px">{p}</p>' for p in paragraphs)
    html_body = f"""<div style="background:#f4f1eb;padding:24px 12px;font-family:Georgia,serif;color:#1d1b19">
<div style="max-width:560px;margin:0 auto;background:#fff;padding:32px 28px">
<p style="font-size:22px;margin:0">{html.escape(config.BRAND)}</p>
<p style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#888;margin:2px 0 26px">{html.escape(config.TAGLINE)}</p>
<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.6">{body}{rows}{btn}
<p style="color:#888;font-size:13px;margin-top:28px">¿Dudas? Responde a este correo y te contestamos.</p></div>
</div></div>"""
    import re
    text = "\n\n".join(re.sub("<[^>]+>", "", p) for p in paragraphs)
    if button:
        text += f"\n\n{button[0]}: {button[1]}"
    try:
        await asyncio.to_thread(_send_sync, to, subject, html_body, text)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("email '%s' a %s falló: %s", subject, to, e)
        return False


def _name(o: dict) -> str:
    n = ((o.get("shipping") or {}).get("name") or "").split(" ")[0]
    return html.escape(n) if n else ""


async def order_confirmed(o: dict):
    hola = f"¡Hola, {_name(o)}!" if _name(o) else "¡Hola!"
    return await send(o.get("email"), f"Tu pedido {o['id']} está confirmado",
               [hola, "Gracias por tu pedido. Ya estamos preparando tu cuadro: lo imprimimos bajo pedido y te llegará en <b>5-8 días laborables</b>.",
                "Te escribiremos cuando salga de camino, con el enlace de seguimiento.", f"Número de pedido: <b>{o['id']}</b>"],
               items=o.get("items"))


async def order_in_production(o: dict):
    return await send(o.get("email"), "Tu cuadro ya está en producción",
               ["Tu cuadro ya está en el taller. En cuanto salga hacia tu casa te mandamos el seguimiento.", f"Pedido <b>{o['id']}</b>."])


async def order_shipped(o: dict, tracking_url: str | None, carrier: str | None):
    p = ["¡Buenas noticias! Tu cuadro ya ha salido del taller y va de camino." + (f" Lo lleva {html.escape(carrier)}." if carrier else ""),
         "Suele llegar en 2-5 días laborables.", f"Pedido <b>{o['id']}</b>."]
    return await send(o.get("email"), "Tu cuadro va de camino", p, button=("Seguir mi envío", tracking_url) if tracking_url else None)


async def order_delivered(o: dict):
    return await send(o.get("email"), "¿Qué tal ha quedado tu cuadro?",
               ["Según el transportista, tu cuadro ya está en casa. ¡Esperamos que te encante!",
                "Si tienes un minuto, nos ayudaría muchísimo que nos contaras qué te ha parecido respondiendo a este correo (y si te animas, con una foto de cómo ha quedado en la pared).",
                "Si algo no ha llegado bien, dínoslo y lo solucionamos."])


async def admin_alert(subject: str, text: str):
    return await send(ADMIN, f"[{config.BRAND}] {subject}", [html.escape(text)])
