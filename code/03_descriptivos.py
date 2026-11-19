"""Paso 3. Primera mirada a los datos (no es la estimación final).

Salidas:
  output/figures/fig_descriptiva_complementarios.png
      Índice de cada genérico complementario en las 3 sedes y el promedio de las
      ciudades no sede, relativo a su promedio de marzo–mayo 2026 (= 0).
  output/tables/did_simple.csv
      Diferencia en diferencias "a mano" por genérico: cambio en log-precio entre
      las 6 quincenas previas (mar–may 2026) y las 3 del Mundial, sedes menos no sedes.

Uso (desde la raíz del repositorio):
    .venv/bin/python code/03_descriptivos.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import CLEAN, COMPLEMENTARIOS, FIG, PLACEBO, TAB

PRE =[(2026, 3, 1), (2026, 3, 2), (2026, 4, 1), (2026, 4, 2), (2026, 5, 1), (2026, 5, 2)]
COLORES = {"CDMX": "#1b6ca8", "Guadalajara": "#d1495b", "Monterrey": "#edae49"}


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(CLEAN / "inpc_analisis.csv", dtype={"generico_cod": str, "sede_nombre": str},
                     parse_dates=["fecha"])

    # Normaliza cada serie a su promedio en las 6 quincenas previas (mar–may 2026).
    # Se usa un promedio y no una sola quincena para que un salto aislado en la
    # base no fabrique un "efecto" aparente.
    es_pre = pd.Series(list(zip(df.anio, df.mes, df.quincena))).isin(PRE).values
    base = (df[es_pre].groupby(["ciudad", "generico_cod"])["ln_indice"].mean().rename("ln_base"))
    df = df.join(base, on=["ciudad", "generico_cod"])
    df["rel"] = 100 * (df["ln_indice"] - df["ln_base"])  # ≈ % respecto a mar–may 2026

    # --- Figura: sedes vs promedio no sede ---------------------------------
    ventana = df[df.fecha >= "2025-07-01"]
    codigos = list(COMPLEMENTARIOS)
    fig, axes = plt.subplots(4, 4, figsize=(16, 13), sharex=True)
    for ax, cod in zip(axes.flat, codigos):
        g = ventana[ventana.generico_cod == cod]
        ctrl = g[g.sede == 0].groupby("fecha")["rel"]
        ax.fill_between(ctrl.quantile(0.25).index, ctrl.quantile(0.25), ctrl.quantile(0.75),
                        color="0.85", label="No sede (p25–p75)")
        ax.plot(ctrl.mean().index, ctrl.mean(), color="0.35", lw=1.6, label="No sede (promedio)")
        for sede, color in COLORES.items():
            s = g[g.sede_nombre == sede]
            ax.plot(s.fecha, s.rel, color=color, lw=1.4, label=sede)
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color="#2a9d8f", alpha=0.12)
        ax.axhline(0, color="0.5", lw=0.6, ls=":")
        ax.set_title(COMPLEMENTARIOS[cod][0], fontsize=11)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
        ax.tick_params(labelsize=8)
    for ax in axes.flat[len(codigos):]:
        ax.axis("off")
    handles, labels = axes.flat[0].get_legend_handles_labels()
    axes.flat[-1].legend(handles, labels, loc="center", fontsize=10, frameon=False)
    fig.suptitle("Precios de complementarios al futbol: sedes vs. ciudades no sede\n"
                 "log-índice ×100 relativo al promedio mar–may 2026; franja = quincenas con partidos",
                 fontsize=13)
    fig.tight_layout()
    fig.savefig(FIG / "fig_descriptiva_complementarios.png", dpi=150)
    plt.close(fig)

    # --- Tabla: DiD simple por genérico ----------------------------------------
    clave = list(zip(df.anio, df.mes, df.quincena))
    df["periodo_did"] = np.select(
        [pd.Series(clave).isin(PRE).values, df.mundial.eq(1).values], ["pre", "mundial"], "otro")
    m = (df[df.periodo_did != "otro"]
         .groupby(["generico_cod", "sede", "periodo_did"])["ln_indice"].mean().unstack())
    cambio = 100 * (m["mundial"] - m["pre"])
    tabla = cambio.unstack("sede").rename(columns={0: "cambio_no_sede", 1: "cambio_sedes"})
    tabla["did_pp"] = tabla["cambio_sedes"] - tabla["cambio_no_sede"]
    nombres = {k: v[0] for k, v in COMPLEMENTARIOS.items()} | PLACEBO
    tabla.insert(0, "generico", tabla.index.map(nombres))
    tabla.insert(1, "tipo", np.where(tabla.index.isin(list(COMPLEMENTARIOS)), "complementario", "placebo"))
    tabla = tabla.sort_values(["tipo", "did_pp"], ascending=[True, False]).round(2)
    tabla.to_csv(TAB / "did_simple.csv")
    print("Cambio % (aprox.) entre mar–may 2026 y las quincenas del Mundial:\n")
    print(tabla.to_string())


if __name__ == "__main__":
    main()
