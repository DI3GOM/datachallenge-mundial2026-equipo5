"""Parámetros compartidos del proyecto (Data Challenge, equipo 5).

Métrica asignada: precios de productos complementarios al futbol (sin hospedaje).
Todos los scripts importan rutas, ciudades sede, calendario de partidos y la
lista de genéricos desde aquí, para que cualquier cambio se haga en un solo lugar.
"""
from datetime import date
from pathlib import Path

# --- Rutas -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_INPC = ROOT / "data" / "raw" / "inpc_ciudad"
CLEAN = ROOT / "data" / "clean"
FIG = ROOT / "output" / "figures"
TAB = ROOT / "output" / "tables"

# --- Fuente: INEGI, INPC quincenal por ciudad --------------------------------
# Estructura "Por ciudad" del INPC base 2Q julio 2018, con la actualización de
# canasta y ponderadores 2024. Es la versión vigente y llega a la quincena más
# reciente publicada; las series de genéricos empiezan en 2Q julio 2018.
INEGI_ESTRUCTURA_CIUDAD = "112001600060"
INEGI_API_ESTRUCTURA = "https://www.inegi.org.mx/app/api/inp/datos/Estructura/{}"
INEGI_EXPORTA = "https://www.inegi.org.mx/app/indicesdepreciosV2/Exportacion.aspx"
ANIO_INICIO = 2018
ANIO_FIN = 2026

# --- Tratamiento ---------------------------------------------------------------
# Nombres tal como aparecen en INEGI (se verifican en 02_limpieza.py).
SEDES = {
    "Area Metropolitana de la Cd. de México": "CDMX",
    "Guadalajara, Jal.": "Guadalajara",
    "Monterrey, N.L.": "Monterrey",
}

# Ciudades de control que conviene excluir en pruebas de robustez:
# - vecinas a una sede (a menos de ~2 h): pudieron recibir aficionados (contagio).
# - frontera norte: IVA de 8% y salario mínimo propio, su inflación sigue otra dinámica.
VECINAS_SEDES = [
    "Toluca, Edo. de Méx.", "Atlacomulco, Méx.", "Cuernavaca, Mor.", "Pachuca, Hgo.",
    "Tlaxcala, Tlax.", "Tepatitlán, Jal.", "Saltillo, Coah.",
]
FRONTERA_NORTE = [
    "Tijuana, B.C.", "Mexicali, B.C.", "Cd. Juárez, Chih.", "Cd. Acuña, Coah.", "Matamoros, Tamps.",
]

# Los 13 partidos jugados en México (fuentes: ESPN y calendario oficial; ver README).
PARTIDOS = [
    # fecha, sede, fase, partido, juega México
    (date(2026, 6, 11), "CDMX", "Grupo A", "México 2-0 Sudáfrica", True),
    (date(2026, 6, 11), "Guadalajara", "Grupo A", "Corea del Sur 2-1 Chequia", False),
    (date(2026, 6, 14), "Monterrey", "Grupo F", "Suecia 5-1 Túnez", False),
    (date(2026, 6, 17), "CDMX", "Grupo K", "Uzbekistán 1-3 Colombia", False),
    (date(2026, 6, 18), "Guadalajara", "Grupo A", "México 1-0 Corea del Sur", True),
    (date(2026, 6, 20), "Monterrey", "Grupo F", "Túnez 0-4 Japón", False),
    (date(2026, 6, 23), "Guadalajara", "Grupo K", "Colombia 0-1 RD Congo", False),
    (date(2026, 6, 24), "CDMX", "Grupo A", "Chequia 0-3 México", True),
    (date(2026, 6, 24), "Monterrey", "Grupo A", "Sudáfrica 1-0 Corea del Sur", False),
    (date(2026, 6, 26), "Guadalajara", "Grupo H", "Uruguay 0-1 España", False),
    (date(2026, 6, 29), "Monterrey", "Dieciseisavos", "Países Bajos 1-1 Marruecos (pen.)", False),
    (date(2026, 6, 30), "CDMX", "Dieciseisavos", "México 2-0 Ecuador", True),
    (date(2026, 7, 5), "CDMX", "Octavos", "México 2-3 Inglaterra", True),
]

# Quincenas con partidos en México: 1Q junio, 2Q junio y 1Q julio de 2026.
# Se expresan como (año, mes, quincena) para empatar con el INPC.
QUINCENAS_MUNDIAL = [(2026, 6, 1), (2026, 6, 2), (2026, 7, 1)]

# Ventana de estimación: de la 1Q de enero 2025 a la última quincena publicada.
# Incluye un ciclo estacional completo (junio–julio 2025) antes del Mundial.
INICIO_VENTANA = (2025, 1, 1)


def t_quincena(anio, mes, quincena):
    """Índice consecutivo de quincena (0 = 1Q ene 2018), igual que la columna t del panel."""
    return (anio - 2018) * 24 + (mes - 1) * 2 + (quincena - 1)

# --- Genéricos del INPC (canasta 2024) ---------------------------------------------
# Complementarios al futbol, agrupados según la teoría de heterogeneidad:
# los "comerciables" tienen precio casi nacional (marcas, cadenas); los demás
# son servicios locales cuya oferta no puede crecer en el corto plazo.
COMPLEMENTARIOS = {
    # código: (nombre corto, grupo, comerciable)
    "108": ("Cerveza", "Bebidas y botanas empacadas", True),
    "100": ("Refrescos envasados", "Bebidas y botanas empacadas", True),
    "074": ("Papas fritas", "Bebidas y botanas empacadas", True),
    "002": ("Botanas de cereales", "Bebidas y botanas empacadas", True),
    "265": ("Loncherías, fondas y taquerías", "Comida y bebida fuera de casa", False),
    "268": ("Restaurantes", "Comida y bebida fuera de casa", False),
    "266": ("Pizzas", "Comida y bebida fuera de casa", False),
    "246": ("Servicios recreativos y centros nocturnos", "Comida y bebida fuera de casa", False),
    "225": ("Taxi", "Transporte", False),
    "219": ("Estacionamiento", "Transporte", False),
    "222": ("Autobús foráneo", "Transporte", False),
    "227": ("Transporte aéreo", "Transporte", False),
    "231": ("Televisores", "Equipo para ver o jugar", True),
    "241": ("Artículos deportivos", "Equipo para ver o jugar", True),
}

# Genéricos placebo: no deberían responder al Mundial. Se evita electricidad
# (tiene tarifas de verano distintas por ciudad) y todo lo de hospedaje.
PLACEBO = {
    "014": "Tortilla de maíz",
    "176": "Detergentes",
    "184": "Analgésicos",
    "280": "Pañales",
    "199": "Consulta médica",
    "216": "Mantenimiento de automóvil",
}

# Excluidos explícitamente por la consigna (hospedaje).
EXCLUIDOS_HOSPEDAJE = {"270": "Hoteles", "255": "Servicios turísticos en paquete"}

# --- Segunda fuente: PROFECO, "Quién es Quién en los Precios" (QQP) ------------------
# Precios por tienda y producto (marca y presentación). Datos abiertos en datos.gob.mx;
# cada CSV cubre una quincena ("primera parte" = días 1–15). Ver README para descargar.
RAW_PROFECO = ROOT / "data" / "raw" / "profeco"
PROFECO_DATASETS = {
    2025: "https://www.datos.gob.mx/dataset/programa_quien_es_quien_precios_2025",
    2026: "https://www.datos.gob.mx/dataset/programa_quien_es_quien_precios_2026",
}
# Archivos publicados al 18 nov 2026. En 2026 PROFECO no publicó la 1Q feb, marzo, abril
# ni de agosto en adelante.
PROFECO_ARCHIVOS = (
    [f"{m:02d}-2025_{p:02d}.csv" for m in range(1, 12) for p in (1, 2)]
    + [f"b{m:02d}_2026_q{p}.csv" for m, p in
       [(1, 1), (1, 2), (2, 2), (5, 1), (5, 2), (6, 1), (6, 2), (7, 1), (7, 2)]]
)

# Productos que se usan (catálogos "Basicos", "Electrodomesticos" y "Especial"; se dejan
# fuera "Pacic", con precios pactados con el gobierno, y "Mercados").
# Clave: (categoria, producto) tal como vienen en el CSV; producto None = toda la categoría.
PROFECO_COMPLEMENTARIOS = {
    ("Cerveza", None): "Cerveza",
    ("Refrescos Envasados", "Refresco"): "Refrescos",
    ("Refrescos Envasados", "Agua Sin Gas"): "Agua y bebidas hidratantes",
    ("Refrescos Envasados", "Agua con Gas"): "Agua y bebidas hidratantes",
    ("Refrescos Envasados", "Bebidas Hidratantes"): "Agua y bebidas hidratantes",
    ("Chocolates y Golosinas", "Papas Fritas y Similares"): "Botanas",
    ("Chocolates y Golosinas", "Cacahuates"): "Botanas",
    ("Vinos y Licores", None): "Vinos y licores",
    ("Aparatos Electronicos", "Pantallas"): "Pantallas y audio",
    ("Aparatos Electronicos", "Barra de Sonido"): "Pantallas y audio",
    ("Alimentos Cocinados F/casa", None): "Pollo rostizado",
    # Catálogo "Especial": botanas para ver partidos y artículos de futbol (playera
    # oficial, balón). Se usa solo si también tiene precios antes del torneo.
    ("Botanas y Bebidas", None): "Especial: botanas y bebidas",
    ("Artículos Deportivos", None): "Especial: artículos de futbol",
}
# Productos de uso diario que no deberían responder al Mundial.
PROFECO_PLACEBO = {
    ("Detergentes y Productos Similares", None): "Detergentes",
    ("Arts. de Papel P/higiene Personal", None): "Papel higiénico y pañales",
    ("Aceites y Grasas Veg. Comestibles", None): "Aceites",
    ("Arroz y Cereales Preparados", None): "Arroz y cereales",
    ("Leche Procesada", None): "Leche procesada",
}
PROFECO_CATALOGOS = ["Basicos", "Electrodomesticos", "Especial"]

# Ubicaciones (lat, lon) para asignar tiendas a sedes y medir cercanía.
ESTADIOS = {
    "CDMX": (19.3029, -99.1505),         # Estadio Azteca (Banorte)
    "Guadalajara": (20.6818, -103.4626), # Estadio Akron
    "Monterrey": (25.6690, -100.2445),   # Estadio BBVA
}
FAN_FEST = {
    "CDMX": (19.4326, -99.1332),         # Zócalo
    "Guadalajara": (20.6770, -103.3468), # Plaza de la Liberación
    "Monterrey": (25.6783, -100.2836),   # Parque Fundidora
}
# Una tienda es "sede" si está a menos de RADIO_SEDE_KM del estadio. Las tiendas entre
# RADIO_SEDE_KM y BUFFER_KM de cualquier estadio (Toluca, Cuernavaca, Pachuca, Saltillo…)
# se excluyen del control porque pudieron recibir aficionados.
RADIO_SEDE_KM = 40
BUFFER_KM = 100
