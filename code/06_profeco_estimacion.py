"""Diferencia en diferencias con precios de PROFECO por tienda y producto (segunda fuente).

Diseño
------
Unidad: par tienda × producto (misma marca y presentación en la misma tienda).
Para cada par se calcula el cambio en 100·ln(precio) entre un periodo "antes" y uno
"después". El contrafactual de cada producto es el cambio promedio del MISMO producto en
las tiendas de control (ciudades a más de 100 km de un estadio). El efecto de una ciudad
es el promedio de los cambios ajustados de sus pares, y β es el promedio simple de las
tres sedes. Esto equivale a una regresión con efectos fijos de tienda×producto y de
producto×quincena, con la ciudad como unidad de tratamiento.

Periodos (principal): antes = 1Q y 2Q mayo 2026; durante = 1Q jun a 1Q jul 2026 (las
quincenas con partidos en México); después = 2Q jul 2026.

Inferencia (Conley–Taber / permutación): a cada ciudad de control se le calcula su
"efecto" igual que a una sede (dejándola fuera del contrafactual). La distribución del
promedio de 3 ciudades de control da el p-valor y el intervalo de confianza de β.

Salidas en output/tables/profeco_*.csv y output/figures/fig_profeco_*.png.

Uso:  .venv/bin/python code/06_profeco_estimacion.py
"""
import itertools

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyfixest as pf  # noqa: E402

import config as C  # noqa: E402

SEDES = ["CDMX", "Guadalajara", "Monterrey"]
T_PRE = [C.t_quincena(2026, 5, 1), C.t_quincena(2026, 5, 2)]
T_DUR = [C.t_quincena(*q) for q in C.QUINCENAS_MUNDIAL]
T_DESP = [C.t_quincena(2026, 7, 2)]
T_REF = T_PRE[-1]
MIN_PARES = 30     # una ciudad de control entra a la inferencia si tiene al menos 30 pares
CERCA_KM = 5       # "cerca" del estadio o del Fan Fest
REPS = 4_999       # permutaciones de la etiqueta "cerca" dentro de cada sede
SEMILLA = 20260611
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

BEBIDAS = ["Cerveza", "Refrescos", "Agua y bebidas hidratantes", "Botanas",
           "Especial: botanas y bebidas", "Vinos y licores", "Pollo rostizado"]
CONJUNTOS = {  # nombre → función que selecciona pares
    "Complementarios": lambda d: d.tipo == "Complementario",
    "Bebidas, botanas y comida": lambda d: d.grupo.isin(BEBIDAS),
    "Pantallas y audio": lambda d: d.grupo == "Pantallas y audio",
    "Placebo": lambda d: d.tipo == "Placebo",
}


def fecha_t(t):
    t = np.asarray(t)
    anio, resto = 2018 + t // 24, t % 24
    return pd.to_datetime({"year": anio, "month": resto // 2 + 1, "day": np.where(resto % 2 == 0, 1, 16)})


def etiqueta_t(t):
    anio, resto = 2018 + t // 24, t % 24
    return f"{resto % 2 + 1}Q {MESES[resto // 2]} {anio}"


# --- Datos ----------------------------------------------------------------------------
def cargar():
    p = pd.read_parquet(C.CLEAN / "profeco_precios.parquet")
    t = pd.read_csv(C.CLEAN / "profeco_tiendas.csv")
    t = t[t.zona.isin(["Sede", "Control"])].copy()
    t["cerca_estadio"] = t.dist_estadio_km <= CERCA_KM
    t["cerca_fanfest"] = t.dist_fanfest_km <= CERCA_KM
    t["cerca"] = t.cerca_estadio | t.cerca_fanfest
    p = p.merge(t[["tienda_id", "ciudad", "zona", "sede", "giro", "cerca", "cerca_estadio",
                   "cerca_fanfest"]], on="tienda_id")
    p["y"] = 100 * np.log(p.precio)
    p["grupo"] = p.grupo.astype(str)
    p["tipo"] = p.tipo.astype(str)
    return p


def cambios(p, antes, despues):
    """Cambio de 100·ln(precio) por par tienda×producto entre dos conjuntos de quincenas."""
    llave = ["tienda_id", "producto_id"]
    a = p[p.t.isin(antes)].groupby(llave).y.mean()
    b = p[p.t.isin(despues)].groupby(llave).y.mean()
    d = (b - a).dropna().rename("delta").reset_index()
    info = p.drop_duplicates(llave)[llave + ["grupo", "tipo", "ciudad", "zona", "sede", "giro",
                                              "cerca", "cerca_estadio", "cerca_fanfest"]]
    return d.merge(info, on=llave)


def ajustar(d):
    """Resta a cada par el cambio promedio del mismo producto en el control.

    Para una ciudad de control se usa el promedio del resto del control (sin ella), de modo
    que su "efecto" se calcula igual que el de una sede.
    """
    ctrl = d[d.zona == "Control"]
    tot = ctrl.groupby("producto_id").delta.agg(s="sum", n="count")
    por_ciudad = ctrl.groupby(["producto_id", "ciudad"]).delta.agg(s_c="sum", n_c="count")
    d = d.join(tot, on="producto_id").join(por_ciudad, on=["producto_id", "ciudad"])
    d[["s_c", "n_c"]] = d[["s_c", "n_c"]].fillna(0)
    n = d.n - d.n_c
    d["ajustado"] = d.delta - (d.s - d.s_c) / n.where(n > 0)
    return d.dropna(subset=["ajustado"])


def efectos_ciudad(d):
    """Efecto por ciudad: promedio de los cambios ajustados de sus pares."""
    d = ajustar(d)
    return d.groupby("ciudad").agg(theta=("ajustado", "mean"), pares=("ajustado", "size"),
                                   tiendas=("tienda_id", "nunique"), zona=("zona", "first"))


# --- Inferencia -----------------------------------------------------------------------
def inferir(theta, min_pares=MIN_PARES):
    """β (promedio de sedes), p-valor e IC 95% con la distribución de tripletas de control."""
    sedes = theta.reindex(SEDES).dropna(subset=["theta"])
    ctrl = theta[(theta.zona == "Control") & (theta.pares >= min_pares)].theta.to_numpy()
    beta = sedes.theta.mean()
    k = len(sedes)
    if k == 0 or len(ctrl) < k + 5:
        return {"beta": beta, "p_permutacion": np.nan, "ic95_inf": np.nan, "ic95_sup": np.nan,
                "ciudades_control": len(ctrl), "pares_sedes": int(sedes.pares.sum())}, np.array([])
    combos = np.array(list(itertools.combinations(range(len(ctrl)), k)), dtype=int)
    dist = ctrl[combos].mean(axis=1)
    p = (np.sum(np.abs(dist) >= abs(beta)) + 1) / (len(dist) + 1)
    inf, sup = beta - np.quantile(dist, 0.975), beta - np.quantile(dist, 0.025)
    fila = {"beta": beta, "p_permutacion": p, "ic95_inf": inf, "ic95_sup": sup,
            "ciudades_control": len(ctrl), "pares_sedes": int(sedes.pares.sum()),
            "pares_control": int(theta[theta.zona == "Control"].pares.sum())}
    for s in SEDES:
        if s in sedes.index:
            ts = sedes.loc[s, "theta"]
            fila[f"beta_{s}"] = ts
            fila[f"p_{s}"] = (np.sum(np.abs(ctrl) >= abs(ts)) + 1) / (len(ctrl) + 1)
    return fila, dist


def did(p, conjunto, antes=T_PRE, despues=T_DUR, filtro=None):
    d = cambios(p, antes, despues)
    d = d[CONJUNTOS[conjunto](d)]
    if filtro is not None:
        d = d[filtro(d)]
    fila, _ = inferir(efectos_ciudad(d))
    return fila


# --- Resultados -----------------------------------------------------------------------
def did_principal(p):
    filas = []
    for conjunto in CONJUNTOS:
        for nombre, despues in [("Durante (1Q jun–1Q jul)", T_DUR), ("Después (2Q jul)", T_DESP)]:
            filas.append({"conjunto": conjunto, "periodo": nombre, **did(p, conjunto, despues=despues)})
    return pd.DataFrame(filas)


def did_por_grupo(p):
    d = cambios(p, T_PRE, T_DUR)
    filas = []
    for (tipo, grupo), sub in d.groupby(["tipo", "grupo"]):
        theta = efectos_ciudad(sub)
        if theta.reindex(SEDES).theta.isna().any():
            continue
        fila, _ = inferir(theta, min_pares=10)
        filas.append({"tipo": tipo, "grupo": grupo, **fila})
    return pd.DataFrame(filas)


def robustez(p):
    """Pruebas de robustez para 'Bebidas, botanas y comida' y 'Complementarios'."""
    t = C.t_quincena
    pre25 = [t(2025, 5, 1), t(2025, 5, 2)]
    dur25 = [t(2025, 6, 1), t(2025, 6, 2), t(2025, 7, 1)]
    pruebas = [
        ("Principal: may 2026 → 1Q jun–1Q jul 2026", T_PRE, T_DUR, None),
        ("Placebo de tendencia: ene–feb 2026 → may 2026", [t(2026, 1, 1), t(2026, 1, 2), t(2026, 2, 2)], T_PRE, None),
        ("Placebo estacional: may 2025 → 1Q jun–1Q jul 2025", pre25, dur25, None),
        ("Durante incluye 2Q jul (final)", T_PRE, T_DUR + T_DESP, None),
        ("Sin frontera norte en el control", T_PRE, T_DUR,
         lambda d: ~d.ciudad.str.contains("Tijuana|Juárez|Reynosa|Mexicali", regex=True)),
        ("Solo supermercados", T_PRE, T_DUR, lambda d: d.giro.str.startswith("Supermercado")),
    ]
    filas = []
    for conjunto in ["Bebidas, botanas y comida", "Complementarios", "Placebo"]:
        for nombre, antes, despues, filtro in pruebas:
            filas.append({"conjunto": conjunto, "prueba": nombre,
                          **did(p, conjunto, antes, despues, filtro)})
        # Triple diferencia: (may → 1Q jun–1Q jul 2026) − (mismo cambio en 2025), con la
        # misma inferencia aplicada a la diferencia de efectos por ciudad.
        th26 = efectos_ciudad(cambios(p, T_PRE, T_DUR).pipe(lambda d: d[CONJUNTOS[conjunto](d)]))
        th25 = efectos_ciudad(cambios(p, pre25, dur25).pipe(lambda d: d[CONJUNTOS[conjunto](d)]))
        th = th26[["theta", "zona"]].join(th25[["theta"]].rename(columns={"theta": "theta_25"}), how="inner")
        th["theta"] = th.theta - th.theta_25
        th["pares"] = np.minimum(th26.pares.reindex(th.index), th25.pares.reindex(th.index))
        fila, _ = inferir(th)
        filas.append({"conjunto": conjunto, "prueba": "Triple diferencia: 2026 menos el mismo cambio en 2025",
                      **fila})
    return pd.DataFrame(filas)


def regresion_panel(p):
    """Misma comparación como regresión de panel (peso por par; errores por ciudad)."""
    v = p[p.t.isin(T_PRE + T_DUR + T_DESP) & (p.tipo == "Complementario")].copy()
    v["par"] = v.tienda_id.astype(str) + "_" + v.producto_id.astype(str)
    v["prod_t"] = v.producto_id.astype(str) + "_" + v.t.astype(str)
    v["sede_d"] = (v.zona == "Sede").astype(int)
    v["durante"] = (v.sede_d * v.t.isin(T_DUR)).astype(int)
    v["despues"] = (v.sede_d * v.t.isin(T_DESP)).astype(int)
    m = pf.feols("y ~ durante + despues | par + prod_t", data=v, vcov={"CRV1": "ciudad"})
    r = m.tidy().loc[["durante", "despues"]]
    return pd.DataFrame({"coeficiente": r.index, "beta": r.Estimate.values,
                         "ee_cluster_ciudad": r["Std. Error"].values, "p_cluster": r["Pr(>|t|)"].values,
                         "n_obs": m._N})


def heterogeneidad_distancia(p):
    """Dentro de cada sede: tiendas cerca (≤5 km) del estadio o Fan Fest vs. el resto.

    Efecto = promedio sobre sedes de [cambio ajustado cerca − cambio ajustado lejos].
    p-valor: se permuta la etiqueta "cerca" entre tiendas de la misma sede.
    """
    rng = np.random.default_rng(SEMILLA)
    d0 = ajustar(cambios(p, T_PRE, T_DUR))
    filas = []
    for conjunto in ["Bebidas, botanas y comida", "Complementarios", "Placebo"]:
        d = d0[CONJUNTOS[conjunto](d0) & (d0.zona == "Sede")]
        for col, nombre in [("cerca", "Estadio o Fan Fest"), ("cerca_estadio", "Estadio"),
                            ("cerca_fanfest", "Fan Fest")]:
            por_tienda = d.groupby(["sede", "tienda_id"]).agg(
                s=("ajustado", "sum"), n=("ajustado", "size"), cerca=(col, "first")).reset_index()
            obs, nulos, detalle = [], np.zeros(REPS), {}
            for sede, g in por_tienda.groupby("sede"):
                s, n, c = g.s.to_numpy(), g.n.to_numpy(), g.cerca.to_numpy(bool)
                if c.sum() == 0 or (~c).sum() == 0:
                    continue
                dif = s[c].sum() / n[c].sum() - s[~c].sum() / n[~c].sum()
                obs.append(dif)
                detalle[f"dif_{sede}"] = dif
                detalle[f"tiendas_cerca_{sede}"] = int(c.sum())
                perm = np.array([rng.permutation(c) for _ in range(REPS)])
                sc, nc = perm @ s, perm @ n
                nulos += sc / nc - (s.sum() - sc) / (n.sum() - nc)
            k = len(obs)
            efecto = np.mean(obs)
            nulos = nulos / k
            filas.append({"conjunto": conjunto, "cerca_de": nombre, "km": CERCA_KM,
                          "efecto_cerca_menos_lejos": efecto,
                          "p_permutacion": (np.sum(np.abs(nulos) >= abs(efecto)) + 1) / (REPS + 1),
                          "sedes": k, **detalle})
    return pd.DataFrame(filas)


def estudio_evento(p):
    """β por quincena relativo a 2Q may 2026, con bandas de Conley–Taber."""
    ts = sorted(p.t.unique())
    filas, matrices = [], {}
    for conjunto in ["Bebidas, botanas y comida", "Pantallas y audio", "Placebo"]:
        thetas = {}
        for tt in ts:
            if tt == T_REF:
                filas.append({"conjunto": conjunto, "t": tt, "beta": 0.0, "ic95_inf": 0.0,
                              "ic95_sup": 0.0, "p_permutacion": np.nan})
                continue
            d = cambios(p, [T_REF], [tt])
            theta = efectos_ciudad(d[CONJUNTOS[conjunto](d)])
            fila, _ = inferir(theta)
            thetas[tt] = theta
            filas.append({"conjunto": conjunto, "t": tt, **{k: fila[k] for k in
                          ["beta", "ic95_inf", "ic95_sup", "p_permutacion"]}})
        matrices[conjunto] = thetas
    ev = pd.DataFrame(filas).sort_values(["conjunto", "t"]).reset_index(drop=True)
    ev["fecha"] = fecha_t(ev.t).dt.date
    ev["periodo"] = ev.t.map(etiqueta_t)
    return ev, prueba_pre(matrices)


def prueba_pre(matrices):
    """Prueba conjunta: RMS de β en las quincenas previas a mayo 2026 vs. tripletas de control."""
    filas = []
    for conjunto, thetas in matrices.items():
        # Se omite la 2Q nov 2025: el archivo de PROFECO viene cortado (solo hasta el día 28
        # y con la mitad de las tiendas), así que muchas ciudades no tienen datos.
        pre = [tt for tt in thetas if tt < T_PRE[0] and tt != C.t_quincena(2025, 11, 2)]
        m = pd.DataFrame({tt: thetas[tt].theta.astype(float) for tt in pre})
        zona = pd.concat([thetas[tt].zona for tt in pre]).groupby(level=0).first()
        pares = pd.concat([thetas[tt].pares for tt in pre], axis=1).min(axis=1)
        ctrl = m[(zona.reindex(m.index) == "Control") & (pares.reindex(m.index) >= 10)].dropna()
        obs = np.sqrt((m.reindex(SEDES).mean(axis=0) ** 2).mean())
        if len(ctrl) < 8:
            filas.append({"conjunto": conjunto, "quincenas_previas": len(pre),
                          "ciudades_control": len(ctrl), "rms_sedes": obs, "p_permutacion_pre": np.nan})
            continue
        combos = np.array(list(itertools.combinations(range(len(ctrl)), 3)), dtype=int)
        x = ctrl.to_numpy(dtype=float)[combos].mean(axis=1)
        nulos = np.sqrt((x ** 2).mean(axis=1))
        filas.append({"conjunto": conjunto, "quincenas_previas": len(pre), "ciudades_control": len(ctrl),
                      "rms_sedes": obs,
                      "p_permutacion_pre": (np.sum(nulos >= obs) + 1) / (len(nulos) + 1)})
    return pd.DataFrame(filas)


# --- Figuras --------------------------------------------------------------------------
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


def fig_estudio_evento(ev, pre):
    # Pantallas y audio queda fuera de la figura: antes de 2026 casi ninguna ciudad de control
    # tiene suficientes pares para construir la banda (sus cifras están en la tabla).
    titulos = {"Bebidas, botanas y comida": "Cerveza, refrescos, agua, botanas, licores y pollo rostizado",
               "Placebo": "Placebo: detergentes, papel, aceite, arroz y leche"}
    fig, axes = plt.subplots(2, 1, figsize=(8, 6.2), sharex=True, sharey=True)
    for ax, conjunto in zip(axes, titulos):
        e = ev[ev.conjunto == conjunto].sort_values("t")
        x = pd.to_datetime(e.fecha)
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color=FRANJA, lw=0)
        ax.axhline(0, color=GRIS, lw=0.8)
        color = GRIS if conjunto == "Placebo" else AZUL
        ax.vlines(x, e.ic95_inf, e.ic95_sup, color=color, lw=1.6, alpha=0.35)
        ax.scatter(x, e.beta, s=16, color=color, zorder=3, edgecolor="white", linewidth=0.6)
        p_pre = pre.set_index("conjunto").loc[conjunto, "p_permutacion_pre"]
        ax.set_title(titulos[conjunto], loc="left", fontsize=10.5, color=TEXTO)
        if np.isfinite(p_pre):
            ax.text(0.01, 0.06, f"Prueba conjunta antes de mayo 2026: p = {p_pre:.2f}",
                    transform=ax.transAxes, fontsize=8, color=TEXTO2)
        ax.set_ylabel("% vs. 2Q may 2026", fontsize=8.5, color=TEXTO2)
        estilo(ax)
    ticks = pd.date_range("2025-01-01", "2026-07-01", freq="3MS")
    axes[-1].set_xticks(ticks)
    axes[-1].set_xticklabels([f"{MESES[d.month - 1]} {d:%y}" for d in ticks])
    axes[0].annotate("Mundial", (pd.Timestamp("2026-06-03"), 1), xycoords=("data", "axes fraction"),
                     fontsize=8, color=TEXTO2, va="top")
    fig.suptitle("PROFECO: precio del mismo producto en la misma tienda, sedes vs. resto del país\n"
                 "β por quincena e IC 95% por permutación (Conley–Taber); sin datos en los huecos",
                 fontsize=11.5, color=TEXTO, x=0.02, ha="left")
    fig.tight_layout()
    fig.savefig(C.FIG / "fig_profeco_estudio_evento.png", dpi=200)
    plt.close(fig)


def fig_por_grupo(gr):
    # Grupos sin suficientes ciudades de control para el intervalo (pollo rostizado,
    # artículos de futbol) quedan solo en la tabla.
    d = (gr.dropna(subset=["ic95_inf"]).sort_values(["tipo", "beta"], ascending=[False, True])
         .reset_index(drop=True))
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    for i, r in d.iterrows():
        color = GRIS if r.tipo == "Placebo" else AZUL
        ax.plot([r.ic95_inf, r.ic95_sup], [i, i], color=color, lw=1.6, alpha=0.45, solid_capstyle="round")
        ax.scatter(r.beta, i, s=36, color=color, zorder=3, edgecolor="white", linewidth=0.8)
    ax.axvline(0, color=GRIS, lw=0.8)
    ax.set_yticks(np.arange(len(d)))
    ax.set_yticklabels(d.grupo, fontsize=8.5)
    for tipo, sub in d.groupby("tipo"):
        ax.text(1.0, sub.index.max() + 0.1, tipo, transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", fontsize=8.5, color=TEXTO2, style="italic")
        if sub.index.min() > 0:
            ax.axhline(sub.index.min() - 0.5, color="#c3c2b7", lw=0.6, ls=":")
    ax.set_xlabel("Efecto durante el Mundial (%, sedes − resto del país)", fontsize=9, color=TEXTO2)
    ax.set_title("PROFECO: efecto por grupo de productos durante el Mundial\n"
                 "1Q jun–1Q jul vs. mayo 2026. Punto: β; línea: IC 95% (Conley–Taber)",
                 loc="left", fontsize=11, color=TEXTO)
    estilo(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color="#ecebe7", lw=0.8)
    fig.tight_layout()
    fig.savefig(C.FIG / "fig_profeco_por_grupo.png", dpi=200)
    plt.close(fig)


def main():
    C.FIG.mkdir(parents=True, exist_ok=True)
    C.TAB.mkdir(parents=True, exist_ok=True)
    p = cargar()
    print(f"Panel: {len(p):,} filas; {p.tienda_id.nunique()} tiendas "
          f"({p[p.zona == 'Sede'].tienda_id.nunique()} en sedes); quincenas: "
          f"{', '.join(etiqueta_t(t) for t in sorted(p.t.unique()))}")

    tab = did_principal(p)
    tab.round(4).to_csv(C.TAB / "profeco_did_principal.csv", index=False)
    cols = ["conjunto", "periodo", "beta", "p_permutacion", "ic95_inf", "ic95_sup",
            "beta_CDMX", "beta_Guadalajara", "beta_Monterrey", "ciudades_control", "pares_sedes"]
    print("\nDiD principal (%):\n", tab[cols].round(3).to_string(index=False))

    gr = did_por_grupo(p)
    gr.round(4).to_csv(C.TAB / "profeco_did_por_grupo.csv", index=False)
    print("\nPor grupo, durante:\n", gr[["tipo", "grupo", "beta", "p_permutacion", "ic95_inf",
                                         "ic95_sup", "beta_CDMX", "beta_Guadalajara",
                                         "beta_Monterrey", "pares_sedes"]].round(3).to_string(index=False))

    rob = robustez(p)
    rob.round(4).to_csv(C.TAB / "profeco_robustez.csv", index=False)
    print("\nRobustez:\n", rob[["conjunto", "prueba", "beta", "p_permutacion", "ic95_inf",
                                "ic95_sup"]].round(3).to_string(index=False))

    reg = regresion_panel(p)
    reg.round(4).to_csv(C.TAB / "profeco_regresion_panel.csv", index=False)
    print("\nRegresión de panel equivalente (complementarios, peso por par):\n", reg.round(4).to_string(index=False))

    het = heterogeneidad_distancia(p)
    het.round(4).to_csv(C.TAB / "profeco_heterogeneidad_distancia.csv", index=False)
    print("\nCerca vs. lejos dentro de las sedes:\n", het.round(3).to_string(index=False))

    ev, pre = estudio_evento(p)
    ev.round(4).to_csv(C.TAB / "profeco_estudio_evento.csv", index=False)
    print("\nPrueba conjunta de tendencias previas:\n", pre.round(3).to_string(index=False))
    print("\nEstudio de evento:\n", ev.pivot(index="periodo", columns="conjunto", values="beta")
          .reindex([etiqueta_t(t) for t in sorted(p.t.unique())]).round(2).to_string())

    fig_estudio_evento(ev, pre)
    fig_por_grupo(gr)


if __name__ == "__main__":
    main()
