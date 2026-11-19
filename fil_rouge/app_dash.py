"""Exo 4 : la même appli en Dash, avec un drill-down. Environ 25 min.

Question : quelles ouvertures coûtent des points, et dans quelles parties ?
À produire : un curseur (parties minimum) et le graphique des familles ; un clic sur une barre
liste les parties, un clic sur une partie liste les coups jugés mauvais, dans deux AG Grid.
Lancer : uv run python fil_rouge/app_dash.py   (http://127.0.0.1:8050)
"""

from functools import lru_cache

import dash_ag_grid as dag
import graphiques as gr
import plotly.express as px
from dash import Dash, Input, Output, callback, dcc, html, no_update

from data import familles, load_coups, load_data

app = Dash(__name__, title="Mes parties d'échecs")
server = app.server  # Dash tourne sur Flask

JUGEMENTS = {"inaccuracy": "imprécision", "mistake": "erreur", "blunder": "gaffe"}
PHASES = {"opening": "ouverture", "middlegame": "milieu", "endgame": "finale"}
GRILLE = {
    "dashGridOptions": {
        "theme": "themeBalham",
        "animateRows": True,
        "pagination": True,
        "paginationPageSize": 10,
    },
    "columnSize": "responsiveSizeToFit",
    "defaultColDef": {"filter": True, "sortable": True},
}


# Les fichiers ne changent pas : lus une fois par processus, à la première demande
@lru_cache(maxsize=1)
def parties():
    return load_data()


@lru_cache(maxsize=1)
def coups():
    return load_coups()


def lignes(df):
    """rowData d'AG Grid : une liste de dicts, NaN remplacé par une case vide (None en JSON)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


app.layout = html.Div(
    [
        html.H2("Quelles ouvertures me coûtent des points ? Cliquez une barre"),
        # 1. le curseur et le graphique des familles
        html.Label("Parties minimum par famille", htmlFor="n-min"),
        dcc.Slider(30, 60, 10, value=30, id="n-min"),
        dcc.Loading(dcc.Graph(id="familles")),
        # 2. les parties de la famille cliquée, une ligne sélectionnable d'un clic
        html.H3(id="titre-parties", children="Cliquez une barre pour voir ses parties"),
        dag.AgGrid(
            id="parties",
            rowData=[],
            columnDefs=[
                {"field": "partie_id", "headerName": "partie"},
                {"field": "date_jeu", "headerName": "date (UTC)"},
                {"field": "cadence"},
                {"field": "couleur"},
                {"field": "resultat", "headerName": "résultat"},
                {"field": "ecart_elo", "headerName": "écart d'Elo"},
                {"field": "gaffes_joueur", "headerName": "gaffes"},
                {"field": "ouverture_nom", "headerName": "ouverture", "flex": 3},
            ],
            **{
                **GRILLE,
                "dashGridOptions": {
                    **GRILLE["dashGridOptions"],
                    "rowSelection": {"mode": "singleRow", "enableClickSelection": True},
                },
            },
        ),
        # 3. mes coups jugés mauvais dans la partie choisie
        html.H3(id="titre-coups", children="Cliquez une partie pour voir mes coups jugés mauvais"),
        dag.AgGrid(
            id="coups",
            rowData=[],
            columnDefs=[
                {"field": "numero_coup", "headerName": "coup n°"},
                {"field": "coup", "headerName": "j'ai joué"},
                {"field": "meilleur_coup", "headerName": "meilleur coup"},
                {"field": "jugement"},
                {"field": "phase"},
                {"field": "variation_eval_cp", "headerName": "perte (cp)"},
                {"field": "temps_restant_s", "headerName": "pendule (s)"},
                {"field": "sous_type", "headerName": "type"},
            ],
            **GRILLE,
        ),
        # En plus de l'exo : l'échiquier des fautes, au niveau du drill-down où l'on est
        html.H3(id="titre-echiquier", children="Où arrivent mes coups jugés mauvais"),
        html.P(
            "Toutes mes parties tant que rien n'est cliqué, puis la famille cliquée, puis la "
            "partie choisie. Chaque échiquier est vu de mon côté. Survolez une case.",
            className="aide",
        ),
        dcc.RadioItems(
            id="echiquier-mesure",
            options=[
                {"label": " nombre de fautes", "value": "fautes"},
                {"label": " part de gaffes", "value": "part_gaffes"},
                {"label": " perte médiane (cp)", "value": "perte"},
            ],
            value="fautes",
            inline=True,
        ),
        dcc.Loading(dcc.Graph(id="echiquier", config={"displayModeBar": False})),
    ],
    className="page",
)


# 4. curseur -> graphique des familles, la pire en haut
@callback(Output("familles", "figure"), Input("n-min", "value"))
def maj_familles(n_min):
    fam = familles(parties(), n_min)
    fig = px.bar(
        fam,
        x="score",
        y="famille",
        orientation="h",
        hover_data={"n": True, "gaffes": ":.2f", "score": ":.2f"},
        labels={"score": "score moyen (1 = victoire)", "famille": "", "n": "parties"},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=fam["famille"][::-1].tolist())
    fig.add_vline(x=parties()["score"].mean(), line_dash="dash", annotation_text="moyenne")
    return fig.update_layout(height=max(360, 26 * len(fam) + 80), margin={"t": 30})


# 5. clic sur une barre -> les parties de cette famille
@callback(
    Output("parties", "rowData"),
    Output("titre-parties", "children"),
    Input("familles", "clickData"),
    prevent_initial_call=True,
)
def maj_parties(click):
    if not click:
        return no_update, no_update
    famille = click["points"][0]["y"]
    df = parties()
    vue = df[df["ouverture_famille"] == famille].sort_values("date_jeu", ascending=False)
    vue = vue.assign(date_jeu=vue["date_jeu"].dt.strftime("%Y-%m-%d %H:%M"))
    colonnes = ["partie_id", "date_jeu", "cadence", "couleur", "resultat", "ecart_elo"]
    titre = f"{famille} : {100 * vue['score'].mean():.1f} % de score en {len(vue)} parties"
    return lignes(vue[colonnes + ["gaffes_joueur", "ouverture_nom"]]), titre


# 6. clic sur une partie -> mes coups jugés mauvais dans cette partie
@callback(
    Output("coups", "rowData"),
    Output("titre-coups", "children"),
    Input("parties", "selectedRows"),
    prevent_initial_call=True,
)
def maj_coups(selection):
    if not selection:
        return [], "Cliquez une partie pour voir mes coups jugés mauvais"
    partie = selection[0]
    c = coups()
    vue = c[c["partie_id"] == partie["partie_id"]].sort_values("ply")
    vue = vue.assign(
        jugement=vue["jugement"].map(JUGEMENTS),
        phase=vue["phase"].map(PHASES),
        sous_type=vue["sous_type"].fillna(vue["categorie"]),
    )
    colonnes = ["numero_coup", "coup", "meilleur_coup", "jugement", "phase"]
    titre = (
        f"{partie['partie_id']} ({partie['resultat']}, {partie['couleur']}) : "
        f"{len(vue)} coups jugés mauvais"
    )
    return lignes(vue[colonnes + ["variation_eval_cp", "temps_restant_s", "sous_type"]]), titre


# 7. (en plus) l'échiquier suit le drill-down : toutes les parties, la famille, puis la partie
@callback(
    Output("echiquier", "figure"),
    Output("titre-echiquier", "children"),
    Input("familles", "clickData"),
    Input("parties", "selectedRows"),
    Input("echiquier-mesure", "value"),
)
def maj_echiquier(click, selection, mesure):
    df = parties()
    titre = "Où arrivent mes coups jugés mauvais : toutes mes parties"
    if selection:
        partie = selection[0]["partie_id"]
        df = df[df["partie_id"] == partie]
        titre = f"Où arrivent mes coups jugés mauvais : la partie {partie}"
    elif click:
        famille = click["points"][0]["y"]
        df = df[df["ouverture_famille"] == famille]
        titre = f"Où arrivent mes coups jugés mauvais : {famille} ({len(df)} parties)"
    # Sur une seule partie, chaque case n'a qu'une ou deux fautes : pas de seuil minimum
    min_case = 1 if selection else 15
    return gr.fig_echiquier(df, mesure, min_case=min_case), titre


if __name__ == "__main__":
    # debug=True : bouton « Callbacks » en bas à droite, le graphe des callbacks
    app.run(debug=True, port=8050)
