"""Paso 3b. Análisis exploratorio (EDA) del panel del INPC.

Revisa si la base sirve para la métrica y el diseño del proyecto:
  1. Cobertura: celdas faltantes, ceros, ciudades y quincenas por genérico.
  2. Cómo se mueven los precios: tamaño de los cambios quincenales, qué tan seguido
     no cambian (rigidez) y qué tan ruidosas son las series.
  3. Volatilidad por ciudad: dónde quedan las sedes frente a las 52 de control.
     Importa para la inferencia por permutación.
  4. "Placebo por año": la misma diferencia en diferencias (jun–1Q jul contra
     mar–may, sedes − no sedes) en cada año de 2018 a 2026. Muestra si las sedes
     tienen una estacionalidad propia.
  5. Brecha de largo plazo entre sedes y no sedes, 2018–2026.

Salidas:
  output/tables/eda_cobertura.csv
  output/tables/eda_cambios_quincenales.csv
  output/tables/eda_volatilidad_ciudades.csv
  output/tables/eda_placebo_anios.csv
  output/figures/eda_rigidez_volatilidad.png
  output/figures/eda_volatilidad_ciudades.png
  output/figures/eda_placebo_anios.png
  output/figures/eda_brecha_largo_plazo.png

Uso (desde la raíz del repositorio):
    .venv/bin/python code/03b_eda.py
"""
import gzip
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import CLEAN, COMPLEMENTARIOS, FIG, PLACEBO, RAW_INPC, SEDES, TAB

TIPOS = ["Servicios", "Bienes comerciables", "Placebo"]
COLOR = {"Servicios": "#2a78d6", "Bienes comerciables": "#eb6834", "Placebo": "#8a8984"}
TEXTO, TEXTO2, EJE, REJILLA = "#0b0b0b", "#52514e", "#c3c2b7", "#ecebe7"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def estilo(ax, rejilla="y"):
    for lado in ["top", "right"]:
        ax.spines[lado].set_visible(False)
    for lado in ["left", "bottom"]:
        ax.spines[lado].set_color(EJE)
    ax.tick_params(colors=TEXTO2, labelsize=8.5)
    if rejilla:
        ax.grid(axis=rejilla, color=REJILLA, lw=0.8)
    ax.set_axisbelow(True)


def cargar():
    df = pd.read_csv(CLEAN / "inpc_analisis.csv",
                     dtype={"generico_cod": str, "sede_nombre": str}, parse_dates=["fecha"])
    df = df.sort_values(["ciudad", "generico_cod", "t"]).reset_index(drop=True)
    df["y"] = 100 * df["ln_indice"]
    df["dlp"] = df.groupby(["ciudad", "generico_cod"])["y"].diff()   # cambio quincenal, %
    df["tipo2"] = np.select([df.tipo.eq("placebo"), df.comerciable.eq(True)],
                            ["Placebo", "Bienes comerciables"], "Servicios")
    return df


# --- 1. Cobertura ---------------------------------------------------------------------
def celdas_crudas():
    """Cuenta celdas, 'N/E' y ceros en los CSV tal como los entrega INEGI."""
    total = ne = ceros = 0
    for ruta in sorted(RAW_INPC.glob("inpc_*.csv.gz")):
        lineas = gzip.open(ruta, "rb").read().decode("cp1252").splitlines()
        inicio = next(i for i, l in enumerate(lineas) if l.startswith('"Fecha"'))
        d = pd.read_csv(io.StringIO("\n".join(lineas[inicio:])), dtype=str)
        v = d.loc[:, ~d.columns.str.startswith("Unnamed")].drop(columns="Fecha").stack(future_stack=True)
        total += len(v)
        ne += int(v.isna().sum() + v.str.strip().eq("N/E").sum())
        ceros += int(pd.to_numeric(v, errors="coerce").eq(0).sum())
    return total, ne, ceros


def cobertura(df):
    filas = []
    for (cod, nombre), g in df.groupby(["generico_cod", "nombre_corto"]):
        inicio = g.t.min()
        esperadas = g.ciudad.nunique() * (df.t.max() - inicio + 1)
        filas.append({"generico_cod": cod, "generico": nombre, "tipo": g.tipo2.iloc[0],
                      "ciudades": g.ciudad.nunique(),
                      "primera_quincena": g.loc[g.t.idxmin(), "periodo"],
                      "ultima_quincena": g.loc[g.t.idxmax(), "periodo"],
                      "celdas": len(g), "celdas_faltantes": esperadas - len(g),
                      "faltantes_desde_2025": int(g[g.anio >= 2025].ciudad.nunique() * g[g.anio >= 2025].t.nunique()
                                                  - (g.anio >= 2025).sum())})
    return pd.DataFrame(filas).sort_values(["tipo", "generico"])


# --- 2. Cambios quincenales ----------------------------------------------------------------
def cambios(df):
    w = df[(df.anio >= 2025) & df.dlp.notna()]
    de_ciudad = w.groupby(["generico_cod", "ciudad", "sede"]).dlp.std().reset_index()
    de_sede = de_ciudad.groupby(["generico_cod", "sede"]).dlp.median().unstack()
    t = w.groupby(["generico_cod", "nombre_corto", "tipo2"]).dlp.agg(
        cambio_medio="mean", desv_est="std",
        pct_sin_cambio=lambda x: 100 * (x.abs() < 1e-6).mean(),
        pct_cambio_mayor_10=lambda x: 100 * (x.abs() > 10).mean(),
        cambio_maximo=lambda x: x.abs().max()).reset_index("nombre_corto").reset_index("tipo2")
    t["desv_est_sedes"] = de_sede[1]
    t["desv_est_no_sedes"] = de_sede[0]
    return t.rename(columns={"nombre_corto": "generico", "tipo2": "tipo"}).reset_index()


# --- 3. Volatilidad por ciudad -------------------------------------------------------------
def volatilidad_ciudades(df):
    w = df[(df.anio >= 2025) & df.dlp.notna() & df.tipo.eq("complementario")]
    v = (w.groupby(["ciudad", "generico_cod"]).dlp.std()
         .groupby("ciudad").mean().rename("desv_est_promedio").reset_index())
    v["sede"] = v.ciudad.map(SEDES)
    v["percentil"] = 100 * v.desv_est_promedio.rank(pct=True)
    return v.sort_values("desv_est_promedio").reset_index(drop=True)


# --- 4. Placebo por año ---------------------------------------------------------------------
def placebo_anios(df):
    """DiD de cada año: [media jun–1Q jul − media mar–may], sedes − no sedes."""
    filas = []
    for anio in sorted(df.anio.unique()):
        a = df[df.anio == anio]
        antes = a[a.mes.isin([3, 4, 5])]
        durante = a[(a.mes == 6) | ((a.mes == 7) & (a.quincena == 1))]
        if antes.empty or durante.empty:
            continue
        claves = ["tipo2", "nombre_corto", "ciudad", "sede"]
        d = (durante.groupby(claves).y.mean() - antes.groupby(claves).y.mean())
        d = d.groupby(["tipo2", "nombre_corto", "sede"]).mean().unstack("sede")
        did = (d[1] - d[0]).rename("did").reset_index()
        for tipo, g in did.groupby("tipo2"):
            filas.append({"anio": anio, "tipo": tipo, "did": g.did.mean()})
    return pd.DataFrame(filas)


# --- 5. Brecha de largo plazo ------------------------------------------------------------
def brecha(df):
    # Cada genérico se centra en su propio promedio de 2025 antes de promediar, para
    # que la entrada de centros nocturnos (2024) no mueva la serie del grupo.
    m = df.groupby(["tipo2", "generico_cod", "fecha", "sede"]).y.mean().unstack("sede")
    gap = (m[1] - m[0]).rename("brecha").reset_index()
    base = gap[gap.fecha.dt.year == 2025].groupby("generico_cod").brecha.mean()
    gap["brecha"] = gap.brecha - gap.generico_cod.map(base)
    return gap.groupby(["tipo2", "fecha"]).brecha.mean().reset_index()


# --- Figuras ---------------------------------------------------------------------------
def fig_rigidez(c):
    c = c.copy()
    c["o"] = c.tipo.map({t: i for i, t in enumerate(TIPOS)})
    c = c.sort_values(["o", "desv_est"], ascending=[False, True]).reset_index(drop=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 6.4), sharey=True,
                                 gridspec_kw={"width_ratios": [1, 1]})
    y = np.arange(len(c))
    colores = c.tipo.map(COLOR)
    a1.barh(y, c.pct_sin_cambio, color=colores, height=0.62)
    a2.barh(y, c.desv_est, color=colores, height=0.62)
    a2.set_xscale("log")
    a2.set_xticks([0.5, 1, 2, 5, 10, 20])
    a2.set_xticklabels(["0.5", "1", "2", "5", "10", "20"])
    a1.set_yticks(y)
    a1.set_yticklabels(c.generico, fontsize=8.5)
    a1.set_xlabel("% de quincenas sin cambio de precio", fontsize=9, color=TEXTO2)
    a2.set_xlabel("Desviación estándar del cambio quincenal (%, escala log)", fontsize=9, color=TEXTO2)
    for ax in (a1, a2):
        estilo(ax, rejilla="x")
    for i, v in enumerate(c.pct_sin_cambio):
        a1.text(v + 1, i, f"{v:.0f}", va="center", fontsize=7.5, color=TEXTO2)
    for i, v in enumerate(c.desv_est):
        a2.text(v * 1.06, i, f"{v:.1f}", va="center", fontsize=7.5, color=TEXTO2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOR[t]) for t in TIPOS]
    fig.legend(handles, TIPOS, loc="upper right", ncol=3, frameon=False, fontsize=8.5,
               bbox_to_anchor=(0.98, 0.915))
    fig.suptitle("Qué tan seguido cambian los precios y qué tan ruidosas son las series\n"
                 "Cambios quincenales por ciudad, 2025–2026", x=0.02, y=0.98, ha="left",
                 fontsize=11.5, color=TEXTO)
    fig.subplots_adjust(left=0.24, right=0.97, top=0.86, bottom=0.09, wspace=0.08)
    fig.savefig(FIG / "eda_rigidez_volatilidad.png", dpi=200)
    plt.close(fig)


def fig_volatilidad(v):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ctrl = v[v.sede.isna()]
    ax.hist(ctrl.desv_est_promedio, bins=18, color="#c3c2b7", edgecolor="white", linewidth=1)
    alto = ax.get_ylim()[1]
    for i, (_, r) in enumerate(v[v.sede.notna()].iterrows()):
        ax.axvline(r.desv_est_promedio, color=COLOR["Servicios"], lw=1.6)
        ax.text(r.desv_est_promedio + 0.02, alto * (0.92 - 0.12 * i),
                f"{r.sede} (percentil {r.percentil:.0f})", fontsize=8.5, color=TEXTO)
    ax.set_xlabel("Desviación estándar promedio del cambio quincenal (%, 14 complementarios, 2025–2026)",
                  fontsize=9, color=TEXTO2)
    ax.set_ylabel("Ciudades no sede", fontsize=9, color=TEXTO2)
    ax.set_title("Las sedes tienen series de precios menos ruidosas que la mayoría de las ciudades",
                 loc="left", fontsize=11, color=TEXTO)
    estilo(ax)
    fig.tight_layout()
    fig.savefig(FIG / "eda_volatilidad_ciudades.png", dpi=200)
    plt.close(fig)


def fig_placebo_anios(p):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.9), sharey=True, sharex=True)
    for ax, tipo in zip(axes, TIPOS):
        g = p[p.tipo == tipo].sort_values("anio")
        otros = g[g.anio < 2026]
        ax.axvline(0, color="#8a8984", lw=0.8)
        ax.scatter(otros.did, otros.anio, s=34, color="#a8a7a0", edgecolor="white", zorder=3)
        a26 = g[g.anio == 2026]
        ax.scatter(a26.did, a26.anio, s=60, color=COLOR[tipo] if tipo != "Placebo" else "#52514e",
                   edgecolor="white", zorder=4)
        ax.axvspan(otros.did.min(), otros.did.max(), color=REJILLA, alpha=0.8, lw=0)
        x26 = float(a26.did.iloc[0])
        ax.annotate(f"2026: {x26:+.2f}", (x26, 2026), xytext=(-8 if x26 > 0.5 else 8, 0),
                    textcoords="offset points", ha="right" if x26 > 0.5 else "left",
                    va="center", fontsize=8.5, color=TEXTO)
        ax.set_title(tipo, loc="left", fontsize=10.5, color=TEXTO)
        ax.set_xlabel("Sedes − no sedes (pp)", fontsize=8.5, color=TEXTO2)
        estilo(ax, rejilla="x")
    axes[0].set_yticks(sorted(p.anio.unique()))
    axes[0].set_ylim(p.anio.max() + 0.6, p.anio.min() - 0.6)
    fig.suptitle("Cambio de precios de mar–may a jun–1Q jul, sedes menos no sedes, cada año\n"
                 "Franja: rango de 2018–2025, sin Mundial", x=0.02, y=0.98, ha="left",
                 fontsize=11.5, color=TEXTO)
    fig.subplots_adjust(left=0.07, right=0.98, top=0.78, bottom=0.15, wspace=0.1)
    fig.savefig(FIG / "eda_placebo_anios.png", dpi=200)
    plt.close(fig)


def fig_brecha(gap):
    fig, axes = plt.subplots(3, 1, figsize=(8, 7), sharex=True, sharey=True)
    for ax, tipo in zip(axes, TIPOS):
        g = gap[gap.tipo2 == tipo]
        ax.axvspan(pd.Timestamp("2020-04-01"), pd.Timestamp("2021-06-30"), color=REJILLA, lw=0)
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color="#e8e7e3", lw=0)
        ax.axhline(0, color="#8a8984", lw=0.8)
        ax.plot(g.fecha, g.brecha, color=COLOR[tipo] if tipo != "Placebo" else "#52514e", lw=1.2)
        ax.set_title(tipo, loc="left", fontsize=10.5, color=TEXTO)
        ax.set_ylabel("pp vs. 2025", fontsize=8.5, color=TEXTO2)
        estilo(ax)
    axes[0].text(pd.Timestamp("2020-05-01"), axes[0].get_ylim()[1] * 0.85, "COVID", fontsize=8,
                 color=TEXTO2)
    ticks = pd.date_range("2018-01-01", gap.fecha.max(), freq="YS")
    axes[-1].set_xticks(ticks)
    axes[-1].set_xticklabels([f"{d:%Y}" for d in ticks])
    fig.suptitle("Brecha de precios entre sedes y no sedes, 2018–2026\n"
                 "Promedio de log-índices (×100), sedes − no sedes, centrado en su promedio de 2025",
                 x=0.02, y=0.98, ha="left", fontsize=11.5, color=TEXTO)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.87, bottom=0.05, hspace=0.32)
    fig.savefig(FIG / "eda_brecha_largo_plazo.png", dpi=200)
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    df = cargar()
    panel = pd.read_parquet(CLEAN / "inpc_ciudad_generico.parquet", columns=["ciudad", "generico_cod", "t"])
    total, ne, ceros = celdas_crudas()
    print(f"Panel completo: {len(panel):,} observaciones, {panel.ciudad.nunique()} ciudades, "
          f"{panel.generico_cod.nunique()} genéricos, {panel.t.nunique()} quincenas")
    print(f"Celdas en los CSV de INEGI: {total:,}; sin dato (N/E): {ne:,} ({100 * ne / total:.1f}%); "
          f"ceros (genérico que no existe en la ciudad): {ceros:,} ({100 * ceros / total:.1f}%)")
    print(f"Genéricos de análisis: {len(COMPLEMENTARIOS)} complementarios y {len(PLACEBO)} placebo")

    cob = cobertura(df)
    cob.to_csv(TAB / "eda_cobertura.csv", index=False)
    print("\nCobertura:\n", cob.drop(columns=["generico_cod"]).to_string(index=False))

    c = cambios(df)
    c.round(3).to_csv(TAB / "eda_cambios_quincenales.csv", index=False)
    print("\nCambios quincenales 2025–2026 (%):\n",
          c.drop(columns=["generico_cod"]).round(2).sort_values(["tipo", "desv_est"]).to_string(index=False))

    v = volatilidad_ciudades(df)
    v.round(3).to_csv(TAB / "eda_volatilidad_ciudades.csv", index=False)
    print("\nVolatilidad de las sedes frente a las 55 ciudades:\n",
          v[v.sede.notna()].round(2).to_string(index=False))

    p = placebo_anios(df)
    p.round(3).to_csv(TAB / "eda_placebo_anios.csv", index=False)
    print("\nPlacebo por año (pp):\n", p.pivot(index="anio", columns="tipo", values="did").round(2).to_string())

    fig_rigidez(c)
    fig_volatilidad(v)
    fig_placebo_anios(p)
    fig_brecha(brecha(df))


if __name__ == "__main__":
    main()
