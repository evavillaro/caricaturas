"""Emails al cliente de Caricaturea (estado del pedido) por SMTP, con el buzón de DonDominio.

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

log = logging.getLogger("caricaturas.mail")

HOST = config.env("SMTP_HOST"); PORT = int(config.env("SMTP_PORT", "587") or 587)
USER = config.env("SMTP_USER"); PASS = config.env("SMTP_PASS")
FROM = config.env("SMTP_FROM") or (formataddr((config.BRAND_NAME, USER)) if USER else "")
BRAND = config.BRAND_NAME
TAGLINE = config.env("TAGLINE", "Caricaturas personalizadas desde una foto")
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
<p style="font-size:22px;margin:0">{html.escape(BRAND)}</p>
<p style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#888;margin:2px 0 26px">{html.escape(TAGLINE)}</p>
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


async def order_confirmed(job_id: str, o: dict, product_name: str, cents: int, digital: bool):
    hola = f"¡Hola, {_name(o)}!" if _name(o) else "¡Hola!"
    base = config.BASE_URL
    if digital:
        return await send(o.get("email"), "Tu caricatura está lista para descargar",
                          [hola, "Gracias por tu compra. Aquí tienes tu caricatura en alta resolución, sin marca de agua.",
                           "Guárdala en tu ordenador o móvil: el enlace funciona durante 14 días."],
                          button=("Descargar mi caricatura", f"{base}/api/download/{job_id}.png"),
                          items=[{"name": product_name, "qty": 1, "cents": cents}])
    return await send(o.get("email"), "Tu caricatura está en marcha",
                      [hola, "Gracias por tu pedido. Ya estamos imprimiendo tu caricatura: se produce en 1-2 días laborables y te llegará en 2-5 días más.",
                       "Te escribiremos cuando salga de camino, con el enlace de seguimiento. Mientras tanto, también puedes descargar el archivo digital."],
                      button=("Descargar el archivo", f"{base}/api/download/{job_id}.png"),
                      items=[{"name": product_name, "qty": 1, "cents": cents}])


async def order_shipped(o: dict, tracking_url: str | None, carrier: str | None):
    p = ["¡Tu caricatura ya ha salido de la imprenta y va de camino!" + (f" Lo lleva {html.escape(carrier)}." if carrier else ""),
         "Suele llegar en 2-5 días laborables."]
    return await send(o.get("email"), "Tu caricatura va de camino", p, button=("Seguir mi envío", tracking_url) if tracking_url else None)


async def order_delivered(o: dict, job_id: str = ""):
    return await send(o.get("email"), "¿Qué tal ha quedado tu caricatura?",
                      ["Según el transportista, tu caricatura ya está en casa. ¡Esperamos que haya sido un regalo de los que no se olvidan!",
                       "Si tienes un minuto, nos ayudaría muchísimo que dejaras tu opinión: se publicará como compra verificada.",
                       "Si algo no ha llegado bien, responde a este correo y lo solucionamos."],
                      button=("Dejar mi opinión", f"{config.BASE_URL}/?pedido={job_id}#opiniones"))


async def admin_alert(subject: str, text: str):
    return await send(ADMIN, f"[{BRAND}] {subject}", [html.escape(text)])
