"""Exo 5 : le service FastAPI. Environ 45 min.

Question : mes parties derrière une API que n'importe quel client peut appeler (votre appli, puis l'agent de l'exo 6).
À produire : GET /ouvertures et GET /parties, paramètres validés (une cadence inconnue renvoie 422, pas une liste vide).
Ensuite : app_api.py, ou votre appli de l'exo 2 ou de l'exo 4, appelle cette API au lieu de lire les CSV.
Bonus : POST /predict avec le modèle fourni (fil_rouge/model.joblib, déjà entraîné), puis client.py.
Lancer : uv run uvicorn api:app --app-dir fil_rouge --host 127.0.0.1 --port 8000 --reload
Documentation interactive : http://127.0.0.1:8000/docs

En plus de l'exo : une route par analyse du dashboard, pour que app_api.py affiche tout le
dashboard sans lire un seul CSV. Toutes acceptent les mêmes filtres que la barre latérale
(plateforme, cadence, couleur, debut, fin) ; les listes se répètent : ?cadence=blitz&cadence=bullet.
"""

from contextlib import asynccontextmanager
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import analyses as an
import graphiques as gr
import joblib
import pandas as pd
from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field

from data import familles

Plateforme = Literal["chesscom", "lichess", "imported"]
Cadence = Literal["bullet", "blitz", "rapid", "classical", "aucune"]
Couleur = Literal["white", "black"]
Piece = Literal["pion", "cavalier", "fou", "tour", "dame", "roi"]
Gravite = Literal["imprécision", "erreur", "gaffe"]
Phase = Literal["ouverture", "milieu", "finale"]
Resultat = Literal["victoire", "nulle", "défaite"]
Pendule = Literal["< 10 s", "10-30 s", "30 s-1 min", "1-2 min", "> 2 min"]
Axe = Literal["couleur", "tranche", "annee"]
Seulement = Literal["toutes", "victoire", "défaite", "timeout"]

COLONNES_PARTIES = [
    "partie_id",
    "date_jeu",
    "plateforme",
    "cadence",
    "couleur",
    "resultat",
    "fin_partie",
    "elo_joueur",
    "elo_adverse",
    "ecart_elo",
    "ouverture_famille",
    "ouverture_nom",
    "precision_joueur",
    "gaffes_joueur",
]


@lru_cache(maxsize=1)
def modele():
    return joblib.load(Path(__file__).parent / "model.joblib")


@asynccontextmanager
async def demarrage(_app):
    # 1. Les données (et le modèle) une fois, au démarrage : les requêtes lisent le cache
    an.parties()
    an.coups()
    an.phases()
    an.moments()
    modele()
    yield


app = FastAPI(title="Mes parties d'échecs", version="2.0", lifespan=demarrage)


def en_json(df: pd.DataFrame) -> list[dict]:
    """Une liste de dicts ; NaN n'existe pas en JSON, il devient null."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


# ---------------------------------------------------------------- les filtres communs


def filtres_parties(
    plateforme: Annotated[list[Plateforme] | None, Query()] = None,
    cadence: Annotated[list[Cadence] | None, Query()] = None,
    couleur: Couleur | None = None,
    debut: Annotated[date | None, Query(description="première date incluse (AAAA-MM-JJ)")] = None,
    fin: Annotated[date | None, Query(description="dernière date incluse (AAAA-MM-JJ)")] = None,
) -> pd.DataFrame:
    """Les parties qui passent les filtres de la barre latérale. Sans filtre : toutes."""
    debut = debut or an.parties()["date_jeu"].min().date()
    fin = fin or an.parties()["date_jeu"].max().date()
    return an.filtrer(
        an.parties(),
        plateformes=plateforme,
        cadence=cadence or "toutes",
        couleur=couleur or "toutes",
        periode=(debut, fin),
    )


def filtres_coups(
    piece: Annotated[list[Piece] | None, Query()] = None,
    gravite: Annotated[list[Gravite] | None, Query()] = None,
    phase: Annotated[list[Phase] | None, Query()] = None,
    famille: Annotated[list[str] | None, Query(description="ouverture_famille")] = None,
    resultat: Annotated[list[Resultat] | None, Query()] = None,
    pendule: Annotated[
        list[Pendule] | None, Query(description="temps restant après le coup")
    ] = None,
) -> dict:
    """Les filtres de l'onglet « L'échiquier », vers ceux de analyses.coups_filtres."""
    return {
        "pieces": piece,
        "gravites": gravite,
        "phases": phase,
        "familles": famille,
        "resultats": resultat,
        "pendules": pendule,
    }


Vue = Annotated[pd.DataFrame, Depends(filtres_parties)]
FiltresCoups = Annotated[dict, Depends(filtres_coups)]


# ---------------------------------------------------------------- l'exo 5


@app.get("/")
def accueil():
    """Vérifier que l'API répond, et la liste des routes (le détail est dans /docs)."""
    return {
        "statut": "ok",
        "parties": int(an.parties()["partie_id"].nunique()),
        "routes": sorted(
            r.path for r in app.routes if r.path.startswith("/") and "{" not in r.path
        ),
    }


@app.get("/options")
def options():
    """Ce qu'il faut pour construire la barre latérale : cadences, plateformes, dates."""
    df = an.parties()
    return {
        "cadences": df["cadence"].value_counts().index.tolist(),  # la plus jouée d'abord
        "plateformes": df["plateforme"].value_counts().index.tolist(),
        "debut": df["date_jeu"].min().date().isoformat(),
        "fin": df["date_jeu"].max().date().isoformat(),
    }


# 2. Les familles d'ouvertures, la pire d'abord
@app.get("/ouvertures")
def ouvertures(
    vue: Vue,
    min_n: Annotated[int, Query(ge=1, description="parties minimum par famille")] = 30,
):
    """Score moyen par famille d'ouvertures (1 = victoire), la pire en premier.

    Colonnes : famille, n (parties), score, gaffes (par partie).
    """
    return en_json(familles(vue, min_n))


# 3. Les dernières parties
@app.get("/parties")
def parties(
    vue: Vue,
    famille: Annotated[str | None, Query(description="ouverture_famille")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 10,
):
    """Mes parties, les plus récentes d'abord (dates en UTC)."""
    if famille:
        vue = vue[vue["ouverture_famille"] == famille]
    d = vue.sort_values("date_jeu", ascending=False).head(limit)
    d = d.assign(date_jeu=d["date_jeu"].dt.strftime("%Y-%m-%d %H:%M"))
    return en_json(d[COLONNES_PARTIES])


# ---------------------------------------------------------------- le dashboard


@app.get("/indicateurs")
def indicateurs(vue: Vue):
    """Parties, score, Elo (série la plus jouée, 6 derniers mois), gaffes par partie,
    part des défaites au temps, part des positions gagnantes non gagnées."""
    return an.kpis(vue)


@app.get("/verdict")
def verdict(vue: Vue) -> list[str]:
    """Les conclusions écrites « À travailler en priorité », pour les parties filtrées."""
    return gr.verdict(vue)  # le texte du verdict est écrit dans graphiques.py


@app.get("/phases-gaffes")
def phases_gaffes(vue: Vue):
    """Nombre de mes gaffes par phase (la figure 2 de l'exo 1)."""
    c = an.de(an.coups(), vue)
    g = (
        c[c["jugement"] == "blunder"]["phase"]
        .value_counts()
        .reindex(an.ORDRE_PHASES, fill_value=0)
        .rename_axis("phase")
        .reset_index(name="gaffes")
    )
    return en_json(g)


@app.get("/elo")
def elo(vue: Vue):
    """Mon Elo médian par mois, une série par plateforme et cadence (30 parties minimum)."""
    return en_json(an.courbe_elo(vue))


@app.get("/gaffes-trimestre")
def gaffes_trimestre(vue: Vue):
    """Gaffes pour 10 coups joués, par phase et par trimestre (trimestres de 30 parties ou plus)."""
    return en_json(an.gaffes_dans_le_temps(vue))


@app.get("/gachees")
def gachees(vue: Vue):
    """Parties où j'étais à +3 avant une grosse faute : la phase de la faute et le résultat."""
    return en_json(an.avantages_gaches(vue))


@app.get("/pendule")
def pendule(vue: Vue):
    """Part de gaffes parmi mes fautes selon le temps restant, par phase."""
    return en_json(an.pendule(vue))


@app.get("/temps-coup")
def temps_coup(vue: Vue, seulement: Seulement = "toutes"):
    """Temps moyen par coup, moi contre l'adversaire, par phase."""
    return en_json(an.temps_par_coup(vue, seulement))


@app.get("/fins")
def fins(vue: Vue):
    """Comment finissent mes victoires et mes défaites (nulles exclues)."""
    return en_json(an.fins_de_partie(vue))


@app.get("/heures")
def heures(vue: Vue):
    """Mon score selon l'heure de début (UTC), heures de 30 parties ou plus, et mon score moyen."""
    moyenne = float(vue["score"].mean()) if len(vue) else None
    return {"moyenne": moyenne, "heures": en_json(an.score_par_heure(vue))}


@app.get("/ouvertures-croisees")
def ouvertures_croisees(
    vue: Vue,
    axe: Axe = "couleur",
    min_n: Annotated[int, Query(ge=1, description="parties minimum par famille")] = 30,
):
    """Score par famille d'ouvertures croisée avec la couleur, la tranche horaire ou l'année.

    Deux tableaux de même forme : score (vide sous 10 parties) et n (parties par case).
    """
    score, n = an.ouvertures_croisees(vue, axe, min_n)
    return {
        "familles": score.index.tolist(),
        "colonnes": [str(c) for c in score.columns],
        "score": score.astype(object).where(score.notna(), None).values.tolist(),
        "n": n.values.tolist(),
    }


@app.get("/natures")
def natures(vue: Vue):
    """Erreurs et gaffes par partie, par phase et par nature (tactique laissée, ratée, stratégique)."""
    return en_json(an.types_fautes(vue))


# ---------------------------------------------------------------- l'échiquier


@app.get("/familles")
def liste_familles(vue: Vue) -> list[str]:
    """Les familles d'ouvertures jouées, la plus jouée d'abord (pour le filtre de l'échiquier)."""
    return vue["ouverture_famille"].value_counts().index.tolist()


@app.get("/echiquier")
def echiquier(vue: Vue, filtres: FiltresCoups):
    """Mes coups jugés mauvais par case d'arrivée, séparés par la couleur jouée, la plus chaude d'abord.

    Colonnes : couleur, case, colonne, rangee, fautes, gaffes, part_gaffes, perte (cp, médiane),
    piece_top (la pièce la plus souvent fautive sur la case).
    """
    cases = an.fautes_par_case(vue, **filtres)
    return en_json(cases.sort_values("fautes", ascending=False))


@app.get("/pieces")
def pieces(vue: Vue, filtres: FiltresCoups):
    """Erreurs et gaffes par pièce jouée, la plus fautive d'abord (le filtre piece est ignoré).

    Colonnes : piece, erreurs, gaffes, fautes, par_partie, part_gaffes, perte (cp, médiane), parties.
    """
    return en_json(an.fautes_par_piece(vue, **filtres))


# ---------------------------------------------------------------- bonus : le modèle


class Partie(BaseModel):
    couleur: Couleur
    cadence: Literal["bullet", "blitz", "rapid"]  # les cadences vues à l'entraînement
    ecart_elo: float = Field(ge=-1000, le=1000, description="Elo de l'adversaire moins le mien")
    heure: int = Field(ge=0, le=23, description="heure de début, UTC")


@app.post("/predict")
def predict(partie: Partie):
    """La probabilité que je gagne une partie dans cette situation."""
    x = pd.DataFrame([partie.model_dump()])
    return {"proba_victoire": round(float(modele().predict_proba(x)[0, 1]), 4)}
