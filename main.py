import requests
import os
import logging
import time
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

POLL_INTERVAL = 15
score_cache = {}

# Direct ESPN game IDs for today's matches - ned.1 scoreboard
ESPN_LEAGUES = [
    ("ned.1", "Eredivisie", "🇳🇱"),
    ("ned.2", "Eerste Divisie", "🇳🇱"),
    ("ned.3", "Eredivisie Playoffs", "🇳🇱"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def send_slack_message(text):
    try:
        res = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            json={"channel": SLACK_CHANNEL_ID, "text": text},
            timeout=10,
        )
        data = res.json()
        if not data.get("ok"):
            logging.error(f"Slack error: {data.get('error')}")
        else:
            logging.info("Slack message sent!")
    except Exception as e:
        logging.error(f"Slack error: {e}")


def get_games(league_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/scoreboard"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        return res.json().get("events", [])
    except Exception as e:
        logging.error(f"ESPN error ({league_id}): {e}")
        return []


def get_game_detail(game_id, league_id="ned.1"):
    """Fetch individual game details for more accurate live score."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/summary?event={game_id}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            header = data.get("header", {})
            comps = header.get("competitions", [])
            if comps:
                comp = comps[0]
                home = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
                away = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
                if home and away:
                    return {
                        "home_score": int(home.get("score", 0) or 0),
                        "away_score": int(away.get("score", 0) or 0),
                        "status": comp.get("status", {}).get("type", {}).get("description", ""),
                        "clock": comp.get("status", {}).get("displayClock", ""),
                    }
    except Exception as e:
        logging.error(f"Game detail error ({game_id}): {e}")
    return None


def check_goals(game_id, home_team, away_team, hs, as_, status, clock, league_name, flag):
    gid = game_id
    status_lower = status.lower()

    is_live = any(s in status_lower for s in ["progress", "halftime", "half time", "first", "second"])

    logging.info(f"  {home_team} vs {away_team} | {hs}-{as_} | {status} | live={is_live}")

    if not is_live:
        return

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"  --> Tracking at {hs}-{as_}")
        return

    home_goals = hs - prev["home"]
    away_goals = as_ - prev["away"]

    logging.info(f"  Change: {prev['home']}-{prev['away']} → {hs}-{as_}")

    for _ in range(max(0, home_goals)):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{home_team}* score! ⏱️ {clock}\n"
            f"📊 *{home_team} {hs} – {as_} {away_team}*"
        )

    for _ in range(max(0, away_goals)):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{away_team}* score! ⏱️ {clock}\n"
            f"📊 *{home_team} {hs} – {as_} {away_team}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — ESPN summary API, polling every 15 seconds.")
    while True:
        try:
            all_game_ids = {}
            
            # First get all games from scoreboard
            for league_id, league_name, flag in ESPN_LEAGUES:
                events = get_games(league_id)
                logging.info(f"{league_name}: {len(events)} games")
                for event in events:
                    try:
                        comp = event["competitions"][0]
                        home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
                        away = next(t for t in comp["competitors"] if t["homeAway"] == "away")
                        all_game_ids[event["id"]] = {
                            "home": home["team"]["displayName"],
                            "away": away["team"]["displayName"],
                            "league": league_name,
                            "flag": flag,
                            "league_id": league_id,
                        }
                    except:
                        pass

            # Now fetch each game's detail for accurate live score
            for game_id, info in all_game_ids.items():
                detail = get_game_detail(game_id, info["league_id"])
                if detail:
                    check_goals(
                        game_id,
                        info["home"],
                        info["away"],
                        detail["home_score"],
                        detail["away_score"],
                        detail["status"],
                        detail["clock"],
                        info["league"],
                        info["flag"],
                    )

        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
