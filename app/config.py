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
PRICE_CANVAS_CENTS = int(env("PRICE_CANVAS_CENTS", "5900"))   # lienzo 30x40
PRICE_POSTER_CENTS = int(env("PRICE_POSTER_CENTS", "3900"))   # póster A3
PRICE_DIGITAL_CENTS = int(env("PRICE_DIGITAL_CENTS", "1900"))  # solo archivo

# --- Generación de imagen ----------------------------------------------------
OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_IMAGE_MODEL = env("OPENAI_IMAGE_MODEL", "gpt-image-1")
IMAGE_SIZE = env("IMAGE_SIZE", "1024x1536")  # vertical, proporción 2:3 (30x45 ~ 30x40)
STYLE_PROMPT = env(
    "STYLE_PROMPT",
    "Convierte a las personas de esta foto en una caricatura ilustrada de estilo "
    "cartoon moderno: cabeza grande, cuerpo pequeño, rasgos exagerados pero muy "
    "reconocibles (misma forma de cara, peinado, gafas, barba, sonrisa, color de "
    "piel, ojos y pelo). Expresión alegre. Trazo limpio, colores planos y vivos, "
    "sombreado suave. Fondo liso de un solo color pastel. Sin texto, sin marca de "
    "agua, sin marco. Composición centrada, apta para imprimir en lienzo vertical.",
)

# --- Pago -----------------------------------------------------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")

# --- Impresión (Gelato) ---------------------------------------------------------
GELATO_API_KEY = env("GELATO_API_KEY")
# UIDs de producto de Gelato. Se obtienen en el catálogo de Gelato; estos son
# ejemplos habituales y hay que confirmarlos en la cuenta antes del primer pedido real.
GELATO_PRODUCT_CANVAS = env(
    "GELATO_PRODUCT_CANVAS",
    "canvas_300x400-mm-12x16-inch_canvas_wood-fsc-slim_4-0_hor",
)
GELATO_PRODUCT_POSTER = env(
    "GELATO_PRODUCT_POSTER",
    "flat_297x420-mm-12r_200-gsm-80lb-uncoated_4-0_ver",
)
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
