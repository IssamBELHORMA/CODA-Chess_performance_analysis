"""L'API de l'exo 5 : routes, validation des paramètres, et le bonus /predict."""

import pytest
from api import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # « with » lance le démarrage : données et modèle chargés
        yield c


def test_accueil(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["parties"] > 1000


def test_ouvertures_pire_en_premier(client):
    r = client.get("/ouvertures", params={"cadence": "blitz", "min_n": 30})
    assert r.status_code == 200
    scores = [f["score"] for f in r.json()]
    assert scores and scores == sorted(scores)
    assert all(f["n"] >= 30 for f in r.json())


def test_cadence_inconnue_renvoie_422(client):
    assert client.get("/ouvertures", params={"cadence": "hyperbullet"}).status_code == 422
    assert client.get("/parties", params={"cadence": "hyperbullet"}).status_code == 422


def test_parties_limit_et_validation(client):
    r = client.get("/parties", params={"cadence": "blitz", "couleur": "black", "limit": 5})
    assert r.status_code == 200
    lignes = r.json()
    assert len(lignes) == 5
    assert {p["couleur"] for p in lignes} == {"black"}
    assert client.get("/parties", params={"limit": 0}).status_code == 422
    assert client.get("/parties", params={"limit": 501}).status_code == 422


def test_echiquier_filtres(client):
    r = client.get(
        "/echiquier", params={"cadence": "blitz", "piece": ["dame", "tour"], "gravite": "gaffe"}
    )
    assert r.status_code == 200
    cases = r.json()
    assert cases and cases[0]["fautes"] >= cases[-1]["fautes"]
    assert {c["piece_top"] for c in cases} <= {"dame", "tour"}
    assert client.get("/echiquier", params={"piece": "licorne"}).status_code == 422


def test_pieces(client):
    r = client.get("/pieces", params={"cadence": "blitz", "phase": "milieu"})
    assert r.status_code == 200
    pieces = [p["piece"] for p in r.json()]
    assert sorted(pieces) == sorted(["pion", "cavalier", "fou", "tour", "dame", "roi"])


def test_predict(client):
    partie = {"couleur": "white", "cadence": "blitz", "ecart_elo": 0, "heure": 20}
    r = client.post("/predict", json=partie)
    assert r.status_code == 200
    assert 0 < r.json()["proba_victoire"] < 1
    assert client.post("/predict", json={**partie, "heure": 24}).status_code == 422


# ---------------------------------------------------------------- les routes du dashboard

FILTRES = {"cadence": ["blitz", "bullet"], "plateforme": ["chesscom"], "couleur": "black"}

ROUTES_TABLEAUX = [
    "/elo",
    "/gaffes-trimestre",
    "/gachees",
    "/pendule",
    "/temps-coup",
    "/fins",
    "/natures",
    "/phases-gaffes",
    "/echiquier",
    "/pieces",
]


@pytest.mark.parametrize("route", ROUTES_TABLEAUX)
def test_routes_du_dashboard_repondent(client, route):
    r = client.get(route, params=FILTRES)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and r.json()


def test_filtres_invalides_renvoient_422(client):
    assert client.get("/elo", params={"plateforme": "fics"}).status_code == 422
    assert client.get("/elo", params={"debut": "pas-une-date"}).status_code == 422
    assert client.get("/temps-coup", params={"seulement": "jamais"}).status_code == 422
    assert client.get("/ouvertures-croisees", params={"axe": "lune"}).status_code == 422


def test_memes_chiffres_que_les_csv(client):
    """L'API ne calcule rien d'autre : ses chiffres sont ceux de analyses.py sur les CSV."""
    import analyses as an

    vue = an.filtrer(
        an.parties(), plateformes=["chesscom"], cadence=["blitz", "bullet"], couleur="black"
    )
    k = client.get("/indicateurs", params=FILTRES).json()
    assert k["parties"] == an.kpis(vue)["parties"]
    assert k["score"] == pytest.approx(an.kpis(vue)["score"])
    cases = client.get("/echiquier", params={**FILTRES, "piece": "dame"}).json()
    local = an.fautes_par_case(vue, pieces=["dame"])
    assert sum(c["fautes"] for c in cases) == local["fautes"].sum()


def test_periode_filtre_les_parties(client):
    tout = client.get("/indicateurs").json()["parties"]
    an_2025 = client.get("/indicateurs", params={"debut": "2025-01-01", "fin": "2025-12-31"}).json()
    assert 0 < an_2025["parties"] < tout


def test_ouvertures_croisees_forme(client):
    r = client.get("/ouvertures-croisees", params={"cadence": "blitz", "axe": "tranche"}).json()
    assert r["colonnes"][0] == "toutes"
    assert len(r["score"]) == len(r["n"]) == len(r["familles"])


def test_app_api_ne_lit_aucun_csv():
    """L'appli de l'exo 5 n'importe ni data.py ni analyses.py : ses chiffres viennent de l'API."""
    import ast
    from pathlib import Path

    source = (Path(__file__).parents[1] / "fil_rouge" / "app_api.py").read_text(encoding="utf-8")
    modules = set()
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Import):
            modules |= {a.name for a in noeud.names}
        elif isinstance(noeud, ast.ImportFrom):
            modules.add(noeud.module)
    assert not modules & {"data", "analyses"}
    assert "read_csv" not in source
