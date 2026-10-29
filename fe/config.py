"""Configuración de la tienda de cuadros religiosos (marca provisional)."""
import os


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


BRAND = env("BRAND_NAME", "Fe Moderna")
BASE_URL = env("BASE_URL", "http://localhost:8000").rstrip("/")
CONTACT_EMAIL = env("CONTACT_EMAIL", "hola@femoderna.com")
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
FRAME_COLORS = {"natural": (196, 164, 122), "dark": (92, 62, 42), "black": (28, 28, 28), "gold": (176, 146, 86), "white": (240, 238, 232)}

# Lienzo: proporción 2:3 (cm, lado corto x lado largo)
CANVAS_SIZES = [("30x45", 300, 450), ("60x90", 600, 900), ("80x120", 800, 1200), ("100x150", 1000, 1500)]
CANVAS_PRICES = {  # (sin marco, con marco)
    "30x45": (79, 109), "60x90": (149, 199), "80x120": (229, 299), "100x150": (349, 439),
}
# Lámina enmarcada (papel fine art)
PRINT_SIZES = [("20x25", 200, 250), ("30x40", 300, 400), ("45x60", 450, 600), ("60x90", 600, 900)]
PRINT_PRICES = {"20x25": 49, "30x40": 69, "45x60": 99, "60x90": 129}

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
    return FRAMES if kind == "lienzo" else [f for f in FRAMES if f[0] != "none"]


def min_price(kind: str) -> int:
    return min(price_eur(kind, s[0], f[0]) for s in sizes_for(kind) for f in frames_for(kind))
