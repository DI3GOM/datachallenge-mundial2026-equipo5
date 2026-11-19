"""Paso 4. Estimación principal: diferencia en diferencias y estudio de evento.

Ecuación (c = ciudad, j = genérico, t = quincena; y = 100 · ln índice):

    y_cjt = α_cj + δ_jt + β · Sede_c · Mundial_t + γ · Sede_c · Después_t + ε_cjt

  α_cj  efecto fijo ciudad × genérico (nivel de precios de cada producto en cada ciudad)
  δ_jt  efecto fijo genérico × quincena (choques nacionales de cada producto:
        inflación, IEPS, estacionalidad, temporada vacacional)
  β     efecto en las 3 quincenas con partidos (1Q jun, 2Q jun, 1Q jul 2026)
  γ     efecto en las quincenas posteriores (los precios rígidos no regresan)

Como y está en 100 · log, β se lee aproximadamente como cambio porcentual.
Ventana: 1Q ene 2025 a la última quincena publicada. El periodo de comparación
es 1Q ene 2025 – 2Q may 2026.

Inferencia. Solo hay 3 ciudades tratadas, así que el error estándar agrupado por
ciudad no es confiable (Conley y Taber, 2011; MacKinnon y Webb, 2017). Se reportan:
  1. Permutación exacta de Fisher: se asigna "sede" a cada una de las
     C(55,3) = 26,235 tripletas de ciudades y se ubica el β observado en esa
     distribución.
  2. Intervalo de Conley y Taber: la distribución del error de β se aproxima
     con las C(52,3) = 22,100 tripletas de ciudades de control.
  3. Wild cluster bootstrap restringido (WCR-t, Rademacher, 9,999 réplicas),
     agrupado por ciudad. Con pocas tratadas suele ser conservador.

El panel está balanceado, así que β de la regresión es exactamente la diferencia
en diferencias de promedios por ciudad. El script lo verifica y aprovecha eso
para que la permutación sea exacta y rápida.

Salidas:
  output/tables/tab_did_principal.csv      β y γ por especificación
  output/tables/tab_did_por_generico.csv   β y γ por genérico
  output/tables/tab_estudio_evento.csv     coeficientes por quincena relativa
  output/figures/fig_estudio_evento.png
  output/figures/fig_efectos_por_generico.png

Uso (desde la raíz del repositorio):
    .venv/bin/python code/04_estimacion.py
"""
import itertools

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

from config import (CLEAN, COMPLEMENTARIOS, FIG, INICIO_VENTANA, PLACEBO, QUINCENAS_MUNDIAL,
                    SEDES, TAB, t_quincena)

T_MUNDIAL = [t_quincena(*q) for q in QUINCENAS_MUNDIAL]
T0 = min(T_MUNDIAL)                     # 1Q jun 2026 = quincena relativa 0
T_INICIO = t_quincena(*INICIO_VENTANA)
K_REF = -1                              # 2Q may 2026, quincena de referencia
FE = "ciudad:generico_cod + generico_cod:t"
REPS_WCR = 9_999
SEMILLA = 20260611                      # fecha del partido inaugural

SERVICIOS = [k for k, v in COMPLEMENTARIOS.items() if not v[2]]
BIENES = [k for k, v in COMPLEMENTARIOS.items() if v[2]]
GRUPOS = {
    "Complementarios": list(COMPLEMENTARIOS),
    "Servicios": SERVICIOS,             # comida fuera de casa y transporte
    "Bienes comerciables": BIENES,      # bebidas, botanas, televisores, artículos deportivos
    "Placebo": list(PLACEBO),
}
NOMBRES = {k: v[0] for k, v in COMPLEMENTARIOS.items()} | PLACEBO
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# --- Datos ----------------------------------------------------------------------
def cargar():
    df = pd.read_csv(CLEAN / "inpc_analisis.csv",
                     dtype={"generico_cod": str, "sede_nombre": str}, parse_dates=["fecha"])
    df = df[df.t >= T_INICIO].copy()
    df["y"] = 100 * df["ln_indice"]
    df["k"] = df["t"] - T0
    df["durante"] = df["t"].isin(T_MUNDIAL).astype(int)
    df["despues"] = (df["t"] > max(T_MUNDIAL)).astype(int)
    df["D"] = df["sede"] * df["durante"]
    df["P"] = df["sede"] * df["despues"]
    n_ciudades, n_quincenas = df.ciudad.nunique(), df.t.nunique()
    celdas = df.groupby("generico_cod").size()
    assert (celdas == n_ciudades * n_quincenas).all(), "El panel no está balanceado"
    return df


# --- Inferencia por permutación de ciudades ---------------------------------------
class Permutaciones:
    """Asignaciones alternativas de 'sede' a tripletas de ciudades.

    Para cada ciudad se calcula un contraste Δ_c (por ejemplo, el cambio promedio de
    precio entre el periodo de comparación y el Mundial). Con el panel balanceado,
    β = media de Δ en las sedes − media de Δ en las 52 ciudades de control.
    """

    def __init__(self, ciudades):
        self.ciudades = np.array(ciudades)
        self.es_sede = np.isin(self.ciudades, list(SEDES))
        n = len(ciudades)
        self.todas = np.array(list(itertools.combinations(range(n), 3)))
        n_ctrl = int((~self.es_sede).sum())
        self.de_control = np.array(list(itertools.combinations(range(n_ctrl), 3)))

    @staticmethod
    def _dif_medias(Z, combos):
        """Para cada tripleta: media de Z en la tripleta − media en las demás ciudades."""
        suma = Z[combos].sum(axis=1)
        return suma / 3 - (Z.sum(axis=0) - suma) / (Z.shape[0] - 3)

    def inferir(self, delta):
        """delta: arreglo (ciudades,) o (ciudades, K). Devuelve β, p de Fisher e IC 95%."""
        Z = np.asarray(delta, dtype=float)
        beta = Z[self.es_sede].mean(axis=0) - Z[~self.es_sede].mean(axis=0)
        fisher = self._dif_medias(Z, self.todas)
        p = (np.abs(fisher) >= np.abs(beta) - 1e-9).mean(axis=0)
        ct = self._dif_medias(Z[~self.es_sede], self.de_control)
        inf = beta - np.quantile(ct, 0.975, axis=0)
        sup = beta - np.quantile(ct, 0.025, axis=0)
        return beta, p, inf, sup, fisher

    def inferir_una_sede(self, delta, sede):
        """Igual que inferir(), con una sola ciudad tratada y las 52 no sede como control."""
        Z = np.asarray(delta, dtype=float)
        i = int(np.flatnonzero(self.ciudades == sede)[0])
        ctrl = Z[~self.es_sede]
        beta = Z[i] - ctrl.mean()
        pool = np.append(ctrl, Z[i])
        stats = np.array([pool[m] - np.delete(pool, m).mean() for m in range(len(pool))])
        p = (np.abs(stats) >= abs(beta) - 1e-9).mean()
        ct = np.array([ctrl[m] - np.delete(ctrl, m).mean() for m in range(len(ctrl))])
        return beta, p, beta - np.quantile(ct, 0.975), beta - np.quantile(ct, 0.025)


def contraste(df, codigos, columna, ciudades):
    """Δ_c por ciudad: promedio entre genéricos de [media de y cuando columna = 1 − media antes]."""
    sub = df[df.generico_cod.isin(codigos)]
    antes = sub[(sub.durante == 0) & (sub.despues == 0)].groupby(["ciudad", "generico_cod"]).y.mean()
    periodo = sub[sub[columna] == 1].groupby(["ciudad", "generico_cod"]).y.mean()
    return (periodo - antes).groupby("ciudad").mean().reindex(ciudades).to_numpy()


# --- Wild cluster bootstrap ---------------------------------------------------------------
def quitar_efectos_fijos(df, columnas):
    """Elimina α_cj y δ_jt. Con panel balanceado basta el doble centrado dentro de cada genérico."""
    out = {}
    for c in columnas:
        x = df[c].astype(float)
        out[c] = (x - x.groupby([df.ciudad, df.generico_cod]).transform("mean")
                  - x.groupby([df.generico_cod, df.t]).transform("mean")
                  + x.groupby(df.generico_cod).transform("mean"))
    return pd.DataFrame(out)


def wild_bootstrap(df, regresores, param, reps=REPS_WCR, semilla=SEMILLA):
    """p-valor WCR-t (H0: param = 0), errores agrupados por ciudad, pesos Rademacher.

    Por Frisch–Waugh–Lovell se trabaja con los datos sin efectos fijos. El factor de
    corrección de grados de libertad se cancela entre t y t*, así que no afecta el p-valor.
    """
    W = quitar_efectos_fijos(df, ["y"] + regresores)
    y, X = W["y"].to_numpy(), W[regresores].to_numpy()
    g = pd.factorize(df["ciudad"])[0]
    G, k, j = g.max() + 1, X.shape[1], regresores.index(param)
    XtX_inv = np.linalg.inv(X.T @ X)

    def por_cluster(v):  # suma X_g' v_g para cada ciudad
        s = np.zeros((G, k))
        np.add.at(s, g, X * v[:, None])
        return s

    beta = XtX_inv @ X.T @ y
    S = por_cluster(y - X @ beta)
    V = XtX_inv @ S.T @ S @ XtX_inv
    t_obs = beta[j] / np.sqrt(V[j, j])

    # Modelo restringido (param = 0) y sus residuales.
    Xr = np.delete(X, j, axis=1)
    y_r = Xr @ np.linalg.lstsq(Xr, y, rcond=None)[0] if Xr.shape[1] else np.zeros_like(y)
    A, B = por_cluster(y - y_r), por_cluster(y_r)
    C = np.zeros((G, k, k))
    np.add.at(C, g, X[:, :, None] * X[:, None, :])

    w = np.random.default_rng(semilla).choice([-1.0, 1.0], size=(reps, G))
    beta_b = (B.sum(axis=0)[None, :] + w @ A) @ XtX_inv
    S_b = B[None] + w[:, :, None] * A[None] - np.einsum("gkl,rl->rgk", C, beta_b)
    V_b = XtX_inv[None] @ np.einsum("rgk,rgl->rkl", S_b, S_b) @ XtX_inv[None]
    t_b = beta_b[:, j] / np.sqrt(V_b[:, j, j])
    return float((np.abs(t_b) >= abs(t_obs)).mean())


# --- Estimación -----------------------------------------------------------------------
def regresion(df, rhs):
    return pf.feols(f"y ~ {rhs} | {FE}", data=df, vcov={"CRV1": "ciudad"})


def fila(espec, coef, modelo, nombre, beta_perm, p, inf, sup, p_wcr=np.nan):
    b = float(modelo.coef()[nombre])
    assert abs(b - beta_perm) < 1e-6, f"{espec}/{nombre}: regresión {b} ≠ DiD de promedios {beta_perm}"
    return {"especificacion": espec, "coeficiente": coef, "beta": b,
            "ee_cluster": float(modelo.se()[nombre]), "p_cluster": float(modelo.pvalue()[nombre]),
            "p_wild_bootstrap": p_wcr, "p_permutacion": p, "ic95_inf": inf, "ic95_sup": sup,
            "n_obs": int(modelo._N)}


def did_principal(df, perm, ciudades):
    filas = []
    # (1) Grupos de genéricos: complementarios, servicios, bienes y placebo.
    for grupo, codigos in GRUPOS.items():
        sub = df[df.generico_cod.isin(codigos)]
        m = regresion(sub, "D + P")
        for nombre, columna, etiqueta in [("D", "durante", "Durante el Mundial (β)"),
                                          ("P", "despues", "Después del Mundial (γ)")]:
            beta, p, inf, sup, _ = perm.inferir(contraste(df, codigos, columna, ciudades))
            p_wcr = wild_bootstrap(sub, ["D", "P"], nombre)
            filas.append(fila(grupo, etiqueta, m, nombre, beta, p, inf, sup, p_wcr))
    # (2) Por sede: cada sede contra las 52 ciudades no sede, complementarios.
    sub = df[df.generico_cod.isin(GRUPOS["Complementarios"])].copy()
    for ciudad, corto in SEDES.items():
        es = (sub.ciudad == ciudad).astype(int)
        sub[f"D_{corto}"], sub[f"P_{corto}"] = es * sub.durante, es * sub.despues
    rhs = " + ".join(f"{p}_{c}" for c in SEDES.values() for p in "DP")
    m = regresion(sub, rhs)
    for ciudad, corto in SEDES.items():
        for prefijo, columna, etiqueta in [("D", "durante", "Durante el Mundial (β)"),
                                           ("P", "despues", "Después del Mundial (γ)")]:
            delta = contraste(df, GRUPOS["Complementarios"], columna, ciudades)
            beta, p, inf, sup = perm.inferir_una_sede(delta, ciudad)
            filas.append(fila(f"Solo {corto}", etiqueta, m, f"{prefijo}_{corto}", beta, p, inf, sup))
    return pd.DataFrame(filas)


def did_por_generico(df, perm, ciudades):
    filas = []
    for cod in list(COMPLEMENTARIOS) + list(PLACEBO):
        sub = df[df.generico_cod == cod]
        m = regresion(sub, "D + P")
        for nombre, columna, etiqueta in [("D", "durante", "beta_durante"),
                                          ("P", "despues", "gamma_despues")]:
            beta, p, inf, sup, _ = perm.inferir(contraste(df, [cod], columna, ciudades))
            r = fila(NOMBRES[cod], etiqueta, m, nombre, beta, p, inf, sup)
            r["generico"] = r.pop("especificacion")
            r |= {"generico_cod": cod,
                  "grupo": COMPLEMENTARIOS[cod][1] if cod in COMPLEMENTARIOS else "Placebo",
                  "tipo": "Servicios" if cod in SERVICIOS else
                          "Bienes comerciables" if cod in BIENES else "Placebo"}
            filas.append(r)
    return pd.DataFrame(filas)


def estudio_evento(df, perm, ciudades):
    """Coeficientes θ_k = sede × (quincena relativa k), con k = −1 como referencia."""
    ks = sorted(k for k in df.k.unique() if k != K_REF)
    df = df.copy()
    nombres = {k: f"ev_{'m' if k < 0 else 'p'}{abs(k)}" for k in ks}
    for k, n in nombres.items():
        df[n] = df.sede * (df.k == k)
    periodo = df.drop_duplicates("k").set_index("k")[["periodo", "fecha"]]
    filas, pruebas = [], []
    for grupo, codigos in GRUPOS.items():
        sub = df[df.generico_cod.isin(codigos)]
        m = regresion(sub, " + ".join(nombres.values()))
        # Z[c, k] = promedio entre genéricos de y_cjk − y_cj,ref
        y = sub.pivot_table(index=["ciudad", "generico_cod"], columns="k", values="y")
        z = y[ks].sub(y[K_REF], axis=0).groupby("ciudad").mean().reindex(ciudades)
        beta, p, inf, sup, dist = perm.inferir(z.to_numpy())
        for i, k in enumerate(ks):
            assert abs(float(m.coef()[nombres[k]]) - beta[i]) < 1e-6
            filas.append({"grupo": grupo, "k": k, "periodo": periodo.loc[k, "periodo"],
                          "fecha": periodo.loc[k, "fecha"], "beta": beta[i],
                          "ee_cluster": float(m.se()[nombres[k]]), "p_permutacion": p[i],
                          "ic95_inf": inf[i], "ic95_sup": sup[i]})
        # Prueba conjunta de tendencias previas: raíz del promedio de θ_k² con k < −1,
        # comparada con la misma estadística en las 26,235 asignaciones.
        pre = np.array(ks) < K_REF
        rms = lambda b: np.sqrt((b[..., pre] ** 2).mean(axis=-1))  # noqa: E731
        pruebas.append({"grupo": grupo, "rms_pre": float(rms(beta)),
                        "p_permutacion_pre": float((rms(dist) >= rms(beta) - 1e-9).mean())})
    ref = periodo.loc[K_REF]
    for grupo in GRUPOS:
        filas.append({"grupo": grupo, "k": K_REF, "periodo": ref["periodo"], "fecha": ref["fecha"],
                      "beta": 0.0, "ee_cluster": 0.0, "p_permutacion": 1.0,
                      "ic95_inf": 0.0, "ic95_sup": 0.0})
    ev = pd.DataFrame(filas).sort_values(["grupo", "k"]).reset_index(drop=True)
    return ev, pd.DataFrame(pruebas)


# --- Figuras -------------------------------------------------------------------------
AZUL, GRIS, TEXTO, TEXTO2 = "#2a78d6", "#8a8984", "#0b0b0b", "#52514e"
FRANJA = "#e8e7e3"


def estilo(ax):
    for lado in ["top", "right"]:
        ax.spines[lado].set_visible(False)
    for lado in ["left", "bottom"]:
        ax.spines[lado].set_color("#c3c2b7")
    ax.tick_params(colors=TEXTO2, labelsize=8.5)
    ax.grid(axis="y", color="#ecebe7", lw=0.8)
    ax.set_axisbelow(True)


def fig_estudio_evento(ev, pruebas):
    paneles = ["Servicios", "Bienes comerciables", "Placebo"]
    titulos = {"Servicios": "Servicios: comida fuera de casa y transporte",
               "Bienes comerciables": "Bienes comerciables: bebidas, botanas y equipo",
               "Placebo": "Placebo: genéricos sin relación con el futbol"}
    fig, axes = plt.subplots(len(paneles), 1, figsize=(8, 8.4), sharex=True, sharey=True)
    for ax, grupo in zip(axes, paneles):
        e = ev[ev.grupo == grupo].sort_values("k")
        x = e["fecha"]
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color=FRANJA, lw=0)
        ax.axhline(0, color=GRIS, lw=0.8)
        color_pt = GRIS if grupo == "Placebo" else AZUL
        ax.fill_between(x, e.ic95_inf, e.ic95_sup, color=color_pt, alpha=0.16, lw=0)
        ax.plot(x, e.beta, color=color_pt, lw=1.4)
        ax.scatter(x, e.beta, s=14, color=color_pt, zorder=3, edgecolor="white", linewidth=0.6)
        p_pre = pruebas.set_index("grupo").loc[grupo, "p_permutacion_pre"]
        ax.set_title(titulos[grupo], loc="left", fontsize=10.5, color=TEXTO)
        ax.text(0.01, 0.06, f"Prueba conjunta antes del Mundial: p = {p_pre:.2f}",
                transform=ax.transAxes, fontsize=8, color=TEXTO2)
        ax.set_ylabel("% vs. 2Q may 2026", fontsize=8.5, color=TEXTO2)
        estilo(ax)
    ticks = pd.date_range("2025-01-01", ev.fecha.max(), freq="3MS")
    axes[-1].set_xticks(ticks)
    axes[-1].set_xticklabels([f"{MESES[d.month - 1]} {d:%y}" for d in ticks])
    axes[0].text(pd.Timestamp("2026-06-04"), axes[0].get_ylim()[1] * 0.92, "Mundial",
                 fontsize=8, color=TEXTO2, va="top")
    fig.suptitle("Precios en ciudades sede vs. ciudades no sede, por quincena\n"
                 "Coeficiente del estudio de evento e IC 95% por permutación (Conley–Taber)",
                 fontsize=11.5, color=TEXTO, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(FIG / "fig_estudio_evento.png", dpi=200)
    plt.close(fig)


def fig_por_generico(gen):
    d = gen[gen.coeficiente == "beta_durante"].copy()
    orden = {"Servicios": 0, "Bienes comerciables": 1, "Placebo": 2}
    d["o"] = d.tipo.map(orden)
    d = d.sort_values(["o", "beta"], ascending=[False, True]).reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.5, 6.6))
    y = np.arange(len(d))
    for i, r in d.iterrows():
        color = GRIS if r.tipo == "Placebo" else AZUL
        ax.plot([r.ic95_inf, r.ic95_sup], [i, i], color=color, lw=1.6, alpha=0.45,
                solid_capstyle="round")
        ax.scatter(r.beta, i, s=36, color=color, zorder=3, edgecolor="white", linewidth=0.8)
    ax.axvline(0, color=GRIS, lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels(d.generico, fontsize=8.5)
    # Separadores y nombres de bloque
    for tipo, sub in d.groupby("tipo"):
        ax.text(1.0, sub.index.max() + 0.1, tipo, transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", fontsize=8.5, color=TEXTO2, style="italic")
        if sub.index.min() > 0:
            ax.axhline(sub.index.min() - 0.5, color="#c3c2b7", lw=0.6, ls=":")
    ax.set_xlabel("Efecto durante el Mundial (%, sedes − no sedes)", fontsize=9, color=TEXTO2)
    ax.set_title("Efecto por genérico durante las quincenas con partidos\n"
                 "Punto: β; línea: IC 95% por permutación (Conley–Taber)",
                 loc="left", fontsize=11, color=TEXTO)
    estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#ecebe7", lw=0.8)
    fig.tight_layout()
    fig.savefig(FIG / "fig_efectos_por_generico.png", dpi=200)
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    df = cargar()
    ciudades = sorted(df.ciudad.unique())
    perm = Permutaciones(ciudades)
    print(f"Ventana: {df.periodo[df.t == df.t.min()].iloc[0]} a "
          f"{df.periodo[df.t == df.t.max()].iloc[0]}; {len(ciudades)} ciudades; "
          f"{len(perm.todas):,} asignaciones de 3 sedes; {len(perm.de_control):,} tripletas de control")

    tab = did_principal(df, perm, ciudades)
    tab.round(4).to_csv(TAB / "tab_did_principal.csv", index=False)
    print("\nDiD principal (β y γ en %):\n",
          tab.drop(columns=["n_obs"]).round(3).to_string(index=False))

    gen = did_por_generico(df, perm, ciudades)
    gen.round(4).to_csv(TAB / "tab_did_por_generico.csv", index=False)
    print("\nPor genérico, durante el Mundial:\n",
          gen[gen.coeficiente == "beta_durante"][["generico", "tipo", "beta", "p_cluster",
                                                  "p_permutacion", "ic95_inf", "ic95_sup"]]
          .sort_values(["tipo", "beta"]).round(3).to_string(index=False))

    ev, pruebas = estudio_evento(df, perm, ciudades)
    ev.assign(fecha=ev.fecha.dt.date).round(4).to_csv(TAB / "tab_estudio_evento.csv", index=False)
    print("\nPrueba conjunta de tendencias previas (permutación):\n", pruebas.round(3).to_string(index=False))
    print("\nEstudio de evento, quincenas −4 a +9:\n",
          ev[ev.k >= -4].pivot(index=["k", "periodo"], columns="grupo", values="beta")
          .round(2).to_string())

    fig_estudio_evento(ev, pruebas)
    fig_por_generico(gen)


if __name__ == "__main__":
    main()
