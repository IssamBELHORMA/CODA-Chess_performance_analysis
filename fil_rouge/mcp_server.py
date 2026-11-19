"""Exo 6 : votre propre serveur MCP. Environ 20 min.

Question : un LLM doit pouvoir interroger mes parties.
À produire : un serveur FastMCP de deux ou trois outils au-dessus de votre API (api.py doit
tourner). Le LLM choisit un outil d'après son nom, sa docstring et ses arguments : soignez-les.
Lancer : uv run python fil_rouge/mcp_server.py   (stdio : c'est le client LLM qui le lance,
voir contexte/README.md pour le brancher). Lancé à la main, il n'affiche rien et attend un
client : c'est normal. Pour tester : npx @modelcontextprotocol/inspector uv run python fil_rouge/mcp_server.py
"""

import os
from typing import Literal

import requests
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API = os.environ.get("AWP_API_URL", "http://127.0.0.1:8000")
# Deux transports. stdio (par défaut) : le client LLM lance ce script lui-même, sur la même machine.
# MCP_TRANSPORT=http : un serveur HTTP sur /mcp, pour un client qui ne lance pas le script (un client
# dans le cloud, via un hébergeur ou un tunnel). En local : 127.0.0.1:8001 (l'API est sur 8000), pas
# ouvert à la salle. Sur un hébergeur qui fixe $PORT (Render, Cloud Run) : 0.0.0.0:$PORT.
HTTP = os.environ.get("MCP_TRANSPORT") == "http"
HOTE = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
# En local, FastMCP refuse un nom d'hôte autre que 127.0.0.1 ou localhost (protection contre le DNS
# rebinding). Derrière un tunnel (MCP_TUNNEL=1), l'hôte est celui du tunnel : on lève la protection,
# le serveur est de toute façon public tant que le tunnel tourne.
TUNNEL = os.environ.get("MCP_TUNNEL") == "1"
SECU = TransportSecuritySettings(enable_dns_rebinding_protection=False) if TUNNEL else None
mcp = FastMCP(
    "echecs", host=HOTE, port=int(os.environ.get("PORT", "8001")), transport_security=SECU
)

Cadence = Literal["bullet", "blitz", "rapid"]
Couleur = Literal["white", "black"]
Piece = Literal["pion", "cavalier", "fou", "tour", "dame", "roi"]
Gravite = Literal["imprécision", "erreur", "gaffe"]
Phase = Literal["ouverture", "milieu", "finale"]


# 1. Un appel à l'API : une réponse refusée (422, 500…) ou une API arrêtée lève une erreur lisible
def appeler(methode: str, chemin: str, **kwargs):
    try:
        r = requests.request(methode, f"{API}{chemin}", timeout=10, **kwargs)
    except requests.RequestException as e:
        raise RuntimeError(f"L'API {API} ne répond pas : lancez api.py d'abord ({e})") from e
    if not r.ok:
        raise RuntimeError(f"L'API a refusé {chemin} ({r.status_code}) : {r.text[:300]}")
    return r.json()


def sans_vides(params: dict) -> dict:
    return {k: v for k, v in params.items() if v is not None}


# 2. Mes pires ouvertures
@mcp.tool()
def pires_ouvertures(cadence: Cadence = "blitz", min_n: int = 30, nombre: int = 5) -> list[dict]:
    """Mes familles d'ouvertures où je marque le moins de points, la pire d'abord.

    Pour répondre à « quelles ouvertures me coûtent des points ? » ou « que dois-je réviser ? ».
    cadence : bullet, blitz ou rapid. min_n : parties minimum par famille (sous 30, le chiffre
    ne dit pas grand-chose). nombre : combien de familles renvoyer.
    Chaque famille : famille, n (parties), score (1 = toujours gagné, 0,5 = autant de points
    gagnés que perdus), gaffes (par partie).
    """
    return appeler("GET", "/ouvertures", params={"cadence": cadence, "min_n": min_n})[:nombre]


@mcp.tool()
def dernieres_parties(
    cadence: Cadence | None = None, couleur: Couleur | None = None, nombre: int = 10
) -> list[dict]:
    """Mes parties les plus récentes : date (UTC), cadence, couleur, résultat, Elo, ouverture, gaffes.

    couleur : white ou black, la couleur que je jouais. nombre : de 1 à 500.
    """
    params = sans_vides({"cadence": cadence, "couleur": couleur, "limit": nombre})
    return appeler("GET", "/parties", params=params)


@mcp.tool()
def ou_je_fais_mes_fautes(
    cadence: Cadence | None = None,
    couleur: Couleur | None = None,
    pieces: list[Piece] | None = None,
    gravites: list[Gravite] | None = None,
    phases: list[Phase] | None = None,
    nombre: int = 10,
) -> list[dict]:
    """Les cases de l'échiquier où arrivent le plus de mes coups jugés mauvais, la plus chaude d'abord.

    Pour « sur quelles cases je fais mes gaffes ? » ou « où ma dame se perd-elle ? ».
    Filtres facultatifs : la pièce jouée, la gravité (imprécision, erreur, gaffe), la phase.
    Chaque case : couleur jouée, case (e4…), fautes, gaffes, part_gaffes, perte (centipions,
    médiane), piece_top (la pièce la plus souvent fautive sur cette case).
    """
    params = sans_vides(
        {
            "cadence": cadence,
            "couleur": couleur,
            "piece": pieces,
            "gravite": gravites,
            "phase": phases,
        }
    )
    return appeler("GET", "/echiquier", params=params)[:nombre]


@mcp.tool()
def pieces_les_plus_fautives(
    cadence: Cadence | None = None,
    couleur: Couleur | None = None,
    phases: list[Phase] | None = None,
) -> list[dict]:
    """Mes erreurs et gaffes par pièce jouée (pion, cavalier, fou, tour, dame, roi), la pire d'abord.

    Pour « avec quelle pièce je fais le plus de fautes ? ». Chaque pièce : erreurs, gaffes,
    fautes (les deux), par_partie, part_gaffes (gaffes / fautes), perte (centipions, médiane).
    """
    params = sans_vides({"cadence": cadence, "couleur": couleur, "phase": phases})
    return appeler("GET", "/pieces", params=params)


# 3. Mes chances de victoire dans une situation donnée
@mcp.tool()
def chances_de_victoire(couleur: Couleur, cadence: Cadence, ecart_elo: float, heure: int) -> dict:
    """La probabilité que je gagne une partie, d'après un modèle entraîné sur mes parties.

    Pour « et si je jouais plus tard, ou avec les noirs ? ». couleur : white ou black.
    ecart_elo : Elo de l'adversaire moins le mien (positif = adversaire plus fort, de -1000 à 1000).
    heure : heure de début en UTC, de 0 à 23. Renvoie {"proba_victoire": 0.0 à 1.0}.
    """
    partie = {"couleur": couleur, "cadence": cadence, "ecart_elo": ecart_elo, "heure": heure}
    return appeler("POST", "/predict", json=partie)


if __name__ == "__main__":
    # Derrière un tunnel : MCP_TUNNEL=1 MCP_TRANSPORT=http uv run python …, puis npx localtunnel --port 8001
    mcp.run(transport="streamable-http" if HTTP else "stdio")
