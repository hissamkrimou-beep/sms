#!/usr/bin/env python3
"""
Générateur de missions Sorare
Crée deux fichiers JSON : mission + rewards
"""

import json
import os
import re
import sys
from difflib import get_close_matches

# ── Chargement des données ──────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")

def load_json(filename):
    """Charge un fichier JSON depuis le dossier data/"""
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# Chargement au démarrage
DECISIVE_ACTIONS = load_json("decisive_actions.json")
FOOTBALL_CLUBS = load_json("football_clubs.json")
FOOTBALL_COMPETITIONS = load_json("football_competitions.json")
NBA_TEAMS = load_json("nba_teams.json")

# ── Constantes ───────────────────────────────────────────────────────────────

CLUE_LABELS = {
    "BEST_STAR_RANK_CRAFT_CLUE": "Highest Tier Clue",
    "COUNTRY_CRAFT_CLUE":        "Nationality Clue",
    "COMPETITION_CRAFT_CLUE":    "League Clue",
    "FIFTY_FIFTY_CRAFT_CLUE":    "Best Five Clue",
    "DIVISION_CRAFT_CLUE":       "Division Clue",
    "POSITION_CRAFT_CLUE":       "Position Clue",
}

# Clues disponibles par sport : (label, currency)
CLUE_OPTIONS_BY_SPORT = {
    "football": [
        ("Highest Tier Clue", "BEST_STAR_RANK_CRAFT_CLUE"),
        ("Nationality Clue",  "COUNTRY_CRAFT_CLUE"),
        ("League Clue",       "COMPETITION_CRAFT_CLUE"),
        ("Best Five Clue",    "FIFTY_FIFTY_CRAFT_CLUE"),
    ],
    "nba": [
        ("Highest Tier Clue", "BEST_STAR_RANK_CRAFT_CLUE"),
        ("Best Five Clue",    "FIFTY_FIFTY_CRAFT_CLUE"),
        ("Division Clue",     "DIVISION_CRAFT_CLUE"),
        ("Position Clue",     "POSITION_CRAFT_CLUE"),
    ],
}

ACTION_VERBS = {
    # Football
    "goals":                        "scores",
    "own_goals":                    "scores",
    "goal_assist":                  "provides",
    "assist_penalty_won":           "provides",
    "big_chance_created":           "creates",
    "big_chance_missed":            "misses",
    "penalty_kick_missed":          "misses",
    "missed_pass":                  "misses",
    "duel_lost":                    "loses",
    "poss_lost_ctrl":               "loses",
    "fouls":                        "commits",
    "error_lead_to_goal":           "commits",
    "yellow_card":                  "receives",
    "red_card":                     "receives",
    "penalty_conceded":             "concedes",
    "duel_won":                     "wins",
    "penalty_won":                  "wins",
    "poss_won":                     "wins",
    "won_contest":                  "completes",
    "won_tackle":                   "wins",
    "was_fouled":                   "suffers",
    "saves":                        "makes",
    "penalty_save":                 "makes",
    "clearance_off_line":           "makes",
    "last_man_tackle":              "makes",
    "effective_clearance":          "makes",
    "interception_won":             "makes",
    "ontarget_scoring_att":         "makes",
    "pen_area_entries":             "makes",
    "accurate_pass":                "completes",
    "accurate_long_balls":          "completes",
    "successful_final_third_passes":"completes",
    # NBA
    "steals":                       "makes",
    "blocks":                       "makes",
    "three_points_made":            "makes",
    "rebounds":                     "grabs",
    "assists":                      "records",
    "points":                       "scores",
    "turnovers":                    "commits",
}

# Overrides de label quand le verbe porte déjà la notion (évite "misses missed passes")
DESCRIPTION_LABEL_OVERRIDES = {
    "missed_pass":        "pass",
    "duel_lost":          "duel",
    "duel_won":           "duel",
    "poss_lost_ctrl":     "possession",
    "poss_won":           "possession",
    "big_chance_missed":  "big chance",
    "big_chance_created": "big chance",
    "penalty_kick_missed":"penalty",
    "penalty_won":        "penalty",
    "won_tackle":         "tackle",
    "won_contest":        "dribble",
    "was_fouled":         "foul",
    "penalty_conceded":   "penalty",
}


def pluralize_label(label):
    """Pluralise correctement un label (gère les irréguliers et composés)."""
    COMPOUND_OVERRIDES = {
        "shot on target":   "shots on target",
        "foul suffered":    "fouls suffered",
        "big chance created": "big chances created",
        "dribble":          "dribbles",
        "penalty area entry": "penalty area entries",
    }
    if label in COMPOUND_OVERRIDES:
        return COMPOUND_OVERRIDES[label]

    IRREGULAR_LAST_WORD = {
        "pass":  "passes",
        "entry": "entries",
    }
    words = label.split()
    last = words[-1]
    if last in IRREGULAR_LAST_WORD:
        words[-1] = IRREGULAR_LAST_WORD[last]
    elif last.endswith(("s", "sh", "ch", "x", "z")):
        words[-1] = last + "es"
    elif last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        words[-1] = last[:-1] + "ies"
    else:
        words[-1] = last + "s"
    return " ".join(words)

NBA_ACTION_PICKER_NAMES = {
    "steals":            "Steal",
    "blocks":            "Block",
    "rebounds":          "Rebound",
    "assists":           "Assist",
    "three_points_made": "Three-Pointer",
    "points":            "Point",
    "turnovers":         "Turnover",
}

ACTION_PICKER_NAMES = {
    "goals": "Goal",
    "goal_assist": "Pass",
    "accurate_pass": "Pass",
    "shots_on_target": "Shot",
    "clean_sheet": "Clean Sheet",
    "duel_won": "Duel",
    "saves": "Save",
    "yellow_card": "Card",
    "red_card": "Card",
    "assist_penalty_won": "Penalty",
    "clearance_off_line": "Clearance",
    "won_contest": "Dribble",
    "won_tackle": "Tackle",
    "interception_won": "Interception",
    "effective_clearance": "Clearance",
    "poss_won": "Possession",
    "ontarget_scoring_att": "Shot",
    "pen_area_entries": "Box Entry",
    "accurate_long_balls": "Long Ball",
    "successful_final_third_passes": "Final Third Pass",
    "fouls": "Foul",
    "was_fouled": "Foul Drawn",
    "big_chance_created": "Big Chance",
    "penalty_won": "Penalty",
    "penalty_save": "Penalty Save",
    "last_man_tackle": "Last Man Tackle",
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def ask(prompt, default=None):
    """Pose une question et retourne la réponse."""
    suffix = f" [{default}]" if default else ""
    answer = input(f"\n{prompt}{suffix}: ").strip()
    return answer if answer else default


def ask_int(prompt, default=None):
    """Pose une question et retourne un entier."""
    while True:
        raw = ask(prompt, default=str(default) if default else None)
        if raw is None:
            print("  ⚠  Une valeur est requise.")
            continue
        try:
            return int(raw)
        except ValueError:
            print("  ⚠  Merci d'entrer un nombre entier.")


def ask_yes_no(prompt, default=True):
    """Pose une question oui/non."""
    hint = "O/n" if default else "o/N"
    answer = input(f"\n{prompt} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("o", "oui", "y", "yes")


def ask_choice(prompt, choices):
    """Affiche un menu numéroté et retourne le choix."""
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    while True:
        raw = input("Votre choix: ").strip()
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except ValueError:
            pass
        print(f"  ⚠  Choisissez un nombre entre 1 et {len(choices)}.")


def ask_multiple(prompt, choices):
    """Permet de sélectionner plusieurs éléments dans une liste."""
    print(f"\n{prompt}")
    for i, choice in enumerate(choices, 1):
        print(f"  {i}. {choice}")
    print("(Entrez les numéros séparés par des virgules, ex: 1,3)")
    while True:
        raw = input("Votre choix: ").strip()
        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected = []
            for idx in indices:
                if 1 <= idx <= len(choices):
                    selected.append(choices[idx - 1])
                else:
                    raise ValueError
            if selected:
                return selected
        except ValueError:
            pass
        print(f"  ⚠  Entrez des numéros valides entre 1 et {len(choices)}, séparés par des virgules.")


def fuzzy_search(query, items, key="name"):
    """Recherche fuzzy dans une liste d'objets avec aliases."""
    query_lower = query.lower().strip()

    # Recherche exacte d'abord
    for item in items:
        if item.get(key, "").lower() == query_lower:
            return item
        # Check aliases
        if "aliases" in item:
            for alias in item["aliases"]:
                if alias.lower() == query_lower:
                    return item

    # Recherche partielle
    for item in items:
        if query_lower in item.get(key, "").lower():
            return item
        if "aliases" in item:
            for alias in item["aliases"]:
                if query_lower in alias.lower():
                    return item

    # Fuzzy match sur les noms
    names = [item.get(key, "") for item in items]
    matches = get_close_matches(query, names, n=1, cutoff=0.6)
    if matches:
        for item in items:
            if item.get(key, "") == matches[0]:
                return item

    return None


NATIONAL_TEAM_COMPETITIONS = {
    "fifa-world-cup-qualification-europe",
    "fifa-world-cup-qualification-south-america",
    "fifa-world-cup-qualification-intercontinental",
}


def find_team_info(query, sport):
    """Trouve le slug et le nom d'une équipe à partir d'un nom/alias. Retourne (slug, name, is_national)."""
    if sport == "nba":
        result = fuzzy_search(query, NBA_TEAMS)
        if result:
            return result["slug"], result["name"], False
        return None, None, False

    # Football : chercher dans toutes les ligues
    for league_slug, clubs in FOOTBALL_CLUBS.items():
        result = fuzzy_search(query, clubs)
        if result:
            is_national = league_slug in NATIONAL_TEAM_COMPETITIONS
            return result["slug"], result["name"], is_national

    return None, None, False


def find_team_slug(query, sport):
    """Trouve le slug d'une équipe à partir d'un nom/alias."""
    slug, _, _ = find_team_info(query, sport)
    return slug


def find_competition_info(query):
    """Trouve le slug et le nom d'une compétition. Retourne (slug, name)."""
    result = fuzzy_search(query, FOOTBALL_COMPETITIONS)
    if result:
        return result["slug"], result["name"]
    return None, None


def find_competition_slug(query):
    """Trouve le slug d'une compétition à partir d'un nom/alias."""
    slug, _ = find_competition_info(query)
    return slug


def slugify(text):
    """Transforme un titre en nom de fichier propre."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "_", text)
    return text


def format_action_label(action, sport):
    """Rend un nom d'action lisible pour la description."""
    sport_actions = DECISIVE_ACTIONS.get(sport, {})
    if action in sport_actions:
        return sport_actions[action]["label"]
    return action.replace("_", " ")


# ── Génération du titre ───────────────────────────────────────────────────────


def generate_title_nba(actions, mission_type, team_names=None):
    """Génère automatiquement le titre pour une mission NBA."""
    first_action = actions[0] if actions else ""
    picker_name = NBA_ACTION_PICKER_NAMES.get(first_action, first_action.replace('_', ' ').title())

    if mission_type == "Match spécifique" and team_names and len(team_names) >= 2:
        return f"{team_names[0]} vs {team_names[1]}"
    elif mission_type == "All Matches":
        return f"{picker_name} - All Matches"
    else:
        return picker_name


def generate_title_football(actions, mission_type, competition_names=None, club_names=None):
    """Génère automatiquement le titre pour une mission football en mode decisive."""
    # Déterminer le nom à partir de la première action
    first_action = actions[0] if actions else ""
    if first_action in ACTION_PICKER_NAMES:
        picker_name = ACTION_PICKER_NAMES[first_action]
    else:
        picker_name = first_action.replace("_", " ").title()

    if mission_type == "Match spécifique" and club_names and len(club_names) >= 2:
        return " vs ".join(club_names)
    elif mission_type == "Match spécifique":
        return picker_name
    elif mission_type == "All Matches":
        return f"{picker_name} - All Matches"
    elif mission_type == "Compétition" and competition_names:
        return f"{picker_name} - {competition_names[0]}"
    else:
        return picker_name


# ── Génération de la description ─────────────────────────────────────────────


def generate_description(sport, mode, target, reward_per_pick, reward_total, essence_name, picked_count, actions=None, mission_type=None, competition_name=None, reward_type="essence", clue_currency=None, positions=None, age_min=None, age_max=None, mc_amount=None, mc_total=None, club_names=None, max_avg_score=None):
    """Génère une description cohérente pour la mission."""
    # Déterminer le sujet selon la position
    if positions and len(positions) == 1:
        pick_subject = f"a {positions[0].lower()}"
    else:
        pick_subject = "a player"

    # Ajouter "from one of the following teams" si Match spécifique avec 3+ équipes
    if mission_type == "Match spécifique" and club_names and len(club_names) > 2:
        pick_subject += " from one of the following teams"

    # Ajouter la contrainte d'âge au sujet
    if age_min and age_max:
        pick_subject += f" aged {age_min} to {age_max}"
    elif age_max:
        pick_subject += f" under {age_max} years old"
    elif age_min:
        pick_subject += f" aged {age_min} or older"

    # Ajouter la contrainte L10
    if max_avg_score:
        pick_subject += f" with a L10 average of {max_avg_score} or less"

    # Reward labels
    if reward_type == "market credit":
        per_pick_display = mc_amount or 0
        total_display = mc_total or 0
        bonus_sentence = ""
        if total_display > per_pick_display * picked_count:
            bonus_sentence = f" Win up to ${total_display} in market credit if all picks are successful."
    elif reward_type == "clues":
        clue_label = CLUE_LABELS.get(clue_currency, "Clue")
        reward_label = clue_label + ("s" if reward_per_pick > 1 else "")
        reward_label_total = clue_label + ("s" if reward_total > 1 else "")
    else:
        # En football, utiliser "All-Star Essence" si l'essence n'est pas précisée
        if sport == "football" and essence_name in ("Essence", ""):
            essence_name = "All-Star Essence"
        reward_label = essence_name
        reward_label_total = essence_name

    # Calcul du bonus (non market credit)
    if reward_type != "market credit":
        base_total = reward_per_pick * picked_count
        bonus = reward_total - base_total
        bonus_sentence = ""
        if bonus > 0:
            bonus_sentence = f" Win up to {reward_total} {reward_label_total} if all picks are successful."

    multi_team = club_names and len(club_names) > 2

    if mode == "score":
        # Mode score : basé sur les points
        if mission_type == "Compétition":
            match_context = f"in today's {competition_name} matches" if competition_name else "in today's matches"
        elif sport == "football":
            if mission_type == "All Matches":
                match_context = "in any match"
            else:
                match_context = "in his match" if multi_team else "in this match"
        else:
            match_context = "in today's game"

        if reward_type == "market credit":
            return (
                f"Classic: Pick {pick_subject} who scores {target} points {match_context} "
                f"and win ${per_pick_display} in market credit per correct choice."
                f"{bonus_sentence}"
            )
        return (
            f"Classic: Pick {pick_subject} who scores {target} points {match_context} "
            f"and win {reward_per_pick} {reward_label} per correct choice."
            f"{bonus_sentence}"
        )

    # Mode decisive : basé sur des actions
    action_parts = []
    for a in actions:
        label = DESCRIPTION_LABEL_OVERRIDES.get(a) or format_action_label(a, sport)
        if target > 1:
            label = pluralize_label(label)
        action_parts.append(f"{target}+ {label}")

    action_text = " or provides ".join(action_parts) if sport == "football" else " or ".join(action_parts)

    if sport == "football":
        if mission_type == "All Matches":
            match_context = "in any match"
        elif mission_type == "Compétition":
            match_context = f"in today's {competition_name} matches" if competition_name else "in today's matches"
        else:
            match_context = "in his match" if multi_team else "in this match"
        verb = ACTION_VERBS.get(actions[0], "achieves") if len(actions) == 1 else "scores"
    else:
        match_context = "in today's game"
        verb = ACTION_VERBS.get(actions[0], "makes") if len(actions) == 1 else "makes"

    if reward_type == "market credit":
        return (
            f"Classic: Pick {pick_subject} who {verb} {action_text} {match_context} "
            f"and win ${per_pick_display} in market credit per correct choice."
            f"{bonus_sentence}"
        )
    return (
        f"Classic: Pick {pick_subject} who {verb} {action_text} {match_context} "
        f"and win {reward_per_pick} {reward_label} per correct choice."
        f"{bonus_sentence}"
    )


def generate_milestone_description(sport, milestones, milestone_reward_amounts, milestone_reward_type, essence_name=None, clue_currency=None, mission_type=None, competition_name=None, positions=None, age_min=None, age_max=None, club_names=None, max_avg_score=None):
    """Génère une description pour une mission avec rewards par palier de DS."""
    # Sujet
    if positions and len(positions) == 1:
        pick_subject = f"a {positions[0].lower()}"
    else:
        pick_subject = "a player"

    if mission_type == "Match spécifique" and club_names and len(club_names) > 2:
        pick_subject += " from one of the following teams"

    if age_min and age_max:
        pick_subject += f" aged {age_min} to {age_max}"
    elif age_max:
        pick_subject += f" under {age_max} years old"
    elif age_min:
        pick_subject += f" aged {age_min} or older"

    if max_avg_score:
        pick_subject += f" with a L10 average of {max_avg_score} or less"

    # Contexte du match
    multi_team = club_names and len(club_names) > 2
    if sport == "football":
        if mission_type == "All Matches":
            match_context = "in any match"
        elif mission_type == "Compétition":
            match_context = f"in today's {competition_name} matches" if competition_name else "in today's matches"
        else:
            match_context = "in his match" if multi_team else "in this match"
    else:
        match_context = "in today's game"

    # Verbe + action du premier milestone pour l'intro
    first_action = milestones[0]["stat"]
    first_target = milestones[0]["min"]
    if sport == "football":
        verb = ACTION_VERBS.get(first_action, "achieves")
    else:
        verb = ACTION_VERBS.get(first_action, "makes")

    first_label = DESCRIPTION_LABEL_OVERRIDES.get(first_action) or format_action_label(first_action, sport)
    if first_target > 1:
        first_label = pluralize_label(first_label)

    # Reward label
    if milestone_reward_type.lower() == "market credit":
        reward_unit = "in market credit"
    elif milestone_reward_type.lower() == "clues":
        reward_unit = CLUE_LABELS.get(clue_currency, "Clue")
    else:
        if sport == "football" and essence_name in ("Essence", "", None):
            reward_unit = "All-Star Essence"
        else:
            reward_unit = essence_name or "Essence"

    # Tiers description
    tier_parts = []
    for i, ms in enumerate(milestones):
        ms_label = DESCRIPTION_LABEL_OVERRIDES.get(ms["stat"]) or format_action_label(ms["stat"], sport)
        if ms["min"] > 1:
            ms_label = pluralize_label(ms_label)
        amt = milestone_reward_amounts[i]
        if milestone_reward_type.lower() == "market credit":
            tier_parts.append(f"{ms['min']}+ {ms_label} = ${amt} {reward_unit}")
        else:
            tier_parts.append(f"{ms['min']}+ {ms_label} = {amt} {reward_unit}")

    return (
        f"Classic: Pick {pick_subject} who {verb} {first_target}+ {first_label} {match_context}. "
        f"Rewards: {', '.join(tier_parts)}."
    )


# ── Collecte des informations ────────────────────────────────────────────────


def collect_inputs():
    """Pose toutes les questions et retourne un dict de paramètres."""
    params = {}

    print("=" * 60)
    print("   GÉNÉRATEUR DE MISSIONS SORARE")
    print("=" * 60)

    # 1. Sport
    params["sport"] = ask_choice("Quel sport ?", ["Football", "NBA"]).lower()

    # 2. Type de mission
    params["mission_type"] = ask_choice(
        "Type de mission ?",
        ["Match spécifique", "Compétition", "All Matches"],
    )

    # 3a. Clubs (si match spécifique)
    if params["mission_type"] == "Match spécifique":
        print("\nEntrez les noms des clubs (ex: PSG, Marseille, Lakers, Celtics)")
        print("Le script trouvera automatiquement les slugs.")
        clubs = []
        club_names = []
        while True:
            query = ask(f"Club {len(clubs) + 1} (laisser vide pour terminer)" if clubs else "Club 1")
            if not query:
                if len(clubs) >= 2:
                    break
                print("  ⚠  Il faut au minimum 2 clubs.")
                continue

            slug, name, _ = find_team_info(query, params["sport"])
            if slug:
                print(f"  ✓ Trouvé : {name} ({slug})")
                clubs.append(slug)
                club_names.append(name)
            else:
                print(f"  ⚠  Club non trouvé. Saisir le slug manuellement ?")
                manual = ask("Slug manuel (ou laisser vide pour réessayer)")
                if manual:
                    clubs.append(manual)
                    club_names.append(manual)
        params["clubs"] = clubs
        params["club_names"] = club_names

    # 3b. Compétitions (si compétition)
    if params["mission_type"] == "Compétition":
        print("\nEntrez les noms des compétitions (ex: Champions League, Ligue 1, Premier League)")
        print("Le script trouvera automatiquement les slugs.")
        competitions = []
        competition_names = []
        while True:
            query = ask(f"Compétition {len(competitions) + 1} (laisser vide pour terminer)" if competitions else "Compétition 1")
            if not query:
                if len(competitions) >= 1:
                    break
                print("  ⚠  Il faut au minimum 1 compétition.")
                continue

            slug, name = find_competition_info(query)
            if slug:
                print(f"  ✓ Trouvé : {name} ({slug})")
                competitions.append(slug)
                competition_names.append(name)
            else:
                print(f"  ⚠  Compétition non trouvée. Saisir le slug manuellement ?")
                manual = ask("Slug manuel (ou laisser vide pour réessayer)")
                if manual:
                    competitions.append(manual)
                    competition_names.append(manual)
        params["competitions"] = competitions
        params["competition_names"] = competition_names

    # 4. Mode
    params["mode"] = ask_choice(
        "Mode de la mission ?",
        ["decisive (actions spécifiques)", "score (points du joueur)"],
    ).split(" ")[0]

    # 7. Decisive actions (seulement en mode decisive) — collecte avant le titre pour auto-génération
    if params["mode"] == "decisive":
        sport_actions = DECISIVE_ACTIONS[params["sport"]]
        actions_list = list(sport_actions.keys())

        print(f"\nDecisive action(s) ? (avec target par défaut)")
        for i, action_key in enumerate(actions_list, 1):
            target_default = sport_actions[action_key]["target"]
            label = sport_actions[action_key]["label"]
            print(f"  {i}. {action_key} (target: {target_default}) - {label}")
        print("(Entrez les numéros séparés par des virgules, ex: 1,3)")

        while True:
            raw = input("Votre choix: ").strip()
            try:
                indices = [int(x.strip()) for x in raw.split(",")]
                selected = []
                for idx in indices:
                    if 1 <= idx <= len(actions_list):
                        selected.append(actions_list[idx - 1])
                    else:
                        raise ValueError
                if selected:
                    params["decisive_actions"] = selected
                    break
            except ValueError:
                print(f"  ⚠  Entrez des numéros valides entre 1 et {len(actions_list)}, séparés par des virgules.")

        if len(params["decisive_actions"]) == 1:
            default_target = sport_actions[params["decisive_actions"][0]]["target"]
        else:
            default_target = sport_actions[params["decisive_actions"][0]]["target"]
    else:
        default_target = 100

    # 5. Titre — auto-généré dans certains cas
    auto_title = None
    if params["sport"] == "nba" and params["mode"] == "decisive" and params.get("decisive_actions"):
        auto_title = generate_title_nba(
            params["decisive_actions"],
            params["mission_type"],
            params.get("club_names"),
        )
    elif params["sport"] == "football" and params["mode"] == "decisive":
        auto_title = generate_title_football(
            params.get("decisive_actions", []),
            params["mission_type"],
            params.get("competition_names"),
        )

    if auto_title:
        print(f"\n✓ Titre auto-généré : {auto_title}")
        use_auto = ask_yes_no("Utiliser ce titre ?", default=True)
        params["title"] = auto_title if use_auto else ask("Titre de la mission")
    elif params["mission_type"] == "All Matches":
        params["title"] = ask("Titre de la mission", default="All Matches")
    else:
        params["title"] = ask("Titre de la mission")

    # 6. Order (optionnel, surtout pour compétitions)
    if params["mission_type"] == "Compétition":
        order_raw = ask("Order (optionnel, laisser vide si aucun)")
        params["order"] = int(order_raw) if order_raw else None
    else:
        params["order"] = None

    # 8. Target
    target_label = "Target (nombre de points requis)" if params["mode"] == "score" else "Target (nombre requis pour valider)"
    params["target"] = ask_int(target_label, default=default_target)

    # 7. Picked count
    params["picked_count"] = ask_int("Nombre de picks (picked_count)", default=3)

    # 8. Rarity
    params["rarity"] = ask_choice(
        "Rareté des cartes ?",
        ["limited", "rare", "super_rare", "unique"],
    )

    # 9. Rewards
    params["reward_type"] = ask_choice(
        "Type de reward ?",
        ["essence", "clues"],
    )

    if params["reward_type"] == "clues":
        clue_options = CLUE_OPTIONS_BY_SPORT[params["sport"]]
        labels = [f"{label} ({currency})" for label, currency in clue_options]
        chosen = ask_choice("Type de Clue ?", labels)
        chosen_idx = labels.index(chosen)
        params["clue_currency"] = clue_options[chosen_idx][1]

        params["reward_per_pick"] = ask_int("Clues par pick réussi", default=16)
        default_bonus = params["reward_per_pick"] * params["picked_count"]
        total_max = params["reward_per_pick"] * params["picked_count"] + default_bonus
        params["reward_total"] = ask_int("Clues TOTAL si tous les picks réussis", default=total_max)
    else:
        params["clue_currency"] = None
        params["reward_per_pick"] = ask_int("Reward par pick réussi (en Essence)", default=50)
        default_bonus = params["reward_per_pick"] * params["picked_count"]
        total_max = params["reward_per_pick"] * params["picked_count"] + default_bonus
        params["reward_total"] = ask_int("Reward TOTAL si tous les picks réussis (en Essence)", default=total_max)

    # Calcul automatique du bonus "all_appearances_successful"
    base_total = params["reward_per_pick"] * params["picked_count"]
    params["reward_bonus"] = params["reward_total"] - base_total

    # 10. Flavour / Ligue - Auto-détection depuis la compétition
    detected_flavour = None
    if params["mission_type"] == "Compétition" and params.get("competitions"):
        # Chercher le flavour de la première compétition
        for comp in FOOTBALL_COMPETITIONS:
            if comp["slug"] in params["competitions"]:
                detected_flavour = comp.get("flavour")
                break

    if detected_flavour:
        print(f"\n✓ Flavour auto-détecté : {detected_flavour}")
        use_detected = ask_yes_no("Utiliser ce flavour ?", default=True)
        params["flavour"] = detected_flavour if use_detected else None
    else:
        print("\nFlavour de ligue (optionnel) — exemples :")
        print("  SEASONAL-ENGLAND, SEASONAL-SPAIN, SEASONAL-FRANCE, etc.")
        params["flavour"] = ask("Flavour (laisser vide si aucune)") or None

    # 11. Essence name (pour la description)
    if params["flavour"]:
        essence_map = {
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
        default_essence = essence_map.get(params["flavour"], f"{params['flavour'].replace('SEASONAL-', '').title()} Essence")
    elif params["mission_type"] == "All Matches" and params["sport"] == "football":
        default_essence = "All-Star Essence"
    else:
        default_essence = "Essence"
    params["essence_name"] = ask("Nom de l'Essence (pour la description)", default=default_essence)

    # 12. Options avancées
    print("\n--- Options avancées ---")
    params["stay_completed"] = ask_yes_no("stay_completed_at_expiration ?", default=True)
    params["disable_auto_claim"] = ask_yes_no("disable_auto_claim_at_expiration ?", default=True)

    return params


# ── Construction des JSON ─────────────────────────────────────────────────────


def build_mission(params):
    """Construit le dict de la mission."""
    competition_names = params.get("competition_names", [])
    description = generate_description(
        sport=params["sport"],
        mode=params["mode"],
        target=params["target"],
        reward_per_pick=params["reward_per_pick"],
        reward_total=params["reward_total"],
        essence_name=params["essence_name"],
        picked_count=params["picked_count"],
        actions=params.get("decisive_actions"),
        mission_type=params["mission_type"],
        competition_name=competition_names[0] if competition_names else None,
        reward_type=params.get("reward_type", "essence"),
        clue_currency=params.get("clue_currency"),
        positions=params.get("positions"),
        age_min=params.get("age_min"),
        age_max=params.get("age_max"),
        mc_amount=params.get("mc_amount"),
        mc_total=params.get("mc_total"),
        club_names=params.get("club_names"),
        max_avg_score=params.get("max_avg_score"),
    )

    mission = {
        "mode": params["mode"],
        "title": params["title"],
        "sealed": False,
        "target": params["target"],
        "rarities": [params["rarity"]],
        "description": description,
        "picked_count": params["picked_count"],
        "max_player_occurence": 1,
        "prevent_concurrent_picks": True,
        "stay_completed_at_expiration": params["stay_completed"],
        "disable_auto_claim_at_expiration": params["disable_auto_claim"],
    }

    # Editions (NBA)
    if params.get("editions"):
        mission["editions"] = params["editions"]

    # Decisive actions seulement en mode decisive
    if params["mode"] == "decisive":
        mission["decisive_actions"] = params["decisive_actions"]

    # Order (si défini)
    if params.get("order") is not None:
        mission["order"] = params["order"]

    # Rules selon le type de mission
    rules = None
    if params["mission_type"] == "Match spécifique":
        rules = {}
        if params.get("clubs"):
            rules["active_clubs"] = params["clubs"]
        if params.get("national_teams"):
            rules["active_national_teams"] = params["national_teams"]
    elif params["mission_type"] == "Compétition":
        rules = {"competitions": params["competitions"]}

    # Ajouter les positions au niveau racine si spécifiées
    if params.get("positions"):
        mission["positions"] = params["positions"]

    # Ajouter la contrainte d'âge dans rules
    if params.get("age_min") or params.get("age_max"):
        if rules is None:
            rules = {}
        age_rule = {}
        if params.get("age_min"):
            age_rule["min"] = params["age_min"]
        if params.get("age_max"):
            age_rule["max"] = params["age_max"]
        rules["age"] = age_rule

    # Ajouter maximum_players_average_score dans rules
    if params.get("max_avg_score"):
        if rules is None:
            rules = {}
        rules["maximum_players_average_score"] = {
            "max": params["max_avg_score"],
            "count": params.get("max_avg_count", 0),
            "average_type": "last_ten_played_so5_average_score",
        }

    # Réordonner pour placer mode, order, rules en tête
    if rules is not None or params.get("order") is not None:
        ordered = {"mode": mission.pop("mode")}
        if params.get("order") is not None:
            ordered["order"] = mission.pop("order")
        if rules is not None:
            ordered["rules"] = rules
        ordered.update(mission)
        mission = ordered

    return mission


def build_reward(params):
    """Construit le dict des rewards."""
    reward_type = params.get("reward_type", "essence")

    if reward_type == "market credit":
        sport_upper = params["sport"].upper()
        rarity_upper = params["rarity"].upper()
        mc_amount_cents = params["mc_amount"] * 100
        duration = params.get("mc_duration", 30)
        discount_bp = params.get("mc_discount_bp", 5000)
        by_appearance = {
            "filter": "by_rarity",
            "conversion_credits": [
                {
                    "max_discount": {
                        "reference_currency": "CURRENCY_USD",
                        "amounts": [{"currency": "CURRENCY_USD", "amount": mc_amount_cents}],
                    },
                    "duration_in_days": duration,
                    "percentage_discount_basis_point": discount_bp,
                    "rarity": rarity_upper,
                    "sport": sport_upper,
                }
            ],
        }
        mc_bonus = params.get("mc_bonus_amount", 0)
        if mc_bonus and mc_bonus > 0:
            mc_bonus_cents = mc_bonus * 100
            by_appearance["all_appearances_successful"] = {
                "conversion_credit": {
                    "max_discount": {
                        "reference_currency": "CURRENCY_USD",
                        "amounts": [{"currency": "CURRENCY_USD", "amount": mc_bonus_cents}],
                    },
                    "duration_in_days": params.get("mc_bonus_duration", 30),
                    "percentage_discount_basis_point": params.get("mc_bonus_discount_bp", 5000),
                    "sport": sport_upper,
                },
            }
        reward = {"by_appearance": by_appearance}
    elif reward_type == "clues":
        currency = params.get("clue_currency", "BEST_STAR_RANK_CRAFT_CLUE")
        by_appearance = {
            "filter": "by_rarity",
            "in_game_currencies": [
                {"amount": params["reward_per_pick"], "currency": currency}
            ],
        }
        if params.get("reward_bonus", 0) > 0:
            by_appearance["all_appearances_successful"] = {
                "in_game_currencies": [
                    {"amount": params["reward_bonus"], "currency": currency}
                ]
            }
        reward = {"by_appearance": by_appearance}
    else:
        shard_entry = {
            "rarity": params["rarity"].upper(),
            "quantity": params["reward_per_pick"],
        }
        if params["flavour"]:
            shard_entry["flavour"] = params["flavour"]

        by_appearance = {
            "filter": "by_rarity",
            "card_shards": [shard_entry],
        }

        if params.get("reward_bonus", 0) > 0:
            bonus_entry = {
                "rarity": params["rarity"].upper(),
                "quantity": params["reward_bonus"],
            }
            if params["flavour"]:
                bonus_entry["flavour"] = params["flavour"]
            by_appearance["all_appearances_successful"] = {
                "card_shards": [bonus_entry],
            }

        reward = {"by_appearance": by_appearance}

    return reward


# ── Sauvegarde ────────────────────────────────────────────────────────────────


def save_files(mission, reward, title):
    """Sauvegarde les fichiers JSON dans un dossier dédié."""
    folder_name = slugify(title)
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", folder_name)
    os.makedirs(output_dir, exist_ok=True)

    mission_path = os.path.join(output_dir, "mission.json")
    reward_path = os.path.join(output_dir, "reward.json")

    with open(mission_path, "w", encoding="utf-8") as f:
        json.dump(mission, f, indent=2, ensure_ascii=False)

    with open(reward_path, "w", encoding="utf-8") as f:
        json.dump(reward, f, indent=2, ensure_ascii=False)

    return output_dir, mission_path, reward_path


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    try:
        params = collect_inputs()
    except (KeyboardInterrupt, EOFError):
        print("\n\nAnnulé.")
        sys.exit(0)

    mission = build_mission(params)
    reward = build_reward(params)

    # Aperçu
    print("\n" + "=" * 60)
    print("   APERÇU")
    print("=" * 60)
    print("\n📋 Mission:")
    print(json.dumps(mission, indent=2, ensure_ascii=False))
    print("\n🎁 Reward:")
    print(json.dumps(reward, indent=2, ensure_ascii=False))

    # Confirmation
    print()
    if not ask_yes_no("Sauvegarder ces fichiers ?", default=True):
        print("Annulé.")
        sys.exit(0)

    output_dir, mission_path, reward_path = save_files(mission, reward, params["title"])

    print("\n" + "=" * 60)
    print("   FICHIERS GÉNÉRÉS")
    print("=" * 60)
    print(f"\n  Dossier : {output_dir}")
    print(f"  → {mission_path}")
    print(f"  → {reward_path}")
    print()


if __name__ == "__main__":
    main()
