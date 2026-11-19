"""Paso 9. Figuras y tablas del reporte (docs/reporte/reporte.tex, máximo 5 páginas).

No vuelve a estimar nada: lee las tablas que ya generaron los scripts 04 a 07 y escribe
  - una versión compacta del estudio de evento, y
  - las dos tablas del reporte en LaTeX, que reporte.tex incluye con \\input.
Así las cifras de las tablas del reporte salen directamente del código.

Salidas:
  output/figures/rep_estudio_evento.png   estudio de evento del INPC en una fila
  output/tables/rep_tabla1_resultados.tex  Tabla 1: efecto principal (INPC y PROFECO)
  output/tables/rep_tabla2_heterogeneidad.tex  Tabla 2: heterogeneidad

Uso:  .venv/bin/python code/09_figuras_reporte.py
      (después de 04_estimacion.py, 05b_profeco_eda.py, 06_profeco_estimacion.py y 07_robustez.py)
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402

AZUL, NARANJA, GRIS, TEXTO, TEXTO2 = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"
FRANJA = "#e8e7e3"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# --- Figura ---------------------------------------------------------------------------
def estilo(ax):
    for lado in ["top", "right"]:
        ax.spines[lado].set_visible(False)
    for lado in ["left", "bottom"]:
        ax.spines[lado].set_color("#c3c2b7")
    ax.tick_params(colors=TEXTO2, labelsize=8)
    ax.grid(axis="y", color="#ecebe7", lw=0.8)
    ax.set_axisbelow(True)


def fig_estudio_evento():
    ev = pd.read_csv(C.TAB / "tab_estudio_evento.csv", parse_dates=["fecha"])
    paneles = [("Servicios", "Servicios: comida fuera de casa\ny transporte", AZUL),
               ("Bienes comerciables", "Bienes comerciables: bebidas,\nbotanas, TV y artículos deportivos", NARANJA),
               ("Placebo", "Placebo: genéricos sin relación\ncon el futbol", GRIS)]
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.1), sharey=True)
    for ax, (grupo, titulo, color) in zip(axes, paneles):
        e = ev[ev.grupo == grupo].sort_values("k")
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color=FRANJA, lw=0)
        ax.axhline(0, color=GRIS, lw=0.8)
        ax.fill_between(e.fecha, e.ic95_inf, e.ic95_sup, color=color, alpha=0.16, lw=0)
        ax.plot(e.fecha, e.beta, color=color, lw=1.3)
        ax.scatter(e.fecha, e.beta, s=9, color=color, zorder=3, edgecolor="white", linewidth=0.4)
        ax.set_title(titulo, loc="left", fontsize=9, color=TEXTO)
        ticks = pd.to_datetime(["2025-01-01", "2025-07-01", "2026-01-01", "2026-07-01"])
        ax.set_xticks(ticks)
        ax.set_xticklabels([f"{MESES[d.month - 1]} {d:%y}" for d in ticks])
        estilo(ax)
    axes[0].set_ylabel("% vs. 2Q may 2026", fontsize=8, color=TEXTO2)
    axes[0].annotate("Mundial", (pd.Timestamp("2026-06-03"), 1), xycoords=("data", "axes fraction"),
                     fontsize=7.5, color=TEXTO2, va="top", ha="right", rotation=90)
    fig.tight_layout(w_pad=1.2)
    fig.savefig(C.FIG / "rep_estudio_evento.png", dpi=250)
    plt.close(fig)


# --- Tablas en LaTeX ------------------------------------------------------------------
def num(x):
    """Número con 2 decimales; el signo menos va en modo matemático para que se vea bien."""
    s = f"{x:.2f}"
    return f"${s}$" if s.startswith("-") else s


def ic(inf, sup):
    return f"[{num(inf)}, {num(sup)}]"


def fila(*celdas):
    return " & ".join(celdas) + r" \\"


def tabla1():
    """Efecto durante (β) y después (γ) del Mundial, INPC y PROFECO."""
    inpc = pd.read_csv(C.TAB / "tab_did_principal.csv")
    prof = pd.read_csv(C.TAB / "profeco_did_principal.csv")

    def inpc_fila(espec, etiqueta):
        d = inpc[inpc.especificacion == espec].set_index("coeficiente")
        b = d.loc[d.index.str.startswith("Durante")].iloc[0]
        g = d.loc[d.index.str.startswith("Después")].iloc[0]
        return fila(etiqueta, num(b.beta), ic(b.ic95_inf, b.ic95_sup), f"{b.p_permutacion:.2f}",
                    num(g.beta), f"{g.p_permutacion:.2f}")

    def prof_fila(conjunto, etiqueta):
        d = prof[prof.conjunto == conjunto]
        b = d[d.periodo.str.startswith("Durante")].iloc[0]
        g = d[d.periodo.str.startswith("Después")].iloc[0]
        return fila(etiqueta, num(b.beta), ic(b.ic95_inf, b.ic95_sup), f"{b.p_permutacion:.2f}",
                    num(g.beta), f"{g.p_permutacion:.2f}")

    lineas = [
        r"\begin{tabular}{@{}lrcrrr@{}}",
        r"\toprule",
        r"& \multicolumn{3}{c}{Durante el Mundial ($\beta$)} & \multicolumn{2}{c}{Después ($\gamma$)} \\",
        r"\cmidrule(lr){2-4}\cmidrule(l){5-6}",
        r"Grupo & $\beta$ & IC 95\% & $p$ & $\gamma$ & $p$ \\",
        r"\midrule",
        r"\multicolumn{6}{@{}l}{\emph{INPC: 3 sedes contra 52 ciudades}} \\",
        inpc_fila("Servicios", "Servicios (comida fuera de casa y transporte)"),
        inpc_fila("Bienes comerciables", "Bienes comerciables"),
        inpc_fila("Complementarios", "Todos los complementarios"),
        inpc_fila("Placebo", "Placebo"),
        r"\multicolumn{6}{@{}l}{\emph{PROFECO: mismo producto en la misma tienda, mayo contra el torneo}} \\",
        prof_fila("Bebidas, botanas y comida", "Cerveza, refrescos, agua, botanas, licores y pollo"),
        prof_fila("Placebo", "Placebo (detergentes, papel, aceite, arroz, leche)"),
        r"\bottomrule",
        r"\end{tabular}",
    ]
    return "\n".join(lineas) + "\n"


def tabla2():
    """Heterogeneidad: tipo de producto, servicios por genérico, sede, cercanía y mecanismo."""
    inpc = pd.read_csv(C.TAB / "tab_did_principal.csv")
    rob = pd.read_csv(C.TAB / "tab_robustez.csv")
    gen = pd.read_csv(C.TAB / "tab_did_por_generico.csv", dtype={"generico_cod": str})
    dist = pd.read_csv(C.TAB / "profeco_heterogeneidad_distancia.csv")
    unif = pd.read_csv(C.TAB / "profeco_eda_precios_uniformes.csv")

    def con_ic(r, dimension, etiqueta, efecto="beta", p="p_permutacion"):
        return fila(dimension, etiqueta, num(r[efecto]), ic(r.ic95_inf, r.ic95_sup), f"{r[p]:.2f}")

    principal = rob[rob.prueba.str.startswith("Principal")].set_index("grupo")
    durante = inpc[inpc.coeficiente.str.startswith("Durante")].set_index("especificacion")
    g = gen[gen.coeficiente == "beta_durante"].set_index("generico_cod")
    servicios = [("219", "Estacionamiento"), ("222", "Autobús foráneo"),
                 ("246", "Servicios recreativos y centros nocturnos"), ("268", "Restaurantes"),
                 ("265", "Loncherías, fondas y taquerías")]
    sedes = [("Solo Guadalajara", "Guadalajara"), ("Solo Monterrey", "Monterrey"), ("Solo CDMX", "CDMX")]
    cerca = dist[(dist.conjunto == "Bebidas, botanas y comida") & (dist.cerca_de == "Estadio o Fan Fest")].iloc[0]
    prima = unif[(unif.medida == "Prima de las sedes (%, mediana)") & (unif.conjunto == "Complementarios")].valor.iloc[0]

    lineas = [
        r"\begin{tabular}{@{}llrcr@{}}",
        r"\toprule",
        r"Dimensión & Grupo & Efecto & IC 95\% & $p$ \\",
        r"\midrule",
        con_ic(principal.loc["Servicios sin transporte aéreo"], "Tipo de producto (INPC)", "Servicios sin transporte aéreo"),
        con_ic(durante.loc["Bienes comerciables"], "", "Bienes comerciables"),
    ]
    for i, (cod, nombre) in enumerate(servicios):
        lineas.append(con_ic(g.loc[cod], "Servicios por producto (INPC)" if i == 0 else "", nombre))
    lineas += [
        fila("Sede (INPC, complementarios)", " / ".join(n for _, n in sedes),
             " / ".join(num(durante.loc[e].beta) for e, _ in sedes), "",
             " / ".join(f"{durante.loc[e].p_permutacion:.2f}" for e, _ in sedes)),
        fila("Cercanía (PROFECO, bienes)", r"A $\le$5 km del estadio o Fan Fest, menos el resto",
             num(cerca.efecto_cerca_menos_lejos), "", f"{cerca.p_permutacion:.2f}"),
        fila("Mecanismo (PROFECO)", r"Precio sede $-$ resto, misma cadena y producto",
             f"mediana {abs(prima):.1f}" if abs(prima) < 0.05 else f"mediana {num(prima)}", "", ""),
        r"\bottomrule",
        r"\end{tabular}",
    ]
    return "\n".join(lineas) + "\n"


def main():
    fig_estudio_evento()
    for nombre, contenido in [("rep_tabla1_resultados.tex", tabla1()),
                              ("rep_tabla2_heterogeneidad.tex", tabla2())]:
        encabezado = "% Generado por code/09_figuras_reporte.py; no editar a mano.\n"
        (C.TAB / nombre).write_text(encabezado + contenido, encoding="utf-8")
        print(f"Escrito output/tables/{nombre}")


if __name__ == "__main__":
    main()
