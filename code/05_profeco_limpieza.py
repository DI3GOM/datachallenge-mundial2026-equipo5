"""Limpieza de PROFECO "Quién es Quién en los Precios" (QQP), 2025–2026.

Entrada: los CSV completos en data/raw/profeco/ (unos 200 MB cada uno; no se suben al
repositorio, ver README para descargarlos).
Salida (sí se sube):
- data/clean/profeco_precios.parquet: precio promedio por tienda × producto × quincena.
- data/clean/profeco_tiendas.csv: una fila por tienda, con su ubicación, si está en una
  sede y su distancia al estadio y al Fan Fest.
- data/clean/profeco_productos.csv: una fila por producto (marca y presentación).
- output/tables/profeco_cobertura.csv: registros leídos y conservados por archivo.

Solo se conservan los productos de config.PROFECO_COMPLEMENTARIOS y PROFECO_PLACEBO.

Uso:  .venv/bin/python code/05_profeco_limpieza.py
"""
import re
import unicodedata
import warnings

import numpy as np
import pandas as pd

import config as C

COLUMNAS = [
    "producto", "presentacion", "marca", "categoria", "catalogo", "precio",
    "fecha_registro", "cadena_comercial", "giro", "nombre_comercial", "direccion",
    "estado", "municipio", "latitud", "longitud",
]
# Un precio que difiere más de 3 veces (hacia arriba o abajo) de la mediana nacional del
# mismo producto se trata como error de captura.
UMBRAL_ATIPICO = np.log(3)
# Rectángulo que contiene a México; coordenadas fuera de él son errores.
LAT, LON = (14.0, 33.0), (-118.5, -86.5)


def limpiar_texto(s):
    return s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)


def _canonico(texto):
    """Clave para comparar textos entre archivos.

    PROFECO escribe los acentos de tres formas según el archivo: sin acento ("Basicos",
    2025 y casi todo 2026), con "?" en su lugar ("Bal?n", junio 2026) o con acento
    ("Básicos", julio 2026). La clave quita acentos, signos y espacios, y después las
    vocales y la "n" (la ñ también se pierde), así las tres versiones coinciden.
    """
    if texto is None or texto is pd.NA:
        return ""
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[aeioun]", "", re.sub(r"[^a-z0-9]", "", s))


def canonico(s):
    """Aplica _canonico a una columna (calcula una vez por valor distinto)."""
    unicos = pd.unique(s)
    return s.map(dict(zip(unicos, map(_canonico, unicos)))).astype("string")


def seleccion():
    """Tabla (categoria, producto) → grupo y tipo; producto "" significa 'toda la categoría'."""
    filas = [(cat, prod, grupo, "Complementario") for (cat, prod), grupo in C.PROFECO_COMPLEMENTARIOS.items()]
    filas += [(cat, prod, grupo, "Placebo") for (cat, prod), grupo in C.PROFECO_PLACEBO.items()]
    sel = pd.DataFrame(filas, columns=["categoria", "producto", "grupo", "tipo"])
    sel["cat_c"] = sel.categoria.map(_canonico)
    sel["prod_c"] = sel.producto.map(_canonico)
    return sel


def leer(archivo, sel):
    """Lee un CSV, filtra los productos de interés y asigna la quincena."""
    ruta = C.RAW_PROFECO / archivo
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        df = pd.read_csv(ruta, encoding="utf-8-sig", usecols=COLUMNAS, engine="pyarrow",
                         dtype="string", on_bad_lines="warn")
    malas = sum(str(a.message).count("Expected") for a in avisos)
    leidos = len(df)
    for col in ["producto", "categoria", "catalogo", "presentacion", "marca", "cadena_comercial",
                "giro", "nombre_comercial", "direccion", "estado", "municipio"]:
        df[col] = limpiar_texto(df[col])
    df = df[canonico(df.catalogo).isin([_canonico(c) for c in C.PROFECO_CATALOGOS])]
    df = df.assign(cat_c=canonico(df.categoria), prod_c=canonico(df.producto))

    completas = sel[sel.prod_c == ""][["cat_c", "grupo", "tipo"]]
    puntuales = sel[sel.prod_c != ""][["cat_c", "prod_c", "grupo", "tipo"]]
    a = df.merge(completas, on="cat_c", how="inner")
    b = df.merge(puntuales, on=["cat_c", "prod_c"], how="inner")
    df = pd.concat([a, b], ignore_index=True).drop(columns=["cat_c", "prod_c"])

    df["precio"] = pd.to_numeric(df.precio, errors="coerce")
    df["latitud"] = pd.to_numeric(df.latitud, errors="coerce")
    df["longitud"] = pd.to_numeric(df.longitud, errors="coerce")
    fecha = pd.to_datetime(df.fecha_registro.str.replace("/", "-", regex=False).str.slice(0, 10),
                           format="%Y-%m-%d", errors="coerce")
    df = df.assign(fecha=fecha).dropna(subset=["fecha", "precio"])
    df = df[df.precio > 0]
    df["t"] = C.t_quincena(df.fecha.dt.year, df.fecha.dt.month, np.where(df.fecha.dt.day <= 15, 1, 2))
    df["archivo"] = archivo
    resumen = {
        "archivo": archivo, "registros_leidos": leidos, "lineas_malformadas": malas,
        "registros_conservados": len(df),
        "fecha_min": df.fecha.min().date() if len(df) else None,
        "fecha_max": df.fecha.max().date() if len(df) else None,
    }
    return df.drop(columns=["fecha_registro", "catalogo"]), resumen


def distancia_km(lat, lon, punto):
    """Distancia de gran círculo (haversine) de cada tienda a un punto (lat, lon)."""
    lat1, lon1, lat2, lon2 = map(np.radians, [lat, lon, punto[0], punto[1]])
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


def tiendas(df):
    """Una fila por tienda: ciudad, zona (sede, vecina o control) y distancias.

    La zona se decide por municipio, con la ubicación mediana de sus tiendas, para que un
    error en las coordenadas de una tienda no la mueva de ciudad. Las distancias al estadio
    y al Fan Fest sí usan las coordenadas de cada tienda.
    """
    llave = ["estado", "municipio", "nombre_comercial", "direccion"]
    ok = df.latitud.between(*LAT) & df.longitud.between(*LON)
    coords = df[ok].groupby("tienda_llave")[["latitud", "longitud"]].median()
    desc = df.groupby("tienda_llave")[llave + ["cadena_comercial", "giro"]].first()
    t = desc.join(coords.astype("float64"))

    # Ciudad = estado + municipio, agrupados por clave canónica ("Estado de Mexico" y
    # "Estado de México" son la misma); se muestra el nombre más común.
    ciudad = canonico(t.estado) + "|" + canonico(t.municipio)
    nombre = (t.estado + " | " + t.municipio).groupby(ciudad).agg(lambda s: s.value_counts().index[0])
    centro = t.groupby(ciudad)[["latitud", "longitud"]].transform("median")
    # Una tienda a más de 30 km del centro de su municipio tiene coordenadas erróneas.
    lejos = pd.Series(distancia_km(t.latitud, t.longitud, (centro.latitud, centro.longitud)),
                      index=t.index) > 30
    t.loc[lejos, ["latitud", "longitud"]] = np.nan
    print(f"Tiendas con coordenadas lejos de su municipio (se ignoran sus coordenadas): {int(lejos.sum())}")
    centro = t.groupby(ciudad)[["latitud", "longitud"]].transform("median")

    dist_ciudad = pd.DataFrame({s: distancia_km(centro.latitud, centro.longitud, p)
                                for s, p in C.ESTADIOS.items()})
    sin_coord = centro.latitud.isna()
    sede_cercana = dist_ciudad.fillna(np.inf).idxmin(axis=1).where(~sin_coord)
    d = dist_ciudad.min(axis=1).to_numpy(dtype="float64", na_value=np.nan)
    t["zona"] = np.select(
        [sin_coord.to_numpy(), d <= C.RADIO_SEDE_KM, d <= C.BUFFER_KM],
        ["Sin coordenadas", "Sede", "Vecina (excluida)"], default="Control",
    )
    t["sede"] = sede_cercana.where(t.zona == "Sede")
    t["ciudad"] = np.where(t.zona == "Sede", sede_cercana, ciudad.map(nombre))

    # Distancias de cada tienda de una sede a su estadio y a su Fan Fest.
    t["dist_estadio_km"] = [
        distancia_km(la, lo, C.ESTADIOS[s]) if isinstance(s, str) else np.nan
        for la, lo, s in zip(t.latitud, t.longitud, t.sede)
    ]
    t["dist_fanfest_km"] = [
        distancia_km(la, lo, C.FAN_FEST[s]) if isinstance(s, str) else np.nan
        for la, lo, s in zip(t.latitud, t.longitud, t.sede)
    ]
    return t


def main():
    sel = seleccion()
    presentes = [a for a in C.PROFECO_ARCHIVOS if (C.RAW_PROFECO / a).exists()]
    faltan = sorted(set(C.PROFECO_ARCHIVOS) - set(presentes))
    print(f"Archivos encontrados: {len(presentes)} de {len(C.PROFECO_ARCHIVOS)}")
    if faltan:
        print("  Faltan:", ", ".join(faltan))

    partes, cobertura = [], []
    for a in presentes:
        df, res = leer(a, sel)
        partes.append(df)
        cobertura.append(res)
        print(f"  {a}: {res['registros_leidos']:>9,} leídos, {res['registros_conservados']:>7,} conservados,"
              f" {res['fecha_min']} a {res['fecha_max']}"
              + (f", {res['lineas_malformadas']} líneas malformadas" if res["lineas_malformadas"] else ""))
    df = pd.concat(partes, ignore_index=True)

    # Llaves que no dependen de cómo se escribieron los acentos en cada archivo.
    df["tienda_llave"] = (canonico(df.estado) + "|" + canonico(df.municipio) + "|"
                          + canonico(df.nombre_comercial) + "|" + canonico(df.direccion))
    df["producto_llave"] = (canonico(df.categoria) + "|" + canonico(df.producto) + "|"
                            + canonico(df.presentacion) + "|" + canonico(df.marca))

    # Precios atípicos: más de 3 veces arriba o abajo de la mediana del producto.
    lp = np.log(df.precio)
    desvio = lp - lp.groupby(df.producto_llave).transform("median")
    atipicos = desvio.abs() > UMBRAL_ATIPICO
    print(f"Precios atípicos eliminados: {atipicos.sum():,} de {len(df):,} ({atipicos.mean():.2%})")
    df = df[~atipicos]

    tab_t = tiendas(df)
    tab_t["tienda_id"] = np.arange(len(tab_t))
    prod = (df.groupby("producto_llave")[["categoria", "producto", "presentacion", "marca", "grupo", "tipo"]]
            .first())
    prod["producto_id"] = np.arange(len(prod))

    df = df.join(tab_t["tienda_id"], on="tienda_llave").join(prod["producto_id"], on="producto_llave")
    panel = (df.groupby(["tienda_id", "producto_id", "t"], as_index=False)
             .agg(precio=("precio", "mean"), n_registros=("precio", "size")))
    panel = panel.join(prod.set_index("producto_id")[["grupo", "tipo"]], on="producto_id")
    for c in ["grupo", "tipo"]:
        panel[c] = panel[c].astype("category")
    panel["t"] = panel.t.astype("int16")

    C.CLEAN.mkdir(parents=True, exist_ok=True)
    C.TAB.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(C.CLEAN / "profeco_precios.parquet", index=False)
    tab_t.reset_index(drop=True)[["tienda_id"] + [c for c in tab_t.columns if c != "tienda_id"]].round(5).to_csv(
        C.CLEAN / "profeco_tiendas.csv", index=False)
    prod.reset_index(drop=True)[["producto_id", "categoria", "producto", "presentacion", "marca", "grupo", "tipo"]].to_csv(
        C.CLEAN / "profeco_productos.csv", index=False)
    pd.DataFrame(cobertura).to_csv(C.TAB / "profeco_cobertura.csv", index=False)

    print(f"\nPanel: {len(panel):,} filas (tienda × producto × quincena), "
          f"{panel.tienda_id.nunique():,} tiendas, {panel.producto_id.nunique():,} productos, "
          f"{panel.t.nunique()} quincenas")
    print(tab_t.zona.value_counts().to_string())
    print(tab_t[tab_t.zona == "Sede"].sede.value_counts().to_string())
    print(panel.groupby(["tipo", "grupo"], observed=True).size().to_string())


if __name__ == "__main__":
    main()
