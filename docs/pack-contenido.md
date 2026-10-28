# Caricaturas personalizadas — pack de contenido

## 1. Nombre de marca (comprobar dominio .com/.es e Instagram antes de elegir)

| Candidato | Por qué | Riesgo |
|---|---|---|
| **Caricaturea** | Verbo inventado, fácil de decir, suena a "caricatura" + "crea". Es el que lleva la web por defecto (cambia `BRAND_NAME`). | Comprobar que no exista en Latinoamérica. |
| **Cara de Cuadro** | Juego de palabras, memorable en vídeo, dice el producto (cara + cuadro). | Más largo; la expresión tiene matiz negativo en España. |
| **Retratoon** | Retrato + cartoon; internacional, válido para EE. UU. hispano. | Puede sonar a app, menos a regalo. |

## 2. Prompt plantilla (ya está en `config.py` como `STYLE_PROMPT`; aquí para afinarlo mañana)

Objetivo del día 2: parecido 4/5 estable en 5 fotos difíciles (gafas, barba, niño, pareja, mascota).

Base:
> Convierte a las personas de esta foto en una caricatura ilustrada de estilo cartoon moderno: cabeza grande, cuerpo pequeño, rasgos exagerados pero muy reconocibles (misma forma de cara, peinado, gafas, barba, sonrisa, color de piel, ojos y pelo). Expresión alegre. Trazo limpio, colores planos y vivos, sombreado suave. Fondo liso de un solo color pastel. Sin texto, sin marca de agua, sin marco. Composición centrada, apta para imprimir en lienzo vertical.

Variantes para probar (una variable cada vez, con las mismas 5 fotos):
- `rasgos exagerados` → `rasgos ligeramente exagerados` (si el parecido baja).
- Añadir `mantén la ropa y los accesorios de la foto` (ayuda mucho al reconocimiento).
- Añadir `estilo de ilustración digital de libro infantil` o `estilo de animación 3D` (elegir UN estilo de marca y no cambiarlo).
- Fondo: `color pastel` → `color liso que contraste con la ropa`.

Criterios de puntuación (1-5): forma de cara, peinado, gafas/barba, sonrisa, "lo reconocería un amigo en 2 segundos".

## 3. Diez caricaturas de catálogo (para web, ads y ejemplos)

Genera con fotos de stock libres o de familia (con permiso). Cada una es un "momento regalo":

1. Pareja en el sofá con el gato: aniversario.
2. Familia de 4 con el perro: Navidad.
3. Abuelos: "50 años juntos".
4. Padre con bebé: Día del Padre / nacimiento.
5. Jubilación: señor con caña de pescar y café.
6. Amigas en la plaza (la foto de ayer): "las de siempre".
7. Compañeros de oficina (5): despedida del trabajo.
8. Mascota sola: perro con pajarita.
9. Novios: boda (regalo de testigos).
10. Deportista: corredor con dorsal, maratón terminada.

## 4. Textos de la web (ya montados en `index.html`)

- Titular: "Tu caricatura en lienzo, a partir de una foto".
- Subtítulo: "Sube una foto, mira tu caricatura al momento y, si te gusta, la imprimimos en lienzo y te la enviamos a casa. Solo pagas si te convence."
- Garantías: ves el resultado antes de pagar · envío 4-7 días · no guardamos tu foto.
- FAQ: no se parece / qué foto / plazos / privacidad / cambios tras pagar.

## 5. Seis ganchos para Meta Ads (vídeo antes/después, 10-15 s, sin tu cara)

1. "Le hice esto a mi madre con una foto del móvil. Lloró." → foto → caricatura → cuadro en la pared.
2. "El regalo que no se puede comprar en Amazon." → tres caricaturas seguidas.
3. "¿Y si tu perro fuera un dibujo animado?" → mascota.
4. "Para la boda regalamos esto en vez de dinero." → novios.
5. "Lo ves antes de pagar. Si no se parece, no pagas." → pantalla del flujo en el móvil.
6. "Pedido antes del 15 de diciembre = en casa para Navidad." → urgencia.

Texto del anuncio (corto): "Sube una foto, mira tu caricatura al momento y recíbela en lienzo. Solo pagas si te gusta. Desde 19 €."

## 6. Política "no se parece" (ya en la FAQ y en legal.html)

- Antes de pagar: regenerar con otra foto, gratis, sin límite razonable.
- Después de pagar (lienzo/póster): una repetición gratis con otra foto. Sin devolución del dinero (producto personalizado, art. 103.c LGDCU).
- Digital: sin devolución una vez descargado.
