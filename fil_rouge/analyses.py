"""Les agrégats du dashboard : pourquoi je stagne, et quoi travailler.

Chaque fonction reçoit les parties déjà filtrées (load_data puis filtres du dashboard)
et renvoie un petit DataFrame prêt pour une figure. Rien n'est calculé côté navigateur.
Lancer : uv run python fil_rouge/analyses.py   (imprime chaque agrégat)
"""

from functools import lru_cache

import pandas as pd

from data import DATA, load_coups, load_data

PHASES = {"opening": "ouverture", "middlegame": "milieu", "endgame": "finale"}
ORDRE_PHASES = list(PHASES.values())
TRANCHES = ["0-5 h", "6-11 h", "12-17 h", "18-23 h"]
PENDULE = [0, 10, 20, 30, 60, 120, float("inf")]
PENDULE_NOMS = ["< 10 s", "10-20 s", "20-30 s", "30-60 s", "1-2 min", "> 2 min"]
FINS = {
    "resign": "abandon",
    "checkmate": "mat",
    "timeout": "temps écoulé",
    "draw": "nulle",
    "other": "autre",
}
FAUTES = {
    "strategic": "stratégique",
    "allowed_tactic": "tactique laissée à l'adversaire",
    "missed_tactic": "tactique ratée",
}
SEUIL_GAGNANT = 300  # cp : à +3, la partie est gagnée (conseils.md, section 9)


# Les fichiers ne changent pas pendant la journée : lus une fois par processus, à la demande.
@lru_cache(maxsize=1)
def parties() -> pd.DataFrame:
    return load_data()


@lru_cache(maxsize=1)
def coups() -> pd.DataFrame:
    c = load_coups()
    c["phase"] = c["phase"].map(PHASES)
    return c


@lru_cache(maxsize=1)
def phases() -> pd.DataFrame:
    p = pd.read_csv(DATA / "phases.csv")
    p = p[p["phase"].isin(PHASES)].copy()  # opening_theory est incluse dans opening
    p["phase"] = p["phase"].map(PHASES)
    return p


@lru_cache(maxsize=1)
def moments() -> pd.DataFrame:
    m = pd.read_csv(DATA / "moments_critiques.csv")
    m["phase"] = m["phase"].map(PHASES)
    return m


def filtrer(
    df, plateformes=None, cadence=None, couleur=None, annees=None, periode=None
) -> pd.DataFrame:
    """Les parties qui passent les filtres, communs à Dash et Streamlit.

    plateformes : liste (None = toutes). cadence : une cadence, une liste, ou "toutes".
    couleur : "white", "black" ou "toutes". annees : (début, fin) en années.
    periode : (date de début, date de fin), bornes comprises.
    """
    out = df
    if plateformes is not None:
        out = out[out["plateforme"].isin(plateformes)]
    if isinstance(cadence, str) and cadence != "toutes":
        out = out[out["cadence"] == cadence]
    elif isinstance(cadence, list | tuple):
        out = out[out["cadence"].isin(cadence)]
    if couleur and couleur != "toutes":
        out = out[out["couleur"] == couleur]
    if annees:
        out = out[out["annee"].between(annees[0], annees[1])]
    if periode:
        out = out[out["date_jeu"].dt.date.between(periode[0], periode[1])]
    return out


def tranche_horaire(heure: pd.Series) -> pd.Series:
    return pd.Categorical(
        pd.Series(heure).floordiv(6).map(dict(enumerate(TRANCHES))), TRANCHES, ordered=True
    )


def de(table: pd.DataFrame, df: pd.DataFrame) -> pd.DataFrame:
    """Les lignes de table qui appartiennent aux parties filtrées."""
    return table[table["partie_id"].isin(df["partie_id"])]


# ---------------------------------------------------------------- indicateurs


def kpis(df: pd.DataFrame) -> dict:
    n = df["partie_id"].nunique()
    if n == 0:
        return {}
    gagnantes = avantages_gaches(df)
    tot_gagnantes = gagnantes["parties"].sum()
    perdues = gagnantes.loc[gagnantes["resultat"] != "victoire", "parties"].sum()
    defaites = df[df["resultat"] == "défaite"]
    return {
        "parties": n,
        "score": df["score"].mean(),
        "elo": tendance_elo(df),
        "gaffes": df["gaffes_joueur"].mean(),
        "temps": (defaites["fin_partie"] == "timeout").mean() if len(defaites) else None,
        "gaches": perdues / tot_gagnantes if tot_gagnantes else None,
        "n_gagnantes": int(tot_gagnantes),
    }


def tendance_elo(df: pd.DataFrame) -> dict | None:
    """Série la plus jouée : médiane des 6 derniers mois contre les 6 mois d'avant."""
    d = df.dropna(subset=["elo_joueur"])
    d = d[d["cadence"] != "aucune"]
    if d.empty:
        return None
    serie = d.groupby(["plateforme", "cadence"]).size().idxmax()
    s = d[(d["plateforme"] == serie[0]) & (d["cadence"] == serie[1])]
    fin = s["date_jeu"].max()
    recent = s[s["date_jeu"] > fin - pd.DateOffset(months=6)]["elo_joueur"]
    avant = s[s["date_jeu"].between(fin - pd.DateOffset(months=12), fin - pd.DateOffset(months=6))]
    if recent.empty or avant.empty:
        return {"serie": f"{serie[0]} · {serie[1]}", "actuel": recent.median(), "delta": None}
    return {
        "serie": f"{serie[0]} · {serie[1]}",
        "actuel": recent.median(),
        "delta": recent.median() - avant["elo_joueur"].median(),
    }


# ---------------------------------------------------------------- figures


def courbe_elo(df: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """Elo médian par mois, une ligne par plateforme et cadence (jamais comparables entre elles)."""
    d = df.dropna(subset=["elo_joueur"])
    d = d[d["cadence"] != "aucune"].assign(
        serie=lambda x: x["plateforme"] + " · " + x["cadence"],
        mois=lambda x: x["date_jeu"].dt.to_period("M").dt.to_timestamp(),
    )
    gardees = d["serie"].value_counts().loc[lambda s: s >= min_n].index
    return (
        d[d["serie"].isin(gardees)]
        .groupby(["serie", "mois"])
        .agg(elo=("elo_joueur", "median"), parties=("partie_id", "nunique"))
        .reset_index()
    )


def gaffes_dans_le_temps(df: pd.DataFrame, min_parties: int = 30) -> pd.DataFrame:
    """Gaffes pour 10 coups joués, par phase et par trimestre (phases.csv compte des demi-coups)."""
    p = de(phases(), df).merge(df[["partie_id", "date_jeu"]], on="partie_id")
    p = p[p["nb_coups"] > 0].assign(
        trimestre=lambda x: x["date_jeu"].dt.to_period("Q").dt.start_time
    )
    g = (
        p.groupby(["trimestre", "phase"])
        .agg(
            gaffes=("gaffes_joueur", "sum"),
            demi=("nb_coups", "sum"),
            parties=("partie_id", "nunique"),
        )
        .reset_index()
    )
    g["taux"] = 20 * g["gaffes"] / g["demi"]
    return g[g["parties"] >= min_parties]


def pendule(df: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    """Part de gaffes parmi mes fautes, selon le temps qu'il me restait, par phase."""
    avec_pendule = df[df["temps_initial_s"] > 0]
    c = de(coups(), avec_pendule).dropna(subset=["temps_restant_s"])
    c = c.assign(
        pendule=pd.cut(c["temps_restant_s"], PENDULE, right=False, labels=PENDULE_NOMS),
        gaffe=c["jugement"].eq("blunder"),
    )
    g = (
        c.groupby(["phase", "pendule"], observed=True)
        .agg(part=("gaffe", "mean"), fautes=("gaffe", "size"))
        .reset_index()
    )
    return g[g["fautes"] >= min_n]


def temps_par_coup(df: pd.DataFrame, seulement="toutes") -> pd.DataFrame:
    """Temps moyen par coup, moi contre l'adversaire, dans chaque phase."""
    if seulement == "timeout":
        df = df[(df["resultat"] == "défaite") & (df["fin_partie"] == "timeout")]
    elif seulement in ("victoire", "défaite"):
        df = df[df["resultat"] == seulement]
    p = de(phases(), df)
    g = p.groupby("phase").agg(
        moi=("temps_moyen_joueur_s", "mean"),
        adversaire=("temps_moyen_adverse_s", "mean"),
        parties=("partie_id", "nunique"),
    )
    g = g.reindex(ORDRE_PHASES).dropna(how="all").reset_index()
    return g.melt(id_vars=["phase", "parties"], var_name="joueur", value_name="secondes")


def ouvertures_croisees(df: pd.DataFrame, axe: str, min_n: int = 30, min_case: int = 10):
    """Score par famille d'ouvertures croisée avec la couleur, la tranche horaire ou l'année.

    Renvoie (score, n) : deux tableaux familles x colonnes. Une case de moins de min_case
    parties est vide, une famille de moins de min_n parties est écartée.
    """
    d = df.dropna(subset=["ouverture_famille"]).copy()
    if axe == "tranche":
        d["col"] = tranche_horaire(d["heure"])
    elif axe == "couleur":
        d["col"] = d["couleur"].map({"white": "avec les blancs", "black": "avec les noirs"})
    else:
        d["col"] = d["annee"]
    tot = d.groupby("ouverture_famille")["score"].agg(["mean", "size"])
    tot = tot[tot["size"] >= min_n].sort_values("mean")
    d = d[d["ouverture_famille"].isin(tot.index)]
    g = d.groupby(["ouverture_famille", "col"], observed=True)["score"].agg(["mean", "size"])
    score = g["mean"].where(g["size"] >= min_case).unstack().reindex(tot.index)
    n = g["size"].unstack().reindex(tot.index).fillna(0).astype(int)
    score.insert(0, "toutes", tot["mean"])
    n.insert(0, "toutes", tot["size"])
    return score, n


def avantages_gaches(df: pd.DataFrame) -> pd.DataFrame:
    """Parties où j'étais à +3 avant une grosse faute : la phase de cette faute, et la fin."""
    m = de(moments(), df)
    m = m[m["eval_avant_cp"] >= SEUIL_GAGNANT].sort_values("ply")
    premiere = m.groupby("partie_id", as_index=False).first()
    premiere = premiere.merge(df[["partie_id", "resultat"]], on="partie_id")
    return premiere.groupby(["phase", "resultat"]).size().rename("parties").reset_index()


def types_fautes(df: pd.DataFrame) -> pd.DataFrame:
    """Erreurs et gaffes par partie, par phase et par nature de la faute."""
    n = df["partie_id"].nunique()
    c = de(coups(), df)
    c = c[c["jugement"].isin(["mistake", "blunder"])]
    nature = c["sous_type"].fillna(c["categorie"]).map(FAUTES)
    g = c.assign(nature=nature).groupby(["phase", "nature"]).size().rename("fautes").reset_index()
    g["par_partie"] = g["fautes"] / max(n, 1)
    return g


PIECES = {"K": "roi", "Q": "dame", "R": "tour", "B": "fou", "N": "cavalier"}
ORDRE_PIECES = ["pion", "cavalier", "fou", "tour", "dame", "roi"]
JUGEMENTS = {"inaccuracy": "imprécision", "mistake": "erreur", "blunder": "gaffe"}
COLONNES_ECHIQUIER = "abcdefgh"


def case_arrivee(coups_san: pd.Series, couleur: pd.Series) -> pd.Series:
    """La case où arrive la pièce, lue dans la notation : Nxe5 -> e5, e8=Q+ -> e8.

    Le roque n'a pas de case écrite : O-O va en g1 (g8 avec les noirs), O-O-O en c1 (c8).
    """
    case = coups_san.str.findall(r"[a-h][1-8]").str[-1]
    rangee = couleur.map({"white": "1", "black": "8"})
    grand = coups_san.str.startswith("O-O-O")
    petit = coups_san.str.startswith("O-O") & ~grand
    case = case.mask(petit, "g" + rangee).mask(grand, "c" + rangee)
    return case


def piece_jouee(coups_san: pd.Series) -> pd.Series:
    """La pièce qui bouge : la première lettre (N, B, R, Q, K), un pion sinon, le roi pour le roque."""
    premiere = coups_san.str[0]
    return premiere.map(PIECES).mask(premiere == "O", "roi").fillna("pion")


def fautes_par_case(df, pieces=None, gravites=None, phases=None) -> pd.DataFrame:
    """Mes coups jugés mauvais comptés par case d'arrivée, séparés par la couleur jouée.

    Colonnes : couleur, case, colonne (a-h), rangee (1-8), fautes, gaffes, part_gaffes,
    perte (cp moyens), piece_top (la pièce la plus souvent fautive sur cette case).
    """
    c = de(coups(), df)
    c = c.assign(piece=piece_jouee(c["coup"]), gravite=c["jugement"].map(JUGEMENTS))
    if pieces is not None:
        c = c[c["piece"].isin(pieces)]
    if gravites is not None:
        c = c[c["gravite"].isin(gravites)]
    if phases is not None:
        c = c[c["phase"].isin(phases)]
    c = c.assign(case=case_arrivee(c["coup"], c["couleur"])).dropna(subset=["case"])
    if c.empty:
        return pd.DataFrame(
            columns=["couleur", "case", "colonne", "rangee", "fautes", "gaffes", "part_gaffes"]
        )
    g = (
        c.groupby(["couleur", "case"])
        .agg(
            fautes=("coup", "size"),
            gaffes=("jugement", lambda j: (j == "blunder").sum()),
            perte=("variation_eval_cp", "median"),  # médiane : quelques pertes énormes (mats)
            piece_top=("piece", lambda p: p.value_counts().index[0]),
        )
        .reset_index()
    )
    g["part_gaffes"] = g["gaffes"] / g["fautes"]
    g["colonne"] = g["case"].str[0]
    g["rangee"] = g["case"].str[1].astype(int)
    return g


def fins_de_partie(df: pd.DataFrame) -> pd.DataFrame:
    """Comment se terminent mes défaites et mes victoires."""
    d = df[df["resultat"] != "nulle"]
    g = d.groupby(["resultat", "fin_partie"]).size().rename("parties").reset_index()
    g["fin"] = g["fin_partie"].map(FINS)
    g["part"] = g["parties"] / g.groupby("resultat")["parties"].transform("sum")
    return g


def score_par_heure(df: pd.DataFrame, min_n: int = 30) -> pd.DataFrame:
    g = df.groupby("heure").agg(score=("score", "mean"), parties=("partie_id", "nunique"))
    return g[g["parties"] >= min_n].reset_index()


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    blitz = filtrer(parties(), ["chesscom", "lichess"], "blitz", "toutes", (2023, 2026))
    print(kpis(blitz))
    for f in (
        courbe_elo,
        gaffes_dans_le_temps,
        pendule,
        temps_par_coup,
        avantages_gaches,
        types_fautes,
        fins_de_partie,
        score_par_heure,
    ):
        print(f"\n== {f.__name__}\n", f(blitz).head(12))
    s, n = ouvertures_croisees(blitz, "couleur")
    print(s.round(2))
