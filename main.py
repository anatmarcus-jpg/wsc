import requests
import os
import logging
import time
import json

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

POLL_INTERVAL = 15
STATE_FILE = "/tmp/score_cache.json"

COMPETITIONS = [
    {"code": "DED", "name": "Eredivisie", "flag": "🇳🇱"},
]


def load_cache():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except:
        return {}


def save_cache(cache):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        logging.error(f"Cache save error: {e}")


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


def get_todays_matches(competition_code):
    """Get all of today's matches regardless of status."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    url = f"https://api.football-data.org/v4/competitions/{competition_code}/matches"
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}
    params = {"dateFrom": today, "dateTo": today}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        matches = res.json().get("matches", [])
        logging.info(f"{competition_code}: {len(matches)} matches today")
        return matches
    except Exception as e:
        logging.error(f"football-data error: {e}")
        return []


def get_score(match):
    """Get current score - football-data updates fullTime live."""
    score = match.get("score", {})
    ft = score.get("fullTime", {})
    home = ft.get("home")
    away = ft.get("away")
    if home is not None and away is not None:
        return int(home), int(away)
    # Try halfTime as fallback
    ht = score.get("halfTime", {})
    home = ht.get("home")
    away = ht.get("away")
    if home is not None and away is not None:
        return int(home), int(away)
    return 0, 0


def check_goals(match, league_name, flag, cache):
    mid = str(match["id"])
    status = match.get("status", "")
    home_team = match["homeTeam"]["name"]
    away_team = match["awayTeam"]["name"]
    minute = match.get("minute", "?")
    hs, as_ = get_score(match)

    # Track IN_PLAY and PAUSED games
    is_live = status in ["IN_PLAY", "PAUSED"]
    
    logging.info(f"  {home_team} vs {away_team} | {hs}-{as_} | {status} | {minute}'")

    if not is_live:
        return

    prev = cache.get(mid)
    if prev is None:
        cache[mid] = {"home": hs, "away": as_}
        logging.info(f"  --> Now tracking at {hs}-{as_}")
        return

    home_goals = hs - prev["home"]
    away_goals = as_ - prev["away"]

    logging.info(f"  Change: {prev['home']}-{prev['away']} → {hs}-{as_}")

    for _ in range(max(0, home_goals)):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{home_team}* score! ⏱️ {minute}'\n"
            f"📊 *{home_team} {hs} – {as_} {away_team}*"
        )

    for _ in range(max(0, away_goals)):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{away_team}* score! ⏱️ {minute}'\n"
            f"📊 *{home_team} {hs} – {as_} {away_team}*"
        )

    cache[mid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — football-data.org, polling every 15 seconds.")
    cache = load_cache()
    logging.info(f"Loaded cache with {len(cache)} entries.")

    while True:
        try:
            for comp in COMPETITIONS:
                matches = get_todays_matches(comp["code"])
                for match in matches:
                    check_goals(match, comp["name"], comp["flag"], cache)
            save_cache(cache)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
