# Caricaturas personalizadas

Web de una página: sube una foto → caricatura con IA → preview con marca de agua → pago (Stripe) → lienzo/póster por Gelato o descarga del archivo. Sin base de datos: todo vive en disco con caducidad (3 h sin pagar, 14 días pagado) y la foto original no se guarda.

## Para ponerlo en producción (15 minutos)

1. **Repo en GitHub**: crea `evavillaro/caricaturas` (vacío), y desde esta carpeta:
   ```
   git init && git add . && git commit -m "Caricaturas: primera versión" && git branch -M main
   git remote add origin https://github.com/evavillaro/caricaturas.git && git push -u origin main
   ```
2. **Render**: New → Blueprint → elige el repo (usa `render.yaml`). O dímelo y creo el servicio yo desde aquí.
3. **Variables de entorno** en Render (Environment):
   - `BASE_URL` = la URL del servicio (p. ej. `https://caricaturas.onrender.com`). Obligatoria: Stripe y Gelato la usan para volver y para descargar el archivo.
   - `OPENAI_API_KEY` → platform.openai.com → API keys. Sin ella, modo demo (caricatura simulada).
   - `STRIPE_SECRET_KEY` → dashboard.stripe.com → Developers → API keys (empieza por `sk_test_` para probar, `sk_live_` para cobrar de verdad). Sin ella, pago simulado.
   - `STRIPE_WEBHOOK_SECRET` → Developers → Webhooks → Add endpoint: URL `BASE_URL/api/stripe/webhook`, evento `checkout.session.completed`. Copia el `whsec_…`. (Si no lo pones, la página de gracias confirma el pago igualmente consultando a Stripe; el webhook es el respaldo por si el cliente cierra la pestaña.)
   - `GELATO_API_KEY` → dashboard.gelato.com → Developer → API keys (la misma que usas en el print-service vale). Sin ella, el pedido se marca "pendiente de imprimir" y lo ves en `/admin/orders`.
   - `GELATO_PRODUCT_CANVAS` y `GELATO_PRODUCT_POSTER`: UIDs de producto de Gelato. Los que hay por defecto son los habituales (lienzo 30x40 bastidor slim, póster A3 200 g) pero **hay que confirmarlos en tu catálogo de Gelato antes del primer pedido real**.
   - `BRAND_NAME`: nombre de marca. `PRICE_CANVAS_CENTS`, `PRICE_POSTER_CENTS`, `PRICE_DIGITAL_CENTS`: precios en céntimos (5900, 3900, 1900).
   - `ADMIN_TOKEN`: cualquier texto; `BASE_URL/admin/orders?token=…` lista los pedidos.
4. **Dominio**: en Render → Settings → Custom domain, y actualiza `BASE_URL`.

## Probar en local
```
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Abre http://localhost:8000. Sin variables funciona en modo demo de principio a fin.

## Cómo está hecho
- `app/main.py` rutas. `app/imaging.py` generación (OpenAI `gpt-image-1`, edición de imagen con la foto como entrada) + marca de agua + archivo de impresión a 300 dpi con sangrado. `app/fulfilment.py` Stripe Checkout (recoge dirección y teléfono) y pedido a Gelato. `app/storage.py` carpetas temporales por trabajo con limpieza automática.
- `app/static/` landing, página de gracias, legal (rellenar NIF, domicilio y email), estilos.
- `docs/pack-contenido.md` nombres, prompt plantilla, catálogo, ganchos de ads.

## Pendiente que solo puedes hacer tú
- Claves: OpenAI, Stripe, Gelato (y confirmar los UIDs de producto).
- Datos legales de Comartinvi en `app/static/legal.html` y el email en el pie.
- Foto de ejemplo antes/después para el hueco del hero (en cuanto tengas una caricatura real que te guste).
- Elegir nombre (tres candidatos en el pack) y comprar dominio.
