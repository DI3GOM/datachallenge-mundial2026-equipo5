"""Paso 8. Prueba nacional: ¿subieron los complementarios en todo el país durante el Mundial?

La diferencia en diferencias (04, 06) compara sedes contra el resto del país, así que no
ve un efecto que haya ocurrido en todas las ciudades. Por ejemplo, mucha gente vio los
partidos de México en casa en todo el país. Esta prueba busca ese efecto nacional
comparando 2026 con los mismos meses de años anteriores. No hay grupo de control
geográfico; el contrafactual es "lo que normalmente pasa en esos meses".

INPC (2018–2026, 55 ciudades, todos los genéricos)
  1. Para cada genérico j y año Y: Δ_jY = promedio entre ciudades de
     [media de 100·ln índice en 1Q jun–1Q jul − media en mar–may].
  2. Se resta la mediana de Δ entre todos los genéricos de ese año, para quitar la
     inflación general del año.
  3. Anomalía de 2026: A_j = Δ_j,2026 − promedio de Δ_j en los años de referencia
     (2018, 2019 y 2021–2025; 2020 queda fuera por el COVID). z_j = A_j / desv. est.
     de Δ_j entre esos años: qué tan raro fue 2026 para ese genérico.
  4. Inferencia:
     a) entre genéricos: ¿la z promedio del grupo es más extrema que la de grupos
        del mismo tamaño tomados al azar de los ~270 genéricos?
     b) entre años: la misma estadística, fingiendo que el Mundial fue en otro año.

PROFECO (2025 y 2026, todas las tiendas del país)
  Para cada par tienda×producto: [cambio may → 1Q jun–1Q jul de 2026] − [el mismo cambio
  en 2025]. Se comparan los productos complementarios contra los placebo, permutando las
  etiquetas entre productos.

Salidas:
  output/tables/nacional_inpc_genericos.csv
  output/tables/nacional_inpc_grupos.csv
  output/tables/nacional_inpc_anios.csv
  output/tables/nacional_profeco.csv
  output/figures/fig_nacional.png

Uso:  .venv/bin/python code/08_prueba_nacional.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402

t = C.t_quincena
ANIOS = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026]
REFERENCIA = [2018, 2019, 2021, 2022, 2023, 2024, 2025]   # sin 2020 (COVID)
MIN_ANIOS = 5            # un genérico entra si tiene al menos 5 años de referencia
REPS = 20_000
SEMILLA = 20260611

BIENES = [k for k, v in C.COMPLEMENTARIOS.items() if v[2]]
SERVICIOS = [k for k, v in C.COMPLEMENTARIOS.items() if not v[2]]
AMPLIADOS = {"105": "Tequila", "106": "Otros licores", "099": "Agua embotellada",
             "267": "Pollos rostizados", "263": "Barbacoa o birria", "269": "Otros alimentos cocinados",
             "236": "Televisión de paga", "137": "Zapatos tenis"}
GRUPOS = {
    "Bienes comerciables (cerveza, refrescos, botanas, TV, deportivos)": BIENES,
    "Bienes ampliados (licores, agua, pollo, barbacoa, TV de paga, tenis)": list(AMPLIADOS),
    "Servicios (comida fuera de casa y transporte)": SERVICIOS,
    "Servicios sin transporte aéreo": [c for c in SERVICIOS if c != "227"],
    "Placebo": list(C.PLACEBO),
}
NARANJA, AZUL, GRIS, TEXTO, TEXTO2 = "#eb6834", "#2a78d6", "#8a8984", "#0b0b0b", "#52514e"


# --- INPC -----------------------------------------------------------------------------
def cambios_inpc():
    """Δ_jY nacional (promedio entre ciudades) para cada genérico y año."""
    d = pd.read_parquet(C.CLEAN / "inpc_ciudad_generico.parquet",
                        columns=["ciudad", "generico_cod", "generico", "t", "ln_indice", "es_indice_general"])
    d = d[~d.es_indice_general & ~d.generico_cod.isin(C.EXCLUIDOS_HOSPEDAJE)]
    nombres = d.drop_duplicates("generico_cod").set_index("generico_cod").generico
    y = d.assign(y=100 * d.ln_indice).pivot_table(index=["ciudad", "generico_cod"], columns="t", values="y")
    filas = {}
    for anio in ANIOS:
        antes = list(range(t(anio, 3, 1), t(anio, 5, 2) + 1))
        durante = [t(anio, 6, 1), t(anio, 6, 2), t(anio, 7, 1)]
        cambio = y[durante].mean(axis=1, skipna=False) - y[antes].mean(axis=1, skipna=False)
        filas[anio] = cambio.groupby(level="generico_cod").mean()
    delta = pd.DataFrame(filas)
    delta = delta - delta.median(axis=0)          # quita la inflación general de cada año
    return delta, nombres


def anomalias(delta, anio, referencia):
    ref = delta[referencia]
    ok = ref.notna().sum(axis=1) >= MIN_ANIOS
    a = (delta[anio] - ref.mean(axis=1))[ok]
    s = ref.std(axis=1, ddof=1)[ok]
    return pd.DataFrame({"anomalia": a, "desv_est_historica": s, "z": a / s}).dropna()


def prueba_grupos(an, rng):
    """Para cada grupo: anomalía y z promedio, y p-valor contra grupos al azar de genéricos."""
    z_todos = an.z.to_numpy()
    filas = []
    for grupo, codigos in GRUPOS.items():
        g = an.reindex([c for c in codigos if c in an.index])
        k = len(g)
        obs = g.z.mean()
        nulos = np.array([z_todos[rng.choice(len(z_todos), k, replace=False)].mean() for _ in range(REPS)])
        filas.append({"grupo": grupo, "genericos": k, "anomalia_promedio_pct": g.anomalia.mean(),
                      "z_promedio": obs, "p_vs_genericos_al_azar": float((np.abs(nulos) >= abs(obs)).mean())})
    return pd.DataFrame(filas)


def prueba_anios(delta):
    """Misma estadística fingiendo que el Mundial fue en cada uno de los otros años."""
    anios = REFERENCIA + [2026]
    filas = []
    for anio in anios:
        an = anomalias(delta, anio, [a for a in anios if a != anio])
        for grupo, codigos in GRUPOS.items():
            g = an.reindex([c for c in codigos if c in an.index])
            filas.append({"anio": anio, "grupo": grupo, "anomalia_promedio_pct": g.anomalia.mean(),
                          "z_promedio": g.z.mean()})
    tab = pd.DataFrame(filas)
    # Lugar de cada año entre los 8 según |z promedio| (1 = el más extremo).
    tab["lugar_abs_z"] = tab.groupby("grupo").z_promedio.transform(
        lambda s: s.abs().rank(ascending=False, method="min"))
    return tab


# --- PROFECO --------------------------------------------------------------------------
def prueba_profeco(rng):
    p = pd.read_parquet(C.CLEAN / "profeco_precios.parquet")
    p["y"] = 100 * np.log(p.precio)
    p["grupo"] = p.grupo.astype(str)
    p["tipo"] = p.tipo.astype(str)
    llave = ["tienda_id", "producto_id"]

    def cambio(antes, durante):
        return p[p.t.isin(durante)].groupby(llave).y.mean() - p[p.t.isin(antes)].groupby(llave).y.mean()

    d26 = cambio([t(2026, 5, 1), t(2026, 5, 2)], [t(2026, 6, 1), t(2026, 6, 2), t(2026, 7, 1)])
    d25 = cambio([t(2025, 5, 1), t(2025, 5, 2)], [t(2025, 6, 1), t(2025, 6, 2), t(2025, 7, 1)])
    dd = (d26 - d25).dropna().rename("dd").reset_index()
    dd = dd.merge(p.drop_duplicates("producto_id")[["producto_id", "grupo", "tipo"]], on="producto_id")
    prod = dd.groupby(["producto_id", "grupo", "tipo"]).dd.mean().reset_index()

    bebidas = ["Cerveza", "Refrescos", "Agua y bebidas hidratantes", "Botanas", "Vinos y licores",
               "Pollo rostizado"]
    conjuntos = {"Bebidas, botanas y comida": prod.grupo.isin(bebidas),
                 "Pantallas y audio": prod.grupo.eq("Pantallas y audio"),
                 **{g: prod.grupo.eq(g) for g in bebidas}}
    placebo = prod.tipo.eq("Placebo")
    filas = [{"conjunto": "Placebo", "productos": int(placebo.sum()), "pares": int(dd.tipo.eq("Placebo").sum()),
              "cambio_2026_menos_2025": prod[placebo].dd.mean(), "dif_vs_placebo": 0.0, "p_permutacion": np.nan}]
    for nombre, m in conjuntos.items():
        sub = prod[m]
        if len(sub) < 5:
            continue
        obs = sub.dd.mean() - prod[placebo].dd.mean()
        pool = pd.concat([sub.dd, prod[placebo].dd]).to_numpy()
        k = len(sub)
        nulos = np.empty(REPS)
        for r in range(REPS):
            perm = rng.permutation(pool)
            nulos[r] = perm[:k].mean() - perm[k:].mean()
        filas.append({"conjunto": nombre, "productos": k, "pares": int(dd.producto_id.isin(sub.producto_id).sum()),
                      "cambio_2026_menos_2025": sub.dd.mean(), "dif_vs_placebo": obs,
                      "p_permutacion": float((np.abs(nulos) >= abs(obs)).mean())})
    return pd.DataFrame(filas)


# --- Figura ---------------------------------------------------------------------------
def fig_nacional(an, nombres, anios_tab):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 5.4), gridspec_kw={"width_ratios": [1.25, 1]})
    # Panel 1: z de 2026 de todos los genéricos, con los complementarios marcados.
    otros = an[~an.index.isin(BIENES + SERVICIOS + list(AMPLIADOS) + list(C.PLACEBO))]
    rng = np.random.default_rng(1)
    a1.scatter(otros.z.clip(-6, 6), rng.uniform(-0.3, 0.3, len(otros)) + 3, s=10, color="#c3c2b7", lw=0)
    filas = [("Bienes comerciables", BIENES, NARANJA, 2), ("Bienes ampliados", list(AMPLIADOS), NARANJA, 1),
             ("Servicios", SERVICIOS, AZUL, 0), ("Placebo", list(C.PLACEBO), GRIS, -1)]
    for etiqueta, codigos, color, yy in filas:
        g = an.reindex([c for c in codigos if c in an.index]).sort_values("z")
        a1.scatter(g.z.clip(-6, 6), np.full(len(g), yy), s=34, color=color, edgecolor="white", lw=0.6, zorder=3)
        arriba = True
        for cod, r in g.iterrows():
            if abs(r.z) >= 1.5:
                nombre = (C.COMPLEMENTARIOS.get(cod, (None,))[0] or AMPLIADOS.get(cod) or C.PLACEBO.get(cod)
                          or nombres.get(cod, cod))
                a1.annotate(nombre, (np.clip(r.z, -6, 6), yy), xytext=(0, 7 if arriba else -12),
                            textcoords="offset points", fontsize=7, color=TEXTO2, ha="center")
                arriba = not arriba  # alterna arriba y abajo para que no se encimen
    a1.axvline(0, color=GRIS, lw=0.8)
    for x in (-2, 2):
        a1.axvline(x, color="#c3c2b7", lw=0.6, ls=":")
    a1.set_yticks([3, 2, 1, 0, -1])
    a1.set_yticklabels(["Otros genéricos", "Bienes comerciables", "Bienes ampliados", "Servicios", "Placebo"],
                       fontsize=8.5)
    a1.set_xlabel("Anomalía de 2026 en desviaciones estándar históricas (z)", fontsize=8.5, color=TEXTO2)
    a1.set_title("Cada genérico: qué tan raro fue el cambio mar–may → jun–1Q jul\nde 2026 frente a 2018–2025",
                 loc="left", fontsize=9.5, color=TEXTO)
    # Panel 2: anomalía promedio por año.
    # Servicios sin transporte aéreo: con el avión, ese genérico (muy volátil) domina el promedio.
    lineas = [(next(g for g in GRUPOS if g.startswith("Bienes comerciables")), "Bienes comerciables", NARANJA),
              ("Servicios sin transporte aéreo", "Servicios (sin avión)", AZUL),
              ("Placebo", "Placebo", GRIS)]
    for grupo, etiqueta, color in lineas:
        g = anios_tab[anios_tab.grupo == grupo].sort_values("anio")
        a2.plot(g.anio, g.anomalia_promedio_pct, color=color, lw=1.2, marker="o", ms=4, label=etiqueta)
        r26 = g[g.anio == 2026]
        a2.scatter(r26.anio, r26.anomalia_promedio_pct, s=70, color=color, edgecolor=TEXTO, lw=0.8, zorder=4)
    a2.axhline(0, color=GRIS, lw=0.8)
    a2.legend(frameon=False, fontsize=8.5, loc="upper left")
    a2.set_xticks(REFERENCIA + [2026])
    a2.set_xticklabels([str(a) for a in REFERENCIA + [2026]], fontsize=8)
    a2.set_ylabel("Anomalía promedio del grupo (pp)", fontsize=8.5, color=TEXTO2)
    a2.set_title("Anomalía de cada año frente a los demás\n(2020 excluido por el COVID)", loc="left",
                 fontsize=9.5, color=TEXTO)
    for ax in (a1, a2):
        for lado in ["top", "right"]:
            ax.spines[lado].set_visible(False)
        for lado in ["left", "bottom"]:
            ax.spines[lado].set_color("#c3c2b7")
        ax.tick_params(colors=TEXTO2, labelsize=8.5)
        ax.grid(axis="x" if ax is a1 else "y", color="#ecebe7", lw=0.8)
        ax.set_axisbelow(True)
    fig.suptitle("Prueba nacional (INPC, promedio de 55 ciudades): ¿subieron los complementarios en todo el país?",
                 x=0.01, ha="left", fontsize=11, color=TEXTO)
    fig.tight_layout()
    fig.savefig(C.FIG / "fig_nacional.png", dpi=200)
    plt.close(fig)


def main():
    rng = np.random.default_rng(SEMILLA)
    delta, nombres = cambios_inpc()
    an = anomalias(delta, 2026, REFERENCIA)
    print(f"INPC: {len(an)} genéricos con al menos {MIN_ANIOS} años de referencia")

    tab_gen = an.join(nombres.rename("generico"))
    tab_gen["grupo"] = np.select(
        [tab_gen.index.isin(BIENES), tab_gen.index.isin(list(AMPLIADOS)), tab_gen.index.isin(SERVICIOS),
         tab_gen.index.isin(list(C.PLACEBO))],
        ["Bienes comerciables", "Bienes ampliados", "Servicios", "Placebo"], default="Otro")
    tab_gen = tab_gen.join(delta[2026].rename("cambio_2026_pp"))
    # Lugar entre los genéricos (1 = la caída más rara de 2026; N = el alza más rara).
    tab_gen["lugar_z_de_menor_a_mayor"] = tab_gen.z.rank(method="min").astype(int)
    tab_gen["genericos_en_la_prueba"] = len(tab_gen)
    tab_gen.sort_values("z").round(3).rename_axis("generico_cod").to_csv(C.TAB / "nacional_inpc_genericos.csv")
    print(tab_gen[tab_gen.grupo != "Otro"].sort_values(["grupo", "z"])
          [["generico", "grupo", "anomalia", "desv_est_historica", "z", "lugar_z_de_menor_a_mayor"]]
          .round(2).to_string())
    print(f"\nGenéricos con |z| > 2 en 2026: {(tab_gen.z.abs() > 2).sum()} de {len(tab_gen)} "
          f"({100 * (tab_gen.z.abs() > 2).mean():.0f}%); los 10 más extremos:")
    print(tab_gen.reindex(tab_gen.z.abs().sort_values(ascending=False).index)
          .head(10)[["generico", "grupo", "anomalia", "z"]].round(2).to_string())

    grupos = prueba_grupos(an, rng)
    grupos.round(4).to_csv(C.TAB / "nacional_inpc_grupos.csv", index=False)
    print("\nINPC, anomalía nacional de 2026 por grupo:\n", grupos.round(3).to_string(index=False))

    anios = prueba_anios(delta)
    anios.round(4).to_csv(C.TAB / "nacional_inpc_anios.csv", index=False)
    print("\nINPC, la misma estadística en cada año:\n",
          anios.pivot(index="anio", columns="grupo", values="anomalia_promedio_pct").round(2).to_string())
    print(anios[anios.anio == 2026][["grupo", "lugar_abs_z"]].to_string(index=False))

    prof = prueba_profeco(rng)
    prof.round(4).to_csv(C.TAB / "nacional_profeco.csv", index=False)
    print("\nPROFECO, todas las tiendas: cambio 2026 − cambio 2025 (pp):\n", prof.round(3).to_string(index=False))

    fig_nacional(an, nombres, anios)


if __name__ == "__main__":
    main()
