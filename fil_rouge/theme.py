"""Couleurs, polices et gabarit Plotly partagés par le dashboard.

Palette catégorielle dans un ordre fixe (validé pour le daltonisme sur les paires voisines),
une couleur suit toujours la même entité : une phase garde sa couleur quel que soit le filtre.
"""

import plotly.graph_objects as go
import plotly.io as pio

SURFACE = "#fcfcfb"
PAGE = "#f4f3f0"
TEXTE = "#0b0b0b"
TEXTE_2 = "#52514e"
TEXTE_3 = "#8a8983"
GRILLE = "#e6e5e1"
NEUTRE = "#c3c2b7"

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]

PHASES = {"ouverture": SERIES[0], "milieu": SERIES[1], "finale": SERIES[2]}
RESULTATS = {"victoire": "#2a78d6", "nulle": NEUTRE, "défaite": "#e34948"}
GRAVITES = {"erreur": "#ec9a96", "gaffe": "#c13a3a"}  # du clair au foncé : la gravité
MOI_ADV = {"moi": SERIES[0], "adversaire": NEUTRE}

# Divergente rouge <-> bleu, gris au milieu (0,5 = autant de points gagnés que perdus)
DIVERGENTE = [
    [0, "#c13a3a"],
    [0.25, "#ec9a96"],
    [0.5, "#f0efec"],
    [0.75, "#86b6ef"],
    [1, "#1c5cab"],
]

# Séquentielle bleue, du clair (peu) au foncé (beaucoup) : l'intensité d'une case de l'échiquier
SEQUENTIELLE = [
    [0, "#cde2fb"],
    [0.25, "#86b6ef"],
    [0.5, "#3987e5"],
    [0.75, "#1c5cab"],
    [1, "#0d366b"],
]
CASE_FONCEE = "rgba(11, 11, 11, 0.14)"  # voile posé sur les cases noires de l'échiquier

POLICE = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"

pio.templates["echecs"] = go.layout.Template(
    layout={
        "font": {"family": POLICE, "size": 13, "color": TEXTE_2},
        "title": {"font": {"size": 15, "color": TEXTE}, "x": 0, "xanchor": "left", "y": 0.97},
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
        "colorway": SERIES,
        "margin": {"l": 8, "r": 16, "t": 56, "b": 8},
        "xaxis": {"gridcolor": GRILLE, "linecolor": GRILLE, "zeroline": False, "automargin": True},
        "yaxis": {"gridcolor": GRILLE, "linecolor": GRILLE, "zeroline": False, "automargin": True},
        "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.0, "x": 0, "title_text": ""},
        "hoverlabel": {"bgcolor": "white", "bordercolor": GRILLE, "font": {"color": TEXTE}},
        "bargap": 0.25,
    }
)
pio.templates.default = "plotly_white+echecs"
