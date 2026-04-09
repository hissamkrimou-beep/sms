import time

import requests
import streamlit as st

GRAPHQL_URL = "https://api.sorare.com/graphql"

FIXTURES_QUERY = """
query($first: Int!) {
  so5 {
    so5Fixtures(first: $first) {
      nodes {
        slug
        displayName
        startDate
        endDate
        gameWeek
      }
    }
  }
}
"""

FIXTURE_GAMES_QUERY = """
query($slug: String!) {
  so5 {
    so5Fixture(slug: $slug) {
      slug
      displayName
      startDate
      endDate
      games {
        id
        date
        homeTeam {
          ... on TeamInterface {
            slug
            name
          }
        }
        awayTeam {
          ... on TeamInterface {
            slug
            name
          }
        }
        competition {
          slug
          displayName
        }
      }
    }
  }
}
"""


def _graphql_request(query, variables=None, api_key=None, retries=2):
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["APIKEY"] = api_key
    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                GRAPHQL_URL,
                json={"query": query, "variables": variables or {}},
                headers=headers,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise Exception(data["errors"][0]["message"])
            return data["data"]
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise


@st.cache_data(ttl=3600)
def fetch_fixtures(api_key=None, count=10):
    data = _graphql_request(FIXTURES_QUERY, {"first": count}, api_key)
    return data["so5"]["so5Fixtures"]["nodes"]


@st.cache_data(ttl=3600)
def fetch_fixture_games(slug, api_key=None, _v=2):
    data = _graphql_request(FIXTURE_GAMES_QUERY, {"slug": slug}, api_key)
    return data["so5"]["so5Fixture"]


# --- Deadlines: fixture leaderboards with competition mapping ---

FIXTURE_LEADERBOARDS_QUERY = """
query($slug: String!) {
  so5 {
    so5Fixture(slug: $slug) {
      so5Leaderboards {
        so5League { slug displayName }
        rules {
          competitions { slug }
        }
      }
    }
  }
}
"""


@st.cache_data(ttl=3600)
def fetch_fixture_leaderboards(slug, api_key=None):
    """Return a dict mapping so5League displayName → set of competition slugs."""
    data = _graphql_request(FIXTURE_LEADERBOARDS_QUERY, {"slug": slug}, api_key)
    leaderboards = data["so5"]["so5Fixture"]["so5Leaderboards"]
    league_comps = {}
    for lb in leaderboards:
        league_name = lb["so5League"]["displayName"]
        if league_name not in league_comps:
            league_comps[league_name] = []
        for c in (lb["rules"].get("competitions") or []):
            if c["slug"] not in league_comps[league_name]:
                league_comps[league_name].append(c["slug"])
    return league_comps


# --- League Monitor: team players with scores ---

TEAM_PLAYERS_QUERY = """
query($slug: String!, $after: String) {
  team(slug: $slug) {
    players(after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        slug
        firstName
        lastName
        position
        age
        activeClub { slug name }
        so5Scores(last: 40) {
          score
          playerGameStats { minsPlayed }
          game { date }
        }
      }
    }
  }
}
"""


@st.cache_data(ttl=3600)
def fetch_team_players_with_scores(team_slug, api_key=None, _v=5):
    all_nodes = []
    cursor = None
    while True:
        variables = {"slug": team_slug}
        if cursor:
            variables["after"] = cursor
        data = _graphql_request(TEAM_PLAYERS_QUERY, variables, api_key)
        page = data["team"]["players"]
        all_nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return all_nodes


# --- SorareInside: starting probability predictions ---

SORAREINSIDE_API_URL = "https://partners-api.sorareinside.com"


@st.cache_data(ttl=1800)
def fetch_start_odds(game_ids, si_api_key):
    """Fetch start odds from SorareInside for a list of Sorare game IDs.

    Returns a dict mapping player UUID → startOdds (0-1).
    game_ids should be the raw UUIDs (without 'Game:' prefix).
    """
    if not si_api_key or not game_ids:
        return {}
    headers = {"x-api-key": si_api_key}
    odds = {}
    for gid in game_ids:
        try:
            resp = requests.get(
                f"{SORAREINSIDE_API_URL}/projections/game/{gid}",
                headers=headers,
                timeout=15,
            )
            if resp.status_code != 200:
                continue
            for proj in resp.json():
                pid = proj.get("playerId", "")
                so = proj.get("startOdds")
                if pid and so is not None:
                    # Keep highest odds if player appears in multiple games
                    if pid not in odds or so > odds[pid]:
                        odds[pid] = so
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            continue
    return odds


def fetch_player_prices_batch(slugs, since, api_key=None, batch_size=10):
    """Fetch Limited tokenPrices for multiple players in batched GraphQL requests.

    Uses aliased queries to fetch up to batch_size players per request.
    Returns dict: slug → list of {"date": str, "eur_cents": int}
    """
    if not slugs:
        return {}
    result = {}
    for start in range(0, len(slugs), batch_size):
        batch = slugs[start:start + batch_size]
        aliases = []
        for i, slug in enumerate(batch):
            aliases.append(
                f'p{i}: player(slug: "{slug}") {{ '
                f'tokenPrices(rarity: limited, since: "{since}", first: 100) {{ '
                f'nodes {{ date amounts {{ eurCents }} }} }} }}'
            )
        query = "{ football { " + " ".join(aliases) + " } }"
        try:
            data = _graphql_request(query, api_key=api_key)
            football = data.get("football", {})
            for i, slug in enumerate(batch):
                player_data = football.get(f"p{i}")
                if not player_data:
                    result[slug] = []
                    continue
                nodes = (player_data.get("tokenPrices") or {}).get("nodes") or []
                result[slug] = [
                    {"date": n["date"], "eur_cents": n["amounts"]["eurCents"]}
                    for n in nodes
                    if n.get("amounts", {}).get("eurCents")
                ]
        except Exception:
            for slug in batch:
                result.setdefault(slug, [])
    return result
