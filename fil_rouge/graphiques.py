"""Les figures du dashboard, communes à Dash (dashboard.py) et Streamlit (app_streamlit.py).

Chaque fonction reçoit les parties déjà filtrées et renvoie une figure Plotly,
ou du texte simple pour les indicateurs et le verdict. Aucune ne dépend de Dash ou de Streamlit.
"""

import analyses as an
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import theme as th

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
    k = an.kpis(df)
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
    d = an.courbe_elo(df)
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
    d = an.gaffes_dans_le_temps(df)
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
    d = an.avantages_gaches(df)
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
    d = an.pendule(df)
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
    d = an.temps_par_coup(df, seulement).dropna()
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
    d = an.fins_de_partie(df)
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
    d = an.score_par_heure(df)
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
        y=df["score"].mean(),
        line_dash="dot",
        line_color=th.TEXTE_2,
        annotation_text=f"moyenne {df['score'].mean():.2f}",
        annotation_font_color=th.TEXTE_2,
    )
    return fig.update_layout(height=340, xaxis_dtick=1, yaxis_range=[0, 1])


def fig_ouvertures(df, axe="couleur", min_n=30):
    score, n = an.ouvertures_croisees(df, axe, min_n)
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
    d = an.types_fautes(df)
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
