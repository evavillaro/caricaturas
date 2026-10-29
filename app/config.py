"""Configuración por variables de entorno. Todo opcional: sin claves, la app
funciona en modo demo (caricatura simulada, pago simulado, pedido simulado)."""
import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- Marca y precios -------------------------------------------------------
BRAND_NAME = env("BRAND_NAME", "Caricaturea")
BASE_URL = env("BASE_URL", "http://localhost:8000").rstrip("/")
CURRENCY = env("CURRENCY", "eur")
DISCOUNT_PCT = int(env("DISCOUNT_PCT", "20"))  # descuento de lanzamiento mostrado (precio tachado)
PHONE = env("PHONE", "")  # teléfono de contacto en la barra superior (vacío = no se muestra)
CONTACT_EMAIL = env("CONTACT_EMAIL", "hola@caricaturea.es")
# Precios finales (ya con el descuento aplicado), en céntimos. Referencia: la tienda
# polaca cobra 109,60 zł el archivo, desde 158 zł el lienzo y desde 153 zł el póster
# (1 zł ≈ 0,235 €). Cada uno se puede cambiar con su variable de entorno.
PRICES_CENTS = {
    "digital": int(env("PRICE_DIGITAL_CENTS", "2590")),
    "canvas_20x30": int(env("PRICE_CANVAS_20x30_CENTS", "3790")),
    "canvas_30x40": int(env("PRICE_CANVAS_30x40_CENTS", "4790")),
    "canvas_40x50": int(env("PRICE_CANVAS_40x50_CENTS", "5990")),
    "canvas_50x70": int(env("PRICE_CANVAS_50x70_CENTS", "7990")),
    "canvas_60x90": int(env("PRICE_CANVAS_60x90_CENTS", "10990")),
    "canvas_80x120": int(env("PRICE_CANVAS_80x120_CENTS", "15990")),
    "poster_a4": int(env("PRICE_POSTER_A4_CENTS", "3590")),
    "poster_a3": int(env("PRICE_POSTER_A3_CENTS", "3990")),
    "poster_a2": int(env("PRICE_POSTER_A2_CENTS", "4990")),
    "poster_a1": int(env("PRICE_POSTER_A1_CENTS", "6990")),
}
PRICE_DIGITAL_CENTS = PRICES_CENTS["digital"]
PRICE_CANVAS_20x30_CENTS = PRICES_CENTS["canvas_20x30"]
PRICE_CANVAS_30x40_CENTS = PRICES_CENTS["canvas_30x40"]
PRICE_CANVAS_40x50_CENTS = PRICES_CENTS["canvas_40x50"]
PRICE_POSTER_A4_CENTS = PRICES_CENTS["poster_a4"]
PRICE_POSTER_A3_CENTS = PRICES_CENTS["poster_a3"]
PRICE_CANVAS_CENTS = PRICE_CANVAS_30x40_CENTS
PRICE_POSTER_CENTS = PRICE_POSTER_A3_CENTS
WHATSAPP = env("WHATSAPP", "")  # número con prefijo, p. ej. 34600000000; vacío = no se muestra

# --- Generación de imagen ----------------------------------------------------
OPENAI_API_KEY = env("OPENAI_API_KEY")
# gpt-image-1 se retiró el 23-oct-2026; el actual por defecto es gpt-image-2.5-sunburst
OPENAI_IMAGE_MODEL = env("OPENAI_IMAGE_MODEL", "gpt-image-2.5-sunburst")
IMAGE_SIZE = env("IMAGE_SIZE", "1152x1536")  # vertical 3:4, la proporción del lienzo 30x40 (múltiplos de 16)
IMAGE_QUALITY = env("IMAGE_QUALITY", "high")  # low, medium, high, xhigh, max
STYLE_PROMPT = env(
    "STYLE_PROMPT",
    "Crea una CARICATURA clásica de cabeza grande a partir de la persona de la foto, en estilo "
    "ilustración digital pintada semirrealista (como las caricaturas de regalo personalizadas): "
    "CABEZA ENORME, aproximadamente un tercio de la altura total de la figura, sobre un CUERPO "
    "PEQUEÑO y estilizado de cuerpo entero. La cara debe ser MUY fiel a la foto (misma forma de "
    "cara, ojos, nariz, boca, sonrisa, peinado, color de pelo y piel, gafas o barba si las tiene), "
    "con los rasgos un poco más exagerados, en clave de caricatura de verdad: los rasgos más característicos de la persona (nariz, sonrisa, mentón, orejas, cejas, mofletes) algo agrandados con humor, ojos expresivos y sonrisa amplia, pero sin perder el parecido: tiene que reconocerse al primer vistazo. Sombreado "
    "pintado suave, colores cálidos y vivos, acabado brillante y detallado. La figura ocupa el "
    "centro de una escena completa y detallada. Sin texto (salvo un número de edad si la escena lo "
    "pide), sin marca de agua, sin marco. Composición vertical para imprimir en lienzo.",
)

# --- Pago -----------------------------------------------------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")

# --- Impresión (Gelato) ---------------------------------------------------------
GELATO_API_KEY = env("GELATO_API_KEY")
# UIDs de producto de Gelato. Se obtienen en el catálogo de Gelato; estos son
# ejemplos habituales y hay que confirmarlos en la cuenta antes del primer pedido real.
GELATO_PRODUCTS = {
    "canvas_20x30": env("GELATO_PRODUCT_CANVAS_20x30", "canvas_200x300-mm-8x12-inch_canvas_wood-fsc-slim_4-0_ver"),
    "canvas_30x40": env("GELATO_PRODUCT_CANVAS_30x40", "canvas_300x400-mm-12x16-inch_canvas_wood-fsc-slim_4-0_ver"),
    "canvas_40x50": env("GELATO_PRODUCT_CANVAS_40x50", "canvas_400x500-mm-16x20-inch_canvas_wood-fsc-slim_4-0_ver"),
    "canvas_50x70": env("GELATO_PRODUCT_CANVAS_50x70", "canvas_500x700-mm-20x28-inch_canvas_wood-fsc-slim_4-0_ver"),
    "canvas_60x90": env("GELATO_PRODUCT_CANVAS_60x90", "canvas_600x900-mm-24x36-inch_canvas_wood-fsc-slim_4-0_ver"),
    "canvas_80x120": env("GELATO_PRODUCT_CANVAS_80x120", "canvas_800x1200-mm-32x48-inch_canvas_wood-fsc-slim_4-0_ver"),
    "poster_a4": env("GELATO_PRODUCT_POSTER_A4", "flat_210x297-mm-8r_200-gsm-80lb-uncoated_4-0_ver"),
    "poster_a3": env("GELATO_PRODUCT_POSTER_A3", "flat_297x420-mm-12r_200-gsm-80lb-uncoated_4-0_ver"),
    "poster_a2": env("GELATO_PRODUCT_POSTER_A2", "flat_420x594-mm-16r_200-gsm-80lb-uncoated_4-0_ver"),
    "poster_a1": env("GELATO_PRODUCT_POSTER_A1", "flat_594x841-mm-23r_200-gsm-80lb-uncoated_4-0_ver"),
}
GELATO_ORDERS_URL = env("GELATO_ORDERS_URL", "https://order.gelatoapis.com/v4/orders")

# --- Almacenamiento temporal ----------------------------------------------------
# Nada en base de datos. Fotos, caricaturas y pedidos viven en disco con caducidad.
DATA_DIR = Path(env("DATA_DIR", "/tmp/caricaturas"))
UPLOAD_TTL_HOURS = int(env("UPLOAD_TTL_HOURS", "3"))      # foto y preview sin pagar
PAID_TTL_DAYS = int(env("PAID_TTL_DAYS", "14"))           # archivo final tras pagar
WATERMARK_TEXT = env("WATERMARK_TEXT", BRAND_NAME.upper())
ADMIN_TOKEN = env("ADMIN_TOKEN")  # para /admin/orders

DEMO_MODE = not OPENAI_API_KEY
PAYMENTS_ENABLED = bool(STRIPE_SECRET_KEY)
PRINT_ENABLED = bool(GELATO_API_KEY)
