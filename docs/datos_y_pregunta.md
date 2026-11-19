# Cómo los datos responden la pregunta

Este documento conecta la pregunta del proyecto con las dos bases que usamos: el INPC por ciudad (INEGI) y los precios por tienda de PROFECO. Explica qué aporta cada una, qué amenaza resuelve y qué deja sin responder. Los detalles están en:
- [`eda.md`](eda.md) y [`robustez.md`](robustez.md) para el INPC;
- [`profeco_eda.md`](profeco_eda.md) y [`profeco.md`](profeco.md) para PROFECO.

## 1. El problema

**Pregunta:** ¿el Mundial subió los precios de lo que se consume junto con el futbol (comida y bebida, transporte, botanas, cerveza, pantallas) en CDMX, Guadalajara y Monterrey?

**La dificultad:** vemos los precios de las sedes en junio de 2026 *con* Mundial, pero nunca vemos cuáles habrían sido *sin* Mundial. Comparar contra mayo no basta, porque los precios suben cada mes por inflación, impuestos o temporada.

**La solución (diferencia en diferencias):** usar como contrafactual el cambio de precios en ciudades donde no hubo partidos. Si sin Mundial las sedes y el resto hubieran cambiado igual, la diferencia entre los dos cambios es el efecto del Mundial.

Para que eso funcione, los datos tienen que permitir comprobar cinco cosas:

1. **Tendencias paralelas:** antes del torneo, sedes y control se movían igual.
2. **Sin otro choque solo en las sedes** en esas quincenas, por ejemplo una estacionalidad propia.
3. **Sin contagio:** las ciudades de control no recibieron el efecto.
4. **Composición estable:** se compara el mismo producto antes y después, no una canasta distinta.
5. **Inferencia correcta con solo 3 ciudades tratadas.**

## 2. Qué le pedimos a los datos y qué da cada base

| Lo que necesitamos | Para qué | INPC (INEGI) | PROFECO |
|---|---|---|---|
| Precio del mismo bien antes y durante el torneo, en las sedes | Medir el cambio | Sí, como índice | Sí, en pesos |
| Muchas ciudades sin Mundial, medidas igual | Contrafactual e inferencia por permutación | 52 ciudades | 30 ciudades |
| Frecuencia fina | El torneo duró 5 semanas | Quincenal | Quincenal, con huecos |
| Historia larga | Probar tendencias paralelas y estacionalidad | 2018–2026 (8 años) | Solo 2025–2026 |
| Productos que deberían responder y productos que no | Heterogeneidad y placebos | 14 complementarios y 6 placebos | 9 grupos y 5 placebos |
| **Servicios** (restaurantes, bares, transporte) | Es donde la teoría predice el efecto | **Sí** | **No** |
| Mismo producto en la misma tienda | Evitar cambios de composición | Canasta fija, pero agregada en un índice | **Sí** |
| Ubicación dentro de la ciudad | Ver si el efecto se concentra cerca del estadio | No | **Sí** (coordenadas) |
| Misma cadena en varias ciudades | Ver cómo se fijan los precios | No | **Sí** |

**Las bases se complementan:**
- El INPC trae los servicios, muchas ciudades de control y 8 años de historia.
- PROFECO trae la precisión del mismo producto en la misma tienda, la ubicación y la cadena.
- Ninguna sola alcanza para contar la historia completa.

## 3. Qué aprendimos de cada base

**INPC: los servicios suben y los bienes no.**

| Grupo | β durante el Mundial | IC 95% | p |
|---|---|---|---|
| Servicios: comida fuera de casa y transporte | +1.80% | −0.35 a 3.83 | 0.10 |
| Bienes comerciables: bebidas, botanas, equipo | −0.57% | −2.78 a 2.25 | 0.67 |
| Placebo | +0.10% | −1.81 a 1.79 | 0.92 |

- **Historia larga:** el análisis exploratorio mostró que, en los 8 años previos, los servicios de las sedes *siempre* se quedan atrás en junio–julio (en promedio −0.7 puntos). En 2026 fue el único año en que subieron.
- **Triple diferencia:** compara 2026 contra lo que pasa normalmente en esos meses. Da **+2.8% (IC 0.2 a 5.3; p = 0.03)**, con el placebo en cero.

**PROFECO: confirma, con más precisión, que los bienes no se movieron.**
- Cerveza, refrescos, agua, botanas, licores y pollo rostizado: **+0.19%** (IC −0.44 a +0.75). El intervalo descarta alzas de más de ~0.8%.
- Las tiendas a menos de 5 km del estadio o del Fan Fest tampoco suben más (−0.38%, p = 0.50).
- Ninguna de las 14 variantes de robustez da un alza significativa.

**PROFECO explica el porqué:**
- Dentro de la misma cadena, producto y quincena, las sedes no son más caras que el resto del país (diferencia mediana 0.0%).
- La cadena explica el doble de la dispersión del precio entre tiendas que la ciudad: 62% contra 31%.
- El precio de los bienes empacados lo fija la cadena para una región, no la tienda según la demanda de su colonia.

## 4. La historia completa

La teoría dice que un choque de demanda temporal y local, como miles de aficionados durante unas semanas, sube el precio de un producto cuando se cumplen tres condiciones:

1. **La oferta no puede crecer rápido.** Un restaurante no duplica sus mesas en un mes; una tienda sí puede resurtir cerveza.
2. **El precio se fija localmente.** La fonda decide su precio; Walmart fija el suyo para una región.
3. **El comprador busca poco.** Un visitante no compara precios como un residente.

Los servicios (comida fuera de casa, estacionamiento, centros nocturnos, autobús foráneo) cumplen las tres. Los bienes empacados no cumplen ninguna. Los datos dicen exactamente eso:

- **INPC:** servicios +1.8% (+2.8% al quitar la estacionalidad propia de las sedes); bienes ≈ 0.
- **PROFECO:** bienes ≈ 0 con intervalo angosto, también cerca del estadio, y con precios fijados por cadena.

Esta es la **heterogeneidad justificada por teoría** que pide la consigna: comerciables contra no comerciables, con el mecanismo medido en los datos.

## 5. Cómo cada base resuelve las amenazas al diseño

| Amenaza | Cómo se detectaría | Qué la resuelve | Resultado |
|---|---|---|---|
| Sedes y control ya iban distinto antes | Estudio de evento antes del torneo | Ambas bases | Sin tendencias previas: INPC servicios p = 0.37; PROFECO bebidas p = 0.45 |
| Estacionalidad propia de las sedes en verano | Placebo por año | INPC (8 años): triple diferencia | Servicios +2.8%, placebo 0 |
| Choques nacionales (inflación, IEPS a refrescos en ene 2026) | Saltos en todas las ciudades | Efectos fijos producto×quincena en ambas bases | Absorbidos |
| Aficionados en ciudades vecinas (contagio) | Vecinas con alza | Excluir vecinas (INPC) o incluirlas (PROFECO) | INPC servicios 1.83%; PROFECO 0.20% |
| Cambio en qué tiendas o productos se miden | Composición distinta antes y después | PROFECO: mismo producto en la misma tienda | Bienes ≈ 0 |
| El promedio de la ciudad diluye un efecto local | Alza solo cerca del estadio | PROFECO: distancia al estadio y al Fan Fest | Sin alza cerca, en bienes |
| Anticipación (servicios suben desde marzo 2026) | Escalón antes del torneo | INPC: base corta contra base larga | Base corta +0.8%, larga +1.8% |
| Solo 3 sedes | Errores agrupados poco confiables | Permutación y Conley–Taber en ambas | p-valores honestos (~0.03–0.4) |
| Efecto en todo el país, que la diferencia en diferencias no ve | Alza nacional fuera de la temporada normal | Prueba nacional: 2026 contra 2018–2025 (INPC) y contra 2025 (PROFECO) ([`prueba_nacional.md`](prueba_nacional.md)) | Sin alza nacional en complementarios; los licores bajan ~3% en las dos bases |

## 6. Lo que los datos no pueden responder

- **Ventas o cantidades.** La consigna pide "precios y/o ventas", así que con precios se cumple. Las encuestas de comercio y servicios de INEGI (EMEC, EMS) traen ventas, pero solo por estado y en sectores muy amplios; el de servicios mezcla restaurantes con hoteles.
- **El efecto en servicios cerca del estadio.** No hay una base pública con precios de restaurantes por ubicación. PROFECO solo cubre tiendas.
- **Quién pagó el aumento,** turistas o residentes. Ninguna base distingue al comprador.
- **Un efecto nacional con certeza causal.** La prueba nacional no tiene grupo de control geográfico. Compara 2026 contra otros años, así que cualquier otro choque de junio de 2026 se confunde con el torneo.
- **Hospedaje y boletos.** El hospedaje está excluido por la consigna; los boletos no están en ninguna base.
- **Guadalajara y Monterrey con detalle.** PROFECO tiene pocas tiendas ahí (26 y 27). El INPC tiene una sola serie por ciudad.

## 7. Qué tan grande tendría que ser el efecto para verlo

Con solo 3 sedes, cada base detecta efectos de distinto tamaño. Es el efecto que tendríamos 80% de probabilidad de encontrar como significativo, calculado con los intervalos de cada estimación:

| Base y grupo | Efecto mínimo detectable |
|---|---|
| INPC, servicios | ~3.0% (~1.6% sin transporte aéreo) |
| INPC, restaurantes | ~2.4% |
| INPC, bienes comerciables | ~3.6% |
| PROFECO, bebidas y botanas | ~0.85% |

**Cómo leerlo:**
- En bienes podemos afirmar que no hubo alzas mayores a ~0.8%.
- En servicios solo veríamos alzas grandes. Además, son promedios de toda la ciudad y de la quincena completa: un 10% solo en días de partido o solo cerca del estadio aparece muy diluido.

## 8. Resumen en una frase

- El INPC nos dice **qué** subió: los servicios locales, ~2–3% al descontar la estacionalidad propia de las sedes.
- PROFECO nos dice **qué no subió y por qué**: los bienes de tienda no se movieron, ni cerca del estadio, porque sus precios los fijan cadenas que cobran lo mismo en las sedes que en el resto de su región.
- La prueba nacional confirma que tampoco subieron en el resto del país. Si acaso bajaron, sobre todo los licores.
