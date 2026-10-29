"""Diseños (IA), mockups (Pillow) y archivos de impresión."""
import base64
import io
import math
import random
import textwrap
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import config, seed

FONTS = Path(__file__).parent / "fonts"

LIENZO_STYLE = (
    "Pintura original contemporánea de galería, óleo muy texturizado aplicado con espátula sobre una "
    "superficie que parece yeso o estuco, estilo minimalista moderno para decoración de interiores. "
    "Enorme espacio negativo, horizonte bajo y difuso, atmósfera brumosa, serena y luminosa. Las figuras "
    "son diminutas, delicadas y apenas insinuadas con unas pocas pinceladas. Paleta muy apagada de {pal}. "
    "Sin texto, sin firma, sin marco, sin pared: la pintura ocupa toda la imagen de borde a borde, vista "
    "totalmente frontal. Escena: {scene}."
)
LAMINA_STYLE = (
    "Ilustración original de línea fina dibujada a mano con tinta, trazo delicado y continuo, algunas "
    "aguadas suaves, sobre papel de acuarela texturizado de color {pal}. Estilo minimalista y elegante de "
    "lámina artística moderna, mucho espacio en blanco, sin texto, sin letras, sin firma, sin marco: el "
    "papel ocupa toda la imagen, vista frontal. Escena: {scene}."
)
LAMINA_TEXT_STYLE = (
    "Pequeña ilustración original de línea fina dibujada a mano con tinta, muy delicada y minimalista, "
    "sobre papel de acuarela texturizado de color {pal}. La ilustración es pequeña y está en el tercio "
    "superior, centrada; el resto del papel queda completamente vacío (ahí irá un texto que no debes "
    "escribir). Sin texto, sin letras, sin firma, sin marco: el papel ocupa toda la imagen, vista frontal. "
    "Dibujo: {scene}."
)


def has_text_layout(p: dict) -> bool:
    return p["kind"] == "lamina" and any(w in (p.get("subtitle") or "").lower() for w in ("versículo", "oración"))


def art_prompt(p: dict) -> str:
    pal = seed.PALETTES.get(p.get("palette") or "beige", seed.PALETTES["beige"])[1]
    if p["kind"] == "lienzo":
        tpl = LIENZO_STYLE
    else:
        tpl = LAMINA_TEXT_STYLE if has_text_layout(p) else LAMINA_STYLE
    return tpl.format(pal=pal, scene=p.get("art_prompt") or p["title"])


async def _openai_image(prompt: str, size: str, quality: str | None = None) -> Image.Image:
    if not config.OPENAI_API_KEY:
        w, h = map(int, size.split("x"))
        img = Image.new("RGB", (w, h), (226, 218, 204))
        ImageDraw.Draw(img).text((40, 40), "DEMO", fill=(120, 110, 100), font=font("serif", 60))
        return img
    body = {"model": config.OPENAI_IMAGE_MODEL, "prompt": prompt, "size": size, "quality": quality or config.ART_QUALITY, "n": 1}
    async with httpx.AsyncClient(timeout=300) as c:
        r = await c.post("https://api.openai.com/v1/images/generations", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return Image.open(io.BytesIO(base64.b64decode(r.json()["data"][0]["b64_json"]))).convert("RGB")


async def generate_art(p: dict) -> Image.Image:
    size = "1536x1024" if p["orient"] == "h" else "1024x1536"
    img = await _openai_image(art_prompt(p), size)
    if has_text_layout(p):
        img = add_verse(img, p)
    return img


def font(kind: str, size: int):
    f = FONTS / ("CormorantGaramond-Medium.ttf" if kind == "serif" else "EBGaramond-Regular.ttf")
    try:
        return ImageFont.truetype(str(f), size)
    except Exception:
        return ImageFont.load_default()


def add_verse(img: Image.Image, p: dict) -> Image.Image:
    """Escribe el versículo centrado bajo la ilustración, en serif fina."""
    img = img.copy(); d = ImageDraw.Draw(img); W, H = img.size
    text = p.get("verse") or ""; ref = p.get("verse_ref") or ""
    size = int(W * 0.052) if len(text) < 90 else int(W * 0.042) if len(text) < 170 else int(W * 0.036)
    f = font("serif", size)
    max_w = W * 0.72
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= max_w:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    lh = int(size * 1.32)
    total = lh * len(lines) + int(size * 1.6)
    y = int(H * 0.40) + max(0, (int(H * 0.50) - total) // 2)
    ink = (62, 56, 50)
    for ln in lines:
        tw = d.textlength(ln, font=f)
        d.text(((W - tw) / 2, y), ln, fill=ink, font=f); y += lh
    fr = font("serif", int(size * 0.62)); y += int(size * 0.5)
    rt = ref.upper()
    tw = d.textlength(rt, font=fr)
    d.text(((W - tw) / 2, y), rt, fill=(120, 110, 100), font=fr)
    return img


# --- marcos y mockups ------------------------------------------------------------

def _noise(size, base, amp=6, seed_=1):
    """Textura suave de pared."""
    import numpy as np
    rng = np.random.default_rng(seed_)
    w, h = size
    small = rng.normal(0, amp, (h // 8 + 1, w // 8 + 1))
    n = Image.fromarray(np.clip(small + 128, 0, 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    bg = Image.new("RGB", size, base)
    return Image.blend(bg, Image.merge("RGB", (n, n, n)), 0.06)


def framed(art: Image.Image, frame: str, kind: str, px_per_cm: float) -> Image.Image:
    """Devuelve el cuadro (RGBA) con su marco o el canto del lienzo."""
    art = art.convert("RGB")
    if kind == "lamina":
        # lámina: paspartú fino blanco + marco
        m = int(art.width * 0.06)
        art = ImageOps.expand(art, border=m, fill=(246, 244, 239))
        ImageDraw.Draw(art).rectangle([m - 2, m - 2, art.width - m + 1, art.height - m + 1], outline=(214, 208, 198), width=2)
    if frame == "none":
        # lienzo sin marco: canto lateral y sombra fina
        out = Image.new("RGBA", (art.width, art.height), (0, 0, 0, 0))
        out.paste(art, (0, 0))
        d = ImageDraw.Draw(out)
        d.rectangle([0, 0, art.width - 1, art.height - 1], outline=(0, 0, 0, 40), width=2)
        return out
    fw = max(6, int(px_per_cm * (2.2 if kind == "lienzo" else 2.0)))
    gap = int(fw * 0.22) if kind == "lienzo" else 0  # marco flotante
    col = config.FRAME_COLORS[frame]
    W, H = art.width + 2 * (fw + gap), art.height + 2 * (fw + gap)
    out = Image.new("RGBA", (W, H), col + (255,))
    d = ImageDraw.Draw(out)
    # biseles: luz arriba/izquierda, sombra abajo/derecha
    light = tuple(min(255, int(c * 1.10 + 8)) for c in col); dark = tuple(int(c * 0.72) for c in col)
    d.polygon([(0, 0), (W, 0), (W - fw, fw), (fw, fw)], fill=light + (255,))
    d.polygon([(0, 0), (fw, fw), (fw, H - fw), (0, H)], fill=tuple(int((a + b) / 2) for a, b in zip(light, col)) + (255,))
    d.polygon([(W, 0), (W, H), (W - fw, H - fw), (W - fw, fw)], fill=dark + (255,))
    d.polygon([(0, H), (fw, H - fw), (W - fw, H - fw), (W, H)], fill=tuple(int((a + b) / 2) for a, b in zip(dark, col)) + (255,))
    if frame in ("natural", "dark"):
        # veta de madera sutil (capa aparte para que se mezcle y no deje transparencias)
        g = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(g)
        rnd = random.Random(7)
        for _ in range(60):
            y = rnd.randint(0, H); a = rnd.randint(6, 14)
            gd.line([(0, y), (fw, y)], fill=(0, 0, 0, a)); gd.line([(W - fw, y), (W, y)], fill=(0, 0, 0, a))
            x = rnd.randint(0, W)
            gd.line([(x, 0), (x, fw)], fill=(0, 0, 0, a)); gd.line([(x, H - fw), (x, H)], fill=(0, 0, 0, a))
        out = Image.alpha_composite(out, g); d = ImageDraw.Draw(out)
    if gap:
        d.rectangle([fw, fw, W - fw - 1, H - fw - 1], fill=(58, 52, 46, 255))
    out.paste(art, (fw + gap, fw + gap))
    # sombra interior del marco sobre la obra
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(sh)
    sd.rectangle([fw + gap, fw + gap, W - fw - gap, fw + gap + max(2, fw // 4)], fill=(0, 0, 0, 50))
    sd.rectangle([fw + gap, fw + gap, fw + gap + max(2, fw // 4), H - fw - gap], fill=(0, 0, 0, 35))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(max(1, fw // 5))))
    return out


def _drop_shadow(obj: Image.Image, offset=(10, 18), blur=22, opacity=95):
    pad = blur * 3
    sh = Image.new("RGBA", (obj.width + pad * 2, obj.height + pad * 2), (0, 0, 0, 0))
    a = obj.split()[3].point(lambda v: opacity if v > 0 else 0)
    sh.paste((0, 0, 0, 255), (pad + offset[0], pad + offset[1]), a)
    return sh.filter(ImageFilter.GaussianBlur(blur)), pad


def on_wall(art: Image.Image, frame: str, kind: str, canvas_size=(1600, 2000), wall=(222, 220, 215), fill=0.62) -> Image.Image:
    """Cuadro centrado sobre pared gris claro, como la foto principal de la referencia."""
    W, H = canvas_size
    bg = _noise((W, H), wall)
    # degradado de luz desde arriba a la izquierda
    gx = Image.linear_gradient("L").rotate(90).resize((W, H))  # claro a la izquierda
    gy = Image.linear_gradient("L").resize((W, H))  # claro arriba
    g = Image.blend(gx, gy, 0.5).point(lambda v: 255 - int(v * 0.45))
    bg = Image.composite(bg, Image.new("RGB", (W, H), tuple(int(c * 0.9) for c in wall)), g)
    horiz = art.width >= art.height
    target_w = int(W * (0.78 if horiz else 0.56)) if fill is None else int(W * (fill + (0.16 if horiz else 0)))
    ppcm = target_w / 90
    a = art.resize((target_w, int(target_w * art.height / art.width)), Image.LANCZOS)
    f = framed(a, frame, kind, ppcm)
    sh, pad = _drop_shadow(f, offset=(int(W * 0.006), int(W * 0.012)), blur=int(W * 0.012))
    x = (W - f.width) // 2; y = int(H * 0.47) - f.height // 2
    out = bg.convert("RGBA")
    out.alpha_composite(sh, (x - pad, y - pad)); out.alpha_composite(f, (x, y))
    return out.convert("RGB")


def close_up(art: Image.Image, out_size=(1600, 2000)) -> Image.Image:
    w, h = art.size
    cw = int(w * 0.42); ch = int(cw * out_size[1] / out_size[0])
    ch = min(ch, h); cw = int(ch * out_size[0] / out_size[1])
    # zona con más detalle: centro-abajo, donde suelen estar las figuras
    x = (w - cw) // 2; y = min(h - ch, int(h * 0.52) - ch // 2)
    crop = art.crop((x, max(0, y), x + cw, max(0, y) + ch)).resize(out_size, Image.LANCZOS)
    return crop.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))


def frame_swatches(art: Image.Image, kind: str, out_size=(1600, 2000)) -> Image.Image:
    """Las 4-5 opciones de marco una al lado de otra (sustituye a la foto de esquinas de marcos)."""
    W, H = out_size
    bg = _noise((W, H), (232, 229, 223))
    opts = [f for f, _ in config.frames_for(kind)]
    n = len(opts)
    cell = W // n
    tw = int(cell * 0.78)
    a = art.resize((tw, int(tw * art.height / art.width)), Image.LANCZOS)
    out = bg.convert("RGBA"); d = ImageDraw.Draw(out)
    labels = dict(config.FRAMES)
    fnt = font("serif", int(W * 0.028))
    for i, fr in enumerate(opts):
        f = framed(a, fr, kind, tw / 30)
        x = i * cell + (cell - f.width) // 2; y = int(H * 0.45) - f.height // 2
        sh, pad = _drop_shadow(f, offset=(4, 8), blur=12)
        out.alpha_composite(sh, (x - pad, y - pad)); out.alpha_composite(f, (x, y))
        lab = labels[fr]; lw = d.textlength(lab, font=fnt)
        d.text((i * cell + (cell - lw) / 2, y + f.height + int(H * 0.035)), lab, fill=(70, 64, 58), font=fnt)
    return out.convert("RGB")


def sizes_chart(art: Image.Image, kind: str, tpl: Image.Image | None, geo: dict | None, out_size=(1600, 2000)) -> Image.Image:
    """Los tamaños a escala sobre un sofá de 220 cm (plantilla IA con el sofá marcado)."""
    if tpl is not None and geo:
        bg = tpl.copy().convert("RGB")
        x0, y0, x1, y1 = geo["sofa"]
        sofa_cm = 220
    else:
        W, H = out_size
        bg = _noise((W, H), (228, 226, 221))
        x0, x1 = int(W * 0.18), int(W * 0.82); y0 = int(H * 0.74); y1 = int(H * 0.95)
        d = ImageDraw.Draw(bg)
        d.rounded_rectangle([x0, y0, x1, y1], radius=30, fill=(214, 206, 192))
        sofa_cm = 220
    W, H = bg.size
    ppcm = (x1 - x0) / sofa_cm
    out = bg.convert("RGBA"); d = ImageDraw.Draw(out)
    fnt = font("serif", max(18, int(W * 0.022)))
    sizes = config.sizes_for(kind)
    horiz = art.width >= art.height
    # 1 grande centrado sobre el sofá, el resto repartido arriba a escala
    placements = []
    big = sizes[-1]; small = sizes[:-1]
    def dims(s):
        a, b = s[1] / 10, s[2] / 10
        return (b, a) if horiz else (a, b)
    bw, bh = dims(big)
    placements.append((big[0], (x0 + x1) / 2 - bw * ppcm / 2, y0 - (bh + 22) * ppcm, bw, bh))
    top = y0 - (bh + 22) * ppcm - 18 * ppcm
    ws = [dims(s)[0] * ppcm for s in small]
    gap = (W * 0.9 - sum(ws)) / (len(ws) + 1)
    cx = W * 0.05 + gap
    for s, wpx in zip(small, ws):
        w_, h_ = dims(s)
        placements.append((s[0], cx, top - h_ * ppcm, w_, h_))
        cx += wpx + gap
    for name, x, y, w_, h_ in placements:
        pw, ph = max(8, int(w_ * ppcm)), max(8, int(h_ * ppcm))
        if y < 30:
            continue
        a = art.resize((pw, ph), Image.LANCZOS)
        f = framed(a, "natural" if kind == "lienzo" else "natural", kind, ppcm)
        fx, fy = int(x - (f.width - pw) / 2), int(y - (f.height - ph) / 2)
        sh, pad = _drop_shadow(f, offset=(3, 6), blur=8, opacity=70)
        out.alpha_composite(sh, (fx - pad, fy - pad)); out.alpha_composite(f, (fx, fy))
        lab = f"{name} cm"; lw = d.textlength(lab, font=fnt)
        d.text((fx + f.width / 2 - lw / 2, fy - fnt.size - 8), lab, fill=(60, 56, 52), font=fnt)
    lab = "Sofá estándar de 220 cm"; lw = d.textlength(lab, font=fnt)
    d.line([(x0, y0 - 18), (x1, y0 - 18)], fill=(60, 56, 52), width=2)
    d.text(((x0 + x1) / 2 - lw / 2, y0 - 18 - fnt.size - 6), lab, fill=(60, 56, 52), font=fnt)
    return out.convert("RGB")


# --- plantillas de estancia (IA, una sola vez) -----------------------------------

ROOM_TEMPLATES = {
    "salon_h": "Fotografía de interiorismo editorial, vista totalmente frontal de la pared de un salón moderno y cálido de estilo minimalista: pared lisa color hueso, sofá de lino beige, cojines neutros, mesa baja de madera clara, jarrón de cerámica con ramas secas, suelo de roble, luz natural suave desde la izquierda. Colgado en la pared, centrado sobre el sofá, un rectángulo horizontal perfectamente plano pintado de verde puro uniforme (#00FF00), proporción 3:2, sin marco, sin textura, sin reflejos.",
    "recibidor_h": "Fotografía de interiorismo editorial, vista frontal de un recibidor elegante: pared con molduras clásicas color blanco roto, consola de madera antigua con libros y dos jarrones de barro con hortensias, apliques de latón con pantalla de lino, suelo de madera. Colgado en la pared sobre la consola, un rectángulo horizontal perfectamente plano pintado de verde puro uniforme (#00FF00), proporción 3:2, sin marco, sin textura, sin reflejos.",
    "comedor_h": "Fotografía de interiorismo editorial, vista frontal de un comedor moderno y luminoso: mesa de madera maciza con sillas tapizadas en lino, lámpara de papel colgante, aparador bajo, pared lisa beige claro. Colgado en la pared, centrado, un rectángulo horizontal perfectamente plano pintado de verde puro uniforme (#00FF00), proporción 3:2, sin marco, sin textura, sin reflejos.",
    "dormitorio_v": "Fotografía de interiorismo editorial, vista frontal de un dormitorio sereno: cama con ropa de lino beige y cabecero tapizado, mesita de madera con lámpara de cerámica, pared lisa color hueso, luz natural suave. Colgado en la pared junto a la cama, un rectángulo vertical perfectamente plano pintado de verde puro uniforme (#00FF00), proporción 2:3, sin marco, sin textura, sin reflejos.",
    "pasillo_v": "Fotografía de interiorismo editorial, vista frontal de un rincón de recibidor estrecho: banco de madera, cesta de mimbre, una planta de olivo en maceta, pared lisa blanco roto. Colgado en la pared, un rectángulo vertical perfectamente plano pintado de verde puro uniforme (#00FF00), proporción 2:3, sin marco, sin textura, sin reflejos.",
    "sofa_tallas": "Fotografía de interiorismo minimalista, vista totalmente frontal y recta de una pared lisa gris muy claro con un sofá de lino blanco roto de tres plazas en la parte inferior, suelo claro, mucha pared vacía encima. Justo encima del respaldo del sofá, una franja horizontal fina de verde puro (#00FF00) exactamente igual de ancha que el sofá, de lado a lado del sofá. Sin cuadros, sin texto, sin objetos en la pared.",
}


async def generate_room(key: str) -> Image.Image:
    size = "1536x1024" if key.endswith("_h") else ("1024x1536" if key.endswith("_v") else "1024x1536")
    return await _openai_image(ROOM_TEMPLATES[key], size, "high")


def _quad_from_mask(mask):
    import numpy as np
    ys, xs = np.nonzero(mask)
    if len(xs) < 1500:
        return None
    pts = np.stack([xs, ys], axis=1)
    s_ = pts.sum(axis=1); d_ = pts[:, 0] - pts[:, 1]
    tl = pts[s_.argmin()]; br = pts[s_.argmax()]; tr = pts[d_.argmax()]; bl = pts[d_.argmin()]
    return [tuple(map(int, tl)), tuple(map(int, tr)), tuple(map(int, br)), tuple(map(int, bl))]


def detect_green(img: Image.Image):
    import numpy as np
    arr = np.asarray(img.convert("RGB")).astype(int)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mask = (g > 140) & (g - r > 60) & (g - b > 60)
    return _quad_from_mask(mask), mask


def clean_green(img: Image.Image, mask) -> Image.Image:
    """Quita el verde de la plantilla (para la de tallas) rellenando con el color de la pared cercano."""
    import numpy as np
    arr = np.asarray(img.convert("RGB")).copy()
    ys, xs = np.nonzero(mask)
    if len(ys):
        y0 = max(0, ys.min() - 12)
        ref = arr[max(0, y0 - 6):y0, xs.min():xs.max()].reshape(-1, 3).mean(axis=0)
        grow = Image.fromarray((mask * 255).astype("uint8")).filter(ImageFilter.MaxFilter(9))
        m = np.asarray(grow) > 0
        arr[m] = ref.astype("uint8")
    return Image.fromarray(arr)


def in_room(tpl: Image.Image, quad, art: Image.Image, frame: str, kind: str) -> Image.Image:
    """Encaja el cuadro (con marco) en el rectángulo verde de la plantilla."""
    out = tpl.copy().convert("RGBA")
    # plantillas frontales: rectángulo recto según la máscara verde; lo que tapa el hueco (flores,
    # lámparas) se respeta porque solo se pinta donde había verde
    import numpy as np
    _, mask = detect_green(tpl)
    ys, xs = np.nonzero(mask)
    bx0, bx1, by0, by1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    ppcm = bw / 90
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rectangle([bx0 + 6, by0 + 10, bx1 + 6, by1 + 12], fill=(0, 0, 0, 70))
    shm = Image.fromarray((~mask * 255).astype("uint8"))  # la sombra solo fuera del hueco
    sh.putalpha(Image.composite(sh.split()[3], Image.new("L", out.size, 0), shm))
    out = Image.alpha_composite(out, sh.filter(ImageFilter.GaussianBlur(10)))
    f = framed(ImageOps.fit(art, (bw, bh), Image.LANCZOS), frame, kind, ppcm).resize((bw, bh), Image.LANCZOS)
    layer = Image.new("RGBA", out.size, (0, 0, 0, 0)); layer.paste(f, (bx0, by0))
    m = Image.fromarray((mask * 255).astype("uint8")).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(0.8))
    layer.putalpha(Image.composite(layer.split()[3], Image.new("L", out.size, 0), m))
    out = Image.alpha_composite(out, layer)
    return out.convert("RGB")


# --- impresión ---------------------------------------------------------------------

def print_file(art: Image.Image, kind: str, size_key: str, frame: str) -> bytes:
    """PNG para Gelato: reescalado al tamaño físico (150 ppp) con sangrado para el canto del lienzo."""
    sizes = {s[0]: (s[1], s[2]) for s in config.sizes_for(kind)}
    a_mm, b_mm = sizes[size_key]
    horiz = art.width >= art.height
    w_mm, h_mm = (b_mm, a_mm) if horiz else (a_mm, b_mm)
    bleed = 40 if (kind == "lienzo" and frame == "none") else 5  # canto envuelto vs. borde
    dpi = 150
    W = int((w_mm + 2 * bleed) / 25.4 * dpi); H = int((h_mm + 2 * bleed) / 25.4 * dpi)
    if kind == "lamina":
        # papel con margen blanco proporcional, la ilustración centrada al aspecto que toque
        img = Image.new("RGB", (W, H), (246, 244, 239))
        m = int(min(W, H) * 0.07)
        inner = ImageOps.contain(art, (W - 2 * m, H - 2 * m), Image.LANCZOS)
        img.paste(inner, ((W - inner.width) // 2, (H - inner.height) // 2))
    else:
        if bleed > 5:
            # sangrado espejo para el canto (no se corta la escena)
            core = ImageOps.fit(art, (int(w_mm / 25.4 * dpi), int(h_mm / 25.4 * dpi)), Image.LANCZOS)
            b = int(bleed / 25.4 * dpi)
            img = Image.new("RGB", (core.width + 2 * b, core.height + 2 * b))
            img.paste(core, (b, b))
            img.paste(ImageOps.mirror(core.crop((0, 0, b, core.height))), (0, b))
            img.paste(ImageOps.mirror(core.crop((core.width - b, 0, core.width, core.height))), (core.width + b, b))
            top = img.crop((0, b, img.width, 2 * b)); img.paste(ImageOps.flip(top), (0, 0))
            bot = img.crop((0, img.height - 2 * b, img.width, img.height - b)); img.paste(ImageOps.flip(bot), (0, img.height - b))
        else:
            img = ImageOps.fit(art, (W, H), Image.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=40, threshold=3))
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=95, dpi=(dpi, dpi), subsampling=0)
    return buf.getvalue()


def jpeg(img: Image.Image, q: int = 86, max_side: int | None = None) -> bytes:
    if max_side:
        img = ImageOps.contain(img, (max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO(); img.convert("RGB").save(buf, format="JPEG", quality=q, optimize=True, progressive=True)
    return buf.getvalue()
