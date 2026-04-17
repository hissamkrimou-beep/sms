import json
import os
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from generate_mission import (
    DECISIVE_ACTIONS,
    FOOTBALL_COMPETITIONS,
    ACTION_PICKER_NAMES,
    CLUE_OPTIONS_BY_SPORT,
    find_team_info,
    find_competition_info,
    generate_title_football,
    generate_title_nba,
    build_mission,
    build_reward,
)

st.title("Mission Generator")

# ── 1. Sport ──────────────────────────────────────────────────────────────────

sport = st.selectbox("Sport", ["football", "nba", "baseball"])

# ══════════════════════════════════════════════════════════════════════════════
#  MLB FLOW
# ══════════════════════════════════════════════════════════════════════════════

if sport == "baseball":

    MLB_POSITIONS = [
        "baseball_catcher",
        "baseball_designated_hitter",
        "baseball_first_base",
        "baseball_outfield",
        "baseball_relief_pitcher",
        "baseball_second_base",
        "baseball_shortstop",
        "baseball_starting_pitcher",
        "baseball_third_base",
    ]

    MLB_POSITION_LABELS = {
        "baseball_catcher": "Catcher (C)",
        "baseball_designated_hitter": "Designated Hitter (DH)",
        "baseball_first_base": "First Base (1B)",
        "baseball_outfield": "Outfield (OF)",
        "baseball_relief_pitcher": "Relief Pitcher (RP)",
        "baseball_second_base": "Second Base (2B)",
        "baseball_shortstop": "Shortstop (SS)",
        "baseball_starting_pitcher": "Starting Pitcher (SP)",
        "baseball_third_base": "Third Base (3B)",
    }

    WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    baseball_actions = DECISIVE_ACTIONS["baseball"]

    # ── Title ────────────────────────────────────────────────────────────
    title = st.text_input("Titre de la mission")

    # ── Positions ────────────────────────────────────────────────────────
    positions = st.multiselect(
        "Positions",
        MLB_POSITIONS,
        format_func=lambda x: MLB_POSITION_LABELS[x],
    )

    # ── Picked count & Rarity ────────────────────────────────────────────
    col_pc, col_rar = st.columns(2)
    with col_pc:
        picked_count = int(st.number_input("Picked count", min_value=1, value=3, step=1, key="mlb_pc"))
    with col_rar:
        RARITIES = ["limited", "rare", "super_rare", "unique"]
        rarities = st.multiselect("Rarities", RARITIES, default=["limited"], key="mlb_rar")

    # ── Season & Recurrence ──────────────────────────────────────────────
    col_s, col_w = st.columns(2)
    with col_s:
        season_enabled = st.toggle("In-Season", value=True, key="mlb_season")
    with col_w:
        weekday = st.selectbox("Jour de récurrence", WEEKDAYS, key="mlb_weekday")

    # ── Milestones ───────────────────────────────────────────────────────
    st.subheader("Milestones")
    st.caption("Chaque milestone = 1 DS action avec un minimum à atteindre. Le target de la mission = le min du premier milestone.")

    num_milestones = int(st.number_input("Nombre de milestones", min_value=1, max_value=10, value=3, key="mlb_num_ms"))

    action_keys = list(baseball_actions.keys())
    action_display = [f"{k} — {baseball_actions[k]['label']}" for k in action_keys]

    milestones = []
    for i in range(num_milestones):
        col_act, col_min = st.columns([3, 1])
        with col_act:
            sel = st.selectbox(
                f"Milestone {i + 1} — DS",
                action_display,
                key=f"mlb_ms_act_{i}",
            )
            action_key = action_keys[action_display.index(sel)]
        with col_min:
            min_val = int(st.number_input(
                "Min",
                min_value=1, max_value=99, value=1, step=1,
                key=f"mlb_ms_min_{i}",
            ))
        milestones.append({"stat": action_key, "min": min_val})

    # ── Rewards par milestone ──────────────────────────────────────────
    st.subheader("Rewards")

    MLB_CLUE_TYPES = [
        ("FIFTY_FIFTY_CRAFT_CLUE", "Best 5 Clue"),
        ("DIVISION_CRAFT_CLUE", "Division Clue"),
        ("POSITION_CRAFT_CLUE", "Position Clue"),
    ]

    mlb_reward_type = st.selectbox(
        "Type de reward",
        ["Clues", "Essence", "Market Credit"],
        key="mlb_reward_type",
    )

    mlb_clue_currency = None
    if mlb_reward_type == "Clues":
        clue_labels = [label for _, label in MLB_CLUE_TYPES]
        clue_keys = [k for k, _ in MLB_CLUE_TYPES]
        clue_sel = st.selectbox("Type de clue", clue_labels, key="mlb_clue_type")
        mlb_clue_currency = clue_keys[clue_labels.index(clue_sel)]

    st.caption("Reward par milestone")
    reward_amounts = []
    reward_cols = st.columns(min(num_milestones, 5))
    for i in range(num_milestones):
        short = baseball_actions[milestones[i]["stat"]].get("short", "?")
        with reward_cols[i % len(reward_cols)]:
            if mlb_reward_type == "Market Credit":
                amt = int(st.number_input(
                    f"MS{i + 1} ({short}) — $ max",
                    min_value=1, value=100, step=50, key=f"mlb_rw_{i}",
                ))
            elif mlb_reward_type == "Essence":
                amt = int(st.number_input(
                    f"MS{i + 1} ({short}) — qté",
                    min_value=1, value=25, step=5, key=f"mlb_rw_{i}",
                ))
            else:
                amt = int(st.number_input(
                    f"MS{i + 1} ({short}) — qté",
                    min_value=1, value=1, step=1, key=f"mlb_rw_{i}",
                ))
            reward_amounts.append(amt)

    # ── Auto-generated description ───────────────────────────────────────
    ms_parts = []
    for ms in milestones:
        short = baseball_actions[ms["stat"]].get("short", ms["stat"])
        ms_parts.append(f"{ms['min']} {short}")

    rw_parts = [str(a) for a in reward_amounts]
    if mlb_reward_type == "Clues":
        clue_label = dict(MLB_CLUE_TYPES).get(mlb_clue_currency, "Clue")
        rw_suffix = f"{', '.join(rw_parts)} {clue_label}s per player"
    elif mlb_reward_type == "Market Credit":
        rw_suffix = f"${', $'.join(rw_parts)} Market Credit per player"
    else:
        rw_suffix = f"{', '.join(rw_parts)} Essence per player"

    auto_desc = f"Milestones: {', '.join(ms_parts)} — Reward: {rw_suffix}"
    st.session_state["mlb_desc"] = auto_desc
    description = st.text_input("Description", key="mlb_desc")

    # ── Generate ─────────────────────────────────────────────────────────
    st.divider()

    if st.button("Générer", type="primary", key="mlb_gen"):
        errors = []
        if not title.strip():
            errors.append("Le titre est requis.")
        if not rarities:
            errors.append("Au moins une rareté requise.")
        if not positions:
            errors.append("Au moins une position requise.")
        if not milestones:
            errors.append("Au moins un milestone requis.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            # Deduplicate while preserving order
            seen = set()
            decisive_actions = []
            for ms in milestones:
                if ms["stat"] not in seen:
                    decisive_actions.append(ms["stat"])
                    seen.add(ms["stat"])
            target = milestones[0]["min"]

            mission = {
                "mode": "decisive",
                "title": title.strip(),
                "sealed": False,
                "target": target,
                "rarities": list(rarities),
                "positions": positions,
                "recurrence": {"weekdays": [weekday]},
                "description": description,
                "picked_count": picked_count,
                "decisive_actions": decisive_actions,
                "max_player_occurence": 1,
                "prevent_concurrent_picks": True,
                "stay_completed_at_expiration": True,
                "allow_multiple_games_per_appearance": True,
            }

            if season_enabled:
                mission["seasons"] = [2026]

            # Display per rarity
            for rarity in rarities:
                rarity_label = rarity.replace("_", " ").title()
                st.subheader(rarity_label)

                mission_copy = dict(mission)
                mission_copy["rarities"] = [rarity]

                # Build reward config for this rarity
                stat_thresholds = []
                for i, ms in enumerate(milestones):
                    amt = reward_amounts[i]

                    if mlb_reward_type == "Market Credit":
                        reward_config = {
                            "conversion_credit": {
                                "sport": "BASEBALL",
                                "max_discount": {
                                    "amounts": [{"amount": amt, "currency": "CURRENCY_USD"}],
                                    "reference_currency": "CURRENCY_USD",
                                },
                                "duration_in_days": 30,
                                "percentage_discount_basis_point": 5000,
                            }
                        }
                    elif mlb_reward_type == "Essence":
                        reward_config = {
                            "card_shards": [{"rarity": rarity.upper(), "quantity": amt}]
                        }
                    else:  # Clues
                        reward_config = {
                            "in_game_currencies": [{"amount": amt, "currency": mlb_clue_currency}]
                        }

                    stat_thresholds.append({
                        "min": ms["min"],
                        "stat": ms["stat"],
                        "reward_config": reward_config,
                    })

                reward = {
                    "by_appearance": {
                        "filter": "by_rarity",
                        "stat_thresholds": stat_thresholds,
                    }
                }

                col_m, col_r = st.columns(2)
                with col_m:
                    st.caption("mission.json")
                    st.code(json.dumps(mission_copy, indent=2, ensure_ascii=False), language="json")
                with col_r:
                    st.caption("reward.json")
                    st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

# ══════════════════════════════════════════════════════════════════════════════
#  FOOTBALL / NBA FLOW
# ══════════════════════════════════════════════════════════════════════════════

else:
    # ── 2. Mission type ──────────────────────────────────────────────────
    mission_type = st.selectbox("Type de mission", ["Match spécifique", "Compétition", "All Matches"])

    # ── 3. Clubs / Compétition ───────────────────────────────────────────
    clubs = []
    club_names = []
    national_teams = []
    competitions = []
    competition_names = []
    competition_slug = None

    if mission_type == "Match spécifique":
        num_teams = int(st.number_input("Nombre d'équipes", min_value=2, max_value=10, value=2, step=1, key="num_teams"))
        team_cols = st.columns(min(num_teams, 3))
        for i in range(num_teams):
            with team_cols[i % len(team_cols)]:
                query = st.text_input(f"Équipe {i + 1}", key=f"team_{i}")
                if query:
                    slug, name, is_nat = find_team_info(query, sport)
                    if slug:
                        st.success(f"✓ {name} ({slug})")
                        if is_nat:
                            national_teams.append(slug)
                        else:
                            clubs.append(slug)
                        club_names.append(name)
                    else:
                        st.error("Équipe non trouvée")

    elif mission_type == "Compétition":
        col_comp1, col_comp2 = st.columns(2)
        with col_comp1:
            comp_query = st.text_input("Compétition 1")
            if comp_query:
                comp_slug, comp_name = find_competition_info(comp_query)
                if comp_slug:
                    st.success(f"✓ {comp_name} ({comp_slug})")
                    competitions.append(comp_slug)
                    competition_names.append(comp_name)
                    competition_slug = comp_slug
                else:
                    manual_slug = st.text_input("Slug manuel compétition 1", key="manual_comp1")
                    if manual_slug:
                        st.success(f"✓ Slug manuel: {manual_slug}")
                        competitions.append(manual_slug)
                        competition_names.append(manual_slug)
                        competition_slug = manual_slug
                    else:
                        st.error("Compétition non trouvée — entre le slug manuellement")
        with col_comp2:
            comp2_query = st.text_input("Compétition 2 (optionnel)")
            if comp2_query:
                comp2_slug, comp2_name = find_competition_info(comp2_query)
                if comp2_slug:
                    st.success(f"✓ {comp2_name} ({comp2_slug})")
                    competitions.append(comp2_slug)
                    competition_names.append(comp2_name)
                else:
                    manual_slug2 = st.text_input("Slug manuel compétition 2", key="manual_comp2")
                    if manual_slug2:
                        st.success(f"✓ Slug manuel: {manual_slug2}")
                        competitions.append(manual_slug2)
                        competition_names.append(manual_slug2)
                    else:
                        st.error("Compétition non trouvée — entre le slug manuellement")

    # ── 3b. Position ─────────────────────────────────────────────────────
    POSITIONS = ["Goalkeeper", "Defender", "Midfielder", "Forward"]
    positions = st.multiselect("Position (optionnel)", POSITIONS)

    # ── 3c. Age ──────────────────────────────────────────────────────────
    col_age1, col_age2 = st.columns(2)
    with col_age1:
        age_min = st.number_input("Âge min (0 = pas de contrainte)", min_value=0, max_value=99, value=0, step=1)
    with col_age2:
        age_max = st.number_input("Âge max (0 = pas de contrainte)", min_value=0, max_value=99, value=0, step=1)

    # ── 3d. Max average score ───────────────────────────────────────────
    use_max_avg = st.toggle("Filtrer par L10 average score", value=False)
    max_avg_score = 50
    max_avg_count = 0
    if use_max_avg:
        col_avg1, col_avg2 = st.columns(2)
        with col_avg1:
            max_avg_score = int(st.number_input("Score max L10", min_value=1, max_value=100, value=50, step=5, key="max_avg_score"))
        with col_avg2:
            max_avg_count = int(st.number_input("Nombre de joueurs (0 = tous)", min_value=0, value=0, step=1, key="max_avg_count"))

    # ── 4. Mode ──────────────────────────────────────────────────────────
    mode = st.selectbox("Mode", ["decisive", "score"])

    # ── 5. Decisive actions ──────────────────────────────────────────────
    decisive_actions = []
    use_milestones = False
    milestones = []
    milestone_reward_amounts = []
    milestone_reward_type = None
    milestone_clue_currency = None

    if mode == "decisive":
        use_milestones = st.toggle("Reward par palier de DS (milestones)", value=False, key="fb_milestones")

        if not use_milestones:
            sport_actions = DECISIVE_ACTIONS[sport]
            action_options = [
                f"{key} — {val['label']} (target: {val['target']})"
                for key, val in sport_actions.items()
            ]
            selected_options = st.multiselect("Decisive actions", action_options)
            decisive_actions = [opt.split(" — ")[0] for opt in selected_options]
        else:
            sport_actions = DECISIVE_ACTIONS[sport]
            action_keys = list(sport_actions.keys())
            action_display = [f"{k} — {sport_actions[k]['label']}" for k in action_keys]

            st.subheader("Milestones")
            st.caption("Chaque milestone = 1 DS action avec un minimum à atteindre. Le target de la mission = le min du premier milestone.")

            num_milestones = int(st.number_input("Nombre de milestones", min_value=1, max_value=10, value=3, key="fb_num_ms"))

            # Milestone 1: user picks the DS action
            col_act1, col_min1 = st.columns([3, 1])
            with col_act1:
                sel1 = st.selectbox("Milestone 1 — DS", action_display, key="fb_ms_act_0")
                ms1_action_key = action_keys[action_display.index(sel1)]
            base_target = sport_actions[ms1_action_key]["target"]

            # When MS1 action changes, propagate action + targets to MS2+ via session_state
            prev_ms1 = st.session_state.get("_fb_ms1_prev")
            if prev_ms1 != sel1:
                st.session_state["fb_ms_min_0"] = base_target
                for j in range(1, num_milestones):
                    st.session_state[f"fb_ms_act_{j}"] = sel1
                    st.session_state[f"fb_ms_min_{j}"] = base_target + j
                st.session_state["_fb_ms1_prev"] = sel1

            with col_min1:
                min_val1 = int(st.number_input(
                    "Min", min_value=1, max_value=99, value=base_target, step=1, key="fb_ms_min_0",
                ))
            milestones.append({"stat": ms1_action_key, "min": min_val1})

            # Milestones 2+: same DS action as milestone 1, target +i
            for i in range(1, num_milestones):
                col_act, col_min = st.columns([3, 1])
                with col_act:
                    sel = st.selectbox(
                        f"Milestone {i + 1} — DS",
                        action_display,
                        index=action_keys.index(ms1_action_key),
                        key=f"fb_ms_act_{i}",
                    )
                    action_key = action_keys[action_display.index(sel)]
                with col_min:
                    min_val = int(st.number_input(
                        "Min",
                        min_value=1, max_value=99, value=base_target + i, step=1,
                        key=f"fb_ms_min_{i}",
                    ))
                milestones.append({"stat": action_key, "min": min_val})

            # Derive decisive_actions from milestones
            seen = set()
            for ms in milestones:
                if ms["stat"] not in seen:
                    decisive_actions.append(ms["stat"])
                    seen.add(ms["stat"])

            # ── Milestone rewards ────────────────────────────────────────
            st.subheader("Rewards par milestone")

            milestone_reward_type = st.selectbox(
                "Type de reward",
                ["Clues", "Essence", "Market Credit"],
                key="fb_ms_reward_type",
            )

            if milestone_reward_type == "Clues":
                sport_clues = {label: currency for label, currency in CLUE_OPTIONS_BY_SPORT[sport]}
                clue_label_sel = st.selectbox("Type de Clue", list(sport_clues.keys()), key="fb_ms_clue_type")
                milestone_clue_currency = sport_clues[clue_label_sel]

            st.caption("Reward par milestone")
            reward_cols = st.columns(min(num_milestones, 5))
            for i in range(num_milestones):
                ms_label = ACTION_PICKER_NAMES.get(milestones[i]["stat"], milestones[i]["stat"].replace("_", " ").title())
                with reward_cols[i % len(reward_cols)]:
                    if milestone_reward_type == "Market Credit":
                        amt = int(st.number_input(
                            f"MS{i + 1} ({ms_label}) — $ max",
                            min_value=1, value=100, step=50, key=f"fb_ms_rw_{i}",
                        ))
                    elif milestone_reward_type == "Essence":
                        amt = int(st.number_input(
                            f"MS{i + 1} ({ms_label}) — qté",
                            min_value=1, value=25, step=5, key=f"fb_ms_rw_{i}",
                        ))
                    else:
                        amt = int(st.number_input(
                            f"MS{i + 1} ({ms_label}) — qté",
                            min_value=1, value=1, step=1, key=f"fb_ms_rw_{i}",
                        ))
                    milestone_reward_amounts.append(amt)

    # ── 6. Titre auto-généré ─────────────────────────────────────────────
    auto_title = ""
    if sport == "nba" and mode == "decisive" and decisive_actions:
        auto_title = generate_title_nba(decisive_actions, mission_type, club_names or None)
    elif sport == "football" and mode == "decisive" and decisive_actions:
        auto_title = generate_title_football(decisive_actions, mission_type, competition_names or None, club_names or None)

    title = st.text_input("Titre", value=auto_title)

    # ── 7. Order ─────────────────────────────────────────────────────────
    order = None
    if mission_type == "Compétition":
        order_val = st.number_input("Order (optionnel, 0 = aucun)", min_value=0, value=0, step=1)
        order = int(order_val) if order_val != 0 else None

    # ── 8. Target ────────────────────────────────────────────────────────
    if use_milestones and milestones:
        target = milestones[0]["min"]
        st.caption(f"Target auto (milestone 1) : {target}")
    else:
        if mode == "decisive" and decisive_actions:
            sport_actions = DECISIVE_ACTIONS[sport]
            default_target = sport_actions[decisive_actions[0]]["target"]
        else:
            default_target = 100

        target = st.number_input("Target", min_value=1, value=default_target, step=1)

    # ── 9. Picked count ──────────────────────────────────────────────────
    picked_count = st.number_input("Picked count", min_value=1, value=3, step=1)

    # ── 10. Rarity ───────────────────────────────────────────────────────
    RARITIES = ["limited", "rare", "super_rare", "unique"]
    rarities = st.multiselect("Rarities", RARITIES, default=["limited"])

    # ── 11. Rewards ──────────────────────────────────────────────────────
    reward_type = "essence"
    clue_currency = None
    custom_rewards = False
    mc_amount = None
    mc_total = None
    mc_duration = 30
    mc_discount_bp = 5000
    mc_bonus_amount = None
    mc_bonus_duration = 30
    mc_bonus_discount_bp = 5000

    if use_milestones:
        st.caption("Rewards configurés dans la section Milestones ci-dessus.")
    else:

        REWARDS_BY_RARITY = {
            "football": {
                "limited":    (50, 500),
                "rare":       (50, 500),
                "super_rare": (50, 500),
                "unique":     (30, 250),
            },
            "nba": {
                "limited":    (50, 250),
                "rare":       (50, 250),
                "super_rare": (50, 250),
                "unique":     (50, 250),
            },
        }

        reward_type = st.selectbox("Type de reward", ["essence", "clues", "market credit"])

        if reward_type == "clues":
            sport_clues = {label: currency for label, currency in CLUE_OPTIONS_BY_SPORT[sport]}
            clue_label = st.selectbox("Type de Clue", list(sport_clues.keys()))
            clue_currency = sport_clues[clue_label]
        elif reward_type == "market credit":
            MC_REWARDS_BY_RARITY = {
                "limited":    (2, 10),
                "rare":       (6, 30),
                "super_rare": (25, 120),
                "unique":     (60, 300),
            }
            if len(rarities) == 1:
                default_mc_per, default_mc_total = MC_REWARDS_BY_RARITY[rarities[0]]
            else:
                default_mc_per, default_mc_total = 2, 10
            col_mc1, col_mc2, col_mc3 = st.columns(3)
            with col_mc1:
                mc_amount = int(st.number_input("$ par pick réussi", min_value=1, value=default_mc_per, step=1, key="mc_amount"))
            with col_mc2:
                mc_total = int(st.number_input("$ total (all picks)", min_value=1, value=default_mc_total, step=1, key="mc_total"))
            with col_mc3:
                mc_discount_bp = int(st.number_input("Discount (bp)", min_value=1, max_value=10000, value=5000, step=500, key="mc_discount"))
            mc_duration = 30
            mc_bonus_amount = mc_total - mc_amount * int(picked_count)
            mc_bonus_duration = mc_duration
            mc_bonus_discount_bp = mc_discount_bp
            if mc_bonus_amount > 0:
                st.caption(f"${mc_amount}/pick × {int(picked_count)} picks = ${mc_amount * int(picked_count)} + ${mc_bonus_amount} bonus = ${mc_total} total — Discount: {mc_discount_bp / 100:.0f}%")
            else:
                st.caption(f"${mc_amount}/pick × {int(picked_count)} picks = ${mc_total} total — Discount: {mc_discount_bp / 100:.0f}%")
            if len(rarities) > 1:
                st.info("MC auto par rareté (L: $2/$10, R: $6/$30, SR: $25/$120, U: $60/$300)")

        CLUE_REWARDS_BY_RARITY = {
            "limited":    (2, 10),
            "rare":       (4, 20),
            "super_rare": (8, 40),
            "unique":     (16, 80),
        }

        if reward_type == "market credit":
            pass  # Config already done above
        elif len(rarities) == 1:
            custom_rewards = True
            if reward_type == "clues":
                default_per_pick = CLUE_REWARDS_BY_RARITY[rarities[0]][0]
                default_total = CLUE_REWARDS_BY_RARITY[rarities[0]][1]
            else:
                default_per_pick = REWARDS_BY_RARITY[sport][rarities[0]][0]
                default_total = REWARDS_BY_RARITY[sport][rarities[0]][1]
            reward_per_pick = st.number_input("Reward par pick", min_value=1, value=default_per_pick, step=1)
            reward_total = st.number_input("Reward total (0 = pas de bonus)", min_value=0, value=default_total, step=1)
        elif reward_type == "clues":
            st.info("Rewards clues auto par rareté (L: 2/10, R: 4/20, SR: 8/40, U: 16/80)")
        else:
            st.info("Rewards auto par rareté (Football: 50/500 L/R/SR, 30/250 U — NBA: 50/250 toutes)")

    # ── 12. Flavour ──────────────────────────────────────────────────────
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

    detected_flavour = None
    if mission_type == "Compétition" and competition_slug:
        for comp in FOOTBALL_COMPETITIONS:
            if comp["slug"] == competition_slug:
                detected_flavour = comp.get("flavour")
                break

    flavour_options = ["Aucun"] + list(ESSENCE_FLAVOURS.keys())
    if detected_flavour and detected_flavour in flavour_options:
        default_idx = flavour_options.index(detected_flavour)
    else:
        default_idx = 0

    selected_flavour = st.selectbox("Flavour Essence", flavour_options, index=default_idx)
    flavour = selected_flavour if selected_flavour != "Aucun" else None

    # ── 13. Essence name ─────────────────────────────────────────────────
    if flavour:
        default_essence = ESSENCE_FLAVOURS.get(flavour, f"{flavour.replace('SEASONAL-', '').title()} Essence")
    elif mission_type == "All Matches" and sport == "football":
        default_essence = "All-Star Essence"
    else:
        default_essence = "Essence"

    essence_name = st.text_input("Essence name", value=default_essence)

    # ── 14. Date de la mission ───────────────────────────────────────────
    mission_date = st.date_input("Date de la mission", value=date.today())
    start_date = datetime.combine(mission_date, datetime.min.time().replace(hour=7))
    end_date = start_date + timedelta(days=1)

    # ── 15. Editions (NBA) ───────────────────────────────────────────────
    editions = []
    if sport == "nba":
        NBA_EDITIONS = ["sunset", "showtime", "rising_star"]
        editions = st.multiselect("Editions (optionnel)", NBA_EDITIONS)

    # ── 16. Options avancées ─────────────────────────────────────────────
    with st.expander("Options avancées"):
        stay_completed = st.toggle("stay_completed_at_expiration", value=True)
        disable_auto_claim = st.toggle("disable_auto_claim_at_expiration", value=True)
        active = st.toggle("Active", value=True)

    # ── Bouton Générer ───────────────────────────────────────────────────
    if st.button("Générer", type="primary"):
        errors = []
        if not rarities:
            errors.append("Au moins une rareté est requise.")
        if not title.strip():
            errors.append("Le titre est requis.")
        if mission_type == "Match spécifique" and (len(clubs) + len(national_teams)) < 2:
            errors.append("Au moins deux équipes sont requises pour un match spécifique.")
        if mission_type == "Compétition" and not competitions:
            errors.append("Une compétition est requise.")
        if mode == "decisive" and not decisive_actions:
            errors.append("Au moins une decisive action est requise en mode decisive.")

        if errors:
            for err in errors:
                st.error(err)
        elif use_milestones:
            # ── Milestone-based generation (stat_thresholds) ─────────
            for rarity in rarities:
                rarity_label = rarity.replace("_", " ").title()
                st.subheader(rarity_label)

                # Build mission via build_mission
                params = {
                    "sport": sport,
                    "mission_type": mission_type,
                    "mode": "decisive",
                    "title": title.strip(),
                    "target": int(target),
                    "picked_count": int(picked_count),
                    "rarity": rarity,
                    "reward_type": milestone_reward_type.lower(),
                    "clue_currency": milestone_clue_currency,
                    "reward_per_pick": milestone_reward_amounts[0] if milestone_reward_amounts else 0,
                    "reward_total": sum(milestone_reward_amounts),
                    "reward_bonus": 0,
                    "flavour": flavour,
                    "essence_name": essence_name,
                    "stay_completed": stay_completed,
                    "disable_auto_claim": disable_auto_claim,
                    "order": order,
                    "decisive_actions": decisive_actions,
                    "mc_amount": milestone_reward_amounts[0] if milestone_reward_type == "Market Credit" and milestone_reward_amounts else None,
                    "mc_total": sum(milestone_reward_amounts) if milestone_reward_type == "Market Credit" else None,
                    "mc_duration": 30,
                    "mc_discount_bp": 5000,
                    "mc_bonus_amount": None,
                    "mc_bonus_duration": 30,
                    "mc_bonus_discount_bp": 5000,
                }

                if mission_type == "Match spécifique":
                    if clubs:
                        params["clubs"] = clubs
                    if national_teams:
                        params["national_teams"] = national_teams
                    params["club_names"] = club_names

                if mission_type == "Compétition":
                    params["competitions"] = competitions
                    params["competition_names"] = competition_names

                if positions:
                    params["positions"] = positions

                if age_min > 0:
                    params["age_min"] = int(age_min)
                if age_max > 0:
                    params["age_max"] = int(age_max)

                if editions:
                    params["editions"] = editions

                if use_max_avg:
                    params["max_avg_score"] = max_avg_score
                    params["max_avg_count"] = max_avg_count

                mission = build_mission(params)

                # Build reward with stat_thresholds (like MLB)
                sport_upper = sport.upper()
                stat_thresholds = []
                for i, ms in enumerate(milestones):
                    amt = milestone_reward_amounts[i]

                    if milestone_reward_type == "Market Credit":
                        reward_config = {
                            "conversion_credit": {
                                "sport": sport_upper,
                                "max_discount": {
                                    "amounts": [{"amount": amt, "currency": "CURRENCY_USD"}],
                                    "reference_currency": "CURRENCY_USD",
                                },
                                "duration_in_days": 30,
                                "percentage_discount_basis_point": 5000,
                            }
                        }
                    elif milestone_reward_type == "Essence":
                        shard_entry = {"rarity": rarity.upper(), "quantity": amt}
                        if flavour:
                            shard_entry["flavour"] = flavour
                        reward_config = {"card_shards": [shard_entry]}
                    else:  # Clues
                        reward_config = {
                            "in_game_currencies": [{"amount": amt, "currency": milestone_clue_currency}]
                        }

                    stat_thresholds.append({
                        "min": ms["min"],
                        "stat": ms["stat"],
                        "reward_config": reward_config,
                    })

                reward = {
                    "by_appearance": {
                        "filter": "by_rarity",
                        "stat_thresholds": stat_thresholds,
                    }
                }

                admin_payload = {
                    "sport": sport,
                    "periodicity": "daily",
                    "start_date": start_date.strftime("%Y-%m-%dT%H:%M"),
                    "end_date": end_date.strftime("%Y-%m-%dT%H:%M"),
                    "genre": "fantasy",
                    "config": {"config": mission},
                    "reward_config": reward,
                    "active": active,
                }

                col_m, col_r = st.columns(2)
                with col_m:
                    st.caption("mission.json")
                    st.code(json.dumps(mission, indent=2, ensure_ascii=False), language="json")
                with col_r:
                    st.caption("reward.json")
                    st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

                with st.expander(f"Payload admin complet — {rarity_label}"):
                    st.code(json.dumps(admin_payload, indent=2, ensure_ascii=False), language="json")
        else:
            for rarity in rarities:
                r_mc_per = mc_amount
                r_mc_total = mc_total
                r_mc_bonus = mc_bonus_amount
                if reward_type == "market credit":
                    if len(rarities) > 1:
                        r_mc_per, r_mc_total = MC_REWARDS_BY_RARITY[rarity]
                    else:
                        r_mc_per, r_mc_total = mc_amount, mc_total
                    r_mc_bonus = r_mc_total - r_mc_per * int(picked_count)
                    r_per_pick = 0
                    r_total = 0
                elif custom_rewards:
                    r_per_pick = int(reward_per_pick)
                    r_total = int(reward_total)
                elif reward_type == "clues":
                    r_per_pick, r_total = CLUE_REWARDS_BY_RARITY[rarity]
                else:
                    r_per_pick, r_total = REWARDS_BY_RARITY[sport][rarity]

                params = {
                    "sport": sport,
                    "mission_type": mission_type,
                    "mode": mode,
                    "title": title.strip(),
                    "target": int(target),
                    "picked_count": int(picked_count),
                    "rarity": rarity,
                    "reward_type": reward_type,
                    "clue_currency": clue_currency,
                    "reward_per_pick": r_per_pick,
                    "reward_total": r_total,
                    "reward_bonus": r_total - r_per_pick * int(picked_count),
                    "flavour": flavour,
                    "essence_name": essence_name,
                    "stay_completed": stay_completed,
                    "disable_auto_claim": disable_auto_claim,
                    "order": order,
                    "mc_amount": r_mc_per if reward_type == "market credit" else mc_amount,
                    "mc_total": r_mc_total if reward_type == "market credit" else None,
                    "mc_duration": mc_duration,
                    "mc_discount_bp": mc_discount_bp,
                    "mc_bonus_amount": r_mc_bonus if reward_type == "market credit" else mc_bonus_amount,
                    "mc_bonus_duration": mc_bonus_duration,
                    "mc_bonus_discount_bp": mc_bonus_discount_bp,
                }

                if mission_type == "Match spécifique":
                    if clubs:
                        params["clubs"] = clubs
                    if national_teams:
                        params["national_teams"] = national_teams
                    params["club_names"] = club_names

                if mission_type == "Compétition":
                    params["competitions"] = competitions
                    params["competition_names"] = competition_names

                if mode == "decisive":
                    params["decisive_actions"] = decisive_actions

                if positions:
                    params["positions"] = positions

                if age_min > 0:
                    params["age_min"] = int(age_min)
                if age_max > 0:
                    params["age_max"] = int(age_max)

                if editions:
                    params["editions"] = editions

                if use_max_avg:
                    params["max_avg_score"] = max_avg_score
                    params["max_avg_count"] = max_avg_count

                mission = build_mission(params)
                reward = build_reward(params)

                admin_payload = {
                    "sport": sport,
                    "periodicity": "daily",
                    "start_date": start_date.strftime("%Y-%m-%dT%H:%M"),
                    "end_date": end_date.strftime("%Y-%m-%dT%H:%M"),
                    "genre": "fantasy",
                    "config": {"config": mission},
                    "reward_config": reward,
                    "active": active,
                }

                rarity_label = rarity.replace("_", " ").title()
                st.subheader(f"{rarity_label}")

                col_m, col_r = st.columns(2)
                with col_m:
                    st.caption("mission.json")
                    st.code(json.dumps(mission, indent=2, ensure_ascii=False), language="json")
                with col_r:
                    st.caption("reward.json")
                    st.code(json.dumps(reward, indent=2, ensure_ascii=False), language="json")

                with st.expander(f"Payload admin complet — {rarity_label}"):
                    st.code(json.dumps(admin_payload, indent=2, ensure_ascii=False), language="json")
