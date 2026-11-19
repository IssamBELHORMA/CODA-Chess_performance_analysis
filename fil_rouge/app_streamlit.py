"""Exo 2 : l'appli Streamlit du fil rouge. Environ 1 h.

Question : l'appli que ce joueur ouvrirait chaque semaine pour savoir quoi travailler.
À produire : une barre latérale (cadence, période, couleur), trois st.metric, deux figures
en colonnes. Le titre de la page dit la question, pas « Dashboard ».
Colonnes utilisées : cadence (dont « aucune »), date_jeu (datetime), couleur (white ou black),
score, gaffes_joueur. Si votre load_data() ne les donne pas ainsi, corrigez-la.
Lancer : uv run streamlit run fil_rouge/app_streamlit.py --server.address 127.0.0.1

En plus de l'exo : sous les deux figures, des onglets reprennent le dashboard complet
(figures communes avec dashboard.py, dans graphiques.py), filtrés par la même barre latérale.
"""

import analyses as an
import graphiques as gr
import plotly.express as px
import streamlit as st

from data import familles, load_coups, load_data

st.set_page_config(page_title="Mes parties d'échecs", layout="wide")
print("relance")  # regardez le terminal à chaque clic

PHASES = {"opening": "ouverture", "middlegame": "milieu", "endgame": "finale"}
COULEURS = {"les deux": "toutes", "blancs": "white", "noirs": "black"}
PLATEFORMES = {"Chess.com": "chesscom", "Lichess": "lichess", "importées": "imported"}


# 1. Chargées une seule fois : les relances suivantes lisent le cache, pas le CSV
@st.cache_data
def donnees():
    return load_data(), load_coups()


df, coups = donnees()

# 2. Le titre dit la question, puis la barre latérale
st.title("Où est-ce que je perds des points, et qu'est-ce que je dois travailler ?")

# Version gardée : multiselect pour la cadence, car on veut pouvoir regarder blitz et bullet
# ensemble (une selectbox, l'autre version, n'en montre qu'une à la fois).
with st.sidebar:
    st.header("Filtres")
    # la plus jouée d'abord, « aucune » incluse
    cadences = df["cadence"].value_counts().index.tolist()
    choix_cadences = st.multiselect("Cadence", cadences, default=["blitz"], key="cadence")
    debut, fin = df["date_jeu"].min().date(), df["date_jeu"].max().date()
    periode = st.date_input(
        "Période", value=(debut, fin), min_value=debut, max_value=fin, key="periode"
    )
    couleur = st.radio("Ma couleur", list(COULEURS), horizontal=True, key="couleur")
    plateformes = st.multiselect(
        "Plateforme", list(PLATEFORMES), default=list(PLATEFORMES), key="plateforme"
    )
    n_min = st.slider("Parties minimum par famille", 10, 100, 30, 10, key="n_min")

# 3. Filtrer, et s'arrêter proprement s'il ne reste rien
if len(periode) != 2:
    st.warning("Choisissez la seconde date de la période.")
    st.stop()

vue = an.filtrer(
    df,
    plateformes=[PLATEFORMES[p] for p in plateformes],
    cadence=choix_cadences,
    couleur=COULEURS[couleur],
    periode=periode,
)
if vue.empty:
    st.warning(
        "Aucune partie pour ces filtres : élargissez la cadence, la période ou la plateforme."
    )
    st.stop()

coups_vue = coups[coups["partie_id"].isin(vue["partie_id"])]

# 4. Trois indicateurs
m1, m2, m3 = st.columns(3)
m1.metric("Parties", f"{vue['partie_id'].nunique():,}".replace(",", " "))
m2.metric(
    "Score moyen", f"{vue['score'].mean():.2f}", help="1 = victoire, 0,5 = nulle, 0 = défaite"
)
m3.metric("Gaffes par partie", f"{vue['gaffes_joueur'].mean():.1f}")

# 5. Les deux figures de l'exo 1, calculées sur les parties filtrées
gauche, droite = st.columns(2)

fam = familles(vue, n_min)
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
        fig1.add_vline(x=vue["score"].mean(), line_dash="dash", annotation_text="moyenne")
        fig1.update_layout(height=max(360, 28 * len(fam) + 120))
        # Bonus : un clic sur une barre renvoie la famille choisie
        selection = st.plotly_chart(
            fig1, on_select="rerun", selection_mode="points", key="fig_familles", theme=None
        )

gaffes = (
    coups_vue[coups_vue["jugement"] == "blunder"]["phase"]
    .map(PHASES)
    .value_counts()
    .reindex(list(PHASES.values()), fill_value=0)
    .rename_axis("phase")
    .reset_index(name="gaffes")
)
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

# Bonus : le détail de la famille cliquée
points = selection.selection.points if selection else []
if points:
    famille = points[0]["y"]
    detail = vue[vue["ouverture_famille"] == famille].sort_values("date_jeu", ascending=False)
    st.subheader(f"{famille} : {len(detail)} parties, score {detail['score'].mean():.2f}")
    colonnes = ["partie_id", "date_jeu", "cadence", "couleur", "resultat", "ouverture_nom"]
    st.dataframe(detail[colonnes + ["ecart_elo", "gaffes_joueur"]], hide_index=True)
else:
    st.caption("Cliquez une barre des familles d'ouvertures pour voir ses parties.")


# ---------------------------------------------------------------- en plus : le dashboard complet


def carte(titre, aide, fig, key):
    st.subheader(titre)
    st.caption(aide)
    st.plotly_chart(fig, key=key, theme=None, config={"displayModeBar": False})


st.divider()
st.header("Pourquoi je stagne : le détail")
travail, stagnation, temps, ouvertures, echiquier = st.tabs(
    ["À travailler", "La stagnation", "Le temps", "Ouvertures et fautes", "L'échiquier"]
)

with travail:
    # parties, score et gaffes sont déjà en haut : on garde Elo, défaites au temps, gâchis
    indicateurs = [
        k for k in gr.kpis(vue) if k[1] not in ("parties", "score moyen", "gaffes par partie")
    ]
    for col, (valeur, libelle, detail) in zip(st.columns(3), indicateurs, strict=False):
        col.metric(libelle, valeur, help=detail or None)
    st.subheader("À travailler en priorité")
    st.markdown("\n".join(f"- {p}" for p in gr.verdict(vue)))

with stagnation:
    carte(
        "Mon Elo médian par mois",
        "Une ligne par plateforme et cadence : un Elo ne se compare qu'à lui-même.",
        gr.fig_elo(vue),
        "fig_elo",
    )
    a, b = st.columns(2)
    with a:
        carte(
            "Gaffes pour 10 coups joués, par phase et par trimestre",
            "Si je progressais, ces lignes descendraient. Trimestres d'au moins 30 parties.",
            gr.fig_gaffes_temps(vue),
            "fig_gaffes_temps",
        )
    with b:
        carte(
            "Mes parties gagnées puis gâchées",
            "Parties où j'étais à +3 juste avant une grosse faute, selon la phase de cette faute "
            "et le résultat final.",
            gr.fig_gaches(vue),
            "fig_gaches",
        )

with temps:
    a, b = st.columns(2)
    with a:
        carte(
            "La pendule transforme mes fautes en gaffes",
            "Parmi mes fautes, la part de gaffes selon le temps qu'il me restait, par phase.",
            gr.fig_pendule(vue),
            "fig_pendule",
        )
        carte(
            "Comment finissent mes parties",
            "Part de chaque fin, pour mes victoires et mes défaites (nulles exclues).",
            gr.fig_fins(vue),
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
            gr.fig_temps_coup(vue, seulement),
            "fig_temps_coup",
        )
        carte(
            "Mon score selon l'heure (UTC)",
            "Heures d'au moins 30 parties. La ligne pointillée est mon score moyen.",
            gr.fig_heure(vue),
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
    carte(
        "Mon score par famille d'ouvertures, croisé",
        f"Rouge = je perds des points, bleu = j'en gagne. Familles d'au moins {n_min} parties "
        "(curseur de la barre latérale), case vide sous 10 parties. La pire famille en haut.",
        gr.fig_ouvertures(vue, axe, n_min),
        "fig_ouvertures",
    )
    carte(
        "Erreurs et gaffes par partie, selon leur nature",
        "Tactique laissée : mon coup offre une combinaison à l'adversaire. "
        "Tactique ratée : je ne vois pas la mienne.",
        gr.fig_natures(vue),
        "fig_natures",
    )


# ---------------------------------------------------------------- onglet « L'échiquier »


def tout_ou_rien(choix: list, toutes: list):
    """Tout coché = pas de filtre (None) : les coups sans pendule enregistrée restent comptés."""
    return None if set(choix) == set(toutes) else choix


def choisir_piece():
    """Clic sur une barre des pièces : l'échiquier ne montre plus que cette pièce.

    Un callback s'exécute avant la relance : on peut alors changer la valeur d'un widget.
    """
    points = st.session_state["fig_pieces"].selection.points
    if points:
        st.session_state["ech_pieces"] = [points[0]["y"]]


def toutes_les_pieces():
    st.session_state["ech_pieces"] = list(an.ORDRE_PIECES)


with echiquier:
    st.caption(
        "Ces filtres s'ajoutent à ceux de la barre latérale. Le graphique des pièces les suit "
        "tous sauf « Pièce », pour garder la comparaison entre pièces."
    )
    f1, f2, f3 = st.columns(3)
    familles_vues = vue["ouverture_famille"].value_counts().index.tolist()
    famille_choisie = f1.selectbox(
        "Famille d'ouvertures", ["toutes", *familles_vues], key="ech_famille"
    )
    resultats = f2.multiselect(
        "Résultat de la partie",
        ["victoire", "nulle", "défaite"],
        default=["victoire", "nulle", "défaite"],
        key="ech_resultats",
    )
    pendules = f3.multiselect(
        "Temps restant après le coup",
        an.PENDULE_ECHIQUIER_NOMS,
        default=an.PENDULE_ECHIQUIER_NOMS,
        key="ech_pendules",
    )
    f4, f5, f6 = st.columns(3)
    if "ech_pieces" not in st.session_state:
        st.session_state["ech_pieces"] = list(an.ORDRE_PIECES)
    pieces_choisies = f4.multiselect("Pièce", an.ORDRE_PIECES, key="ech_pieces")
    gravites = f5.multiselect(
        "Gravité",
        ["imprécision", "erreur", "gaffe"],
        default=["imprécision", "erreur", "gaffe"],
        key="ech_gravites",
    )
    phases_choisies = f6.multiselect(
        "Phase", an.ORDRE_PHASES, default=an.ORDRE_PHASES, key="ech_phases"
    )

    filtres = {
        "familles": None if famille_choisie == "toutes" else [famille_choisie],
        "resultats": tout_ou_rien(resultats, ["victoire", "nulle", "défaite"]),
        "pendules": tout_ou_rien(pendules, an.PENDULE_ECHIQUIER_NOMS),
        "gravites": tout_ou_rien(gravites, ["imprécision", "erreur", "gaffe"]),
        "phases": tout_ou_rien(phases_choisies, an.ORDRE_PHASES),
    }

    st.subheader("La pièce avec laquelle je fais le plus d'erreurs et de gaffes")
    st.caption(
        "Erreurs et gaffes par partie, la pire pièce en haut ; à droite de chaque barre, la part "
        "de gaffes. Cliquez une barre pour limiter l'échiquier à cette pièce."
    )
    st.plotly_chart(
        gr.fig_pieces(vue, **filtres),
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
    st.plotly_chart(
        gr.fig_echiquier(
            vue, mesure, pieces=tout_ou_rien(pieces_choisies, an.ORDRE_PIECES), **filtres
        ),
        key="fig_echiquier",
        theme=None,
        config={"displayModeBar": False},
    )
