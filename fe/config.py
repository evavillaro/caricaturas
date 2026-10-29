"""Configuración de la tienda de cuadros religiosos (marca provisional)."""
import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


BRAND = env("BRAND_NAME", "Cuadros con Alma")
TAGLINE = env("TAGLINE", "Arte cristiano contemporáneo")
BASE_URL = env("BASE_URL", "http://localhost:8000").rstrip("/")
CONTACT_EMAIL = env("CONTACT_EMAIL", "hola@cuadrosconalma.com")
ADMIN_TOKEN = env("ADMIN_TOKEN")
WELCOME_DISCOUNT_PCT = int(env("WELCOME_DISCOUNT_PCT", "15"))
STRIPE_COUPON = env("STRIPE_WELCOME_COUPON")  # id de cupón de Stripe del 15 % (opcional)

OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = env("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
OPENAI_TEXT_MODEL = env("OPENAI_TEXT_MODEL", "gpt-6.1-terra")
ART_QUALITY = env("ART_QUALITY", "high")

STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
GELATO_API_KEY = env("GELATO_API_KEY")
GELATO_ORDERS_URL = env("GELATO_ORDERS_URL", "https://order.gelatoapis.com/v4/orders")

SUPABASE_URL = env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = env("SUPABASE_SERVICE_KEY") or env("SUPABASE_KEY")
BUCKET = env("FE_BUCKET", "fe")

# Analítica (vacío = no se carga)
GA4_ID = env("GA4_ID"); GADS_ID = env("GADS_ID"); GADS_LABEL = env("GADS_LABEL")
META_PIXEL_ID = env("META_PIXEL_ID"); CLARITY_ID = env("CLARITY_ID"); PINTEREST_TAG_ID = env("PINTEREST_TAG_ID")

# --- Producto, tamaños y precios (euros, IVA incluido) ----------------------
FRAMES = [
    ("natural", "Madera clara"),
    ("dark", "Madera oscura"),
    ("gold", "Dorado"),
    ("black", "Negro"),
    ("none", "Sin marco"),
]
FRAME_COLORS = {"natural": (198, 174, 138), "dark": (92, 62, 42), "black": (28, 28, 28), "gold": (176, 146, 86), "white": (240, 238, 232)}

# Lienzo: proporción 2:3 (cm, lado corto x lado largo). Gelato llega hasta 60x90 en 2:3.
CANVAS_SIZES = [("30x45", 300, 450), ("40x60", 400, 600), ("50x75", 500, 750), ("60x90", 600, 900)]
CANVAS_PRICES = {  # (sin marco, con marco) · coste Gelato+envío ≈ 36/65, 46/77, 60/93, 78/127
    "30x45": (79, 109), "40x60": (95, 139), "50x75": (119, 169), "60x90": (145, 209),
}
# Lámina enmarcada · coste ≈ 28, 50, 61, 75
PRINT_SIZES = [("30x40", 300, 400), ("45x60", 450, 600), ("50x70", 500, 700), ("60x90", 600, 900)]
PRINT_PRICES = {"30x40": 59, "45x60": 89, "50x70": 105, "60x90": 125}

# UIDs de Gelato: se rellenan con /admin/fe/gelato (se guardan en Supabase) o por variable de entorno JSON
GELATO_UIDS_JSON = env("FE_GELATO_UIDS")


def price_eur(kind: str, size: str, frame: str) -> int:
    if kind == "lienzo":
        a, b = CANVAS_PRICES[size]
        return a if frame == "none" else b
    return PRINT_PRICES[size]


def sizes_for(kind: str):
    return CANVAS_SIZES if kind == "lienzo" else PRINT_SIZES


def frames_for(kind: str):
    # Gelato: lienzo enmarcado en madera clara, oscura o negro (sin dorado); lámina también en dorado
    if kind == "lienzo":
        return [f for f in FRAMES if f[0] != "gold"]
    return [f for f in FRAMES if f[0] != "none"]


def min_price(kind: str) -> int:
    return min(price_eur(kind, s[0], f[0]) for s in sizes_for(kind) for f in frames_for(kind))
