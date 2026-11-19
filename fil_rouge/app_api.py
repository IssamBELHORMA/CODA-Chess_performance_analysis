"""Exo 5, suite : l'appli ne lit plus les CSV, elle demande à l'API. Environ 45 min.

Question : la même appli qu'à l'exo 2, mais ses chiffres viennent de l'API.
À produire : une barre latérale (cadence, parties minimum), la figure des familles depuis GET /ouvertures,
les dix dernières parties depuis GET /parties, et un message lisible si l'API ne répond pas.
Vous pouvez aussi modifier directement votre app_streamlit.py ou votre app_dash.py.
Lancez api.py d'abord.
Lancer : uv run streamlit run fil_rouge/app_api.py --server.address 127.0.0.1

Ici : tout app_streamlit.py (exo 2, les onglets du dashboard et l'échiquier), mais chaque chiffre
vient d'une route de l'API. Ce fichier ne lit aucun CSV : ni data.py ni analyses.py ne chargent
de données ici, graphiques.py ne fait que dessiner (ses fonctions *_depuis).
"""

import os

import graphiques as gr
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API = os.environ.get("AWP_API_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="Mes parties d'échecs", layout="wide")
print("relance")  # regardez le terminal à chaque clic

COULEURS = {"les deux": None, "blancs": "white", "noirs": "black"}
PLATEFORMES = {"Chess.com": "chesscom", "Lichess": "lichess", "importées": "imported"}
PIECES = ["pion", "cavalier", "fou", "tour", "dame", "roi"]
GRAVITES = ["imprécision", "erreur", "gaffe"]
PHASES = ["ouverture", "milieu", "finale"]
RESULTATS = ["victoire", "nulle", "défaite"]
PENDULES = ["< 10 s", "10-30 s", "30 s-1 min", "1-2 min", "> 2 min"]


# 1. Un appel à l'API. Mis en cache 5 minutes : une relance avec les mêmes filtres ne rappelle
#    pas l'API. Une erreur HTTP lève une exception, qui n'est pas mise en cache.
@st.cache_data(ttl=300, show_spinner=False)
def appeler(chemin: str, params: dict):
    r = requests.get(f"{API}{chemin}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


# 5. API arrêtée ou réponse refusée : un message lisible et l'arrêt, pas une trace
def api(chemin: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    try:
        return appeler(chemin, params)
    except requests.RequestException as e:
        st.error(
            f"L'API ne répond pas ({API}{chemin}). Lancez-la d'abord, dans un autre terminal :\n\n"
            "`uv run uvicorn api:app --app-dir fil_rouge --host 127.0.0.1 --port 8000`\n\n"
            f"Détail : {e}"
        )
        st.stop()


def tableau(chemin: str, **params) -> pd.DataFrame:
    return pd.DataFrame(api(chemin, **params))


def tout_ou_rien(choix: list, toutes: list):
    """Tout coché = pas de filtre (None) : les coups sans pendule enregistrée restent comptés."""
    return None if set(choix) == set(toutes) else choix


options = api("/options")

# 2. Le titre dit la question, puis la barre latérale
st.title("Où est-ce que je perds des points, et qu'est-ce que je dois travailler ?")
st.caption(f"Toutes les données viennent de l'API : {API} (documentation : {API}/docs)")

with st.sidebar:
    st.header("Filtres")
    choix_cadences = st.multiselect(
        "Cadence", options["cadences"], default=["blitz"], key="cadence"
    )
    debut, fin = pd.Timestamp(options["debut"]).date(), pd.Timestamp(options["fin"]).date()
    periode = st.date_input(
        "Période", value=(debut, fin), min_value=debut, max_value=fin, key="periode"
    )
    couleur = st.radio("Ma couleur", list(COULEURS), horizontal=True, key="couleur")
    plateformes = st.multiselect(
        "Plateforme", list(PLATEFORMES), default=list(PLATEFORMES), key="plateforme"
    )
    n_min = st.slider("Parties minimum par famille", 10, 100, 30, 10, key="n_min")

# 3. S'arrêter proprement si la période est incomplète ou si un filtre est vide
if len(periode) != 2:
    st.warning("Choisissez la seconde date de la période.")
    st.stop()
if not choix_cadences or not plateformes:
    st.warning(
        "Aucune partie pour ces filtres : choisissez au moins une cadence et une plateforme."
    )
    st.stop()

# Les filtres de la barre latérale, envoyés à chaque route
F = {
    "plateforme": [PLATEFORMES[p] for p in plateformes],
    "cadence": choix_cadences,
    "couleur": COULEURS[couleur],
    "debut": periode[0].isoformat(),
    "fin": periode[1].isoformat(),
}

k = api("/indicateurs", **F)
if not k:
    st.warning(
        "Aucune partie pour ces filtres : élargissez la cadence, la période ou la plateforme."
    )
    st.stop()

# 4. Trois indicateurs
m1, m2, m3 = st.columns(3)
m1.metric("Parties", f"{k['parties']:,}".replace(",", " "))
m2.metric("Score moyen", f"{k['score']:.2f}", help="1 = victoire, 0,5 = nulle, 0 = défaite")
m3.metric("Gaffes par partie", f"{k['gaffes']:.1f}")

# 5. Les deux figures de l'exo 1, depuis GET /ouvertures et GET /phases-gaffes
gauche, droite = st.columns(2)

fam = tableau("/ouvertures", min_n=n_min, **F)
with gauche:
    if fam.empty:
        st.info(f"Aucune famille d'ouvertures n'a {n_min} parties avec ces filtres.")
        selection = None
    else:
        fig1 = px.bar(
            fam,
            x="score",
            y="famille",
            orientation="h",
            hover_data=["n", "gaffes"],
            title="Score moyen par famille d'ouvertures : la pire en haut",
            labels={"score": "score moyen (1 = victoire)", "famille": ""},
        )
        fig1.update_yaxes(categoryorder="array", categoryarray=fam["famille"][::-1].tolist())
        fig1.add_vline(x=k["score"], line_dash="dash", annotation_text="moyenne")
        fig1.update_layout(height=max(360, 28 * len(fam) + 120))
        # Bonus : un clic sur une barre renvoie la famille choisie
        selection = st.plotly_chart(
            fig1, on_select="rerun", selection_mode="points", key="fig_familles", theme=None
        )

gaffes = tableau("/phases-gaffes", **F)
with droite:
    fig2 = px.bar(
        gaffes,
        x="phase",
        y="gaffes",
        text="gaffes",
        title="Nombre de gaffes par phase de la partie",
        labels={"phase": "", "gaffes": "gaffes"},
    )
    st.plotly_chart(fig2, key="fig_phases", theme=None)

# Bonus : le détail de la famille cliquée, depuis GET /parties
points = selection.selection.points if selection else []
if points:
    famille = points[0]["y"]
    detail = tableau("/parties", famille=famille, limit=500, **F)
    score_famille = fam.set_index("famille").loc[famille, "score"]
    st.subheader(f"{famille} : {len(detail)} parties, score {score_famille:.2f}")
    colonnes = ["partie_id", "date_jeu", "cadence", "couleur", "resultat", "ouverture_nom"]
    st.dataframe(detail[colonnes + ["ecart_elo", "gaffes_joueur"]], hide_index=True)
else:
    st.caption("Cliquez une barre des familles d'ouvertures pour voir ses parties.")

st.subheader("Mes dix dernières parties")
st.dataframe(tableau("/parties", limit=10, **F), hide_index=True)


# ---------------------------------------------------------------- en plus : le dashboard complet


def carte(titre, aide, fig, key):
    st.subheader(titre)
    st.caption(aide)
    st.plotly_chart(fig, key=key, theme=None, config={"displayModeBar": False})


def avec_dates(d: pd.DataFrame, colonne: str) -> pd.DataFrame:
    """Le JSON transporte les dates en texte : on les repasse en dates pour l'axe des x."""
    return d.assign(**{colonne: pd.to_datetime(d[colonne])}) if not d.empty else d


st.divider()
st.header("Pourquoi je stagne : le détail")
travail, stagnation, temps, ouvertures, echiquier = st.tabs(
    ["À travailler", "La stagnation", "Le temps", "Ouvertures et fautes", "L'échiquier"]
)

with travail:
    # parties, score et gaffes sont déjà en haut : on garde Elo, défaites au temps, gâchis
    indicateurs = [
        x for x in gr.kpis_depuis(k) if x[1] not in ("parties", "score moyen", "gaffes par partie")
    ]
    for col, (valeur, libelle, detail) in zip(st.columns(3), indicateurs, strict=False):
        col.metric(libelle, valeur, help=detail or None)
    st.subheader("À travailler en priorité")
    st.markdown("\n".join(f"- {p}" for p in api("/verdict", **F)))

with stagnation:
    carte(
        "Mon Elo médian par mois",
        "Une ligne par plateforme et cadence : un Elo ne se compare qu'à lui-même.",
        gr.fig_elo_depuis(avec_dates(tableau("/elo", **F), "mois")),
        "fig_elo",
    )
    a, b = st.columns(2)
    with a:
        carte(
            "Gaffes pour 10 coups joués, par phase et par trimestre",
            "Si je progressais, ces lignes descendraient. Trimestres d'au moins 30 parties.",
            gr.fig_gaffes_temps_depuis(avec_dates(tableau("/gaffes-trimestre", **F), "trimestre")),
            "fig_gaffes_temps",
        )
    with b:
        carte(
            "Mes parties gagnées puis gâchées",
            "Parties où j'étais à +3 juste avant une grosse faute, selon la phase de cette faute "
            "et le résultat final.",
            gr.fig_gaches_depuis(tableau("/gachees", **F)),
            "fig_gaches",
        )

with temps:
    a, b = st.columns(2)
    with a:
        carte(
            "La pendule transforme mes fautes en gaffes",
            "Parmi mes fautes, la part de gaffes selon le temps qu'il me restait, par phase.",
            gr.fig_pendule_depuis(tableau("/pendule", **F)),
            "fig_pendule",
        )
        carte(
            "Comment finissent mes parties",
            "Part de chaque fin, pour mes victoires et mes défaites (nulles exclues).",
            gr.fig_fins_depuis(tableau("/fins", **F)),
            "fig_fins",
        )
    with b:
        seulement = st.selectbox(
            "Parties comparées (temps par coup)",
            ["timeout", "toutes", "victoire", "défaite"],
            format_func={
                "timeout": "mes défaites au temps",
                "toutes": "toutes les parties",
                "victoire": "mes victoires",
                "défaite": "mes défaites",
            }.get,
            key="temps_coup",
        )
        carte(
            "Temps par coup : moi contre l'adversaire",
            "Moyenne par phase, sur les parties choisies ci-dessus.",
            gr.fig_temps_coup_depuis(tableau("/temps-coup", seulement=seulement, **F)),
            "fig_temps_coup",
        )
        h = api("/heures", **F)
        carte(
            "Mon score selon l'heure (UTC)",
            "Heures d'au moins 30 parties. La ligne pointillée est mon score moyen.",
            gr.fig_heure_depuis(pd.DataFrame(h["heures"]), h["moyenne"]),
            "fig_heure",
        )

with ouvertures:
    axe = st.radio(
        "Croiser les familles d'ouvertures",
        ["couleur", "tranche", "annee"],
        format_func={
            "couleur": "par couleur",
            "tranche": "par tranche horaire",
            "annee": "par année",
        }.get,
        horizontal=True,
        key="ouvertures_axe",
    )
    croise = api("/ouvertures-croisees", axe=axe, min_n=n_min, **F)
    score = pd.DataFrame(croise["score"], index=croise["familles"], columns=croise["colonnes"])
    n = pd.DataFrame(croise["n"], index=croise["familles"], columns=croise["colonnes"])
    carte(
        "Mon score par famille d'ouvertures, croisé",
        f"Rouge = je perds des points, bleu = j'en gagne. Familles d'au moins {n_min} parties "
        "(curseur de la barre latérale), case vide sous 10 parties. La pire famille en haut.",
        gr.fig_ouvertures_depuis(score.astype(float), n, n_min),
        "fig_ouvertures",
    )
    carte(
        "Erreurs et gaffes par partie, selon leur nature",
        "Tactique laissée : mon coup offre une combinaison à l'adversaire. "
        "Tactique ratée : je ne vois pas la mienne.",
        gr.fig_natures_depuis(tableau("/natures", **F)),
        "fig_natures",
    )


# ---------------------------------------------------------------- onglet « L'échiquier »


def choisir_piece():
    """Clic sur une barre des pièces : l'échiquier ne montre plus que cette pièce.

    Un callback s'exécute avant la relance : on peut alors changer la valeur d'un widget.
    """
    selection_pieces = st.session_state["fig_pieces"].selection.points
    if selection_pieces:
        st.session_state["ech_pieces"] = [selection_pieces[0]["y"]]


def toutes_les_pieces():
    st.session_state["ech_pieces"] = list(PIECES)


with echiquier:
    st.caption(
        "Ces filtres s'ajoutent à ceux de la barre latérale. Le graphique des pièces les suit "
        "tous sauf « Pièce », pour garder la comparaison entre pièces."
    )
    f1, f2, f3 = st.columns(3)
    famille_choisie = f1.selectbox(
        "Famille d'ouvertures", ["toutes", *api("/familles", **F)], key="ech_famille"
    )
    resultats = f2.multiselect(
        "Résultat de la partie", RESULTATS, default=RESULTATS, key="ech_resultats"
    )
    pendules = f3.multiselect(
        "Temps restant après le coup", PENDULES, default=PENDULES, key="ech_pendules"
    )
    f4, f5, f6 = st.columns(3)
    if "ech_pieces" not in st.session_state:
        st.session_state["ech_pieces"] = list(PIECES)
    pieces_choisies = f4.multiselect("Pièce", PIECES, key="ech_pieces")
    gravites = f5.multiselect("Gravité", GRAVITES, default=GRAVITES, key="ech_gravites")
    phases_choisies = f6.multiselect("Phase", PHASES, default=PHASES, key="ech_phases")

    if not (resultats and pendules and gravites and phases_choisies):
        st.info("Un des filtres est vide : cochez au moins une valeur dans chacun.")
        st.stop()

    FC = {  # les filtres de l'onglet, au format des paramètres de l'API
        "famille": None if famille_choisie == "toutes" else [famille_choisie],
        "resultat": tout_ou_rien(resultats, RESULTATS),
        "pendule": tout_ou_rien(pendules, PENDULES),
        "gravite": tout_ou_rien(gravites, GRAVITES),
        "phase": tout_ou_rien(phases_choisies, PHASES),
    }

    st.subheader("La pièce avec laquelle je fais le plus d'erreurs et de gaffes")
    st.caption(
        "Erreurs et gaffes par partie, la pire pièce en haut ; à droite de chaque barre, la part "
        "de gaffes. Cliquez une barre pour limiter l'échiquier à cette pièce."
    )
    st.plotly_chart(
        gr.fig_pieces_depuis(tableau("/pieces", **F, **FC)),
        key="fig_pieces",
        theme=None,
        on_select=choisir_piece,
        selection_mode="points",
        config={"displayModeBar": False},
    )
    st.button("Toutes les pièces", on_click=toutes_les_pieces, key="ech_reset")

    st.subheader("Où arrivent mes coups jugés mauvais")
    mesure = st.radio(
        "Mesure",
        list(gr.MESURES_ECHIQUIER),
        format_func=lambda m: gr.MESURES_ECHIQUIER[m][2],
        horizontal=True,
        key="ech_mesure",
    )
    st.caption(
        "Chaque échiquier est vu de mon côté (rangée 1 en bas avec les blancs, 8 avec les noirs). "
        "Part de gaffes et perte médiane : cases d'au moins 15 fautes, les autres restent vides. "
        "Survolez une case pour la pièce la plus fautive."
    )
    if not pieces_choisies:
        st.info("Choisissez au moins une pièce.")
    else:
        cases = tableau("/echiquier", piece=tout_ou_rien(pieces_choisies, PIECES), **F, **FC)
        st.plotly_chart(
            gr.fig_echiquier_depuis(cases, mesure),
            key="fig_echiquier",
            theme=None,
            config={"displayModeBar": False},
        )
