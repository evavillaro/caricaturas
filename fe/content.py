"""Textos de cada ficha (misma estructura que la referencia), generados en español."""
import json

import httpx

from . import config, seed

BEST_FOR_H = "salón encima del sofá, comedor, recibidor, despacho, paredes amplias"
BEST_FOR_V = "pasillos, recibidores estrechos, dormitorio junto a la cama, rincón de oración, escaleras"

PROMPT = """Eres redactor de una tienda española de cuadros religiosos modernos (arte cristiano y católico en tonos neutros,
para casas modernas). Escribe en español de España, tono cálido, sereno y elegante, sin exagerar ni prometer milagros.
Producto: {title} ({kind_name}, orientación {orient}). Escena del diseño: {scene}. Paleta: {pal}.
Versículo: "{verse}" ({ref}).

Devuelve SOLO un JSON con estas claves:
- "intro": 2-3 frases que describen la obra: qué se ve, el estilo (minimalista, texturizado o línea fina) y la paleta con nombres de color concretos. Debe empezar con el nombre del cuadro.
- "details_intro": 2 frases: para qué casas está pensado y en qué estilos de decoración encaja (minimalista, nórdico, rústico moderno, clásico...).
- "subject": una línea con el tema y el pasaje bíblico.
- "style": una línea.
- "occasions": lista corta separada por comas de las ocasiones en que más se regala (bautizo, comunión, boda, casa nueva, día de la madre...), coherente con el tema.
- "about_title": "Sobre " + nombre corto de la obra.
- "about": 2 párrafos (100-150 palabras en total) que explican el pasaje o la devoción, con contexto bíblico o de la tradición católica correcto, y cómo lo refleja la obra.
- "faq": lista de 3 objetos {{"q":..., "a":...}}: 1) qué significa el versículo o la devoción, 2) una pregunta sobre el tema (historia, simbolismo o dónde aparece en la Biblia), 3) qué tamaño elegir para esa pared (usa la regla de los dos tercios del ancho del mueble; los tamaños de lienzo son 30x45, 40x60, 50x75 y 60x90 cm; los de lámina 30x40, 45x60, 50x70 y 60x90 cm).
No inventes datos sobre la empresa, cifras de clientes ni reseñas."""


async def generate(p: dict) -> dict:
    pal = seed.PALETTES.get(p.get("palette") or "beige")[0]
    prompt = PROMPT.format(title=p["title"], kind_name="lienzo" if p["kind"] == "lienzo" else "lámina enmarcada en papel fine art",
                           orient="horizontal" if p["orient"] == "h" else "vertical", scene=p.get("art_prompt") or "", pal=pal,
                           verse=p.get("verse") or "", ref=p.get("verse_ref") or "")
    body = {"model": config.OPENAI_TEXT_MODEL, "messages": [{"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"}, json=body)
    if r.status_code != 200:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:200]}")
    data = json.loads(r.json()["choices"][0]["message"]["content"])
    data["palette"] = pal
    data["best_for"] = BEST_FOR_H if p["orient"] == "h" else BEST_FOR_V
    return data


def fallback(p: dict) -> dict:
    pal = seed.PALETTES.get(p.get("palette") or "beige")[0]
    kind = "lienzo" if p["kind"] == "lienzo" else "lámina enmarcada"
    return {
        "intro": f"{p['title']}: {kind} de arte cristiano moderno en {pal}. Una obra serena, con mucho espacio y un mensaje que se entiende sin necesidad de explicarlo.",
        "details_intro": "Pensado para casas que buscan una decoración limpia y neutra y quieren llevar la fe de forma discreta pero inconfundible.",
        "subject": f"{p['title']} · {p.get('verse_ref') or ''}", "style": "moderno, minimalista, neutro", "palette": pal,
        "best_for": BEST_FOR_H if p["orient"] == "h" else BEST_FOR_V, "occasions": "bautizo, comunión, boda, casa nueva, cumpleaños",
        "about_title": f"Sobre {p['title']}", "about": "", "faq": [],
    }
