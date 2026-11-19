# Data Challenge – Mundial 2026 · Equipo 5

**Microeconometría Aplicada / Inferencia Causal, ITAM.**
Equipo: Diego Méndez, André Herrera, Luis Victoria.

**Métrica asignada:** precios de productos complementarios al futbol, sin contar hospedaje.

**Pregunta:** ¿subieron los precios de los bienes y servicios que se consumen junto
con el futbol en las ciudades sede (CDMX, Guadalajara y Monterrey) durante las
quincenas en que se jugaron partidos del Mundial 2026, comparado con lo que
habría pasado sin el torneo?

**Método:** diferencia en diferencias con estudio de evento. Las ciudades tratadas
son las 3 sedes, el grupo de control son las otras 52 ciudades del INPC y la
unidad de observación es ciudad × producto genérico × quincena.

**Segunda fuente:** precios de PROFECO por tienda y producto. Sirve para confirmar el
resultado de los bienes de tienda y para medir la cercanía al estadio y al Fan Fest.
Ver [Segunda fuente: PROFECO](#segunda-fuente-profeco-quién-es-quién-en-los-precios).

## Datos

| | |
|---|---|
| **Fuente** | INEGI, Índice Nacional de Precios al Consumidor (INPC), base 2ª quincena de julio 2018, con la actualización de canasta y ponderadores 2024 |
| **Quién lo recaba** | INEGI levanta precios de una muestra fija de establecimientos en 55 ciudades |
| **Unidad** | Índice de precios de un producto genérico en una ciudad, por quincena |
| **Cobertura** | 55 ciudades × 292 genéricos, de la 1ª quincena de enero 2018 a la última publicada (2ª quincena de octubre 2026 al momento de la descarga) |
| **Consulta en línea** | https://www.inegi.org.mx/app/indicesdeprecios/ → INPC → "Por ciudad" |

**Virtudes:**
- Es oficial, público y se puede replicar sin token.
- Viene cada quincena, lo bastante fino para un evento de unas 4 semanas.
- Trae 52 ciudades no sede que sirven de control.

**Limitaciones:**
- INEGI toma los precios siempre en los mismos establecimientos de toda la zona metropolitana. No mide los precios junto al estadio, así que un efecto local aparece diluido.
- Es un índice, no un precio en pesos.
- No incluye boletos de partidos.

### Cómo se descarga

`code/01_descarga_inpc.py` usa los mismos servicios que la consulta en línea de INEGI:

1. `https://www.inegi.org.mx/app/api/inp/datos/Estructura/<nodo>` lista las series de cada ciudad. El nodo `112001600060` es "Por ciudad".
2. `https://www.inegi.org.mx/app/indicesdepreciosV2/Exportacion.aspx` exporta las series en CSV.

Los archivos se guardan sin modificar (comprimidos) en `data/raw/inpc_ciudad/`.

### Notas de limpieza

- INEGI pone 0 cuando un genérico no existe en una ciudad (por ejemplo, metro en ciudades sin metro). Esos registros se eliminan.
- "Servicios recreativos y centros nocturnos" es un genérico nuevo de la canasta 2024 y empieza en la 2ª quincena de julio 2024. Los demás de análisis empiezan en 2018.
- Algunos precios cambian poco: en 2025–2026, estacionamiento no se movió en 94% de las quincenas, taxi en 67% y loncherías en 69%. Un efecto en esos genéricos aparecería como un escalón que se queda, no como un pico.
- Los refrescos saltan en todas las ciudades en enero 2026, probablemente por el aumento del IEPS. Es un choque nacional y lo absorben los efectos fijos genérico×quincena.

### Calendario de partidos en México (tratamiento)

Fuentes: [ESPN](https://espndeportes.espn.com/futbol/mundial/nota/_/id/16052541/mundial-2026-partidos-fechas-horarios-jugaran-mexico-monterrey-guadalajara) y [Grupo Animal](https://grupoanimal.mx/deportes/calendario-mundial-2026-partidos-fechas-sedes).
Se jugaron 13 partidos entre el 11 de junio y el 5 de julio de 2026. El detalle está en `code/config.py`.

| Sede | Partidos | De México | 1Q jun | 2Q jun | 1Q jul |
|---|---|---|---|---|---|
| CDMX | 5 | 4 | 1 | 3 | 1 |
| Guadalajara | 4 | 1 | 1 | 3 | 0 |
| Monterrey | 4 | 0 | 1 | 3 | 0 |

### Genéricos de análisis (`code/config.py`)

- **Complementarios.** Se agrupan según la teoría de heterogeneidad:
  - **Bebidas y botanas empacadas** (comerciables): cerveza, refrescos, papas fritas y botanas de cereales.
  - **Comida y bebida fuera de casa** (servicios locales): loncherías y taquerías, restaurantes, pizzas, centros nocturnos.
  - **Transporte:** taxi, estacionamiento, autobús foráneo y transporte aéreo.
  - **Equipo para ver o jugar** (comerciables): televisores y artículos deportivos.
- **Placebo** (no deberían moverse con el Mundial): tortilla, detergentes, analgésicos, pañales, consulta médica y mantenimiento de automóvil.
- **Excluidos por la consigna:** hoteles y servicios turísticos en paquete.

## Análisis exploratorio

[`docs/eda.md`](docs/eda.md) revisa si la base cumple con lo que pide la consigna. Cubre:
- cobertura y celdas faltantes;
- rigidez y ruido de los precios;
- dónde quedan las sedes en volatilidad;
- un placebo por año (2018–2026) que muestra la estacionalidad propia de las sedes;
- la brecha de largo plazo entre sedes y no sedes.

Las cifras y gráficas salen de `code/03b_eda.py`.

## Estimación (`code/04_estimacion.py`)

Ecuación, con y = 100 · ln(índice) del genérico j en la ciudad c en la quincena t:

```
y_cjt = α_cj + δ_jt + β · Sede_c · Mundial_t + γ · Sede_c · Después_t + ε_cjt
```

- **α_cj:** efecto fijo ciudad × genérico.
- **δ_jt:** efecto fijo genérico × quincena. Absorbe los choques nacionales de cada producto: inflación, IEPS, estacionalidad y vacaciones.
- **β:** efecto en las 3 quincenas con partidos.
- **γ:** efecto en las quincenas posteriores (2Q jul–2Q oct 2026).
- **Ventana:** 1Q ene 2025 a la última quincena publicada. El periodo de comparación es 1Q ene 2025–2Q may 2026.
- **Estudio de evento:** reemplaza β y γ por un coeficiente por quincena relativa al inicio del Mundial. La referencia es 2Q may 2026.

**Inferencia.** Con solo 3 ciudades tratadas, el error estándar agrupado por ciudad no es confiable (Conley y Taber, 2011; MacKinnon y Webb, 2017). Se reporta, pero las conclusiones se basan en:
1. **Permutación exacta de Fisher.** Se asigna "sede" a cada una de las C(55,3) = 26,235 tripletas de ciudades.
2. **Intervalos al 95% de Conley y Taber.** Usan las C(52,3) = 22,100 tripletas de ciudades de control.
3. **Wild cluster bootstrap restringido** (WCR-t, Rademacher, 9,999 réplicas). Con pocas tratadas suele ser conservador.

El panel está balanceado, así que β de la regresión es exactamente la diferencia en diferencias de promedios por ciudad. El script lo verifica y por eso la permutación puede ser exacta.

**Salidas:**
- `output/tables/tab_did_principal.csv`: por grupo (complementarios, servicios, bienes comerciables, placebo) y por sede.
- `output/tables/tab_did_por_generico.csv`
- `output/tables/tab_estudio_evento.csv`
- `output/figures/fig_estudio_evento.png`
- `output/figures/fig_efectos_por_generico.png`

## Robustez (`code/07_robustez.py`)

Se prueban 10 variantes del diseño, cada una cambiando una sola cosa:
- base de comparación corta o de un mes;
- la final dentro de "durante";
- tendencias lineales por ciudad×genérico;
- control sin ciudades vecinas ni fronterizas;
- control con las ciudades menos ruidosas;
- placebo con un Mundial falso en 2025;
- triple diferencia contra años anteriores.

**Resultados:**
- Los servicios suben en todas las variantes (+0.6% a +2.8%).
- La triple diferencia contra 2020–2025 da **+2.8% (IC 95%: 0.2 a 5.3; p = 0.03)**, con el placebo en cero. Quita la estacionalidad y la tendencia propias de las sedes.
- Bienes comerciables y placebos no se mueven en ninguna variante.

Detalle e interpretación en [`docs/robustez.md`](docs/robustez.md).

**Salidas:**
- `output/tables/tab_robustez.csv`
- `output/figures/fig_robustez.png`

## Segunda fuente: PROFECO, "Quién es Quién en los Precios"

| | |
|---|---|
| **Fuente** | PROFECO, programa "Quién es Quién en los Precios", datos abiertos ([2025](https://www.datos.gob.mx/dataset/programa_quien_es_quien_precios_2025), [2026](https://www.datos.gob.mx/dataset/programa_quien_es_quien_precios_2026)) |
| **Quién lo recaba** | Personal de PROFECO registra precios en supermercados, tiendas de conveniencia, departamentales y mercados |
| **Unidad** | Precio en pesos de un producto (marca y presentación) en una tienda; trae las coordenadas de la tienda |
| **Cobertura** | Archivos quincenales de ene–nov 2025 y de 2026: ene, 2Q feb, may, jun y jul (PROFECO no publicó los demás meses de 2026) |

**Resultado:** cerveza, refrescos, agua, botanas, licores y pollo rostizado subieron
+0.19% en las sedes frente al resto del país (IC 95%: −0.44 a +0.75). Los placebos dan
+0.22%. Tampoco suben más en las tiendas cerca del estadio o del Fan Fest. Confirma que los
bienes de tienda no se movieron, igual que en el INPC. Detalle en [`docs/profeco.md`](docs/profeco.md).

**Cómo se descarga.** El servidor de datos abiertos rechaza descargas automáticas, así que los CSV se bajan a mano:
1. Abran las dos páginas de arriba y den clic en "Descargar" en cada quincena. Son ~200 MB por archivo.
2. Muevan los archivos a `data/raw/profeco/`, sin cambiarles el nombre. La lista está en `config.PROFECO_ARCHIVOS`.

Esa carpeta no se sube al repositorio. Al repositorio solo suben los productos de análisis ya filtrados:
- `data/clean/profeco_precios.parquet` (4 MB)
- `data/clean/profeco_tiendas.csv`
- `data/clean/profeco_productos.csv`

Faltan 7 archivos de 2025 que el servidor cortaba a la mitad; ninguno entra en el diseño principal.

**Salidas** (`code/05_profeco_limpieza.py` y `code/06_profeco_estimacion.py`):
- `output/tables/profeco_did_principal.csv`
- `output/tables/profeco_did_por_grupo.csv`
- `output/tables/profeco_robustez.csv`
- `output/tables/profeco_heterogeneidad_distancia.csv`
- `output/tables/profeco_estudio_evento.csv`
- `output/tables/profeco_regresion_panel.csv`
- `output/tables/profeco_cobertura.csv`
- `output/figures/fig_profeco_estudio_evento.png`
- `output/figures/fig_profeco_por_grupo.png`

## Estructura del repositorio

```
code/
  config.py               rutas, sedes, calendario, genéricos (todo se cambia aquí)
  01_descarga_inpc.py     descarga INEGI → data/raw/inpc_ciudad/
  02_limpieza.py          arma el panel → data/clean/
  03_descriptivos.py      primera gráfica y DiD simple → output/
  03b_eda.py              análisis exploratorio (ver docs/eda.md) → output/
  04_estimacion.py        DiD con efectos fijos, estudio de evento e inferencia → output/
  05_profeco_limpieza.py  filtra los CSV de PROFECO → data/clean/profeco_*
  06_profeco_estimacion.py DiD por tienda×producto, robustez y cercanía al estadio → output/
  07_robustez.py          pruebas de robustez de la estimación con el INPC → output/
data/
  raw/inpc_ciudad/        catálogo de series y un CSV.gz por ciudad (tal como lo entrega INEGI)
  raw/profeco/            CSV completos de PROFECO (no se suben; ver arriba cómo bajarlos)
  clean/                  inpc_ciudad_generico.parquet (todo), inpc_analisis.csv (selección)
                          y profeco_precios.parquet, profeco_tiendas.csv, profeco_productos.csv
output/
  figures/  tables/
docs/                     eda.md (análisis exploratorio), robustez.md, profeco.md (segunda fuente), reporte y notas
```

## Cómo replicar

Requiere Python 3.12 y [uv](https://docs.astral.sh/uv/) (o `pip`).

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python code/01_descarga_inpc.py   # ~10 min; descarga solo lo que falte
.venv/bin/python code/02_limpieza.py
.venv/bin/python code/03_descriptivos.py
.venv/bin/python code/03b_eda.py
.venv/bin/python code/04_estimacion.py      # ~5 s
.venv/bin/python code/07_robustez.py        # ~1 s; usa la tabla de volatilidad de 03b_eda.py
# PROFECO: primero bajen los CSV a data/raw/profeco/ (ver arriba)
.venv/bin/python code/05_profeco_limpieza.py   # ~1 min
.venv/bin/python code/06_profeco_estimacion.py # ~10 s
```

`06_profeco_estimacion.py` corre sin los CSV completos, porque usa los archivos filtrados de `data/clean/`.

Para volver a bajar todo desde INEGI (por ejemplo, para agregar quincenas nuevas), usen
`01_descarga_inpc.py --rehacer`.

## Pendiente

- [x] Estimación principal: efectos fijos ciudad×genérico y genérico×quincena, más el estudio de evento.
- [x] Inferencia con pocas ciudades tratadas: wild cluster bootstrap y permutación de sedes.
- [x] Heterogeneidad: servicios vs. bienes comerciables, y por sede.
- [x] Análisis exploratorio de la base (`docs/eda.md`).
- [x] Segunda fuente: precios de PROFECO por tienda y producto, con robustez (placebo 2025, triple diferencia, tendencias previas) y heterogeneidad por cercanía al estadio y al Fan Fest (`docs/profeco.md`).
- [ ] Ponderadores del INPC 2024, para traducir el efecto a gasto de los hogares.
- [ ] Decidir si se agregan genéricos complementarios que ya están descargados (tequila, otros licores, agua embotellada, pollos rostizados, televisión de paga).
- [x] Robustez (`docs/robustez.md`): placebo en 2025, bases cortas, triple diferencia, sin vecinas ni frontera, tendencias lineales, final dentro de "durante" y control con ciudades menos ruidosas.
- [ ] Reporte (máx. 5 páginas) e invitación al repositorio para `aguilares26` y `juanmaldonado1902`.

## Uso de IA

Se usó Claude (Anthropic) para ubicar las fuentes de datos (INEGI y PROFECO), escribir
los scripts de descarga, limpieza y estimación, y proponer el diseño y la inferencia. El equipo revisó y validó cada paso.
