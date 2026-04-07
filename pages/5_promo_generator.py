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

PROMO_TYPES = ["Double Up", "Wheel Up", "Lucky Loser", "Mega Cart"]
RARITIES = ["limited", "rare", "super_rare", "unique"]

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

CLUE_TYPES = [
    ("COUNTRY_CRAFT_CLUE", "Nationality"),
    ("COMPETITION_CRAFT_CLUE", "League"),
    ("FIFTY_FIFTY_CRAFT_CLUE", "Best Five"),
    ("BEST_STAR_RANK_CRAFT_CLUE", "Highest Tier"),
]
CLUE_KEYS = [k for k, _ in CLUE_TYPES]
CLUE_LABELS_MAP = dict(CLUE_TYPES)

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

# Mega Cart collections
MEGA_CART_COLLECTIONS = load_json("mega_cart_collections.json")

# Competition name lookup for Mega Cart league selector
MC_LEAGUE_OPTIONS = {
    comp["slug"]: comp["name"]
    for comp in FOOTBALL_COMPETITIONS
    if comp["slug"] in MEGA_CART_COLLECTIONS
}


def _clue_key_index(clue_key):
    try:
        return CLUE_KEYS.index(clue_key)
    except ValueError:
        return 0


# ── 0. Type de promo ─────────────────────────────────────────────────────────

promo_type = st.selectbox("Type de promo", PROMO_TYPES, key="promo_type")

# ══════════════════════════════════════════════════════════════════════════════
#  ÉLIGIBILITÉ
# ══════════════════════════════════════════════════════════════════════════════

st.header("1. Éligibilité")

rarities = st.multiselect("Raretés", RARITIES, default=["limited"], key="du_rarities")

# ── Mega Cart: eligibility by collections ────────────────────────────────────

if promo_type == "Mega Cart":
    if not MC_LEAGUE_OPTIONS:
        st.warning("Aucune ligue configurée dans mega_cart_collections.json.")
    else:
        league_slugs = list(MC_LEAGUE_OPTIONS.keys())
        league_labels = [MC_LEAGUE_OPTIONS[s] for s in league_slugs]

        mc_league_idx = st.selectbox(
            "Ligue",
            range(len(league_slugs)),
            format_func=lambda i: league_labels[i],
            key="mc_league",
        )
        mc_league_slug = league_slugs[mc_league_idx]
        mc_teams = MEGA_CART_COLLECTIONS[mc_league_slug]

        season = st.text_input("Saison", value="2026-27", key="mc_season")
        cart_count = int(st.number_input("Nombre min de cartes (cart_cards_count)", 1, 20, 5, key="mc_cart_count"))

        # Build collection slugs preview
        mc_collection_slugs = []
        for team in mc_teams:
            for r in rarities:
                mc_collection_slugs.append(f"{team}-{r}-{season}")

        st.info(f"{len(mc_collection_slugs)} collections ({len(mc_teams)} équipes × {len(rarities)} raretés)")
        with st.expander("Voir les collections"):
            st.write(mc_collection_slugs)

# ── Double Up / Wheel Up / Lucky Loser: standard eligibility ─────────────────

else:
    elig_type = st.radio(
        "Critère d'éligibilité",
        ["Compétition", "Équipe", "Joueurs (CSV)"],
        key="du_elig_type",
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
        num_teams = int(st.number_input("Nombre d'équipes", 1, 20, 1, key="du_num_teams"))
        for i in range(num_teams):
            if i % 3 == 0:
                cols = st.columns(min(num_teams - i, 3))
            with cols[i % 3]:
                q = st.text_input(f"Équipe {i + 1}", key=f"du_team_{i}")
                if q:
                    slug, name, _ = find_team_info(q, "football")
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

            total = sum(st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            total += st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
            total += sum(st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0]) for pi in range(3))

            if total == 10000:
                st.success(f"Total : {total}/10000")
            else:
                st.error(f"Total : {total}/10000")

            with st.expander("Détail des clues"):
                for pi in range(3):
                    st.caption(f"Pack {pi + 1}")
                    dc = st.columns(3)
                    for ci in range(3):
                        def_key = DEFAULT_CLUE_PACKS[tk][pi][1][ci][0]
                        def_amt = DEFAULT_CLUE_PACKS[tk][pi][1][ci][1]
                        with dc[ci]:
                            st.selectbox(
                                "Type", CLUE_KEYS,
                                index=_clue_key_index(def_key),
                                format_func=lambda x: CLUE_LABELS_MAP[x],
                                key=f"du_clt_{tk}_{pi}_{ci}",
                            )
                            st.number_input(
                                "Qté", min_value=0, max_value=100,
                                value=def_amt, step=1,
                                key=f"du_cla_{tk}_{pi}_{ci}",
                            )

    st.divider()

    if st.button("Générer les JSONs", type="primary"):
        errors = _validate_standard_elig()

        for ti in range(4):
            tk = TIER_KEYS[ti]
            t = sum(st.session_state.get(f"du_cp_{tk}_{ct}", DEFAULT_CARD_PROBS[tk][ct]) for ct in range(6))
            t += st.session_state.get(f"du_sp_{tk}", DEFAULT_SHARD_PROB)
            t += sum(st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0]) for pi in range(3))
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
                        probable_rewards.append({
                            "probability_basis_point": sp,
                            "card_shards": [{"rarity": rarity, "quantity": sq, "flavour": flavour}],
                        })

                    for pi in range(3):
                        cp = st.session_state.get(f"du_clp_{tk}_{pi}", DEFAULT_CLUE_PACKS[tk][pi][0])
                        if cp > 0:
                            currencies = []
                            for ci in range(3):
                                ctype = st.session_state.get(
                                    f"du_clt_{tk}_{pi}_{ci}",
                                    DEFAULT_CLUE_PACKS[tk][pi][1][ci][0],
                                )
                                camount = st.session_state.get(
                                    f"du_cla_{tk}_{pi}_{ci}",
                                    DEFAULT_CLUE_PACKS[tk][pi][1][ci][1],
                                )
                                if camount > 0:
                                    currencies.append({"currency": ctype, "amount": camount})
                            if currencies:
                                probable_rewards.append({
                                    "probability_basis_point": cp,
                                    "in_game_currencies": currencies,
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

elif promo_type == "Mega Cart":
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
        if not MC_LEAGUE_OPTIONS:
            errors.append("Aucune ligue configurée.")

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
#  LUCKY LOSER (à venir)
# ══════════════════════════════════════════════════════════════════════════════

else:
    st.warning(f"{promo_type} — bientôt disponible.")
