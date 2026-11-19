"""Dashboard : je joue depuis 2023, je stagne, qu'est-ce que je devrais travailler ?

Une seule page, des filtres en haut, et des figures qui croisent le temps (pendule, heure,
trimestre) avec les phases, les ouvertures et la nature des fautes.
Lancer : uv run python fil_rouge/dashboard.py   (http://127.0.0.1:8051)
"""

import analyses as an
import graphiques as gr
import theme as th
from dash import Dash, Input, Output, callback, dcc, html

app = Dash(__name__, title="Pourquoi je stagne")
server = app.server

CONFIG = {"displayModeBar": False, "responsive": True}


def carte(titre, aide, graph_id, controle=None, large=False):
    return html.Section(
        [
            html.Div(
                [html.H3(titre), html.P(aide, className="aide")]
                + ([html.Div(controle, className="controle")] if controle is not None else []),
                className="carte-tete",
            ),
            dcc.Loading(dcc.Graph(id=graph_id, config=CONFIG), type="dot", color=th.SERIES[0]),
        ],
        className="carte large" if large else "carte",
    )


def filtres():
    df = an.parties()
    annees = sorted(df["annee"].unique())
    cadences = df["cadence"].value_counts().index.tolist()
    return html.Div(
        [
            html.Div(
                [
                    html.Label("Plateforme"),
                    dcc.Checklist(
                        id="filtre-plateforme",
                        options=[
                            {"label": " Chess.com", "value": "chesscom"},
                            {"label": " Lichess", "value": "lichess"},
                        ],
                        value=["chesscom", "lichess"],
                        inline=True,
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Cadence"),
                    dcc.Dropdown(
                        id="filtre-cadence",
                        options=[{"label": "toutes", "value": "toutes"}]
                        + [{"label": c, "value": c} for c in cadences],
                        value="blitz",
                        clearable=False,
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Ma couleur"),
                    dcc.RadioItems(
                        id="filtre-couleur",
                        options=[
                            {"label": " les deux", "value": "toutes"},
                            {"label": " blancs", "value": "white"},
                            {"label": " noirs", "value": "black"},
                        ],
                        value="toutes",
                        inline=True,
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label("Années"),
                    dcc.RangeSlider(
                        id="filtre-annees",
                        min=annees[0],
                        max=annees[-1],
                        step=1,
                        value=[annees[0], annees[-1]],
                        marks={int(a): str(a) for a in annees},
                    ),
                ],
                className="filtre-annees",
            ),
        ],
        className="filtres",
    )


app.layout = html.Main(
    [
        html.Header(
            [
                html.H1("Je joue depuis 2023, je stagne : qu'est-ce que je dois travailler ?"),
                html.P(
                    "3 023 parties Lichess et Chess.com analysées par le moteur. "
                    "Heures en UTC. Chaque chiffre suit les filtres ci-dessous.",
                    className="sous-titre",
                ),
            ]
        ),
        filtres(),
        html.Div(id="kpis", className="kpis"),
        html.Section(
            [html.H2("À travailler en priorité"), html.Ul(id="verdict")], className="verdict"
        ),
        html.H2("La stagnation", className="section"),
        html.Div(
            [
                carte(
                    "Mon Elo médian par mois",
                    "Une ligne par plateforme et cadence : un Elo ne se compare qu'à lui-même.",
                    "fig-elo",
                    large=True,
                ),
                carte(
                    "Gaffes pour 10 coups joués, par phase et par trimestre",
                    "Si je progressais, ces lignes descendraient. Trimestres d'au moins 30 parties.",
                    "fig-gaffes-temps",
                ),
                carte(
                    "Mes parties gagnées puis gâchées",
                    "Parties où j'étais à +3 (gagnant) juste avant une grosse faute, "
                    "selon la phase de cette faute et le résultat final.",
                    "fig-gaches",
                ),
            ],
            className="grille",
        ),
        html.H2("Le temps : pendule, réflexion, heure", className="section"),
        html.Div(
            [
                carte(
                    "La pendule transforme mes fautes en gaffes",
                    "Parmi mes fautes, la part de gaffes selon le temps qu'il me restait, par phase.",
                    "fig-pendule",
                ),
                carte(
                    "Temps par coup : moi contre l'adversaire",
                    "Moyenne par phase. Choisissez les parties à comparer.",
                    "fig-temps-coup",
                    controle=dcc.Dropdown(
                        id="temps-coup-parties",
                        options=[
                            {"label": "toutes les parties", "value": "toutes"},
                            {"label": "mes victoires", "value": "victoire"},
                            {"label": "mes défaites", "value": "défaite"},
                            {"label": "mes défaites au temps", "value": "timeout"},
                        ],
                        value="timeout",
                        clearable=False,
                    ),
                ),
                carte(
                    "Comment finissent mes parties",
                    "Part de chaque fin, pour mes victoires et mes défaites (nulles exclues).",
                    "fig-fins",
                ),
                carte(
                    "Mon score selon l'heure (UTC)",
                    "Heures d'au moins 30 parties. La ligne pointillée est mon score moyen.",
                    "fig-heure",
                ),
            ],
            className="grille",
        ),
        html.H2("Les ouvertures et la nature des fautes", className="section"),
        html.Div(
            [
                carte(
                    "Mon score par famille d'ouvertures, croisé",
                    "Rouge = je perds des points, bleu = j'en gagne. Case vide : moins de 10 "
                    "parties. La pire famille en haut.",
                    "fig-ouvertures",
                    controle=html.Div(
                        [
                            dcc.RadioItems(
                                id="ouvertures-axe",
                                options=[
                                    {"label": " par couleur", "value": "couleur"},
                                    {"label": " par tranche horaire", "value": "tranche"},
                                    {"label": " par année", "value": "annee"},
                                ],
                                value="couleur",
                                inline=True,
                            ),
                            html.Div(
                                [
                                    html.Span("parties minimum par famille"),
                                    dcc.Slider(
                                        id="ouvertures-min",
                                        min=10,
                                        max=100,
                                        step=10,
                                        value=30,
                                        marks={v: str(v) for v in (10, 30, 50, 100)},
                                    ),
                                ],
                                className="curseur",
                            ),
                        ]
                    ),
                    large=True,
                ),
                carte(
                    "Erreurs et gaffes par partie, selon leur nature",
                    "Tactique laissée : mon coup offre une combinaison à l'adversaire. "
                    "Tactique ratée : je ne vois pas la mienne.",
                    "fig-natures",
                    large=True,
                ),
            ],
            className="grille",
        ),
    ],
    className="page",
)

FILTRES = [
    Input("filtre-plateforme", "value"),
    Input("filtre-cadence", "value"),
    Input("filtre-couleur", "value"),
    Input("filtre-annees", "value"),
]


def vue(plateformes, cadence, couleur, annees):
    return an.filtrer(an.parties(), plateformes, cadence, couleur, annees=annees)


def tuile(valeur, libelle, detail=""):
    return html.Div(
        [
            html.Div(valeur, className="kpi-valeur"),
            html.Div(libelle, className="kpi-libelle"),
            html.Div(detail, className="kpi-detail"),
        ],
        className="kpi",
    )


# Un callback par sortie : les figures elles-mêmes sont dans graphiques.py


@callback(Output("kpis", "children"), *FILTRES)
def maj_kpis(*filtres):
    return [tuile(*k) for k in gr.kpis(vue(*filtres))]


@callback(Output("verdict", "children"), *FILTRES)
def maj_verdict(*filtres):
    return [html.Li(x) for x in gr.verdict(vue(*filtres))]


@callback(Output("fig-elo", "figure"), *FILTRES)
def maj_elo(*filtres):
    return gr.fig_elo(vue(*filtres))


@callback(Output("fig-gaffes-temps", "figure"), *FILTRES)
def maj_gaffes_temps(*filtres):
    return gr.fig_gaffes_temps(vue(*filtres))


@callback(Output("fig-gaches", "figure"), *FILTRES)
def maj_gaches(*filtres):
    return gr.fig_gaches(vue(*filtres))


@callback(Output("fig-pendule", "figure"), *FILTRES)
def maj_pendule(*filtres):
    return gr.fig_pendule(vue(*filtres))


@callback(Output("fig-fins", "figure"), *FILTRES)
def maj_fins(*filtres):
    return gr.fig_fins(vue(*filtres))


@callback(Output("fig-heure", "figure"), *FILTRES)
def maj_heure(*filtres):
    return gr.fig_heure(vue(*filtres))


@callback(Output("fig-natures", "figure"), *FILTRES)
def maj_natures(*filtres):
    return gr.fig_natures(vue(*filtres))


@callback(Output("fig-temps-coup", "figure"), *FILTRES, Input("temps-coup-parties", "value"))
def maj_temps_coup(plateformes, cadence, couleur, annees, seulement):
    return gr.fig_temps_coup(vue(plateformes, cadence, couleur, annees), seulement)


@callback(
    Output("fig-ouvertures", "figure"),
    *FILTRES,
    Input("ouvertures-axe", "value"),
    Input("ouvertures-min", "value"),
)
def maj_ouvertures(plateformes, cadence, couleur, annees, axe, min_n):
    return gr.fig_ouvertures(vue(plateformes, cadence, couleur, annees), axe, min_n)


if __name__ == "__main__":
    app.run(debug=False, port=8051)
