import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from generate_mission import (
    FOOTBALL_COMPETITIONS,
    find_team_info,
    find_competition_info,
    load_json,
)

st.title("Promo Generator")

# ── Constants ────────────────────────────────────────────────────────────────

PROMO_TYPES = ["Double Up", "Wheel Up", "Mega Cart"]
RARITIES = ["limited", "rare", "super_rare", "unique"]

SPORTS = ["football", "mlb", "nba"]
SPORT_LABELS = {"football": "Football", "mlb": "MLB", "nba": "NBA"}
CONVERSION_CREDIT_SPORT = {"football": "FOOTBALL", "mlb": "BASEBALL", "nba": "NBA"}

ESSENCE_FLAVOURS = {
    "SEASONAL-GERMANY": "Bundesliga Essence",
    "SEASONAL-ENGLAND": "Premier League Essence",
    "SEASONAL-FRANCE": "Ligue 1 Essence",
    "SEASONAL-JUPILER": "Jupiler Essence",
    "SEASONAL-NETHERLANDS": "Eredivisie Essence",
    "SEASONAL-SPAIN": "LALIGA Essence",
    "SEASONAL-JAPAN": "J1 League Essence",
    "SEASONAL-KOREA": "K League 1 Essence",
    "SEASONAL-US": "MLS Essence",
    "SEASONAL-ITALY": "Serie A Essence",
}

CLUE_TYPES_BY_SPORT = {
    "football": [
        ("COUNTRY_CRAFT_CLUE", "Nationality"),
        ("COMPETITION_CRAFT_CLUE", "League"),
        ("FIFTY_FIFTY_CRAFT_CLUE", "Best Five"),
        ("BEST_STAR_RANK_CRAFT_CLUE", "Highest Tier"),
    ],
    "mlb": [
        ("FIFTY_FIFTY_CRAFT_CLUE", "Best Five"),
        ("DIVISION_CRAFT_CLUE", "Division"),
        ("POSITION_CRAFT_CLUE", "Position"),
    ],
    "nba": [
        ("BEST_STAR_RANK_CRAFT_CLUE", "Highest Tier"),
        ("FIFTY_FIFTY_CRAFT_CLUE", "Best Five"),
        ("DIVISION_CRAFT_CLUE", "Division"),
        ("POSITION_CRAFT_CLUE", "Position"),
    ],
}

TIER_KEYS = ["tier_0", "tier_1", "tier_2", "rest"]
TIER_LABELS = ["Tier 0", "Tier 1", "Tier 2", "Tier 3+"]

DEFAULT_CARD_PROBS = {
    "tier_0": [200, 200, 250, 350, 0, 0],
    "tier_1": [50, 100, 100, 350, 400, 0],
    "tier_2": [25, 50, 100, 325, 300, 200],
    "rest":   [10, 40, 100, 200, 300, 350],
}

DEFAULT_SHARD_PROB = 7000
DEFAULT_SHARD_QTY = {"tier_0": 250, "tier_1": 200, "tier_2": 150, "rest": 100}

DEFAULT_CLUE_PACKS = {
    "tier_0": [
        (400, [("COUNTRY_CRAFT_CLUE", 2), ("COMPETITION_CRAFT_CLUE", 2), ("FIFTY_FIFTY_CRAFT_CLUE", 1)]),
        (800, [("COMPETITION_CRAFT_CLUE", 10), ("COUNTRY_CRAFT_CLUE", 10), ("FIFTY_FIFTY_CRAFT_CLUE", 5)]),
        (800, [("COUNTRY_CRAFT_CLUE", 4), ("COMPETITION_CRAFT_CLUE", 4), ("FIFTY_FIFTY_CRAFT_CLUE", 2)]),
    ],
    "tier_1": [
        (600, [("COUNTRY_CRAFT_CLUE", 2), ("COMPETITION_CRAFT_CLUE", 2), ("FIFTY_FIFTY_CRAFT_CLUE", 1)]),
        (800, [("COMPETITION_CRAFT_CLUE", 4), ("COUNTRY_CRAFT_CLUE", 4), ("FIFTY_FIFTY_CRAFT_CLUE", 2)]),
        (600, [("FIFTY_FIFTY_CRAFT_CLUE", 5), ("COUNTRY_CRAFT_CLUE", 10), ("COMPETITION_CRAFT_CLUE", 10)]),
    ],
    "tier_2": [
        (800, [("COUNTRY_CRAFT_CLUE", 2), ("COMPETITION_CRAFT_CLUE", 2), ("FIFTY_FIFTY_CRAFT_CLUE", 1)]),
        (800, [("COMPETITION_CRAFT_CLUE", 4), ("COUNTRY_CRAFT_CLUE", 4), ("FIFTY_FIFTY_CRAFT_CLUE", 2)]),
        (400, [("FIFTY_FIFTY_CRAFT_CLUE", 5), ("COUNTRY_CRAFT_CLUE", 10), ("COMPETITION_CRAFT_CLUE", 10)]),
    ],
    "rest": [
        (800, [("COUNTRY_CRAFT_CLUE", 2), ("COMPETITION_CRAFT_CLUE", 2), ("FIFTY_FIFTY_CRAFT_CLUE", 1)]),
        (800, [("COMPETITION_CRAFT_CLUE", 4), ("COUNTRY_CRAFT_CLUE", 4), ("FIFTY_FIFTY_CRAFT_CLUE", 2)]),
        (400, [("FIFTY_FIFTY_CRAFT_CLUE", 5), ("COUNTRY_CRAFT_CLUE", 10), ("COMPETITION_CRAFT_CLUE", 10)]),
    ],
}

# XP and Conversion Credit defaults — start at 0 bp so existing 10000 totals stay valid
DEFAULT_XP_PROB = 0
DEFAULT_XP_AMOUNT = 100
DEFAULT_CC_PROB = 0
DEFAULT_CC_AMOUNT = 5            # dollars
DEFAULT_CC_DURATION = 30          # days
DEFAULT_CC_DISCOUNT_BP = 5000     # 50%

WHEEL_TICKET_CURRENCIES = {
    "limited": "WHEEL_TICKET",
    "rare": "RARE_WHEEL_TICKET",
    "super_rare": "SUPER_RARE_WHEEL_TICKET",
    "unique": "UNIQUE_WHEEL_TICKET",
}

# Mega Cart defaults: card probabilities per tier [T0, T1, T2, T3, T4, T5]
MC_DEFAULT_CARD_PROBS = {
    "mc_tier_0": [5000, 5000, 0, 0, 0, 0],
    "mc_tier_1": [2000, 3000, 2500, 500, 1000, 1000],
    "mc_tier_2": [1000, 3000, 3000, 1000, 1000, 1000],
    "mc_tier_3": [100, 900, 2000, 2000, 2500, 2500],
    "mc_tier_4": [100, 900, 2000, 2000, 2500, 2500],
    "mc_tier_5": [100, 900, 2000, 2000, 2500, 2500],
}
MC_TIER_KEYS = [f"mc_tier_{i}" for i in range(6)]
MC_TIER_LABELS = [f"Tier {i}" for i in range(6)]

# Mega Cart collections (per sport)
def _load_mega_cart_for_sport(sport):
    filename = "mega_cart_collections.json" if sport == "football" else f"mega_cart_collections_{sport}.json"
    try:
        return load_json(filename)
    except FileNotFoundError:
        return {}


def _mc_league_options(sport, collections):
    """Return {league_slug: display_name} for the Mega Cart league selector."""
    if sport == "football":
        return {
            comp["slug"]: comp["name"]
            for comp in FOOTBALL_COMPETITIONS
            if comp["slug"] in collections
        }
    # MLB / NBA: no curated competition list yet; use the slug as display name
    return {slug: slug.replace("-", " ").title() for slug in collections.keys()}


def _clue_key_index(clue_keys, clue_key):
    try:
        return clue_keys.index(clue_key)
    except ValueError:
        return 0


# ── 0. Sport & type de promo ─────────────────────────────────────────────────

col_sport, col_type = st.columns(2)
with col_sport:
    sport = st.selectbox("Sport", SPORTS, format_func=lambda s: SPORT_LABELS[s], key="promo_sport")
with col_type:
    promo_type = st.selectbox("Type de promo", PROMO_TYPES, key="promo_type")

# Per-sport clue setup
CLUE_TYPES = CLUE_TYPES_BY_SPORT[sport]
CLUE_KEYS = [k for k, _ in CLUE_TYPES]
CLUE_LABELS_MAP = dict(CLUE_TYPES)

# ══════════════════════════════════════════════════════════════════════════════
#  ÉLIGIBILITÉ
# ══════════════════════════════════════════════════════════════════════════════

st.header("1. Éligibilité")

rarities = st.multiselect("Raretés", RARITIES, default=["limited"], key="du_rarities")

# ── Mega Cart: eligibility by collections (football) ─────────────────────────

mc_team_slugs = []
mc_player_slugs = []
mc_elig_type = None

if promo_type == "Mega Cart" and sport == "football":
    mc_collections = _load_mega_cart_for_sport(sport)
    mc_league_options = _mc_league_options(sport, mc_collections)
    mc_collection_slugs = []
    mc_teams = []
    mc_league_slug = None
    season = ""
    cart_count = 5

    if not mc_league_options:
        st.warning("Aucune ligue configurée dans mega_cart_collections.json.")
    else:
        league_slugs = list(mc_league_options.keys())
        league_labels = [mc_league_options[s] for s in league_slugs]

        mc_league_idx = st.selectbox(
            "Ligue",
            range(len(league_slugs)),
            format_func=lambda i: league_labels[i],
            key="mc_league",
        )
        mc_league_slug = league_slugs[mc_league_idx]
        mc_teams = mc_collections[mc_league_slug]

        season = st.text_input("Saison", value="2026-27", key="mc_season")
        cart_count = int(st.number_input("Nombre min de cartes (cart_cards_count)", 1, 20, 5, key="mc_cart_count"))

        for team in mc_teams:
            for r in rarities:
                mc_collection_slugs.append(f"{team}-{r}-{season}")

        st.info(f"{len(mc_collection_slugs)} collections ({len(mc_teams)} équipes × {len(rarities)} raretés)")
        with st.expander("Voir les collections"):
            st.write(mc_collection_slugs)

# ── Mega Cart MLB/NBA: club / player filter (cart-amount based) ──────────────

elif promo_type == "Mega Cart":
    mc_elig_type = st.radio(
        "Critère d'éligibilité",
        ["Aucun", "Équipe", "Joueurs (CSV)"],
        key=f"mc_elig_type_{sport}",
        horizontal=True,
    )

    if mc_elig_type == "Équipe":
        num_teams = int(st.number_input("Nombre d'équipes", 1, 30, 1, key="mc_num_teams"))
        for i in range(num_teams):
            if i % 3 == 0:
                cols = st.columns(min(num_teams - i, 3))
            with cols[i % 3]:
                q = st.text_input(f"Équipe {i + 1}", key=f"mc_team_{i}")
                if q:
                    slug, name, _ = find_team_info(q, sport)
                    if slug:
                        st.success(f"✓ {name} (`{slug}`)")
                        mc_team_slugs.append(slug)
                    else:
                        st.error("Non trouvée")

    elif mc_elig_type == "Joueurs (CSV)":
        uploaded = st.file_uploader("CSV de slugs joueurs (un slug par ligne)", type=["csv"], key="mc_csv")
        if uploaded:
            content = uploaded.read().decode("utf-8")
            lines = [l.strip() for l in content.replace(",", "\n").split("\n") if l.strip()]
            if lines and "slug" in lines[0].lower():
                lines = lines[1:]
            mc_player_slugs = lines
            st.success(f"✓ {len(mc_player_slugs)} joueurs chargés")
            with st.expander("Voir les slugs"):
                st.write(mc_player_slugs)

# ── Double Up / Wheel Up: standard eligibility ───────────────────────────────

else:
    elig_options = ["Compétition", "Équipe", "Joueurs (CSV)"] if sport == "football" else ["Équipe", "Joueurs (CSV)"]
    elig_type = st.radio(
        "Critère d'éligibilité",
        elig_options,
        key=f"du_elig_type_{sport}",
        horizontal=True,
    )

comp_slugs = []
team_slugs = []
player_slugs = []

if promo_type != "Mega Cart":
    if elig_type == "Compétition":
        num_comps = int(st.number_input("Nombre de compétitions", 1, 10, 1, key="du_num_comps"))
        for i in range(num_comps):
            if i % 3 == 0:
                cols = st.columns(min(num_comps - i, 3))
            with cols[i % 3]:
                q = st.text_input(f"Compétition {i + 1}", key=f"du_comp_{i}")
                if q:
                    slug, name = find_competition_info(q)
                    if slug:
                        st.success(f"✓ {name} (`{slug}`)")
                        comp_slugs.append(slug)
                    else:
                        st.error("Non trouvée")

    elif elig_type == "Équipe":
        num_teams = int(st.number_input("Nombre d'équipes", 1, 30, 1, key="du_num_teams"))
        for i in range(num_teams):
            if i % 3 == 0:
                cols = st.columns(min(num_teams - i, 3))
            with cols[i % 3]:
                q = st.text_input(f"Équipe {i + 1}", key=f"du_team_{i}")
                if q:
                    slug, name, _ = find_team_info(q, sport)
                    if slug:
                        st.success(f"✓ {name} (`{slug}`)")
                        team_slugs.append(slug)
                    else:
                        st.error("Non trouvée")

    else:  # Joueurs (CSV)
        uploaded = st.file_uploader("CSV de slugs joueurs (un slug par ligne)", type=["csv"])
        if uploaded:
            content = uploaded.read().decode("utf-8")
            lines = [l.strip() for l in content.replace(",", "\n").split("\n") if l.strip()]
            if lines and "slug" in lines[0].lower():
                lines = lines[1:]
            player_slugs = lines
            st.success(f"✓ {len(player_slugs)} joueurs chargés")
            with st.expander("Voir les slugs"):
                st.write(player_slugs)

# ══════════════════════════════════════════════════════════════════════════════
#  REWARDS
# ══════════════════════════════════════════════════════════════════════════════

st.header("2. Rewards")


def _build_eligibility():
    elig = {"eligible_rarities": list(rarities)}
    if comp_slugs:
        elig["eligible_competitions"] = comp_slugs
    elif team_slugs:
        elig["eligible_teams"] = team_slugs
    elif player_slugs:
        elig["eligible_player_slugs"] = player_slugs
    return elig


def _validate_standard_elig():
    errors = []
    if not rarities:
        errors.append("Au moins une rareté requise.")
    if elig_type == "Compétition" and not comp_slugs:
        errors.append("Au moins une compétition requise.")
    if elig_type == "Équipe" and not team_slugs:
        errors.append("Au moins une équipe requise.")
    if elig_type == "Joueurs (CSV)" and not player_slugs:
        errors.append("CSV de joueurs requis.")
    return errors


# ══════════════════════════════════════════════════════════════════════════════
#  DOUBLE UP
# ══════════════════════════════════════════════════════════════════════════════

if promo_type == "Double Up":
    domestic_league = st.toggle("Card from domestic league", value=True, key="du_domestic")

    flavour = None
    if sport == "football":
        detected_flavour = None
        if comp_slugs:
            for comp in FOOTBALL_COMPETITIONS:
                if comp["slug"] == comp_slugs[0]:
                    detected_flavour = comp.get("flavour")
                    break

        flavour_options = list(ESSENCE_FLAVOURS.keys())
        default_flav_idx = 0
        if detected_flavour and detected_flavour in flavour_options:
            default_flav_idx = flavour_options.index(detected_flavour)

        flavour = st.selectbox(
            "Flavour Essence",
            flavour_options,
            index=default_flav_idx,
            format_func=lambda x: f"{x} — {ESSENCE_FLAVOURS[x]}",
        )

    st.divider()

    tabs = st.tabs(TIER_LABELS)

    for tier_idx, tab in enumerate(tabs):
        tk = TIER_KEYS[tier_idx]
        with tab:
            st.markdown("**Cartes**")
            card_cols = st.columns(6)
            for ct in range(6):
                with card_cols[ct]:
                    st.number_input(
                        f"T{ct}", min_value=0, max_value=10000,
                        value=DEFAULT_CARD_PROBS[tk][ct], step=25,
                        key=f"du_cp_{tk}_{ct}",
                    )
                    bp = st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct])
                    if bp > 0:
                        st.caption(f"{bp / 100:.2f}%")

            st.markdown("**Essence**")
            ess_c1, ess_c2 = st.columns(2)
            with ess_c1:
                st.number_input(
                    "Probabilité (bp)", min_value=0, max_value=10000,
                    value=DEFAULT_SHARD_PROB, step=100,
                    key=f"du_sp_{tk}",
                )
                sp_val = st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
                if sp_val > 0:
                    st.caption(f"{sp_val / 100:.2f}%")
            with ess_c2:
                st.number_input(
                    "Quantité", min_value=0, max_value=1000,
                    value=DEFAULT_SHARD_QTY[tk], step=25,
                    key=f"du_sq_{tk}",
                )

            st.markdown("**Packs de clues**")
            clue_cols = st.columns(3)
            for pi in range(3):
                with clue_cols[pi]:
                    st.number_input(
                        f"Pack {pi + 1}", min_value=0, max_value=10000,
                        value=DEFAULT_CLUE_PACKS[tk][pi][0], step=25,
                        key=f"du_clp_{tk}_{pi}",
                    )
                    clp_val = st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0])
                    if clp_val > 0:
                        st.caption(f"{clp_val / 100:.2f}%")

            st.markdown("**XP**")
            xp_c1, xp_c2 = st.columns(2)
            with xp_c1:
                st.number_input(
                    "Probabilité (bp)", min_value=0, max_value=10000,
                    value=DEFAULT_XP_PROB, step=100,
                    key=f"du_xpp_{tk}",
                )
                xpp_val = st.session_state.get(f"du_xpp_{tk}", DEFAULT_XP_PROB)
                if xpp_val > 0:
                    st.caption(f"{xpp_val / 100:.2f}%")
            with xp_c2:
                st.number_input(
                    "Quantité (XP)", min_value=0, max_value=100000,
                    value=DEFAULT_XP_AMOUNT, step=50,
                    key=f"du_xpq_{tk}",
                )

            st.markdown("**Conversion Credit**")
            cc_c1, cc_c2, cc_c3, cc_c4 = st.columns(4)
            with cc_c1:
                st.number_input(
                    "Probabilité (bp)", min_value=0, max_value=10000,
                    value=DEFAULT_CC_PROB, step=100,
                    key=f"du_ccp_{tk}",
                )
                ccp_val = st.session_state.get(f"du_ccp_{tk}", DEFAULT_CC_PROB)
                if ccp_val > 0:
                    st.caption(f"{ccp_val / 100:.2f}%")
            with cc_c2:
                st.number_input(
                    "Montant ($)", min_value=1, max_value=10000,
                    value=DEFAULT_CC_AMOUNT, step=1,
                    key=f"du_cca_{tk}",
                )
            with cc_c3:
                st.number_input(
                    "Durée (j)", min_value=1, max_value=365,
                    value=DEFAULT_CC_DURATION, step=1,
                    key=f"du_ccd_{tk}",
                )
            with cc_c4:
                st.number_input(
                    "Discount (bp)", min_value=0, max_value=10000,
                    value=DEFAULT_CC_DISCOUNT_BP, step=100,
                    key=f"du_ccdbp_{tk}",
                )

            total = sum(st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            total += st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
            total += sum(st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0]) for pi in range(3))
            total += st.session_state.get(f"du_xpp_{tk}", DEFAULT_XP_PROB)
            total += st.session_state.get(f"du_ccp_{tk}", DEFAULT_CC_PROB)

            if total == 10000:
                st.success(f"Total : {total}/10000")
            else:
                st.error(f"Total : {total}/10000")

            with st.expander("Détail des clues"):
                for pi in range(3):
                    st.caption(f"Pack {pi + 1}")
                    dc = st.columns(3)
                    for ci in range(3):
                        default_pack = DEFAULT_CLUE_PACKS[tk][pi][1]
                        # Default key may not exist for current sport (e.g. football defaults vs MLB clues)
                        if ci < len(default_pack) and default_pack[ci][0] in CLUE_KEYS:
                            def_key = default_pack[ci][0]
                            def_amt = default_pack[ci][1]
                        else:
                            def_key = CLUE_KEYS[0]
                            def_amt = 1
                        with dc[ci]:
                            st.selectbox(
                                "Type", CLUE_KEYS,
                                index=_clue_key_index(CLUE_KEYS, def_key),
                                format_func=lambda x: CLUE_LABELS_MAP[x],
                                key=f"du_clt_{tk}_{pi}_{ci}_{sport}",
                            )
                            st.number_input(
                                "Qté", min_value=0, max_value=100,
                                value=def_amt, step=1,
                                key=f"du_cla_{tk}_{pi}_{ci}_{sport}",
                            )

    st.divider()

    if st.button("Générer les JSONs", type="primary"):
        errors = _validate_standard_elig()

        for ti in range(4):
            tk = TIER_KEYS[ti]
            t = sum(st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            t += st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
            t += sum(st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0]) for pi in range(3))
            t += st.session_state.get(f"du_xpp_{tk}", DEFAULT_XP_PROB)
            t += st.session_state.get(f"du_ccp_{tk}", DEFAULT_CC_PROB)
            if t != 10000:
                errors.append(f"{TIER_LABELS[ti]} : total {t} ≠ 10000")

        if errors:
            for e in errors:
                st.error(e)
        else:
            eligibility = _build_eligibility()

            reward = {
                "card_from_domestic_league": domestic_league,
                "rewards": [],
            }

            cc_sport = CONVERSION_CREDIT_SPORT[sport]

            for rarity in rarities:
                for ti in range(4):
                    tk = TIER_KEYS[ti]
                    conditions = {"rarity": rarity}
                    if ti < 3:
                        conditions["card_tier"] = f"tier_{ti}"

                    probable_rewards = []

                    for ct in range(6):
                        prob = st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct])
                        if prob > 0:
                            probable_rewards.append({
                                "probability_basis_point": prob,
                                "cards": [{"rarity": rarity, "tier": ct}],
                            })

                    sp = st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
                    sq = st.session_state.get(f"du_sq_{tk}", DEFAULT_SHARD_QTY[tk])
                    if sp > 0:
                        shard_entry = {"rarity": rarity, "quantity": sq}
                        if flavour:
                            shard_entry["flavour"] = flavour
                        probable_rewards.append({
                            "probability_basis_point": sp,
                            "card_shards": [shard_entry],
                        })

                    for pi in range(3):
                        cp = st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0])
                        if cp > 0:
                            currencies = []
                            default_pack = DEFAULT_CLUE_PACKS[tk][pi][1]
                            for ci in range(3):
                                if ci < len(default_pack) and default_pack[ci][0] in CLUE_KEYS:
                                    def_key = default_pack[ci][0]
                                    def_amt = default_pack[ci][1]
                                else:
                                    def_key = CLUE_KEYS[0]
                                    def_amt = 1
                                ctype = st.session_state.get(f"du_clt_{tk}_{pi}_{ci}_{sport}", def_key)
                                camount = st.session_state.get(f"du_cla_{tk}_{pi}_{ci}_{sport}", def_amt)
                                if camount > 0:
                                    currencies.append({"currency": ctype, "amount": camount})
                            if currencies:
                                probable_rewards.append({
                                    "probability_basis_point": cp,
                                    "in_game_currencies": currencies,
                                })

                    xp_prob = st.session_state.get(f"du_xpp_{tk}", DEFAULT_XP_PROB)
                    xp_amount = st.session_state.get(f"du_xpq_{tk}", DEFAULT_XP_AMOUNT)
                    if xp_prob > 0 and xp_amount > 0:
                        probable_rewards.append({
                            "probability_basis_point": xp_prob,
                            "in_game_currencies": [{
                                "currency": f"{rarity.upper()}_XP",
                                "amount": xp_amount,
                            }],
                        })

                    cc_prob = st.session_state.get(f"du_ccp_{tk}", DEFAULT_CC_PROB)
                    cc_amount = st.session_state.get(f"du_cca_{tk}", DEFAULT_CC_AMOUNT)
                    cc_duration = st.session_state.get(f"du_ccd_{tk}", DEFAULT_CC_DURATION)
                    cc_discount_bp = st.session_state.get(f"du_ccdbp_{tk}", DEFAULT_CC_DISCOUNT_BP)
                    if cc_prob > 0 and cc_amount > 0:
                        probable_rewards.append({
                            "probability_basis_point": cc_prob,
                            "conversion_credit": {
                                "sport": cc_sport,
                                "max_discount": {
                                    "reference_currency": "CURRENCY_USD",
                                    "amounts": [{"currency": "CURRENCY_USD", "amount": cc_amount * 100}],
                                },
                                "duration_in_days": cc_duration,
                                "single_use": False,
                                "percentage_discount_basis_point": cc_discount_bp,
                            },
                        })

                    reward["rewards"].append({
                        "conditions": conditions,
                        "probable_rewards": probable_rewards,
                    })

            col_e, col_r = st.columns(2)
            with col_e:
                st.caption("eligibility.json")
                st.code(json.dumps(eligibility, indent=2, ensure_ascii=False), language="json")
            with col_r:
                st.caption("reward.json")
                st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

# ══════════════════════════════════════════════════════════════════════════════
#  WHEEL UP
# ══════════════════════════════════════════════════════════════════════════════

elif promo_type == "Wheel Up":
    st.info("Chaque achat de carte éligible offre un Wheel Ticket (100%).")

    st.divider()

    if st.button("Générer les JSONs", type="primary"):
        errors = _validate_standard_elig()

        if errors:
            for e in errors:
                st.error(e)
        else:
            eligibility = _build_eligibility()

            st.caption("eligibility.json")
            st.code(json.dumps(eligibility, indent=2, ensure_ascii=False), language="json")

            for rarity in rarities:
                reward = {
                    "rewards": [
                        {
                            "probable_rewards": [
                                {
                                    "probability_basis_point": 10000,
                                    "in_game_currencies": [
                                        {
                                            "currency": WHEEL_TICKET_CURRENCIES[rarity],
                                            "amount": 1,
                                        }
                                    ],
                                }
                            ]
                        }
                    ]
                }
                rarity_label = rarity.replace("_", " ").title()
                st.caption(f"reward.json — {rarity_label}")
                st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

# ══════════════════════════════════════════════════════════════════════════════
#  MEGA CART
# ══════════════════════════════════════════════════════════════════════════════

elif promo_type == "Mega Cart" and sport == "football":
    st.info("Rewards = cartes uniquement. Tiers 0-2 par rareté, Tiers 3-5 en DYNAMIC (rareté auto).")

    st.divider()

    # ── Reward config per tier ───────────────────────────────────────────
    tabs = st.tabs(MC_TIER_LABELS)

    for tier_idx, tab in enumerate(tabs):
        tk = MC_TIER_KEYS[tier_idx]
        with tab:
            if tier_idx >= 3:
                st.caption("DYNAMIC — la rareté de la reward s'adapte à la carte achetée")

            st.markdown("**Cartes** (probabilité par tier)")
            card_cols = st.columns(6)
            for ct in range(6):
                with card_cols[ct]:
                    st.number_input(
                        f"T{ct}", min_value=0, max_value=10000,
                        value=MC_DEFAULT_CARD_PROBS[tk][ct], step=25,
                        key=f"mc_cp_{tk}_{ct}",
                    )
                    bp = st.session_state.get(f"mc_cp_{tk}_{ct}", MC_DEFAULT_CARD_PROBS[tk][ct])
                    if bp > 0:
                        st.caption(f"{bp / 100:.2f}%")

            total = sum(st.session_state.get(f"mc_cp_{tk}_{ct}", MC_DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            if total == 10000:
                st.success(f"Total : {total}/10000")
            else:
                st.error(f"Total : {total}/10000")

    # ── Generate Mega Cart ───────────────────────────────────────────────
    st.divider()

    if st.button("Générer les JSONs", type="primary"):
        errors = []
        if not rarities:
            errors.append("Au moins une rareté requise.")
        if not mc_league_options:
            errors.append("Aucune ligue configurée.")
        if not mc_collection_slugs:
            errors.append("Aucune collection — sélectionne une ligue.")

        for ti in range(6):
            tk = MC_TIER_KEYS[ti]
            t = sum(st.session_state.get(f"mc_cp_{tk}_{ct}", MC_DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            if t != 10000:
                errors.append(f"Tier {ti} : total {t} ≠ 10000")

        if errors:
            for e in errors:
                st.error(e)
        else:
            # ── Eligibility JSON ─────────────────────────────────────────
            eligibility = {
                "eligible_collections": {
                    "card_collections": mc_collection_slugs,
                    "cart_cards_count": cart_count,
                }
            }

            # ── Reward JSON ──────────────────────────────────────────────
            reward = {"rewards": []}

            # Tiers 0-2: per rarity
            for ti in range(3):
                tk = MC_TIER_KEYS[ti]
                for rarity in rarities:
                    conditions = {"card_tier": f"tier_{ti}", "rarity": rarity}
                    probable_rewards = []
                    for ct in range(6):
                        prob = st.session_state.get(f"mc_cp_{tk}_{ct}", MC_DEFAULT_CARD_PROBS[tk][ct])
                        if prob > 0:
                            probable_rewards.append({
                                "probability_basis_point": prob,
                                "cards": [{"rarity": rarity.upper(), "tier": ct}],
                            })
                    reward["rewards"].append({
                        "conditions": conditions,
                        "probable_rewards": probable_rewards,
                    })

            # Tiers 3-5: DYNAMIC (no rarity condition)
            for ti in range(3, 6):
                tk = MC_TIER_KEYS[ti]
                conditions = {"card_tier": f"tier_{ti}"}
                probable_rewards = []
                for ct in range(6):
                    prob = st.session_state.get(f"mc_cp_{tk}_{ct}", MC_DEFAULT_CARD_PROBS[tk][ct])
                    if prob > 0:
                        probable_rewards.append({
                            "probability_basis_point": prob,
                            "cards": [{"rarity": "DYNAMIC", "tier": ct}],
                        })
                reward["rewards"].append({
                    "conditions": conditions,
                    "probable_rewards": probable_rewards,
                })

            # ── Display ──────────────────────────────────────────────────
            col_e, col_r = st.columns(2)
            with col_e:
                st.caption("eligibility.json")
                st.code(json.dumps(eligibility, indent=2, ensure_ascii=False), language="json")
            with col_r:
                st.caption("reward.json")
                st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

# ══════════════════════════════════════════════════════════════════════════════
#  MEGA CART — MLB / NBA (cart amount → conversion credit)
# ══════════════════════════════════════════════════════════════════════════════

elif promo_type == "Mega Cart":
    st.info("Pour chaque palier de panier (en $), accorde un Conversion Credit (100%).")

    DEFAULT_MC_CC_TIERS = [
        (20, 5), (50, 15), (100, 30), (200, 60), (500, 150), (1000, 300),
    ]

    num_tiers = int(st.number_input(
        "Nombre de paliers", min_value=1, max_value=15,
        value=len(DEFAULT_MC_CC_TIERS), step=1,
        key="mc_cc_num_tiers",
    ))

    cc_duration = int(st.number_input(
        "Durée du crédit (jours)", min_value=1, max_value=365,
        value=DEFAULT_CC_DURATION, step=1,
        key="mc_cc_duration",
    ))
    cc_discount_bp = int(st.number_input(
        "Discount (bp)", min_value=0, max_value=10000,
        value=DEFAULT_CC_DISCOUNT_BP, step=100,
        key="mc_cc_discount_bp",
    ))

    st.markdown("**Paliers** (montant panier → crédit accordé, en $)")
    tiers = []
    for i in range(num_tiers):
        if i % 3 == 0:
            cols = st.columns(min(num_tiers - i, 3))
        with cols[i % 3]:
            default_thresh, default_credit = DEFAULT_MC_CC_TIERS[i] if i < len(DEFAULT_MC_CC_TIERS) else (0, 0)
            thresh = int(st.number_input(
                f"Palier {i + 1} — Panier $",
                min_value=1, max_value=100000,
                value=default_thresh if default_thresh else 20,
                step=10, key=f"mc_cc_th_{i}",
            ))
            credit = int(st.number_input(
                f"Palier {i + 1} — Crédit $",
                min_value=1, max_value=100000,
                value=default_credit if default_credit else 5,
                step=5, key=f"mc_cc_cr_{i}",
            ))
            tiers.append((thresh, credit))

    st.divider()

    if st.button("Générer les JSONs", type="primary"):
        errors = []
        thresholds = [t[0] for t in tiers]
        if len(set(thresholds)) != len(thresholds):
            errors.append("Les paliers doivent avoir des montants distincts.")
        if not tiers:
            errors.append("Au moins un palier requis.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            sorted_tiers = sorted(tiers, key=lambda t: t[0])
            min_threshold_cents = sorted_tiers[0][0] * 100
            cc_sport = CONVERSION_CREDIT_SPORT[sport]

            # ── Eligibility JSON ─────────────────────────────────────────
            eligibility = {"eligible_cart_amount_in_usd_cents": min_threshold_cents}
            if rarities:
                eligibility["eligible_rarities"] = list(rarities)
            if mc_team_slugs:
                eligibility["eligible_teams"] = mc_team_slugs
            if mc_player_slugs:
                eligibility["eligible_player_slugs"] = mc_player_slugs

            # ── Reward JSON ──────────────────────────────────────────────
            reward = {"rewards": []}
            for thresh_dollars, credit_dollars in sorted_tiers:
                reward["rewards"].append({
                    "conditions": {"cart_amount_in_usd_cents": thresh_dollars * 100},
                    "probable_rewards": [
                        {
                            "probability_basis_point": 10000,
                            "conversion_credit": {
                                "max_discount": {
                                    "reference_currency": "CURRENCY_USD",
                                    "amounts": [
                                        {"currency": "CURRENCY_USD", "amount": credit_dollars * 100}
                                    ],
                                },
                                "duration_in_days": cc_duration,
                                "single_use": False,
                                "percentage_discount_basis_point": cc_discount_bp,
                                "sport": cc_sport,
                            },
                        }
                    ],
                })

            col_e, col_r = st.columns(2)
            with col_e:
                st.caption("eligibility.json")
                st.code(json.dumps(eligibility, indent=2, ensure_ascii=False), language="json")
            with col_r:
                st.caption("reward.json")
                st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")
