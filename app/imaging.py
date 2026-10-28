"""Generación de la caricatura y preparación de archivos.

- generate(): llama a la API de imágenes de OpenAI (edición de imagen con la foto
  como entrada). Sin OPENAI_API_KEY entra en modo demo y devuelve una versión
  "posterizada" de la foto para poder probar todo el flujo.
- make_preview(): copia en tamaño web con marca de agua repetida.
- prepare_print_file(): archivo final a 300 dpi con sangrado para el lienzo.
"""
import base64
import io
import math

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import config

MAX_UPLOAD_SIDE = 2048


def load_and_normalize(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_UPLOAD_SIDE, MAX_UPLOAD_SIDE))
    return img


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def generate(photo: Image.Image, extra_prompt: str = "", scene_prompt: str = "", dedication: str = "") -> Image.Image:
    if config.DEMO_MODE:
        return _demo_caricature(photo)
    prompt = config.STYLE_PROMPT
    if scene_prompt:
        prompt += " Escena: " + scene_prompt
    if dedication:
        prompt += f" Dedicatoria que el cliente ha pedido (NO la escribas en la imagen; solo úsala si da pistas como un número de edad o unos colores): '{dedication[:80]}'."
    if extra_prompt:
        prompt += " Detalles del cliente: " + extra_prompt[:300]
    files = {"image[]": ("photo.png", _to_png_bytes(photo), "image/png")}
    data = {
        "model": config.OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": config.IMAGE_SIZE,
        "quality": "high",
        "n": "1",
    }
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(
            "https://api.openai.com/v1/images/edits", headers=headers, data=data, files=files
        )
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


def _demo_caricature(photo: Image.Image) -> Image.Image:
    """Efecto cartoon barato para probar el flujo sin gastar en la API."""
    w, h = 1024, 1536
    base = ImageOps.fit(photo, (w, h), method=Image.LANCZOS)
    smooth = base.filter(ImageFilter.SMOOTH_MORE).filter(ImageFilter.SMOOTH_MORE)
    poster = ImageOps.posterize(smooth, 3)
    edges = base.convert("L").filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
    edges = ImageOps.invert(edges).point(lambda v: 255 if v > 120 else 0)
    out = Image.composite(poster, Image.new("RGB", (w, h), (30, 30, 30)), edges)
    d = ImageDraw.Draw(out)
    d.rectangle([0, h - 90, w, h], fill=(255, 230, 120))
    d.text((24, h - 70), "MODO DEMO: sin OPENAI_API_KEY no se genera la caricatura real", fill=(40, 40, 40), font=_font(28))
    return out


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def add_dedication(result: Image.Image, text: str) -> Image.Image:
    """Escribe la dedicatoria en una banda en la parte baja del cuadro (fiable,
    a diferencia de pedirle a la IA que escriba texto)."""
    text = " ".join(text.split())[:60]
    if not text:
        return result
    img = result.copy()
    w, h = img.size
    size = max(28, w // 16)
    font = _font(size)
    d = ImageDraw.Draw(img, "RGBA")
    while d.textlength(text, font=font) > w * 0.9 and size > 18:
        size -= 2
        font = _font(size)
    tw = d.textlength(text, font=font)
    pad = size // 2
    box_h = size + 2 * pad
    y0 = h - box_h - size
    d.rounded_rectangle([(w - tw) / 2 - pad * 1.5, y0, (w + tw) / 2 + pad * 1.5, y0 + box_h], radius=box_h // 2, fill=(255, 255, 255, 230))
    d.text(((w - tw) / 2, y0 + pad - size * 0.1), text, font=font, fill=(30, 30, 30))
    return img


def make_preview(result: Image.Image, max_side: int = 900) -> bytes:
    img = result.copy()
    img.thumbnail((max_side, max_side))
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    font = _font(max(22, w // 12))
    text = config.WATERMARK_TEXT
    tw = d.textlength(text, font=font)
    step_y = int(font.size * 3.2)
    for y in range(-h, h * 2, step_y):
        for x in range(-w, w * 2, int(tw + font.size * 2)):
            d.text((x, y), text, font=font, fill=(255, 255, 255, 95))
    layer = layer.rotate(-30, resample=Image.BICUBIC, expand=False)
    out = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    buf = io.BytesIO()
    out.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def prepare_print_file(result: Image.Image, width_mm: int = 300, height_mm: int = 400, bleed_mm: int = 10, dpi: int = 300) -> bytes:
    """Archivo de impresión: tamaño exacto en mm + sangrado por los 4 lados, 300 dpi.
    La IA entrega 1024x1536 (2:3); el lienzo 30x40 es 3:4, así que se recorta con
    cuidado por el centro (la composición está centrada)."""
    px = lambda mm: int(round(mm / 25.4 * dpi))
    W, H = px(width_mm + 2 * bleed_mm), px(height_mm + 2 * bleed_mm)
    img = ImageOps.fit(result, (W, H), method=Image.LANCZOS, centering=(0.5, 0.45))
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(dpi, dpi))
    return buf.getvalue()


def prepare_digital_file(result: Image.Image) -> bytes:
    buf = io.BytesIO()
    result.save(buf, format="PNG", dpi=(300, 300))
    return buf.getvalue()
