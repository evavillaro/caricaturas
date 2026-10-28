"""Catálogo: las mismas escenas que la tienda de referencia, agrupadas como ellos
("Regalo para ella" / "Regalo para él") más pareja, familia y mascotas.

Cada escena tiene su prompt: lo que la IA añade a la caricatura (ropa, objetos,
fondo). La cara, el peinado y los rasgos salen siempre de la foto.
"""

GROUPS = [
    ("ella", "Regalo para ella"),
    ("el", "Regalo para él"),
    ("pareja", "Boda, aniversario y pareja"),
    ("familia", "Familia y mascotas"),
]

CATEGORIES = {
    "cumpleanos": {"name": "Cumpleaños", "title": "Caricatura personalizada para regalo de cumpleaños", "intro": "El regalo de cumpleaños que nadie se espera: su caricatura en lienzo, con la escena que mejor le describe."},
    "para-ella": {"name": "Para ella", "title": "Regalo original para una mujer: caricatura desde una foto", "intro": "Glamour, alfombra roja, su copa de vino o su bici con flores. Elige la escena y sube su foto."},
    "para-el": {"name": "Para él", "title": "Regalo original para un hombre: caricatura desde una foto", "intro": "Motero, cazador, fan de la F1 o del Barça, el jefe… la escena que le define, con su cara."},
    "40-50-60": {"name": "40, 50 y 60 años", "title": "Regalo para 40, 50 o 60 cumpleaños: caricatura desde una foto", "intro": "Para los cumpleaños redondos, con el número en el cuadro."},
    "boda": {"name": "Boda y aniversario", "title": "Caricatura de pareja para boda o aniversario", "intro": "Los novios o la pareja de siempre, en su escena. Un regalo de boda que se cuelga."},
    "familia": {"name": "Familia y mascotas", "title": "Caricatura de familia o de tu mascota desde una foto", "intro": "Toda la familia en un cuadro, mascota incluida."},
}

# id, nombre, grupo, categorías, descripción corta, prompt de escena
SCENES = [
    # Regalo para ella
    ("cumple-dorado", "Caricatura de cumpleaños personalizada", "ella", ["para-ella", "cumpleanos", "40-50-60"], "Vestido negro, copa de champán y globos dorados con el número.", "Mujer con vestido negro elegante sentada entre globos dorados gigantes que forman su número de cumpleaños (el número se indica en la dedicatoria), copa de champán en la mano, confeti dorado, fondo dorado brillante."),
    ("glamour", "Caricatura glamurosa: regalo para una amiga", "ella", ["para-ella", "cumpleanos"], "Vestido de gala verde esmeralda y luces de neón con su edad.", "Mujer con vestido largo de gala verde esmeralda brillante, pose de alfombra roja, copa en la mano, detrás un número de neón dorado con su edad (indicada en la dedicatoria), cortina dorada y confeti."),
    ("glamour-40", "Retrato glamuroso para el 40 cumpleaños", "ella", ["para-ella", "40-50-60"], "Sillón de terciopelo, vestido rojo y lámpara de araña.", "Mujer con vestido rojo de gala sentada en un sillón de terciopelo, copa de champán, un gran '40' luminoso (o la edad de la dedicatoria) y lámpara de araña de fondo, ambiente de salón elegante."),
    ("vino", "Caricatura de amante del vino", "ella", ["para-ella", "cumpleanos"], "Sentada dentro de una copa de vino gigante, botella en mano.", "Mujer sentada dentro de una copa de vino tinto gigante, con una botella de vino en la mano y gesto divertido, fondo cálido con brillos."),
    ("alfombra-roja", "Caricatura en la alfombra roja", "ella", ["para-ella", "cumpleanos"], "Vestido de estrella, flashes y alfombra roja.", "Mujer con vestido de gala brillante posando en una alfombra roja, flashes de fotógrafos y cordones dorados de fondo, pose de estrella de cine."),
    ("ciclista-flores", "Caricatura de ciclista con flores", "ella", ["para-ella", "cumpleanos"], "Bicicleta vintage con cesta llena de flores.", "Mujer montando una bicicleta vintage con una cesta llena de flores, vestido veraniego, calle de pueblo con casas de colores y sol de fondo."),
    ("reina-oriente", "Caricatura de reina (35, 36, 37 o 40 años)", "ella", ["para-ella", "40-50-60"], "Como una reina en su trono, con corona y joyas.", "Mujer vestida de reina con corona dorada, vestido con bordados y joyas, sentada en un trono, palacio de fondo, gesto de majestad divertida."),
    ("fitness", "Caricatura de entrenadora / fitness", "ella", ["para-ella"], "Ropa deportiva, mancuernas y gimnasio.", "Mujer con ropa deportiva levantando mancuernas con una sonrisa, gimnasio moderno de fondo, pose de fuerza divertida."),
    # Regalo para él
    ("motero", "Caricatura de motociclista", "el", ["para-el", "cumpleanos"], "Chaqueta de cuero, su moto y carretera al atardecer.", "Hombre vestido de motero con chaqueta de cuero marrón, montado en una motocicleta clásica grande, carretera con curvas y atardecer naranja de fondo, sonrisa amplia."),
    ("cazador", "Caricatura de cazador", "el", ["para-el", "cumpleanos"], "Sombrero, chaleco y bosque.", "Hombre vestido de cazador con sombrero y chaleco verde, escopeta al hombro (estilo cartoon inofensivo), perro de caza a su lado, bosque otoñal de fondo."),
    ("formula1", "Regalo para fan de la Fórmula 1", "el", ["para-el", "cumpleanos"], "Mono de piloto, casco bajo el brazo y monoplaza detrás.", "Hombre con mono de piloto de carreras de colores (sin logotipos de marcas reales), casco bajo el brazo, un monoplaza de Fórmula 1 detrás, circuito y podio de fondo."),
    ("traje-18", "Elegante en traje (18 cumpleaños)", "el", ["para-el", "cumpleanos"], "Traje a medida, reloj y ciudad de noche.", "Hombre joven con traje elegante oscuro, corbata, reloj, pose de seguridad, ciudad de noche con luces de fondo, estilo elegante."),
    ("jefe-oleo", "Caricatura del jefe estilo óleo", "el", ["para-el", "40-50-60"], "Retrato de jefe al estilo pintura al óleo clásica, con humor.", "Hombre con traje, retratado al estilo de una pintura al óleo clásica de un noble o general, marco dorado pintado, gesto de jefe orgulloso con un toque de humor."),
    ("cumple-el", "Caricatura de cumpleaños para él", "el", ["para-el", "cumpleanos", "40-50-60"], "Tarta, confeti y el número de su cumpleaños.", "Hombre con camisa, sosteniendo una tarta con velas, gran número dorado con su edad detrás (indicado en la dedicatoria), confeti y globos."),
    ("barca", "Regalo para fan del FC Barcelona", "el", ["para-el", "cumpleanos"], "Camiseta blaugrana y estadio lleno.", "Hombre con camiseta de fútbol a rayas azul y granate (sin escudo ni logotipos reales), balón bajo el brazo, estadio lleno de fondo, gesto de celebración."),
    ("carpintero", "Caricatura de carpintero", "el", ["para-el"], "Taller, delantal y herramientas.", "Hombre con delantal de carpintero y lápiz en la oreja, sosteniendo una tabla y un martillo, taller de madera con herramientas de fondo."),
    ("mecanico", "Caricatura de mecánico con su coche", "el", ["para-el"], "Mono de trabajo, llave inglesa y su coche.", "Hombre con mono de mecánico, llave inglesa en la mano, apoyado en un coche clásico, taller de fondo."),
    ("medico", "Caricatura de médico / enfermera", "el", ["para-el", "para-ella"], "Bata, fonendo y hospital.", "Con bata blanca o pijama sanitario, fonendoscopio al cuello, hospital de fondo, sonrisa tranquilizadora."),
    # Pareja
    ("novios", "Caricatura de novios: regalo de boda", "pareja", ["boda"], "Vestido de novia y traje, lluvia de pétalos.", "Pareja vestida de novios (vestido blanco y traje), ramo en la mano, lluvia de pétalos y confeti, iglesia o jardín de fondo, muy felices."),
    ("aniversario", "Caricatura de pareja para aniversario", "pareja", ["boda"], "Abrazados, con el número de años juntos.", "Pareja abrazada con corazones flotando y un cartel con el número de años juntos (indicado en la dedicatoria), fondo cálido y romántico."),
    ("pareja-moto", "Pareja en moto", "pareja", ["boda", "para-el"], "Los dos en la moto, carretera y atardecer.", "Pareja montada en una motocicleta clásica, ella abrazada a él, chaquetas de cuero, carretera y atardecer de fondo."),
    ("superheroes", "Caricatura de superhéroes", "pareja", ["boda", "familia", "cumpleanos"], "Capa, puños en la cintura y ciudad al fondo.", "Vestidos de superhéroes genéricos con capa y traje de colores (sin logotipos de marcas conocidas), pose de puños en la cintura, ciudad de fondo."),
    # Familia y mascotas
    ("familia-sofa", "Caricatura de familia en el sofá", "familia", ["familia"], "Todos en el sofá, con la mascota.", "Toda la familia sentada junta en un sofá grande, mascota incluida si aparece, salón acogedor de fondo, todos riendo."),
    ("abuelos", "Caricatura de los abuelos", "familia", ["familia", "boda"], "Los abuelos en su sillón, con los nietos.", "Pareja mayor sentada en un sillón, rodeada de nietos dibujados como cartoon si aparecen en la foto, salón cálido, manta y taza de té."),
    ("mascota-rey", "Tu mascota como realeza", "familia", ["familia"], "Perro o gato con corona y capa en su trono.", "La mascota con corona dorada y capa de terciopelo rojo, sentada en un trono, mirada de realeza."),
    ("mascota-pajarita", "Tu mascota elegante", "familia", ["familia"], "Con pajarita, retrato de estudio.", "La mascota con pajarita y sombrero elegante, fondo liso de color vivo, retrato tipo estudio."),
    ("jubilacion", "Caricatura de jubilación", "familia", ["40-50-60", "para-el", "para-ella"], "Hamaca, caña de pescar y cero prisas.", "Tumbado en una hamaca entre dos palmeras con caña de pescar y bebida con sombrilla, cartel de 'Jubilado' de fondo, cara de felicidad absoluta."),
    ("clasica", "Caricatura clásica (fondo liso)", "familia", ["cumpleanos", "familia", "boda", "para-ella", "para-el"], "Sin disfraz: la caricatura tal cual, con fondo de color.", "Ropa como en la foto. Fondo liso de un color pastel que contraste."),
]

SCENE_BY_ID = {s[0]: {"id": s[0], "name": s[1], "group": s[2], "categories": s[3], "desc": s[4], "prompt": s[5]} for s in SCENES}


def scenes_for(category: str | None) -> list[dict]:
    out = []
    for s in SCENES:
        d = SCENE_BY_ID[s[0]]
        if not category or category in d["categories"]:
            out.append({k: d[k] for k in ("id", "name", "group", "categories", "desc")})
    return out
