"""Paso 5b. Análisis exploratorio (EDA) del panel de PROFECO, en paralelo al del INPC (03b).

Revisa si la base sirve para la métrica y el diseño, y qué agrega frente al INPC:
  1. Cobertura: tiendas, productos y pares tienda×producto por quincena; cuántos pares
     de mayo 2026 se vuelven a observar (continuidad del panel).
  2. Cómo se mueven los precios: rigidez y tamaño de los cambios quincenales.
  3. Composición: qué tipo de tiendas hay en las sedes y en el control.
  4. Precios uniformes: ¿las cadenas cobran lo mismo en todas las ciudades? Si sí, un
     choque de demanda local no debería mover sus precios. Es el mecanismo que explica
     por qué los bienes de tienda no responden.
  5. Volatilidad por ciudad: dónde quedan las sedes (importa para la permutación).
  6. "Placebo por año": la misma comparación en 2025 y 2026.
  7. Brecha sedes − control por quincena, 2025–2026.

Salidas:
  output/tables/profeco_eda_cobertura.csv
  output/tables/profeco_eda_cambios.csv
  output/tables/profeco_eda_composicion.csv
  output/tables/profeco_eda_precios_uniformes.csv
  output/tables/profeco_eda_volatilidad_ciudades.csv
  output/tables/profeco_eda_placebo_anios.csv
  output/tables/profeco_eda_brecha.csv
  output/figures/eda_profeco_cobertura.png
  output/figures/eda_profeco_rigidez.png
  output/figures/eda_profeco_precios_uniformes.png
  output/figures/eda_profeco_brecha.png

Uso:  .venv/bin/python code/05b_profeco_eda.py   (después de 05_profeco_limpieza.py)
"""
import importlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config as C  # noqa: E402

pe = importlib.import_module("06_profeco_estimacion")  # cambios(), efectos_ciudad(), etiquetas
t = C.t_quincena

NARANJA, GRIS, AZUL = "#eb6834", "#8a8984", "#2a78d6"
TEXTO, TEXTO2, EJE, REJILLA = "#0b0b0b", "#52514e", "#c3c2b7", "#ecebe7"
T_REF = t(2026, 5, 2)
PRE_2026 = [t(2026, 1, 1), t(2026, 1, 2), t(2026, 2, 2), t(2026, 5, 1), t(2026, 5, 2)]
MISMO_PRECIO = 1.0  # diferencia máxima (en 100·log ≈ %) para decir "mismo precio"


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
    p = pd.read_parquet(C.CLEAN / "profeco_precios.parquet")
    tiendas = pd.read_csv(C.CLEAN / "profeco_tiendas.csv")
    # El giro viene escrito de varias formas ("Electrodomsticos", "Tiendas Departamentales").
    tiendas["giro"] = tiendas.giro.replace({"Tienda de Electrodomsticos": "Tienda de Electrodomésticos",
                                            "Tiendas Departamentales": "Tienda Departamentales"})
    p = p.merge(tiendas[["tienda_id", "zona", "ciudad", "cadena_comercial", "giro"]], on="tienda_id")
    p["y"] = 100 * np.log(p.precio)
    p["grupo"] = p.grupo.astype(str)
    p["tipo"] = p.tipo.astype(str)
    return p, tiendas


# --- 1. Cobertura --------------------------------------------------------------------------
def cobertura(p):
    ref = set(map(tuple, p[p.t == T_REF][["tienda_id", "producto_id"]].to_numpy()))
    filas = []
    for tt, g in p.groupby("t"):
        pares = set(map(tuple, g[["tienda_id", "producto_id"]].to_numpy()))
        filas.append({
            "t": tt, "quincena": pe.etiqueta_t(tt), "fecha": pe.fecha_t([tt])[0].date(),
            "tiendas_sede": g[g.zona == "Sede"].tienda_id.nunique(),
            "tiendas_control": g[g.zona == "Control"].tienda_id.nunique(),
            "productos": g.producto_id.nunique(), "pares": len(pares),
            "registros": int(g.n_registros.sum()),
            "pct_pares_de_2q_may_2026": 100 * len(pares & ref) / len(ref),
            "pares_especial": int(g.grupo.str.startswith("Especial").sum()),
        })
    return pd.DataFrame(filas)


# --- 2. Cambios quincenales ----------------------------------------------------------------
def cambios(p):
    """Cambio de 100·ln(precio) entre quincenas consecutivas del mismo par tienda×producto."""
    q = p[p.zona.isin(["Sede", "Control"])].sort_values(["tienda_id", "producto_id", "t"])
    mismo = (q.tienda_id.eq(q.tienda_id.shift()) & q.producto_id.eq(q.producto_id.shift())
             & q.t.sub(q.t.shift()).eq(1))
    q = q.assign(dlp=q.y.diff().where(mismo)).dropna(subset=["dlp"])
    tab = q.groupby(["tipo", "grupo"]).dlp.agg(
        cambios_observados="size", cambio_medio="mean", desv_est="std",
        pct_sin_cambio=lambda x: 100 * (x.abs() < 1e-6).mean(),
        pct_cambio_mayor_10=lambda x: 100 * (x.abs() > 10).mean()).reset_index()
    por_zona = q.groupby(["grupo", "zona"]).dlp.agg(lambda x: 100 * (x.abs() < 1e-6).mean()).unstack()
    tab["pct_sin_cambio_sedes"] = tab.grupo.map(por_zona["Sede"])
    tab["pct_sin_cambio_control"] = tab.grupo.map(por_zona["Control"])
    return tab, q


# --- 3. Composición ------------------------------------------------------------------------
def composicion(p):
    q = p[p.zona.isin(["Sede", "Control"]) & p.t.isin(PRE_2026)]
    tiendas = q.drop_duplicates("tienda_id")
    giro = (tiendas.groupby(["zona", "giro"]).size().unstack(0).fillna(0)
            .apply(lambda c: 100 * c / c.sum()).round(1))
    giro["dimension"] = "Tipo de tienda (% de tiendas)"
    top = tiendas.cadena_comercial.value_counts().head(12).index
    cad = (tiendas[tiendas.cadena_comercial.isin(top)].groupby(["zona", "cadena_comercial"]).size()
           .unstack(0).fillna(0))
    cad = (100 * cad / tiendas.groupby("zona").size()).round(1)
    cad["dimension"] = "Cadena (% de tiendas)"
    return pd.concat([giro, cad]).rename_axis("categoria").reset_index()[
        ["dimension", "categoria", "Sede", "Control"]]


# --- 4. Precios uniformes ------------------------------------------------------------------
def precios_uniformes(p):
    """¿Una cadena cobra lo mismo por el mismo producto en ciudades distintas?

    Para cada celda producto × quincena × cadena con tiendas en 2 o más ciudades:
      - "mismo precio": todas sus tiendas cobran lo mismo (diferencia < 1%).
      - descomposición de la varianza del precio entre tiendas, dentro de producto ×
        quincena: qué parte explica la cadena y qué parte la ciudad.
      - prima de las sedes: dentro de la misma cadena, producto y quincena, precio en
        tiendas de sedes − precio en tiendas de control.
    Se usan las quincenas de 2026 previas al Mundial.
    """
    q = p[p.zona.isin(["Sede", "Control"]) & p.t.isin(PRE_2026)].copy()
    celda = ["producto_id", "t", "cadena_comercial"]
    g = q.groupby(celda)
    info = g.agg(ciudades=("ciudad", "nunique"), tiendas=("tienda_id", "nunique"),
                 rango=("y", lambda s: s.max() - s.min()), tipo=("tipo", "first"),
                 grupo=("grupo", "first")).reset_index()
    multi = info[info.ciudades >= 2]

    filas = []
    for tipo, sub in [("Complementarios", multi[multi.tipo == "Complementario"]),
                      ("Placebo", multi[multi.tipo == "Placebo"])]:
        filas.append({"medida": "Celdas cadena×producto×quincena con tiendas en 2+ ciudades",
                      "conjunto": tipo, "valor": len(sub)})
        filas.append({"medida": "% de esas celdas con el mismo precio en todas las tiendas (±1%)",
                      "conjunto": tipo, "valor": 100 * (sub.rango < MISMO_PRECIO).mean()})

    # Descomposición de varianza dentro de producto × quincena.
    for tipo, sub in [("Complementarios", q[q.tipo == "Complementario"]),
                      ("Placebo", q[q.tipo == "Placebo"])]:
        dev = lambda llaves: sub.y - sub.groupby(llaves).y.transform("mean")  # noqa: E731
        sct = (dev(["producto_id", "t"]) ** 2).sum()
        r2_cadena = 1 - (dev(["producto_id", "t", "cadena_comercial"]) ** 2).sum() / sct
        r2_ciudad = 1 - (dev(["producto_id", "t", "ciudad"]) ** 2).sum() / sct
        filas.append({"medida": "% de la varianza del precio entre tiendas que explica la cadena",
                      "conjunto": tipo, "valor": 100 * r2_cadena})
        filas.append({"medida": "% de la varianza del precio entre tiendas que explica la ciudad",
                      "conjunto": tipo, "valor": 100 * r2_ciudad})

    for tipo, sub in [("Complementarios", multi[multi.tipo == "Complementario"]),
                      ("Placebo", multi[multi.tipo == "Placebo"])]:
        filas.append({"medida": "Diferencia mediana entre la tienda más cara y la más barata de la cadena (%)",
                      "conjunto": tipo, "valor": sub.rango.median()})

    # Prima de las sedes dentro de la misma cadena, producto y quincena.
    z = q.groupby(celda + ["zona"]).y.mean().unstack("zona").dropna()
    z = z.join(info.set_index(celda)[["tipo"]])
    z["dif"] = z.Sede - z.Control
    for tipo, sub in [("Complementarios", z[z.tipo == "Complementario"]),
                      ("Placebo", z[z.tipo == "Placebo"])]:
        filas.append({"medida": "Celdas con tiendas de la misma cadena en sedes y en control",
                      "conjunto": tipo, "valor": len(sub)})
        filas.append({"medida": "Prima de las sedes: precio sede − control, misma cadena y producto (%, media)",
                      "conjunto": tipo, "valor": sub.dif.mean()})
        filas.append({"medida": "Prima de las sedes (%, mediana)", "conjunto": tipo, "valor": sub.dif.median()})
        for umbral in (1, 5):
            filas.append({"medida": f"% de celdas donde sede y control difieren menos de {umbral}%",
                          "conjunto": tipo, "valor": 100 * (sub.dif.abs() < umbral).mean()})
    resumen = pd.DataFrame(filas)

    # Por cadena (complementarios).
    por_cadena = (multi[multi.tipo == "Complementario"].groupby("cadena_comercial")
                  .agg(celdas=("rango", "size"), pct_mismo_precio=("rango", lambda s: 100 * (s < MISMO_PRECIO).mean()),
                       rango_mediano=("rango", "median"), ciudades_promedio=("ciudades", "mean"))
                  .query("celdas >= 200").sort_values("pct_mismo_precio").reset_index())
    return resumen, por_cadena, z[z.tipo == "Complementario"].dif


# --- 5. Volatilidad por ciudad -------------------------------------------------------------
def volatilidad_ciudades(q):
    """Desviación estándar del cambio quincenal de cada par, promediada por ciudad (complementarios)."""
    w = q[q.tipo == "Complementario"]
    por_par = w.groupby(["ciudad", "zona", "tienda_id", "producto_id"]).dlp.std().dropna()
    v = (por_par.groupby(["ciudad", "zona"]).agg(desv_est_promedio="mean", pares="size")
         .reset_index().query("pares >= 30"))
    v["percentil"] = 100 * v.desv_est_promedio.rank(pct=True)
    return v.sort_values("desv_est_promedio").reset_index(drop=True)


# --- 6. Placebo por año --------------------------------------------------------------------
def placebo_anios(p):
    """Para 2025 y 2026: cambio may → 1Q jun–1Q jul, sedes − control (mismo estimador que 06)."""
    q = preparar(p)
    filas = []
    for anio in [2025, 2026]:
        antes = [t(anio, 5, 1), t(anio, 5, 2)]
        durante = [t(anio, 6, 1), t(anio, 6, 2), t(anio, 7, 1)]
        d = pe.cambios(q, antes, durante)
        for conjunto, f in pe.CONJUNTOS.items():
            theta = pe.efectos_ciudad(d[f(d)])
            fila, _ = pe.inferir(theta)
            filas.append({"anio": anio, "conjunto": conjunto, "beta": fila["beta"],
                          "p_permutacion": fila["p_permutacion"]})
    return pd.DataFrame(filas)


# --- 7. Brecha sedes − control -------------------------------------------------------------
def preparar(p):
    """Columnas que esperan las funciones de 06_profeco_estimacion.py."""
    q = p[p.zona.isin(["Sede", "Control"])].copy()
    q["sede"] = np.where(q.zona == "Sede", q.ciudad, pd.NA)
    q["cerca"] = q["cerca_estadio"] = q["cerca_fanfest"] = False
    return q


def brecha(p):
    """Brecha sedes − control por quincena, relativa al promedio de 2025.

    Usa el mismo estimador que la estimación (06): cambio de cada par tienda×producto
    entre 2025 y la quincena, menos el cambio del mismo producto en el control; promedio
    por ciudad; promedio simple de las 3 sedes. Así cada par pesa igual dentro de su
    ciudad y la entrada o salida de tiendas no mueve la serie.
    """
    q = preparar(p)
    base = sorted(tt for tt in q.t.unique() if tt < t(2026, 1, 1))
    filas = []
    for conjunto in ["Bebidas, botanas y comida", "Placebo"]:
        for tt in sorted(q.t.unique()):
            d = pe.cambios(q, base, [tt])
            theta = pe.efectos_ciudad(d[pe.CONJUNTOS[conjunto](d)])
            filas.append({"conjunto": conjunto, "t": tt,
                          "brecha": theta.reindex(pe.SEDES).theta.mean()})
    out = pd.DataFrame(filas)
    out["fecha"] = pe.fecha_t(out.t).values
    return out


# --- Figuras ---------------------------------------------------------------------------
def fig_cobertura(cob):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 5.4), sharex=True,
                                 gridspec_kw={"height_ratios": [1.3, 1]})
    x = pd.to_datetime(cob.fecha)
    a1.bar(x, cob.tiendas_control, width=9, color="#c3c2b7", label="Control")
    a1.bar(x, cob.tiendas_sede, width=9, bottom=cob.tiendas_control, color=NARANJA, label="Sedes")
    a1.set_ylabel("Tiendas", fontsize=8.5, color=TEXTO2)
    a1.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=2)
    a1.set_title("Tiendas con precios en cada quincena (sin datos en los huecos)", loc="left",
                 fontsize=10, color=TEXTO)
    a2.plot(x, cob.pct_pares_de_2q_may_2026, color=AZUL, lw=1.2, marker="o", ms=3.5)
    a2.set_ylim(0, 105)
    a2.set_ylabel("%", fontsize=8.5, color=TEXTO2)
    a2.set_title("% de los pares tienda×producto de la 2Q may 2026 que también se observan",
                 loc="left", fontsize=10, color=TEXTO)
    for ax in (a1, a2):
        ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color="#e8e7e3", lw=0, zorder=0)
        estilo(ax)
    ticks = pd.date_range("2025-01-01", "2026-07-01", freq="3MS")
    a2.set_xticks(ticks)
    a2.set_xticklabels([f"{pe.MESES[d.month - 1]} {d:%y}" for d in ticks])
    fig.suptitle("PROFECO: cobertura del panel, 2025–2026", x=0.02, ha="left", fontsize=11.5, color=TEXTO)
    fig.tight_layout()
    fig.savefig(C.FIG / "eda_profeco_cobertura.png", dpi=200)
    plt.close(fig)


def fig_rigidez(c):
    c = c.sort_values(["tipo", "desv_est"], ascending=[False, True]).reset_index(drop=True)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 5.2), sharey=True)
    y = np.arange(len(c))
    colores = np.where(c.tipo == "Placebo", GRIS, NARANJA)
    a1.barh(y, c.pct_sin_cambio, color=colores, height=0.62)
    a2.barh(y, c.desv_est, color=colores, height=0.62)
    a1.set_yticks(y)
    a1.set_yticklabels(c.grupo, fontsize=8.5)
    a1.set_xlabel("% de cambios quincenales iguales a cero", fontsize=9, color=TEXTO2)
    a2.set_xlabel("Desviación estándar del cambio quincenal (%)", fontsize=9, color=TEXTO2)
    for ax in (a1, a2):
        estilo(ax, rejilla="x")
    for i, v in enumerate(c.pct_sin_cambio):
        a1.text(v + 1, i, f"{v:.0f}", va="center", fontsize=7.5, color=TEXTO2)
    for i, v in enumerate(c.desv_est):
        a2.text(v + 0.1, i, f"{v:.1f}", va="center", fontsize=7.5, color=TEXTO2)
    handles = [plt.Rectangle((0, 0), 1, 1, color=k) for k in (NARANJA, GRIS)]
    fig.legend(handles, ["Complementarios", "Placebo"], loc="upper right", ncol=2, frameon=False,
               fontsize=8.5, bbox_to_anchor=(0.98, 0.915))
    fig.suptitle("PROFECO: qué tan seguido cambia el precio del mismo producto en la misma tienda\n"
                 "Quincenas consecutivas, 2025–2026", x=0.02, y=0.98, ha="left", fontsize=11.5, color=TEXTO)
    fig.subplots_adjust(left=0.24, right=0.97, top=0.84, bottom=0.11, wspace=0.08)
    fig.savefig(C.FIG / "eda_profeco_rigidez.png", dpi=200)
    plt.close(fig)


def fig_precios_uniformes(dif, resumen):
    """Histograma de la prima de las sedes dentro de la misma cadena, producto y quincena."""
    r = resumen.set_index(["medida", "conjunto"]).valor
    r2c = r[("% de la varianza del precio entre tiendas que explica la cadena", "Complementarios")]
    r2u = r[("% de la varianza del precio entre tiendas que explica la ciudad", "Complementarios")]
    fig, ax = plt.subplots(figsize=(8, 3.9))
    ax.hist(dif.clip(-20, 20), bins=np.arange(-20, 20.5, 1), color=NARANJA, edgecolor="white", linewidth=0.6)
    ax.axvline(0, color=GRIS, lw=0.8)
    ax.axvline(dif.median(), color=TEXTO, lw=1, ls="--")
    ax.text(dif.median() + 0.4, ax.get_ylim()[1] * 0.92, f"mediana {dif.median():+.1f}%  ·  media {dif.mean():+.1f}%",
            fontsize=8.5, color=TEXTO)
    ax.set_xlabel("Precio en tiendas de sedes − precio en tiendas de control (%, misma cadena, producto y quincena)",
                  fontsize=8.5, color=TEXTO2)
    ax.set_ylabel("Celdas", fontsize=8.5, color=TEXTO2)
    ax.set_title("PROFECO: dentro de la misma cadena, las sedes no son más caras\n"
                 f"Complementarios, ene–may 2026, {len(dif):,} celdas cadena × producto × quincena\n"
                 f"Entre tiendas, la cadena explica {r2c:.0f}% de la dispersión del precio; la ciudad, {r2u:.0f}%",
                 loc="left", fontsize=10, color=TEXTO)
    estilo(ax)
    fig.tight_layout()
    fig.savefig(C.FIG / "eda_profeco_precios_uniformes.png", dpi=200)
    plt.close(fig)


def fig_brecha(gap):
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.axvspan(pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-15"), color="#e8e7e3", lw=0)
    ax.axhline(0, color=GRIS, lw=0.8)
    for conjunto, color, nombre in [("Bebidas, botanas y comida", NARANJA, "Cerveza, refrescos, agua, botanas, licores y pollo"),
                                    ("Placebo", "#52514e", "Placebo")]:
        g = gap[gap.conjunto == conjunto]
        ax.plot(pd.to_datetime(g.fecha), g.brecha, color=color, lw=1.3, marker="o", ms=3, label=nombre)
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    ax.set_ylabel("% vs. promedio de 2025", fontsize=8.5, color=TEXTO2)
    ticks = pd.date_range("2025-01-01", "2026-07-01", freq="3MS")
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{pe.MESES[d.month - 1]} {d:%y}" for d in ticks])
    ax.set_title("PROFECO: precio del mismo producto en la misma tienda, sedes − resto del país\n"
                 "Promedio simple de las 3 sedes, relativo a su promedio de 2025", loc="left", fontsize=10.5, color=TEXTO)
    estilo(ax)
    fig.tight_layout()
    fig.savefig(C.FIG / "eda_profeco_brecha.png", dpi=200)
    plt.close(fig)


def main():
    C.FIG.mkdir(parents=True, exist_ok=True)
    C.TAB.mkdir(parents=True, exist_ok=True)
    p, tiendas = cargar()
    print(f"Panel: {len(p):,} precios tienda×producto×quincena; {p.tienda_id.nunique()} tiendas; "
          f"{p.producto_id.nunique()} productos; {p.t.nunique()} quincenas")
    print(tiendas.zona.value_counts().to_string())

    cob = cobertura(p)
    cob.round(1).to_csv(C.TAB / "profeco_eda_cobertura.csv", index=False)
    print("\nCobertura por quincena:\n", cob.drop(columns=["t", "fecha"]).round(1).to_string(index=False))

    cam, q = cambios(p)
    cam.round(2).to_csv(C.TAB / "profeco_eda_cambios.csv", index=False)
    print("\nCambios quincenales (%):\n", cam.round(2).to_string(index=False))

    comp = composicion(p)
    comp.to_csv(C.TAB / "profeco_eda_composicion.csv", index=False)
    print("\nComposición de tiendas (%):\n", comp.to_string(index=False))

    res, por_cadena, dif = precios_uniformes(p)
    res.round(2).to_csv(C.TAB / "profeco_eda_precios_uniformes.csv", index=False)
    por_cadena.round(1).to_csv(C.TAB / "profeco_eda_precios_uniformes_cadena.csv", index=False)
    print("\nPrecios uniformes:\n", res.round(2).to_string(index=False))
    print(por_cadena.round(1).to_string(index=False))

    vol = volatilidad_ciudades(q)
    vol.round(3).to_csv(C.TAB / "profeco_eda_volatilidad_ciudades.csv", index=False)
    print("\nVolatilidad de las sedes:\n", vol[vol.zona == "Sede"].round(2).to_string(index=False),
          f"\n(de {len(vol)} ciudades con 30+ pares)")

    pla = placebo_anios(p)
    pla.round(4).to_csv(C.TAB / "profeco_eda_placebo_anios.csv", index=False)
    print("\nPlacebo por año:\n", pla.round(3).to_string(index=False))

    gap = brecha(p)
    gap.round(3).to_csv(C.TAB / "profeco_eda_brecha.csv", index=False)
    print("\nBrecha sedes − control vs. 2025 (%):\n",
          gap.pivot(index="t", columns="conjunto", values="brecha").round(2).to_string())
    fig_cobertura(cob)
    fig_rigidez(cam)
    fig_precios_uniformes(dif, res)
    fig_brecha(gap)


if __name__ == "__main__":
    main()
