"""Paso 1. Descarga el INPC quincenal por ciudad y producto genérico desde INEGI.

Qué hace:
  1. Recorre la estructura "Por ciudad" del INPC (canasta 2024) en la API de
     consulta de INEGI y arma un catálogo con todas las series de cada ciudad.
  2. Para cada ciudad exporta en CSV el índice general y los 292 genéricos,
     de ANIO_INICIO a ANIO_FIN, y guarda el archivo tal como lo entrega INEGI.

No requiere token. Uso (desde la raíz del repositorio):
    .venv/bin/python code/01_descarga_inpc.py            # descarga lo que falte
    .venv/bin/python code/01_descarga_inpc.py --rehacer  # vuelve a bajar todo
"""
import argparse
import gzip
import re
import sys
import time

import pandas as pd
import requests

from config import (
    ANIO_FIN,
    ANIO_INICIO,
    INEGI_API_ESTRUCTURA,
    INEGI_ESTRUCTURA_CIUDAD,
    INEGI_EXPORTA,
    RAW_INPC,
)

HEADERS = {"User-Agent": "Mozilla/5.0 (proyecto academico ITAM)"}
PAUSA = 1.0  # segundos entre peticiones, para no saturar el servidor de INEGI
RE_GENERICO = re.compile(r"^(\d{3}) (.+)$")


def pedir(metodo, url, **kw):
    """Petición con reintentos simples."""
    for intento in range(4):
        try:
            r = requests.request(metodo, url, headers=HEADERS, timeout=120, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            espera = 5 * (intento + 1)
            print(f"  aviso: {e}; reintento en {espera}s", file=sys.stderr)
            time.sleep(espera)
    raise RuntimeError(f"No se pudo descargar {url}")


def catalogo_ciudades():
    """Lista las ciudades de la estructura y las series de cada una."""
    filas, i, vacios = [], 1, 0
    while vacios < 2:
        nodo = f"{INEGI_ESTRUCTURA_CIUDAD}{i * 10:04d}"
        datos = pedir("GET", INEGI_API_ESTRUCTURA.format(nodo)).json()
        nodos = (datos.get("data") or {}).get("nodos") or []
        if not datos.get("success") or not nodos:
            vacios += 1
            i += 1
            continue
        vacios = 0
        ciudad = nodos[0]["descripcion"].strip()
        print(f"  {ciudad}: {len(nodos)} nodos")
        for x in nodos[1:]:
            if not x.get("numeroSerie"):
                continue
            desc = x["descripcion"].strip()
            m = RE_GENERICO.match(desc)
            filas.append(
                {
                    "ciudad_nodo": nodo,
                    "ciudad_inegi": ciudad,
                    "serie": int(x["numeroSerie"]),
                    "nodo": x["nodoId"],
                    "descripcion": desc,
                    "es_generico": bool(m),
                    "generico_cod": m.group(1) if m else None,
                    "es_indice_general": desc == "Índice general",
                    "periodo_ini": x.get("periodoIni"),
                    "periodo_fin": x.get("periodoFin"),
                }
            )
        i += 1
        time.sleep(PAUSA)
    return pd.DataFrame(filas)


def exportar_csv(series, titulo):
    """Exporta un conjunto de series a CSV con el mismo formulario que usa el sitio."""
    form = {
        "_anioI": ANIO_INICIO,
        "_anioF": ANIO_FIN,
        "_orient": "vertical",
        "_meta": "0",
        "_tipo": "Niveles",
        "_formato": "CSV",
        "_series": "e|" + ",".join(str(s) for s in series),
        "idEstructura": INEGI_ESTRUCTURA_CIUDAD,
        "cuadro": INEGI_ESTRUCTURA_CIUDAD,
        "cvEstructura": INEGI_ESTRUCTURA_CIUDAD,
        "esquema": "INP",
        "pf": "inp",
        "titulo": titulo,
        "st": "",
    }
    r = pedir("POST", INEGI_EXPORTA, params={"INPtipoExporta": "CSV"}, data=form)
    if "csv" not in r.headers.get("Content-Type", ""):
        raise RuntimeError(f"INEGI no devolvió CSV para {titulo}")
    return r.content  # bytes en Windows-1252, se guardan sin modificar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rehacer", action="store_true", help="vuelve a descargar todo")
    args = ap.parse_args()
    RAW_INPC.mkdir(parents=True, exist_ok=True)

    ruta_cat = RAW_INPC / "catalogo_series.csv"
    if args.rehacer or not ruta_cat.exists():
        print("Leyendo la estructura de ciudades de INEGI...")
        cat = catalogo_ciudades()
        cat.to_csv(ruta_cat, index=False)
    else:
        cat = pd.read_csv(ruta_cat, dtype={"ciudad_nodo": str, "nodo": str, "generico_cod": str})
    print(f"Catálogo: {cat.ciudad_inegi.nunique()} ciudades, {len(cat)} series")

    for (nodo, ciudad), g in cat.groupby(["ciudad_nodo", "ciudad_inegi"], sort=True):
        destino = RAW_INPC / f"inpc_{nodo}.csv.gz"
        if destino.exists() and not args.rehacer:
            continue
        series = g.loc[g.es_generico | g.es_indice_general, "serie"].drop_duplicates()
        print(f"Descargando {ciudad} ({len(series)} series)...")
        contenido = exportar_csv(series.tolist(), ciudad)
        with gzip.open(destino, "wb") as f:
            f.write(contenido)
        time.sleep(PAUSA)
    print("Listo.")


if __name__ == "__main__":
    main()
