"""Exo 1 : trois figures. Environ 25 min.

Question : où ce joueur perd-il des points ?
À produire : trois figures Plotly dont le titre dit ce qu'elles montrent.
Lancer : uv run python fil_rouge/01_figures.py
"""

import plotly.express as px

from data import familles, load_coups, load_data

df, coups = load_data(), load_coups()
print(df.shape, coups.shape)

# 1. Le score par famille d'ouvertures, la pire en haut (px.bar, familles(df))
fam = familles(df)
fig1 = px.bar(
    fam,
    x="score",
    y="famille",
    orientation="h",
    hover_data=["n", "gaffes"],
    title="Score moyen par famille d'ouvertures (≥ 30 parties) : la Hongroise et l'Anglaise coûtent le plus",
    labels={"score": "score moyen (1 = victoire)", "famille": ""},
)
fig1.update_yaxes(categoryorder="array", categoryarray=fam["famille"][::-1].tolist())
fig1.add_vline(x=df["score"].mean(), line_dash="dash", annotation_text="moyenne")
fig1.show()

# 2. La phase de la partie où tombent ses gaffes : ouverture, milieu, finale (coups)
noms = {"opening": "ouverture", "middlegame": "milieu", "endgame": "finale"}
gaffes = (
    coups[coups["jugement"] == "blunder"]["phase"]
    .map(noms)
    .value_counts()
    .reindex(list(noms.values()))
    .rename_axis("phase")
    .reset_index(name="gaffes")
)
fig2 = px.bar(
    gaffes,
    x="phase",
    y="gaffes",
    text="gaffes",
    title="Nombre de gaffes par phase de la partie : la plupart tombent au milieu de partie",
    labels={"phase": "", "gaffes": "gaffes"},
)
fig2.show()

# 3. Le score selon l'heure de la partie (heures UTC, au moins 30 parties par heure)
heures = df.groupby("heure").agg(n=("partie_id", "nunique"), score=("score", "mean")).reset_index()
heures = heures[heures["n"] >= 30]
fig3 = px.bar(
    heures,
    x="heure",
    y="score",
    hover_data=["n"],
    title="Score moyen selon l'heure (UTC, ≥ 30 parties) : au plus bas entre 0 h et 1 h, au plus haut à 18 h",
    labels={"heure": "heure (UTC)", "score": "score moyen"},
)
fig3.add_hline(y=df["score"].mean(), line_dash="dash", annotation_text="moyenne")
fig3.show()

print(gaffes)
print(heures.sort_values("score").to_string(index=False))
