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


async def generate(photo: Image.Image, extra_prompt: str = "", scene_prompt: str = "", dedication: str = "", quality: str | None = None) -> Image.Image:
    if config.DEMO_MODE:
        return _demo_caricature(photo)
    prompt = config.STYLE_PROMPT
    if scene_prompt:
        prompt += " Escena: " + scene_prompt
    if dedication:
        prompt += f" Dedicatoria que el cliente ha pedido (NO la escribas en la imagen; solo úsala si da pistas como un número de edad o unos colores): '{dedication[:80]}'."
    if extra_prompt:
        prompt += " Detalles del cliente: " + extra_prompt[:300]
    data_url = "data:image/png;base64," + base64.b64encode(_to_png_bytes(photo)).decode()
    body = {
        "model": config.OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "images": [{"image_url": data_url}],
        "size": config.IMAGE_SIZE,
        "quality": quality or config.IMAGE_QUALITY,
        "n": 1,
    }
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post("https://api.openai.com/v1/images/edits", headers=headers, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


async def generate_from_text(scene_prompt: str) -> Image.Image:
    """Imagen de catálogo (sin foto de cliente): una persona genérica en la escena."""
    prompt = (
        "Ilustración de caricatura estilo cartoon moderno, cabeza grande y cuerpo pequeño, "
        "trazo limpio, colores vivos, sombreado suave, composición vertical centrada para "
        "imprimir en lienzo. Persona genérica sonriente. Sin texto, sin marcas de agua, sin "
        "logotipos reales. Escena: " + scene_prompt
    )
    if config.DEMO_MODE:
        img = Image.new("RGB", (1152, 1536), (240, 220, 200))
        d = ImageDraw.Draw(img); d.text((40, 40), "DEMO", fill=(80, 80, 80), font=_font(60))
        return img
    body = {"model": config.OPENAI_IMAGE_MODEL, "prompt": prompt, "size": config.IMAGE_SIZE, "quality": config.env("CATALOG_IMAGE_QUALITY", "medium"), "n": 1}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    b64 = r.json()["data"][0]["b64_json"]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


async def generate_photo(scene_prompt: str) -> Image.Image:
    """Foto 'realista' de una persona inventada, para el antes/después del catálogo."""
    prompt = (
        "Fotografía realista tipo selfie o retrato de móvil, luz natural, de una persona genérica "
        "sonriente mirando a cámara, plano medio, fondo cotidiano neutro (calle, casa). Sin texto. "
        "La persona debe encajar con esta descripción de producto (edad, género, estilo): " + scene_prompt[:300]
    )
    if config.DEMO_MODE:
        img = Image.new("RGB", (1024, 1024), (200, 210, 230)); ImageDraw.Draw(img).text((40, 40), "FOTO DEMO", fill=(60, 60, 60), font=_font(60)); return img
    body = {"model": config.OPENAI_IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "quality": config.env("CATALOG_PHOTO_QUALITY", "medium"), "n": 1}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")


def compose_main(art: Image.Image, photo: Image.Image, label: str = "tu foto") -> Image.Image:
    """Imagen principal de catálogo como la tienda de referencia: lienzo apoyado a la izquierda,
    móvil con la foto de origen a la derecha, texto y flecha hacia el cuadro."""
    W = H = 1200
    bg = Image.new("RGB", (W, H), (236, 231, 222))
    ImageDraw.Draw(bg).rectangle([0, 1010, W, H], fill=(205, 190, 170))
    a = art.copy(); a.thumbnail((900, 1200)); w, h = a.size
    scale = min((W * 0.52) / w, (H * 0.76) / h)
    cw, ch = int(w * scale), int(h * scale)
    piece = a.resize((cw, ch), Image.LANCZOS)
    x, y = int(W * 0.09), int(H * 0.10)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    sd.rectangle([x + 18, y + 24, x + cw + 18, y + ch + 24], fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow).convert("RGB")
    edge = int(cw * 0.025)
    side = piece.crop((cw - edge, 0, cw, ch)).resize((edge, ch)).point(lambda v: int(v * 0.6))
    bg.paste(side, (x + cw, y + int(edge * 0.6)))
    bg.paste(piece, (x, y))
    # móvil
    pw = int(W * 0.19); ph = int(pw * 2.05)
    px, py = int(W * 0.72), int(H * 0.50)
    d = ImageDraw.Draw(bg)
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=int(pw * 0.14), fill=(22, 22, 22))
    inner = ImageOps.fit(photo, (pw - 18, ph - 18), method=Image.LANCZOS)
    mask = Image.new("L", inner.size, 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, inner.width - 1, inner.height - 1], radius=int(pw * 0.10), fill=255)
    bg.paste(inner, (px + 9, py + 9), mask)
    d.rounded_rectangle([px + pw * 0.38, py + 4, px + pw * 0.62, py + 10], radius=3, fill=(70, 70, 70))
    # texto y flecha
    font = _font(int(W * 0.045))
    tx, ty = px - int(W * 0.02), int(H * 0.30)
    d.text((tx, ty), label, fill=(40, 40, 40), font=font)
    ax0, ay0 = tx + int(W * 0.04), ty + int(H * 0.065)
    ax1, ay1 = x + cw + int(W * 0.03), int(H * 0.42)
    mid = ((ax0 + ax1) // 2, ay0 + int(H * 0.03))
    d.line([(ax0, ay0), mid, (ax1, ay1)], fill=(40, 40, 40), width=5, joint="curve")
    d.polygon([(ax1 - int(W * 0.012), ay1 - int(H * 0.018)), (ax1 - int(W * 0.004), ay1 + int(H * 0.018)), (ax1 - int(W * 0.03), ay1 + int(H * 0.004))], fill=(40, 40, 40))
    return bg


def _jpeg(img: Image.Image, q: int = 86) -> bytes:
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=q); return buf.getvalue()


def make_mockups(art: Image.Image, photo: Image.Image | None = None) -> dict[str, bytes]:
    """Mockups baratos sin IA: lienzo con canto sobre pared lisa, sobre pared de ladrillo
    claro y versión póster con sombra. Devuelve JPEGs para web."""
    art = art.copy(); art.thumbnail((900, 1200))
    w, h = art.size
    out = {}
    out["art"] = _jpeg(art, 88)
    rendered = {}

    def canvas_on_wall(bg: Image.Image, label: str):
        W, H = bg.size
        scale = min((W * 0.55) / w, (H * 0.72) / h)
        cw, ch = int(w * scale), int(h * scale)
        piece = art.resize((cw, ch), Image.LANCZOS)
        x, y = (W - cw) // 2, int(H * 0.12)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rectangle([x + 18, y + 24, x + cw + 18, y + ch + 24], fill=(0, 0, 0, 110))
        shadow = shadow.filter(ImageFilter.GaussianBlur(22))
        bg = Image.alpha_composite(bg.convert("RGBA"), shadow).convert("RGB")
        edge = int(cw * 0.025)
        side = piece.crop((cw - edge, 0, cw, ch)).resize((edge, ch)).point(lambda v: int(v * 0.6))
        bg.paste(side, (x + cw, y + int(edge * 0.6)))
        bg.paste(piece, (x, y))
        rendered[label] = bg
        out[label] = _jpeg(bg, 86)

    wall = Image.new("RGB", (1200, 1200), (236, 231, 222))
    d = ImageDraw.Draw(wall); d.rectangle([0, 1000, 1200, 1200], fill=(205, 190, 170))
    canvas_on_wall(wall, "wall")

    brick = Image.new("RGB", (1200, 1200), (226, 214, 200))
    bd = ImageDraw.Draw(brick)
    for row in range(0, 1200, 60):
        off = 0 if (row // 60) % 2 == 0 else 60
        for col in range(-60, 1260, 120):
            bd.rectangle([col + off, row, col + off + 112, row + 52], fill=(234, 224, 212), outline=(214, 200, 184))
    canvas_on_wall(brick, "brick")

    poster_bg = Image.new("RGB", (1200, 1200), (245, 243, 240))
    pw, ph = int(w * 0.8), int(h * 0.8)
    piece = art.resize((pw, ph), Image.LANCZOS).rotate(-6, resample=Image.BICUBIC, expand=True, fillcolor=(245, 243, 240))
    px, py = (1200 - piece.width) // 2, (1200 - piece.height) // 2
    shadow = Image.new("RGBA", (1200, 1200), (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    sd.rectangle([px + 14, py + 20, px + piece.width + 14, py + piece.height + 20], fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    poster_bg = Image.alpha_composite(poster_bg.convert("RGBA"), shadow).convert("RGB")
    mask = Image.new("L", piece.size, 255)
    poster_bg.paste(piece, (px, py))
    out["poster"] = _jpeg(poster_bg, 86)
    # imagen principal: lienzo en pared gris claro con el móvil "tu foto" (como la tienda de referencia)
    if photo is not None:
        out["main"] = _jpeg(compose_main(art, photo), 86)
    else:
        out["main"] = out["art"]
    return out


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
