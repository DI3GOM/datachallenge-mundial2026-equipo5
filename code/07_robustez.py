"""Paso 7. Pruebas de robustez de la estimación con el INPC (04_estimacion.py).

Todas las pruebas usan el mismo estimador que la estimación principal: con el panel
balanceado, β de la regresión con efectos fijos ciudad×genérico y genérico×quincena es
igual a la diferencia en diferencias de promedios por ciudad

    Δ_c = promedio entre genéricos de [media de y en "durante" − media de y en "antes"]
    β   = media de Δ en las 3 sedes − media de Δ en las ciudades de control

y la inferencia es la misma: permutación exacta de Fisher sobre tripletas de ciudades e
intervalo de Conley–Taber con tripletas de control. Cada prueba cambia una sola cosa:

  1. Base corta: el periodo de comparación es mar–may 2026 (no ene 2025–may 2026).
  2. Base de un mes: solo mayo 2026 (igual que el diseño de PROFECO).
  3. "Durante" incluye la 2Q jul 2026 (la final del torneo).
  4. Tendencia lineal propia de cada ciudad×genérico, estimada con ene 2025–may 2026 y
     extrapolada (equivale a agregar λ_cj·t a la regresión).
  5. Control sin ciudades vecinas a una sede (posible contagio) ni de la frontera norte
     (IVA de 8% y salario mínimo propio).
  6. Control solo con la mitad de ciudades con series menos ruidosas. Las sedes tienen
     series muy estables (ver docs/eda.md), así que la permutación con todas las
     ciudades es conservadora.
  7. Placebo: el mismo diseño, pero con un "Mundial" falso en 2025 (con base larga y
     con base mar–may).
  8. Triple diferencia: el cambio de 2026 menos el mismo cambio promedio de años
     anteriores, para quitar la estacionalidad propia de las sedes. Con base larga
     (ene del año anterior–may, vs. 2020–2025) también quita su tendencia; con base
     mar–may se compara contra 2019–2025.

Salidas:
  output/tables/tab_robustez.csv
  output/figures/fig_robustez.png

Uso:  .venv/bin/python code/07_robustez.py
"""
import importlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402

est = importlib.import_module("04_estimacion")  # reutiliza GRUPOS, Permutaciones y estilo
t = C.t_quincena

T_MUNDIAL = est.T_MUNDIAL
T_FINAL = t(2026, 7, 2)
ANTES = list(range(t(*C.INICIO_VENTANA), t(2026, 5, 2) + 1))   # 1Q ene 2025 – 2Q may 2026
BASE_CORTA = list(range(t(2026, 3, 1), t(2026, 5, 2) + 1))      # mar–may 2026
MAYO = [t(2026, 5, 1), t(2026, 5, 2)]
ANIOS_PREVIOS = range(2019, 2026)  # 2018 queda fuera: 9 ciudades entran hasta la 2Q jul 2018

AEREO = "227"
GRUPOS = {
    "Servicios": est.GRUPOS["Servicios"],
    "Servicios sin transporte aéreo": [g for g in est.GRUPOS["Servicios"] if g != AEREO],
    "Bienes comerciables": est.GRUPOS["Bienes comerciables"],
    "Complementarios": est.GRUPOS["Complementarios"],
    "Placebo": est.GRUPOS["Placebo"],
}


def cargar():
    df = pd.read_csv(C.CLEAN / "inpc_analisis.csv", dtype={"generico_cod": str},
                     usecols=["ciudad", "generico_cod", "t", "ln_indice"])
    df["y"] = 100 * df.ln_indice
    return df.pivot_table(index=["ciudad", "generico_cod"], columns="t", values="y")


def quitar_tendencia(y, periodo):
    """Resta a cada serie ciudad×genérico su recta ajustada con las quincenas de `periodo`."""
    tt = np.array(periodo, dtype=float)
    Y = y[periodo].to_numpy()
    tc = tt - tt.mean()
    pendiente = (Y - Y.mean(axis=1, keepdims=True)) @ tc / (tc @ tc)
    ordenada = Y.mean(axis=1) - pendiente * tt.mean()
    todas = np.array(y.columns, dtype=float)
    return y - (ordenada[:, None] + pendiente[:, None] * todas[None, :])


def delta(y, codigos, antes, durante, ciudades):
    """Δ_c: promedio entre genéricos del cambio de y entre `antes` y `durante`."""
    sub = y[y.index.get_level_values("generico_cod").isin(codigos)]
    cambio = sub[durante].mean(axis=1) - sub[antes].mean(axis=1)
    return cambio.groupby(level="ciudad").mean().reindex(ciudades).to_numpy()


def base_corta(anio):
    return list(range(t(anio, 3, 1), t(anio, 5, 2) + 1))          # mar–may del año


def base_larga(anio):
    return list(range(t(anio - 1, 1, 1), t(anio, 5, 2) + 1))      # ene del año anterior–may


def delta_triple(y, codigos, ciudades, base, anios):
    """Cambio base → 1Q jun–1Q jul de 2026 menos el promedio del mismo cambio en `anios`.

    Se calcula por ciudad×genérico con los años disponibles (centros nocturnos solo tiene
    2025, porque entra a la canasta en la 2Q jul 2024) y luego se promedia por ciudad.
    Quita la estacionalidad propia de las sedes y, con la base larga, también su
    tendencia de largo plazo.
    """
    sub = y[y.index.get_level_values("generico_cod").isin(codigos)]

    def cambio(anio):
        durante = [t(anio, 6, 1), t(anio, 6, 2), t(anio, 7, 1)]
        return sub[durante].mean(axis=1) - sub[base(anio)].mean(axis=1)

    previos = pd.concat([cambio(a) for a in anios], axis=1).mean(axis=1)
    return (cambio(2026) - previos).groupby(level="ciudad").mean().reindex(ciudades).to_numpy()


def especificaciones(y):
    """Cada prueba: (nombre, ciudades, función grupo → Δ_c)."""
    todas = sorted(y.index.get_level_values("ciudad").unique())
    sedes = list(C.SEDES)
    excluir = set(C.VECINAS_SEDES) | set(C.FRONTERA_NORTE)
    sin_vecinas = [c for c in todas if c not in excluir]
    vol = pd.read_csv(C.TAB / "eda_volatilidad_ciudades.csv")
    ctrl_vol = vol[vol.sede.isna()].nsmallest(26, "desv_est_promedio").ciudad.tolist()
    poco_ruido = sorted(sedes + ctrl_vol)
    y_tend = quitar_tendencia(y, ANTES)
    durante_25 = [t(2025, 6, 1), t(2025, 6, 2), t(2025, 7, 1)]
    return [
        ("Principal: ene 2025–may 2026 → 1Q jun–1Q jul 2026", todas,
         lambda g, c: delta(y, g, ANTES, T_MUNDIAL, c)),
        ("Base corta: mar–may 2026", todas,
         lambda g, c: delta(y, g, BASE_CORTA, T_MUNDIAL, c)),
        ("Base de un mes: mayo 2026", todas,
         lambda g, c: delta(y, g, MAYO, T_MUNDIAL, c)),
        ("Durante incluye la 2Q jul (final)", todas,
         lambda g, c: delta(y, g, ANTES, T_MUNDIAL + [T_FINAL], c)),
        ("Tendencia lineal por ciudad×genérico", todas,
         lambda g, c: delta(y_tend, g, ANTES, T_MUNDIAL, c)),
        ("Control sin vecinas ni frontera norte", sin_vecinas,
         lambda g, c: delta(y, g, ANTES, T_MUNDIAL, c)),
        ("Control: 26 ciudades con series menos ruidosas", poco_ruido,
         lambda g, c: delta(y, g, ANTES, T_MUNDIAL, c)),
        ("Placebo: Mundial falso en 2025 (base larga)", todas,
         lambda g, c: delta(y, g, base_larga(2025), durante_25, c)),
        ("Placebo: Mundial falso en 2025 (base mar–may)", todas,
         lambda g, c: delta(y, g, base_corta(2025), durante_25, c)),
        ("Triple diferencia vs. 2020–2025 (base larga)", todas,
         lambda g, c: delta_triple(y, g, c, base_larga, range(2020, 2026))),
        ("Triple diferencia vs. 2019–2025 (base mar–may)", todas,
         lambda g, c: delta_triple(y, g, c, base_corta, ANIOS_PREVIOS)),
    ]


def robustez(y):
    filas = []
    for nombre, ciudades, funcion in especificaciones(y):
        perm = est.Permutaciones(ciudades)
        for grupo, codigos in GRUPOS.items():
            d = funcion(codigos, ciudades)
            assert not np.isnan(d).any(), f"{nombre}/{grupo}: faltan datos"
            beta, p, inf, sup, _ = perm.inferir(d)
            filas.append({"prueba": nombre, "grupo": grupo, "beta": float(beta),
                          "p_permutacion": float(p), "ic95_inf": float(inf), "ic95_sup": float(sup),
                          "ciudades": len(ciudades), "tripletas_fisher": len(perm.todas)})
    return pd.DataFrame(filas)


def verificar_principal(tab):
    """La fila principal debe reproducir tab_did_principal.csv de 04_estimacion.py."""
    ref = pd.read_csv(C.TAB / "tab_did_principal.csv")
    ref = ref[ref.coeficiente.str.startswith("Durante")].set_index("especificacion").beta
    mia = tab[tab.prueba.str.startswith("Principal")].set_index("grupo").beta
    for g in ["Servicios", "Bienes comerciables", "Complementarios", "Placebo"]:
        assert abs(ref[g] - mia[g]) < 1e-3, f"{g}: {mia[g]} ≠ {ref[g]} de 04_estimacion.py"


def fig_robustez(tab):
    paneles = ["Servicios", "Bienes comerciables", "Placebo"]
    titulos = {"Servicios": "Servicios\n(comida fuera de casa y transporte)",
               "Bienes comerciables": "Bienes comerciables\n(bebidas, botanas, equipo)",
               "Placebo": "Placebo\n(sin relación con el futbol)"}
    pruebas = list(dict.fromkeys(tab.prueba))
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 5.4), sharey=True, sharex=True)
    y = np.arange(len(pruebas))[::-1]
    for ax, grupo in zip(axes, paneles):
        d = tab[tab.grupo == grupo].set_index("prueba").loc[pruebas]
        color = est.GRIS if grupo == "Placebo" else est.AZUL
        ax.axvline(0, color=est.GRIS, lw=0.8)
        for yi, (_, r) in zip(y, d.iterrows()):
            ax.plot([r.ic95_inf, r.ic95_sup], [yi, yi], color=color, lw=1.6, alpha=0.45,
                    solid_capstyle="round")
            ax.scatter(r.beta, yi, s=34, color=color, zorder=3, edgecolor="white", linewidth=0.8)
            ax.text(r.ic95_sup + 0.15, yi, f"p={r.p_permutacion:.2f}", va="center",
                    fontsize=7, color=est.TEXTO2)
        ax.axhspan(y[0] - 0.5, y[0] + 0.5, color=est.FRANJA, lw=0, zorder=0)
        # Separadores entre bloques: diseño, grupo de control, placebos, triple diferencia.
        for i, prueba in enumerate(pruebas[1:], start=1):
            if prueba.startswith(("Control sin", "Placebo: Mundial falso en 2025 (base larga)",
                                  "Triple diferencia vs. 2020")):
                ax.axhline(y[i] + 0.5, color="#c3c2b7", lw=0.6, ls=":")
        ax.set_title(titulos[grupo], loc="left", fontsize=9.5, color=est.TEXTO)
        est.estilo(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color="#ecebe7", lw=0.8)
        ax.set_xlabel("β (%, sedes − no sedes)", fontsize=8.5, color=est.TEXTO2)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(pruebas, fontsize=8.5)
    fig.suptitle("Robustez del efecto durante las quincenas con partidos (INPC)\n"
                 "Punto: β; línea: IC 95% por permutación (Conley–Taber); p: permutación de Fisher",
                 fontsize=11, color=est.TEXTO, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(C.FIG / "fig_robustez.png", dpi=200)
    plt.close(fig)


def main():
    y = cargar()
    tab = robustez(y)
    verificar_principal(tab)
    tab.round(4).to_csv(C.TAB / "tab_robustez.csv", index=False)
    print(tab.pivot(index="prueba", columns="grupo", values="beta")
          .reindex(list(dict.fromkeys(tab.prueba)))[list(GRUPOS)].round(2).to_string())
    print()
    print(tab.pivot(index="prueba", columns="grupo", values="p_permutacion")
          .reindex(list(dict.fromkeys(tab.prueba)))[list(GRUPOS)].round(3).to_string())
    fig_robustez(tab)


if __name__ == "__main__":
    main()
