"""Les figures du dashboard, communes à Dash, à app_streamlit.py (CSV) et à app_api.py (API).

Deux formes pour chaque figure :
- fig_x(parties filtrées) calcule l'agrégat avec analyses.py, puis le dessine ;
- fig_x_depuis(agrégat) dessine seulement : app_api.py lui passe la réponse de l'API.
Aucune ne dépend de Dash ou de Streamlit.
"""

import analyses as an
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import theme as th
from plotly.subplots import make_subplots

SERIES_ELO = {
    "chesscom · blitz": th.SERIES[0],
    "lichess · blitz": th.SERIES[1],
    "chesscom · bullet": th.SERIES[2],
    "chesscom · rapid": th.SERIES[3],
    "lichess · rapid": th.SERIES[4],
    "lichess · bullet": th.SERIES[5],
}
NOM_PHASE = {"ouverture": "L'ouverture", "milieu": "Le milieu de partie", "finale": "La finale"}
EN_PHASE = {"ouverture": "en ouverture", "milieu": "au milieu de partie", "finale": "en finale"}
NATURES = {
    "tactique laissée à l'adversaire": th.SERIES[6],
    "tactique ratée": th.SERIES[3],
    "stratégique": th.SERIES[4],
}


def vide(message="Aucune partie pour ces filtres"):
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font={"color": th.TEXTE_3, "size": 14})
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig.update_layout(height=320)


def pct(x, decimales=0):
    return "–" if x is None else f"{100 * x:.{decimales}f} %"


# ---------------------------------------------------------------- indicateurs et verdict


def kpis(df) -> list[tuple[str, str, str]]:
    """Les indicateurs du haut : (valeur, libellé, détail)."""
    return kpis_depuis(an.kpis(df))


def kpis_depuis(k: dict) -> list[tuple[str, str, str]]:
    """Les mêmes indicateurs, à partir du dict de analyses.kpis (ou de GET /indicateurs)."""
    if not k:
        return [("0", "parties", "")]
    elo = k["elo"]
    elo_txt, elo_detail = "–", ""
    if elo:
        elo_txt = f"{elo['actuel']:.0f}"
        variation = "" if elo["delta"] is None else f", {elo['delta']:+.0f} en 6 mois"
        elo_detail = f"{elo['serie']}{variation}"
    return [
        (f"{k['parties']:,}".replace(",", " "), "parties", ""),
        (f"{k['score']:.2f}", "score moyen", "1 = victoire, 0,5 = nulle"),
        (elo_txt, "Elo médian, 6 derniers mois", elo_detail),
        (f"{k['gaffes']:.1f}", "gaffes par partie", ""),
        (pct(k["temps"]), "de mes défaites au temps", ""),
        (
            pct(k["gaches"]),
            "des positions gagnantes non gagnées",
            f"sur {k['n_gagnantes']} parties à +3",
        ),
    ]


def verdict(df) -> list[str]:
    """Les conclusions écrites, recalculées pour les parties filtrées."""
    if df.empty:
        return ["Aucune partie pour ces filtres."]
    points = []

    g = an.gaffes_dans_le_temps(df, min_parties=1)
    if not g.empty:
        par_phase = g.groupby("phase")[["gaffes", "demi"]].sum()
        taux = (20 * par_phase["gaffes"] / par_phase["demi"]).sort_values(ascending=False)
        pire = taux.index[0]
        texte = (
            f"{NOM_PHASE[pire]} : {taux.iloc[0]:.2f} gaffe pour 10 coups, contre "
            f"{taux.iloc[-1]:.2f} {EN_PHASE[taux.index[-1]]}."
        )
        # Tendance : la dernière année de parties contre l'année d'avant, même phase
        d = an.de(an.phases(), df).merge(df[["partie_id", "date_jeu"]], on="partie_id")
        d = d[d["phase"] == pire]
        fin = d["date_jeu"].max()
        recent = d[d["date_jeu"] > fin - pd.DateOffset(years=1)]
        avant = d[d["date_jeu"].between(fin - pd.DateOffset(years=2), fin - pd.DateOffset(years=1))]
        if len(recent) >= 30 and len(avant) >= 30:
            r = 20 * recent["gaffes_joueur"].sum() / recent["nb_coups"].sum()
            a = 20 * avant["gaffes_joueur"].sum() / avant["nb_coups"].sum()
            sens = "baisse" if r < 0.9 * a else ("monte" if r > 1.1 * a else "ne baisse pas")
            texte += f" Sur la dernière année ce taux {sens} ({a:.2f} → {r:.2f})."
        points.append(texte)

    k = an.kpis(df)
    if k.get("gaches") is not None and k["n_gagnantes"] >= 20:
        points.append(
            f"La conversion : sur {k['n_gagnantes']} parties où j'étais à +3, "
            f"{pct(k['gaches'])} ne sont pas gagnées. Travailler les finales gagnantes "
            "et la vérification « qu'est-ce qu'il menace ? » avant chaque coup."
        )

    nat = an.types_fautes(df)
    if not nat.empty:
        tot = nat.groupby("nature")["fautes"].sum()
        laissee = tot.get("tactique laissée à l'adversaire", 0) / tot.sum()
        points.append(
            f"Les tactiques que je laisse : {pct(laissee)} de mes erreurs et gaffes offrent "
            "une combinaison à l'adversaire. Des problèmes tactiques en défense, pas en attaque."
        )

    t = an.temps_par_coup(df, "timeout")
    if not t.empty:
        ouv = t[t["phase"] == "ouverture"].set_index("joueur")["secondes"]
        if {"moi", "adversaire"} <= set(ouv.index) and ouv["moi"] > ouv["adversaire"]:
            points.append(
                f"Le temps en ouverture : dans mes défaites au temps, je joue l'ouverture à "
                f"{ouv['moi']:.1f} s par coup contre {ouv['adversaire']:.1f} s pour "
                "l'adversaire. Mieux connaître mon répertoire libère du temps pour le milieu."
            )

    score, n = an.ouvertures_croisees(df, "couleur")
    if len(score):
        pires = ", ".join(
            f"{f} ({s:.2f} sur {n.loc[f, 'toutes']})" for f, s in score["toutes"].head(3).items()
        )
        points.append(f"Les ouvertures qui coûtent des points : {pires}.")

    p = an.pendule(df)
    if not p.empty:
        court = p[p["pendule"].isin(["< 10 s", "10-20 s"])]
        long = p[p["pendule"] == "> 2 min"]
        if len(court) and len(long):
            points.append(
                f"La pendule : sous 20 secondes, {pct(court['part'].mean())} de mes fautes sont "
                f"des gaffes, contre {pct(long['part'].mean())} avec plus de 2 minutes."
            )
    return points


# ---------------------------------------------------------------- figures


def fig_elo(df):
    return fig_elo_depuis(an.courbe_elo(df))


def fig_elo_depuis(d):
    if d.empty:
        return vide()
    fig = px.line(
        d,
        x="mois",
        y="elo",
        color="serie",
        markers=True,
        color_discrete_map=SERIES_ELO,
        custom_data=["parties"],
        labels={"mois": "", "elo": "Elo médian", "serie": ""},
    )
    fig.update_traces(
        line_width=2,
        marker_size=8,
        hovertemplate="%{x|%B %Y}<br>Elo médian %{y:.0f}<br>%{customdata[0]} parties<extra></extra>",
    )
    return fig.update_layout(height=340, hovermode="closest")


def fig_gaffes_temps(df):
    return fig_gaffes_temps_depuis(an.gaffes_dans_le_temps(df))


def fig_gaffes_temps_depuis(d):
    if d.empty:
        return vide("Pas assez de parties par trimestre")
    fig = px.line(
        d,
        x="trimestre",
        y="taux",
        color="phase",
        markers=True,
        category_orders={"phase": an.ORDRE_PHASES},
        color_discrete_map=th.PHASES,
        custom_data=["parties", "gaffes"],
        labels={"trimestre": "", "taux": "gaffes pour 10 coups", "phase": ""},
    )
    fig.update_traces(
        line_width=2,
        marker_size=8,
        hovertemplate="%{x|%Y T%q}<br>%{y:.2f} gaffe pour 10 coups"
        "<br>%{customdata[1]} gaffes, %{customdata[0]} parties<extra></extra>",
    )
    return fig.update_layout(height=340, yaxis_rangemode="tozero")


def fig_gaches(df):
    return fig_gaches_depuis(an.avantages_gaches(df))


def fig_gaches_depuis(d):
    if d.empty:
        return vide("Aucune position gagnante gâchée")
    fig = px.bar(
        d,
        x="phase",
        y="parties",
        color="resultat",
        category_orders={"phase": an.ORDRE_PHASES, "resultat": ["défaite", "nulle", "victoire"]},
        color_discrete_map=th.RESULTATS,
        labels={"phase": "phase de la grosse faute", "parties": "parties", "resultat": ""},
    )
    fig.update_traces(
        marker_line_color=th.SURFACE,
        marker_line_width=2,
        hovertemplate="%{x}<br>%{y} parties<extra>%{fullData.name}</extra>",
    )
    return fig.update_layout(height=340, barmode="stack")


def fig_pendule(df):
    return fig_pendule_depuis(an.pendule(df))


def fig_pendule_depuis(d):
    if d.empty:
        return vide("Pas de pendule enregistrée pour ces parties")
    d = d.assign(part=100 * d["part"])
    fig = px.line(
        d,
        x="pendule",
        y="part",
        color="phase",
        markers=True,
        category_orders={"phase": an.ORDRE_PHASES, "pendule": an.PENDULE_NOMS},
        color_discrete_map=th.PHASES,
        custom_data=["fautes"],
        labels={"pendule": "temps restant après le coup", "part": "% de gaffes", "phase": ""},
    )
    fig.update_traces(
        line_width=2,
        marker_size=8,
        hovertemplate="%{x} restant<br>%{y:.0f} % de gaffes"
        "<br>sur %{customdata[0]} fautes<extra></extra>",
    )
    return fig.update_layout(height=340, yaxis_ticksuffix=" %", yaxis_rangemode="tozero")


def fig_temps_coup(df, seulement="toutes"):
    return fig_temps_coup_depuis(an.temps_par_coup(df, seulement))


def fig_temps_coup_depuis(d):
    d = d.dropna()
    if d.empty:
        return vide("Pas de temps enregistré pour ces parties")
    fig = px.bar(
        d,
        x="phase",
        y="secondes",
        color="joueur",
        barmode="group",
        text="secondes",
        color_discrete_map=th.MOI_ADV,
        custom_data=["parties"],
        labels={"phase": "", "secondes": "secondes par coup", "joueur": ""},
    )
    fig.update_traces(
        texttemplate="%{y:.1f} s",
        textposition="outside",
        marker_line_color=th.SURFACE,
        marker_line_width=2,
        hovertemplate="%{x}<br>%{y:.1f} s par coup<br>%{customdata[0]} parties"
        "<extra>%{fullData.name}</extra>",
    )
    return fig.update_layout(height=340, uniformtext_minsize=10)


def fig_fins(df):
    return fig_fins_depuis(an.fins_de_partie(df))


def fig_fins_depuis(d):
    if d.empty:
        return vide()
    d = d.assign(part=100 * d["part"])
    fig = px.bar(
        d,
        y="fin",
        x="part",
        color="resultat",
        orientation="h",
        barmode="group",
        color_discrete_map=th.RESULTATS,
        category_orders={"resultat": ["défaite", "victoire"]},
        custom_data=["parties"],
        labels={"fin": "", "part": "% des parties", "resultat": ""},
    )
    fig.update_traces(
        marker_line_color=th.SURFACE,
        marker_line_width=2,
        hovertemplate="%{y}<br>%{x:.0f} %<br>%{customdata[0]} parties"
        "<extra>%{fullData.name}</extra>",
    )
    return fig.update_layout(
        height=340, xaxis_ticksuffix=" %", yaxis_categoryorder="total ascending"
    )


def fig_heure(df):
    return fig_heure_depuis(an.score_par_heure(df), df["score"].mean())


def fig_heure_depuis(d, moyenne: float):
    if d.empty:
        return vide("Aucune heure avec 30 parties")
    fig = px.bar(
        d,
        x="heure",
        y="score",
        custom_data=["parties"],
        labels={"heure": "heure de début (UTC)", "score": "score moyen"},
    )
    fig.update_traces(
        marker_color=th.SERIES[0],
        hovertemplate="%{x} h<br>score %{y:.2f}<br>%{customdata[0]} parties<extra></extra>",
    )
    fig.add_hline(
        y=moyenne,
        line_dash="dot",
        line_color=th.TEXTE_2,
        annotation_text=f"moyenne {moyenne:.2f}",
        annotation_font_color=th.TEXTE_2,
    )
    return fig.update_layout(height=340, xaxis_dtick=1, yaxis_range=[0, 1])


def fig_ouvertures(df, axe="couleur", min_n=30):
    score, n = an.ouvertures_croisees(df, axe, min_n)
    return fig_ouvertures_depuis(score, n, min_n)


def fig_ouvertures_depuis(score: pd.DataFrame, n: pd.DataFrame, min_n: int = 30):
    """score et n : familles en lignes, colonnes croisées (« toutes » d'abord)."""
    if score.empty:
        return vide(f"Aucune famille d'au moins {min_n} parties")
    cols = [str(c) for c in score.columns]
    texte = [
        [
            "" if pd.isna(s) else f"{s:.2f}<br><span style='font-size:10px'>{k}</span>"
            for s, k in zip(score.loc[f], n.loc[f])
        ]
        for f in score.index
    ]
    fig = go.Figure(
        go.Heatmap(
            z=score.values,
            x=cols,
            y=score.index,
            text=texte,
            texttemplate="%{text}",
            customdata=n.values,
            colorscale=th.DIVERGENTE,
            zmin=0.2,
            zmax=0.8,
            zmid=0.5,
            xgap=2,
            ygap=2,
            hoverongaps=False,
            hovertemplate="%{y}<br>%{x}<br>score %{z:.2f} sur %{customdata} parties<extra></extra>",
            colorbar={"title": "score", "thickness": 10, "outlinewidth": 0, "len": 0.6},
        )
    )
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(side="top", showgrid=False)
    return fig.update_layout(height=140 + 34 * len(score), margin={"t": 40})


def fig_natures(df):
    return fig_natures_depuis(an.types_fautes(df))


def fig_natures_depuis(d):
    if d.empty:
        return vide()
    fig = px.bar(
        d,
        y="phase",
        x="par_partie",
        color="nature",
        orientation="h",
        category_orders={"phase": an.ORDRE_PHASES, "nature": list(NATURES)},
        color_discrete_map=NATURES,
        custom_data=["fautes"],
        labels={"phase": "", "par_partie": "erreurs et gaffes par partie", "nature": ""},
    )
    fig.update_traces(
        marker_line_color=th.SURFACE,
        marker_line_width=2,
        hovertemplate="%{y}<br>%{x:.2f} par partie<br>%{customdata[0]} fautes"
        "<extra>%{fullData.name}</extra>",
    )
    return fig.update_layout(height=300, barmode="stack", yaxis_autorange="reversed")


MESURES_ECHIQUIER = {
    "fautes": ("fautes", "{:.0f}", "nombre de fautes"),
    "part_gaffes": ("part de gaffes", "{:.0%}", "part de gaffes parmi les fautes"),
    "perte": ("perte médiane", "{:.0f}", "perte médiane (cp)"),
}


def _plateau(cases: pd.DataFrame, couleur: str, mesure: str, min_case: int):
    """Une grille 8 x 8 vue de mon côté : rangée 1 en bas avec les blancs, rangée 8 avec les noirs."""
    colonnes = an.COLONNES_ECHIQUIER if couleur == "white" else an.COLONNES_ECHIQUIER[::-1]
    rangees = range(1, 9) if couleur == "white" else range(8, 0, -1)
    par_case = cases[cases["couleur"] == couleur].set_index("case")
    z, texte, info = [], [], []
    for r in rangees:
        ligne_z, ligne_t, ligne_i = [], [], []
        for c in colonnes:
            case = f"{c}{r}"
            if case in par_case.index:
                x = par_case.loc[case]
                assez = mesure == "fautes" or x["fautes"] >= min_case
                v = x[mesure] if assez else None
                ligne_i.append(
                    [case, int(x["fautes"]), x["part_gaffes"], x["perte"], x["piece_top"]]
                )
            else:
                v = None
                ligne_i.append([case, 0, None, None, "-"])
            fmt = MESURES_ECHIQUIER[mesure][1]
            ligne_z.append(v)
            ligne_t.append("" if v is None else fmt.format(v))
        z.append(ligne_z)
        texte.append(ligne_t)
        info.append(ligne_i)
    return list(colonnes), list(rangees), z, texte, info


def fig_echiquier(df, mesure="fautes", min_case=15, **filtres):
    """Deux échiquiers, avec les blancs et avec les noirs : où arrivent mes coups jugés mauvais.

    filtres : ceux de analyses.coups_filtres (pieces, gravites, phases, familles, resultats, pendules).
    """
    return fig_echiquier_depuis(an.fautes_par_case(df, **filtres), mesure, min_case)


def fig_echiquier_depuis(cases: pd.DataFrame, mesure="fautes", min_case=15):
    """cases : le tableau de analyses.fautes_par_case (ou de GET /echiquier)."""
    if cases.empty:
        return vide("Aucune faute pour ces filtres")
    titre_barre = MESURES_ECHIQUIER[mesure][2]
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["avec les blancs", "avec les noirs"],
        horizontal_spacing=0.08,
    )
    zmax = None
    for i, couleur in enumerate(["white", "black"], start=1):
        colonnes, rangees, z, texte, info = _plateau(cases, couleur, mesure, min_case)
        fig.add_trace(
            go.Heatmap(
                z=z,
                x=list(range(8)),
                y=list(range(8)),
                text=texte,
                texttemplate="%{text}",
                textfont={"size": 12},
                customdata=info,
                coloraxis="coloraxis",
                xgap=1,
                ygap=1,
                hoverongaps=False,
                hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]} fautes"
                "<br>part de gaffes %{customdata[2]:.0%}"
                "<br>perte médiane %{customdata[3]:.0f} cp"
                "<br>pièce la plus fautive : %{customdata[4]}<extra></extra>",
            ),
            row=1,
            col=i,
        )
        valeurs = [v for ligne in z for v in ligne if v is not None]
        zmax = max([zmax or 0, *valeurs]) if valeurs else zmax
        axe = "" if i == 1 else str(i)
        fig.update_xaxes(
            tickvals=list(range(8)),
            ticktext=colonnes,
            showgrid=False,
            range=[-0.5, 7.5],
            constrain="domain",
            row=1,
            col=i,
        )
        fig.update_yaxes(
            tickvals=list(range(8)),
            ticktext=[str(r) for r in rangees],
            showgrid=False,
            range=[-0.5, 7.5],
            scaleanchor=f"x{axe}",
            constrain="domain",
            row=1,
            col=i,
        )
        # Les cases noires de l'échiquier : a1 est noire, la couleur alterne d'une case à l'autre
        for ix, c in enumerate(colonnes):
            for iy, r in enumerate(rangees):
                if (an.COLONNES_ECHIQUIER.index(c) + r) % 2 == 1:
                    continue
                fig.add_shape(
                    type="rect",
                    x0=ix - 0.5,
                    x1=ix + 0.5,
                    y0=iy - 0.5,
                    y1=iy + 0.5,
                    fillcolor=th.CASE_FONCEE,
                    line_width=0,
                    layer="above",
                    xref=f"x{axe}",
                    yref=f"y{axe}",
                )
    fig.update_layout(
        height=560,
        coloraxis={
            "colorscale": th.SEQUENTIELLE,
            "cmin": 0,
            "cmax": zmax,
            "colorbar": {
                "title": titre_barre,
                "thickness": 10,
                "outlinewidth": 0,
                "len": 0.7,
                "tickformat": ".0%" if mesure == "part_gaffes" else "",
            },
        },
        margin={"t": 40, "l": 8, "r": 8, "b": 8},
    )
    return fig


def fig_pieces(df, **filtres):
    """Erreurs et gaffes par partie pour chaque pièce, la plus fautive en haut."""
    return fig_pieces_depuis(an.fautes_par_piece(df, **filtres))


def fig_pieces_depuis(d: pd.DataFrame):
    """d : le tableau de analyses.fautes_par_piece (ou de GET /pieces)."""
    if d.empty or d["fautes"].sum() == 0:
        return vide("Aucune erreur ni gaffe pour ces filtres")
    n = max(int(d["parties"].iloc[0]), 1)
    long = d.melt(
        id_vars=["piece", "fautes", "part_gaffes", "perte"],
        value_vars=["erreurs", "gaffes"],
        var_name="gravite",
        value_name="nombre",
    ).assign(par_partie=lambda x: x["nombre"] / n)
    long["gravite"] = long["gravite"].map({"erreurs": "erreur", "gaffes": "gaffe"})
    fig = px.bar(
        long,
        y="piece",
        x="par_partie",
        color="gravite",
        orientation="h",
        category_orders={"piece": d["piece"].tolist(), "gravite": ["gaffe", "erreur"]},
        color_discrete_map=th.GRAVITES,
        custom_data=["nombre", "fautes", "part_gaffes", "perte"],
        labels={"piece": "", "par_partie": "erreurs et gaffes par partie", "gravite": ""},
    )
    fig.update_traces(
        marker_line_color=th.SURFACE,
        marker_line_width=2,
        hovertemplate="<b>%{y}</b><br>%{x:.2f} %{fullData.name} par partie (%{customdata[0]})"
        "<br>%{customdata[1]} erreurs et gaffes, dont %{customdata[2]:.0%} de gaffes"
        "<br>perte médiane %{customdata[3]:.0f} cp<extra></extra>",
    )
    # La part de gaffes au bout de chaque barre : une pièce peut être peu fautive mais grave
    for _, ligne in d[d["fautes"] > 0].iterrows():
        fig.add_annotation(
            x=ligne["fautes"] / n,
            y=ligne["piece"],
            text=f"{ligne['part_gaffes']:.0%} de gaffes",
            showarrow=False,
            xanchor="left",
            xshift=6,
            font={"size": 11, "color": th.TEXTE_2},
        )
    fig.update_xaxes(range=[0, d["fautes"].max() / n * 1.3])
    return fig.update_layout(height=340, barmode="stack", clickmode="event+select")
