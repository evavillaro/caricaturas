"""Fotos del cuadro colgado en una estancia real (plantillas IA con hueco verde, compartidas con la tienda de cuadros)."""
import io
import random

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageOps

FRAME_COLORS = {"natural": (198, 174, 138), "dark": (92, 62, 42), "black": (28, 28, 28), "gold": (176, 146, 86), "white": (240, 238, 232)}
# plantillas verticales (dormitorio y recibidor) ya generadas para la tienda de cuadros
ROOMS = {
    "dormitorio": "https://hvyheqafntipzywvkoqr.supabase.co/storage/v1/object/public/fe/_rooms/dormitorio_v.png",
    "recibidor": "https://hvyheqafntipzywvkoqr.supabase.co/storage/v1/object/public/fe/_rooms/pasillo_v.png",
}
_cache = {}


def room(name: str) -> Image.Image:
    if name not in _cache:
        _cache[name] = Image.open(io.BytesIO(httpx.get(ROOMS[name], timeout=60).content)).convert("RGB")
    return _cache[name]


class config:  # compatibilidad con el código copiado
    FRAME_COLORS = FRAME_COLORS


def _drop_shadow(obj: Image.Image, offset=(10, 18), blur=22, opacity=95):
    pad = blur * 3
    sh = Image.new("RGBA", (obj.width + pad * 2, obj.height + pad * 2), (0, 0, 0, 0))
    a = obj.split()[3].point(lambda v: opacity if v > 0 else 0)
    sh.paste((0, 0, 0, 255), (pad + offset[0], pad + offset[1]), a)
    return sh.filter(ImageFilter.GaussianBlur(blur)), pad


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


