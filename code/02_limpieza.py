"""Paso 2. Limpia los CSV de INEGI y arma el panel ciudad × genérico × quincena.

Entradas:  data/raw/inpc_ciudad/catalogo_series.csv y inpc_<nodo>.csv.gz
Salidas:
  data/clean/inpc_ciudad_generico.parquet  todos los genéricos e índice general
  data/clean/inpc_analisis.csv             solo complementarios y placebos

Uso (desde la raíz del repositorio):
    .venv/bin/python code/02_limpieza.py
"""
import gzip
import io
import re
from datetime import date

import numpy as np
import pandas as pd

from config import CLEAN, COMPLEMENTARIOS, PLACEBO, QUINCENAS_MUNDIAL, RAW_INPC, SEDES

MESES = {m: i for i, m in enumerate(
    ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"], 1)}
RE_PERIODO = re.compile(r"^([12])Q (\w{3}) (\d{4})$")


def leer_exportacion(ruta):
    """Lee un CSV exportado por INEGI (encabezado de varias líneas, Windows-1252)."""
    texto = gzip.open(ruta, "rb").read().decode("cp1252")
    lineas = texto.splitlines()
    inicio = next(i for i, l in enumerate(lineas) if l.startswith('"Fecha"'))
    df = pd.read_csv(io.StringIO("\n".join(lineas[inicio:])), na_values=["N/E", ""], dtype=str)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    largo = df.melt(id_vars="Fecha", var_name="serie", value_name="indice")
    largo["serie"] = largo["serie"].astype(int)
    largo["indice"] = pd.to_numeric(largo["indice"], errors="coerce")
    return largo


def partir_periodo(periodo):
    m = RE_PERIODO.match(periodo.strip())
    if not m:
        raise ValueError(f"Periodo no reconocido: {periodo}")
    q, mes, anio = int(m.group(1)), MESES[m.group(2)], int(m.group(3))
    return anio, mes, q


def main():
    CLEAN.mkdir(parents=True, exist_ok=True)
    cat = pd.read_csv(
        RAW_INPC / "catalogo_series.csv",
        usecols=["ciudad_nodo", "ciudad_inegi", "serie", "descripcion",
                 "es_generico", "generico_cod", "es_indice_general"],
        dtype={"ciudad_nodo": str, "generico_cod": str},
    ).drop_duplicates("serie")
    # INEGI antepone un número a algunas ciudades ("7. Area Metropolitana ...").
    cat["ciudad"] = cat["ciudad_inegi"].str.replace(r"^\d+\.\s*", "", regex=True).str.strip()

    partes = [leer_exportacion(p) for p in sorted(RAW_INPC.glob("inpc_*.csv.gz"))]
    df = pd.concat(partes, ignore_index=True).dropna(subset=["indice"])
    # INEGI reporta 0 cuando un genérico no existe en la ciudad (p. ej. metro en
    # ciudades sin metro); esos registros no son precios y se eliminan.
    df = df[df["indice"] > 0]
    df = df.merge(cat, on="serie", how="left", validate="many_to_one")
    assert df["ciudad"].notna().all(), "Hay series sin ciudad en el catálogo"

    # Tiempo: año, mes, quincena, fecha de inicio y un índice consecutivo t.
    per = pd.DataFrame(df["Fecha"].drop_duplicates())
    per[["anio", "mes", "quincena"]] = per["Fecha"].apply(lambda s: pd.Series(partir_periodo(s)))
    per["fecha"] = pd.to_datetime([date(a, m, 1 if q == 1 else 16)
                                   for a, m, q in zip(per.anio, per.mes, per.quincena)])
    per["t"] = (per.anio - 2018) * 24 + (per.mes - 1) * 2 + (per.quincena - 1)
    per["periodo"] = per["Fecha"]
    df = df.merge(per, on="Fecha").drop(columns="Fecha")

    # Tratamiento.
    df["sede"] = df["ciudad"].isin(SEDES).astype(int)
    df["sede_nombre"] = df["ciudad"].map(SEDES)
    encontradas = set(df.loc[df.sede == 1, "ciudad"])
    assert encontradas == set(SEDES), f"Faltan sedes: {set(SEDES) - encontradas}"
    mundial = pd.MultiIndex.from_tuples(QUINCENAS_MUNDIAL)
    df["mundial"] = pd.MultiIndex.from_arrays([df.anio, df.mes, df.quincena]).isin(mundial).astype(int)

    df["generico"] = np.where(df.es_generico, df.descripcion.str.slice(4), df.descripcion)
    df["ln_indice"] = np.log(df["indice"])
    cols = ["ciudad", "sede", "sede_nombre", "generico_cod", "generico", "es_indice_general",
            "serie", "periodo", "anio", "mes", "quincena", "fecha", "t", "mundial",
            "indice", "ln_indice"]
    df = df[cols].sort_values(["ciudad", "generico_cod", "t"]).reset_index(drop=True)
    df.to_parquet(CLEAN / "inpc_ciudad_generico.parquet", index=False)

    # Subconjunto para el análisis, con etiquetas de grupo.
    sel = df[df.generico_cod.isin(list(COMPLEMENTARIOS) + list(PLACEBO))].copy()
    sel["tipo"] = np.where(sel.generico_cod.isin(list(COMPLEMENTARIOS)), "complementario", "placebo")
    sel["nombre_corto"] = sel.generico_cod.map(
        {k: v[0] for k, v in COMPLEMENTARIOS.items()} | PLACEBO)
    sel["grupo"] = sel.generico_cod.map({k: v[1] for k, v in COMPLEMENTARIOS.items()}).fillna("Placebo")
    sel["comerciable"] = sel.generico_cod.map({k: v[2] for k, v in COMPLEMENTARIOS.items()})
    sel.to_csv(CLEAN / "inpc_analisis.csv", index=False, float_format="%.6f")

    # Resumen para revisar a ojo.
    print(f"Panel completo: {len(df):,} filas, {df.ciudad.nunique()} ciudades, "
          f"{df.generico_cod.nunique()} genéricos, {df.periodo.iloc[0]} a "
          f"{df.sort_values('t').periodo.iloc[-1]}")
    print(f"Sedes: {sorted(encontradas)}")
    cobertura = (sel.groupby(["nombre_corto"]).agg(ciudades=("ciudad", "nunique"),
                                                   primera=("fecha", "min"),
                                                   ultima=("fecha", "max"))
                 .sort_values("ciudades"))
    print("\nCobertura de los genéricos de análisis:\n", cobertura.to_string())


if __name__ == "__main__":
    main()
