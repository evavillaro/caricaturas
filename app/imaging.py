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
from pathlib import Path
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


async def generate(photo, extra_prompt: str = "", scene_prompt: str = "", dedication: str = "", quality: str | None = None) -> Image.Image:
    """photo: una imagen o una lista de imágenes (pareja/grupo)."""
    if config.DEMO_MODE:
        return _demo_caricature(photo)
    prompt = config.STYLE_PROMPT
    if scene_prompt:
        prompt += " Escena: " + scene_prompt
    if dedication:
        prompt += f" Dedicatoria que el cliente ha pedido (NO la escribas en la imagen; solo úsala si da pistas como un número de edad o unos colores): '{dedication[:80]}'."
    if extra_prompt:
        prompt += " Detalles del cliente: " + extra_prompt[:300]
    photos = photo if isinstance(photo, (list, tuple)) else [photo]
    if len(photos) > 1:
        prompt += f" En la foto/fotos aparecen {len(photos)} personas distintas: dibuja a TODAS juntas en la escena, cada una reconocible por su propia foto."
    body = {
        "model": config.OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "images": [{"image_url": "data:image/png;base64," + base64.b64encode(_to_png_bytes(p)).decode()} for p in photos],
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


async def generate_photo(scene_prompt: str, gender: str = "", age: int = 0) -> Image.Image:
    """Foto 'realista' de una persona inventada, para el antes/después del catálogo."""
    prompt = (
        "Fotografía realista hecha con un móvil: retrato de frente, de cara y hombros, de una persona "
        "genérica mirando a cámara y sonriendo con naturalidad, ropa normal de calle (camiseta, camisa "
        "o jersey), SIN disfraz, SIN uniforme, SIN accesorios temáticos, luz natural, fondo cotidiano "
        "desenfocado (casa, calle o parque). Sin texto. Solo debe coincidir la edad, el género y el "
        "aspecto general (pelo, gafas, barba) con esta descripción: " + (f"{gender} de unos {age} años" if gender else scene_prompt[:200])
    )
    if config.DEMO_MODE:
        img = Image.new("RGB", (1024, 1024), (200, 210, 230)); ImageDraw.Draw(img).text((40, 40), "FOTO DEMO", fill=(60, 60, 60), font=_font(60)); return img
    body = {"model": config.OPENAI_IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "quality": config.env("CATALOG_PHOTO_QUALITY", "medium"), "n": 1}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")


FONTS_DIR = Path(__file__).parent / "fonts"


def _hand_font(size: int):
    for name in ("PatrickHand.ttf", "Caveat.ttf"):
        try:
            return ImageFont.truetype(str(FONTS_DIR / name), size)
        except OSError:
            continue
    return _font(size)


_TPL_CACHE: dict = {}


def load_template():
    """Plantilla (imagen + geometría) descargada de Supabase y cacheada en memoria."""
    if "v" in _TPL_CACHE:
        return _TPL_CACHE["v"]
    url = config.env("SUPABASE_URL").rstrip("/")
    if not url:
        _TPL_CACHE["v"] = None; return None
    try:
        base = f"{url}/storage/v1/object/public/caricaturas/_template"
        import json as _json
        r1 = httpx.get(f"{base}/template.png", timeout=30); r2 = httpx.get(f"{base}/geometry.json", timeout=30)
        if r1.status_code == 200 and r2.status_code == 200:
            _TPL_CACHE["v"] = (Image.open(io.BytesIO(r1.content)).convert("RGB"), _json.loads(r2.content))
        else:
            _TPL_CACHE["v"] = None
    except Exception:  # noqa: BLE001
        _TPL_CACHE["v"] = None
    return _TPL_CACHE["v"]


def compose_main(art: Image.Image, photo, label: str = "tu foto") -> Image.Image:
    photos = photo if isinstance(photo, (list, tuple)) else [photo]
    label = label if len(photos) == 1 else "tus fotos"
    """Imagen principal como la tienda de referencia: pared gris clara con suelo, lienzo con
    perspectiva y canto, móvil con la foto abajo a la derecha, texto a mano y flecha curva
    del móvil al cuadro."""
    import math
    W, H = 1160, 1300
    # fondo: pared gris clara con degradado suave y suelo
    bg = Image.new("RGB", (W, H), (232, 232, 234))
    px_ = bg.load()
    for yy in range(H):
        v = 236 - int(14 * yy / H)
        for xx in range(0, W, 1):
            px_[xx, yy] = (v, v, v + 2)
    ImageDraw.Draw(bg).rectangle([0, int(H * 0.86), W, H], fill=(214, 214, 216))
    # lienzo con perspectiva: la cara frontal se estrecha hacia la derecha y se ve el canto
    # izquierdo (imagen envuelta en el bastidor) y el canto superior, como un lienzo real.
    a = art.copy().convert("RGB"); a.thumbnail((900, 1200))
    cw, ch = int(W * 0.58), int(W * 0.58 * 4 / 3)
    piece = a.resize((cw, ch), Image.LANCZOS)
    x0, y0 = int(W * 0.10), int(H * 0.08)
    skew = int(ch * 0.035)
    edge = int(cw * 0.045)   # grosor del bastidor
    dst = [(0, 0), (cw, skew), (cw, ch - skew), (0, ch)]
    src = [(0, 0), (cw, 0), (cw, ch), (0, ch)]
    warped = piece.transform((cw, ch), Image.PERSPECTIVE, _persp_coeffs(dst, src), Image.BICUBIC)
    mask = Image.new("L", (cw, ch), 0); ImageDraw.Draw(mask).polygon(dst, fill=255)
    # sombra proyectada a la derecha y abajo
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(shadow)
    sd.polygon([(x0 + 14, y0 + 18), (x0 + cw + 22, y0 + skew + 26), (x0 + cw + 22, y0 + ch - skew + 34), (x0 + 14, y0 + ch + 26)], fill=(0, 0, 0, 125))
    shadow = shadow.filter(ImageFilter.GaussianBlur(30))
    bg = Image.alpha_composite(bg.convert("RGBA"), shadow).convert("RGB")
    # canto izquierdo: la imagen continúa envuelta (franja espejada) y más oscura
    strip = ImageOps.mirror(piece.crop((0, 0, edge * 2, ch))).resize((edge, ch)).point(lambda v: int(v * 0.5))
    strip_mask = Image.new("L", (edge, ch), 0); ImageDraw.Draw(strip_mask).polygon([(edge, 0), (edge, ch), (0, ch + int(edge * 0.4)), (0, int(edge * 0.4))], fill=255)
    bg.paste(strip, (x0 - edge, y0 - int(edge * 0.4)), strip_mask)
    bg.paste(warped, (x0, y0), mask)
    # móvil(es): uno por persona, en fila a la derecha
    d = ImageDraw.Draw(bg)
    n = len(photos)
    pw = int(W * (0.21 if n == 1 else 0.14)); ph = int(pw * 2.05); gap = int(W * 0.02)
    total = n * pw + (n - 1) * gap
    px = W - total - int(W * 0.05); py = int(H * 0.52)
    for i, ph_img in enumerate(photos):
        xx = px + i * (pw + gap)
        d.rounded_rectangle([xx - 4, py - 4, xx + pw + 4, py + ph + 4], radius=int(pw * 0.16), fill=(30, 30, 30))
        d.rounded_rectangle([xx, py, xx + pw, py + ph], radius=int(pw * 0.14), fill=(10, 10, 10))
        inner = ImageOps.fit(ph_img, (pw - 14, ph - 14), method=Image.LANCZOS)
        m2 = Image.new("L", inner.size, 0); ImageDraw.Draw(m2).rounded_rectangle([0, 0, inner.width - 1, inner.height - 1], radius=int(pw * 0.11), fill=255)
        bg.paste(inner, (xx + 7, py + 7), m2)
        d.rounded_rectangle([xx + pw * 0.36, py + 8, xx + pw * 0.64, py + 16], radius=4, fill=(40, 40, 40))
    pw = total  # para centrar el texto sobre el conjunto
    # texto a mano, dos líneas si hace falta, centrado sobre el móvil
    font = _hand_font(int(W * 0.075))
    lines = label.split(" ") if len(label) > 8 else [label]
    ty = int(H * 0.22)
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text((px + pw / 2 - tw / 2, ty), ln, fill=(20, 20, 20), font=font)
        ty += int(font.size * 0.95)
    # flecha curva: del móvil (arriba-izquierda) hacia el cuadro
    sx, sy = px + int(pw * 0.25), py - int(H * 0.02)
    ex, ey = x0 + cw + int(W * 0.035), int(H * 0.40)
    cx_, cy_ = sx + int(W * 0.02), ey + int(H * 0.02)
    pts = [((1 - t) ** 2 * sx + 2 * (1 - t) * t * cx_ + t ** 2 * ex, (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy_ + t ** 2 * ey) for t in (i / 40 for i in range(41))]
    d.line(pts, fill=(20, 20, 20), width=7, joint="curve")
    ang = math.atan2(ey - pts[-5][1], ex - pts[-5][0])
    L = int(W * 0.04)
    d.line([(ex, ey), (ex - L * math.cos(ang - 0.55), ey - L * math.sin(ang - 0.55))], fill=(20, 20, 20), width=7)
    d.line([(ex, ey), (ex - L * math.cos(ang + 0.55), ey - L * math.sin(ang + 0.55))], fill=(20, 20, 20), width=7)
    return bg


def _persp_coeffs(pa, pb):
    """Coeficientes para Image.transform(PERSPECTIVE): pa = esquinas destino, pb = esquinas origen."""
    import numpy as np
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0] * p1[0], -p2[0] * p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1] * p1[0], -p2[1] * p1[1]])
    A = np.array(matrix, dtype=float); B = np.array([c for p in pb for c in p], dtype=float)
    res = np.linalg.solve(A, B)
    return list(res)


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
        tpl = load_template()
        if tpl:
            out["main"] = _jpeg(compose_with_template(tpl[0], tpl[1], art, photo), 88)
        else:
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


# --- plantilla fotorrealista de mockup (generada una vez con IA) ---------------
TEMPLATE_PROMPT = (
    "Fotografía de producto realista, estilo catálogo de decoración: un lienzo en blanco de "
    "proporción 3:4 (vertical) apoyado contra una pared lisa gris muy claro, ligeramente girado "
    "hacia la derecha para que se vea el canto izquierdo del bastidor de madera (grueso, 2-3 cm), "
    "con sombra suave y realista sobre la pared y el suelo claro. La cara frontal del lienzo está "
    "pintada de un verde puro y uniforme (#00FF00), sin textura ni reflejos. A la derecha del "
    "lienzo, de pie y un poco más abajo, un smartphone negro moderno con la pantalla de un azul puro "
    "uniforme (#0000FF). Mucho espacio libre arriba a la derecha. Sin texto, sin personas, sin logotipos."
)


async def generate_template() -> Image.Image:
    body = {"model": config.OPENAI_IMAGE_MODEL, "prompt": TEMPLATE_PROMPT, "size": "1024x1024", "quality": "high", "n": 1}
    async with httpx.AsyncClient(timeout=240) as client:
        r = await client.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")


def _quad_from_mask(mask) -> list[tuple[int, int]] | None:
    """Esquinas (tl, tr, br, bl) de la mayor región marcada en una máscara booleana numpy."""
    import numpy as np
    ys, xs = np.nonzero(mask)
    if len(xs) < 2000:
        return None
    pts = np.stack([xs, ys], axis=1)
    s_ = pts.sum(axis=1); d_ = pts[:, 0] - pts[:, 1]
    tl = pts[s_.argmin()]; br = pts[s_.argmax()]; tr = pts[d_.argmax()]; bl = pts[d_.argmin()]
    return [tuple(map(int, tl)), tuple(map(int, tr)), tuple(map(int, br)), tuple(map(int, bl))]


def detect_template(tpl: Image.Image) -> dict:
    """Localiza el lienzo (verde) y la pantalla del móvil (azul) en la plantilla."""
    import numpy as np
    arr = np.asarray(tpl.convert("RGB")).astype(int)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    green = (g > 150) & (r < 120) & (b < 120) & (g - r > 60) & (g - b > 60)
    blue = (b > 140) & (r < 110) & (g < 130) & (b - r > 60) & (b - g > 40)
    cq = _quad_from_mask(green); pq = _quad_from_mask(blue)
    if not cq or not pq:
        raise RuntimeError(f"no se detecta lienzo ({'ok' if cq else 'no'}) o móvil ({'ok' if pq else 'no'})")
    return {"canvas": cq, "phone": pq, "size": tpl.size}


def compose_with_template(tpl: Image.Image, geo: dict, art: Image.Image, photo: Image.Image, label: str = "tu foto") -> Image.Image:
    import math
    out = tpl.copy().convert("RGB")
    W, H = out.size
    for key, img in (("canvas", art), ("phone", photo)):
        quad = geo[key]
        xs = [p[0] for p in quad]; ys = [p[1] for p in quad]
        bx0, by0, bx1, by1 = min(xs), min(ys), max(xs), max(ys)
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
        # recorte al aspecto del cuadrilátero y mapeo en perspectiva
        fit = ImageOps.fit(img.convert("RGB"), (bw, bh), method=Image.LANCZOS, centering=(0.5, 0.4 if key == "phone" else 0.5))
        local = [(x - bx0, y - by0) for x, y in quad]
        coeffs = _persp_coeffs(local, [(0, 0), (bw, 0), (bw, bh), (0, bh)])
        warped = fit.transform((bw, bh), Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        mask = Image.new("L", (bw, bh), 0); ImageDraw.Draw(mask).polygon(local, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(0.6))
        out.paste(warped, (bx0, by0), mask)
    # texto a mano y flecha curva del móvil hacia el lienzo
    d = ImageDraw.Draw(out)
    pq = geo["phone"]; cq = geo["canvas"]
    px0, py0 = min(p[0] for p in pq), min(p[1] for p in pq); px1 = max(p[0] for p in pq)
    cx1 = max(p[0] for p in cq); cy_mid = (min(p[1] for p in cq) + max(p[1] for p in cq)) // 2
    font = _hand_font(int(W * 0.075))
    lines = label.split(" ") if len(label) > 8 else [label]
    ty = max(int(H * 0.08), py0 - int(H * 0.36))
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((px0 + px1) / 2 - tw / 2, ty), ln, fill=(20, 20, 20), font=font)
        ty += int(font.size * 0.95)
    sx, sy = px0 + int((px1 - px0) * 0.25), py0 - int(H * 0.025)
    ex, ey = cx1 + int(W * 0.035), int(cy_mid * 0.9)
    cx_, cy_ = sx + int(W * 0.02), ey + int(H * 0.03)
    pts = [((1 - t) ** 2 * sx + 2 * (1 - t) * t * cx_ + t ** 2 * ex, (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy_ + t ** 2 * ey) for t in (i / 40 for i in range(41))]
    d.line(pts, fill=(20, 20, 20), width=max(5, W // 180), joint="curve")
    ang = math.atan2(ey - pts[-5][1], ex - pts[-5][0]); L = int(W * 0.04)
    d.line([(ex, ey), (ex - L * math.cos(ang - 0.55), ey - L * math.sin(ang - 0.55))], fill=(20, 20, 20), width=max(5, W // 180))
    d.line([(ex, ey), (ex - L * math.cos(ang + 0.55), ey - L * math.sin(ang + 0.55))], fill=(20, 20, 20), width=max(5, W // 180))
    return out
