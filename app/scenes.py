"""Catálogo de escenas (el "producto" que el cliente elige antes de subir la foto).

Cada escena tiene su prompt: lo que la IA añade a la caricatura (ropa, objetos,
fondo). La cara, el peinado y los rasgos salen siempre de la foto.
Las categorías son las landings de regalo (SEO y ads): /regalos/<slug>.
"""

CATEGORIES = {
    "cumpleanos": {"name": "Cumpleaños", "title": "Caricatura personalizada para regalo de cumpleaños", "intro": "El regalo de cumpleaños que nadie se espera: su caricatura en lienzo, con la escena que mejor le describe."},
    "40-50-60": {"name": "40, 50 y 60 años", "title": "Regalo original para 40, 50 o 60 cumpleaños: caricatura desde una foto", "intro": "Para los cumpleaños redondos. Con el número en el cuadro si quieres."},
    "boda": {"name": "Boda y aniversario", "title": "Caricatura de pareja para boda o aniversario", "intro": "Los novios o la pareja de siempre, en su escena. Un regalo de boda que se cuelga, no que se guarda en un cajón."},
    "familia": {"name": "Familia", "title": "Caricatura de familia desde una foto", "intro": "Toda la familia en un cuadro, mascota incluida. Para Navidad, Reyes o el salón de los abuelos."},
    "aficiones": {"name": "Aficiones y trabajo", "title": "Caricatura con su afición o su profesión", "intro": "Motero, futbolero, runner, chef, médica… la escena que le define, con su cara."},
    "mascotas": {"name": "Mascotas", "title": "Caricatura de tu perro o tu gato", "intro": "Tu mascota como protagonista, con su carácter exagerado como se merece."},
}

SCENES = [
    # id, nombre, categorías, descripción corta, prompt de escena
    ("clasica", "Clásica (fondo liso)", ["cumpleanos", "familia", "boda"], "Sin disfraz: la caricatura tal cual, con fondo de color.", "Ropa como en la foto. Fondo liso de un color pastel que contraste."),
    ("cumple-tarta", "Con tarta y velas", ["cumpleanos", "40-50-60"], "Soplando una tarta enorme con confeti.", "Sosteniendo una tarta de cumpleaños enorme con velas encendidas, confeti y globos de fondo, gorro de fiesta."),
    ("numero-grande", "Número de cumpleaños gigante", ["40-50-60", "cumpleanos"], "Apoyado en su número (40, 50, 60…) a lo grande.", "Apoyado con un brazo sobre un número gigante en 3D de color dorado que representa su edad (el número se indica en la dedicatoria), fondo de fiesta con confeti."),
    ("motero", "Motero", ["aficiones", "cumpleanos"], "Chaqueta de cuero, casco en la mano y su moto detrás.", "Vestido de motero con chaqueta de cuero negra, casco bajo el brazo, una motocicleta clásica grande detrás, carretera y atardecer de fondo."),
    ("futbol", "Futbolero", ["aficiones", "cumpleanos"], "Con la camiseta de su equipo y el balón bajo el brazo.", "Con camiseta de fútbol (colores indicados en la dedicatoria si se dan; si no, camiseta genérica), balón bajo el brazo, estadio lleno de fondo, gesto de celebración."),
    ("runner", "Runner / maratón", ["aficiones"], "Cruzando la meta con dorsal y medalla.", "Corriendo y cruzando una cinta de meta con dorsal, medalla al cuello, brazos en alto, público animando de fondo."),
    ("chef", "Cocinillas", ["aficiones"], "Con delantal, gorro de chef y una sartén en llamas.", "Con delantal y gorro de chef, sartén flambeando en la mano, cocina de restaurante de fondo, cara de orgullo."),
    ("jefa", "Jefe / jefa", ["aficiones", "40-50-60"], "De traje, en su despacho, con los pies en la mesa.", "Con traje elegante, sentado en un sillón de despacho con los pies sobre la mesa, ventanal con rascacielos de fondo, café en la mano."),
    ("medico", "Médico / enfermera", ["aficiones"], "Con bata, fonendo y mucha paciencia.", "Con bata blanca o pijama sanitario, fonendoscopio al cuello, hospital de fondo, sonrisa tranquilizadora."),
    ("profe", "Profe", ["aficiones"], "Delante de la pizarra, con la tiza en la mano.", "Delante de una pizarra llena de fórmulas y dibujos, tiza en la mano, gafas en la punta de la nariz, aula de fondo."),
    ("vino", "Amante del vino", ["cumpleanos", "40-50-60"], "Copa en mano, entre barricas.", "Con una copa de vino tinto enorme en la mano, bodega con barricas de fondo, gesto de catador satisfecho."),
    ("playa", "De vacaciones", ["cumpleanos", "familia"], "Con gafas de sol, flotador y mojito.", "En la playa con gafas de sol, flotador de flamenco, mojito en la mano, palmeras y mar de fondo."),
    ("novios", "Novios", ["boda"], "Vestido de novia y traje, con confeti.", "Vestidos de novios (vestido blanco y traje), ramo en la mano, lluvia de confeti y pétalos, iglesia o jardín de fondo."),
    ("aniversario", "Aniversario (corazones)", ["boda"], "La pareja abrazada, con el número de años.", "Pareja abrazada, corazones flotando, el número de años juntos en un cartel (indicado en la dedicatoria), fondo cálido."),
    ("familia-sofa", "Familia en el sofá", ["familia"], "Todos en el sofá, con la mascota.", "Toda la familia sentada junta en un sofá grande y cómodo, mascota incluida si aparece, salón acogedor de fondo, todos riendo."),
    ("superheroes", "Superhéroes", ["familia", "cumpleanos"], "Capa, puños en la cintura y ciudad al fondo.", "Vestidos de superhéroes genéricos con capa y traje de colores (sin logotipos de marcas conocidas), pose de puños en la cintura, ciudad de fondo."),
    ("mascota-rey", "Mascota real", ["mascotas"], "Tu perro o gato con corona y capa.", "La mascota con corona dorada y capa de terciopelo rojo, sentada en un trono, mirada de realeza."),
    ("mascota-pajarita", "Mascota elegante", ["mascotas"], "Con pajarita y fondo de color.", "La mascota con pajarita y sombrero elegante, fondo liso de color vivo, retrato tipo estudio."),
    ("abuelos", "Abuelos", ["familia", "boda"], "Los abuelos en su sillón, con los nietos alrededor.", "Pareja mayor sentada en un sillón, rodeada de nietos dibujados como pequeños cartoon (si aparecen en la foto), salón cálido, manta y taza de té."),
    ("jubilacion", "Jubilación", ["40-50-60", "aficiones"], "Hamaca, caña de pescar y cero prisas.", "Tumbado en una hamaca entre dos palmeras con caña de pescar y bebida con sombrilla, cartel de 'Jubilado' de fondo, cara de felicidad absoluta."),
]

SCENE_BY_ID = {s[0]: {"id": s[0], "name": s[1], "categories": s[2], "desc": s[3], "prompt": s[4]} for s in SCENES}


def scenes_for(category: str | None) -> list[dict]:
    out = []
    for s in SCENES:
        d = SCENE_BY_ID[s[0]]
        if not category or category in d["categories"]:
            out.append({k: d[k] for k in ("id", "name", "categories", "desc")})
    return out
