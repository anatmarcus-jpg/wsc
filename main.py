import requests
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")

COMPETITIONS = [
    {"code": "DED", "name": "Eredivisie", "flag": "🇳🇱"},
]

POLL_INTERVAL = 15
score_cache = {}


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


def get_score(match):
    """Extract current score correctly from football-data.org response."""
    score = match.get("score", {})
    
    # Try current score first
    current = score.get("fullTime", {})
    home = current.get("home")
    away = current.get("away")
    
    # If fullTime is null, try halfTime
    if home is None or away is None:
        half = score.get("halfTime", {})
        home = half.get("home")
        away = half.get("away")
    
    # If still null, default to 0
    if home is None: home = 0
    if away is None: away = 0
    
    return int(home), int(away)


def get_live_matches(competition_code):
    url = f"https://api.football-data.org/v4/competitions/{competition_code}/matches"
    headers = {"X-Auth-Token": FOOTBALL_API_KEY}
    params = {"status": "IN_PLAY,PAUSED"}
    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        res.raise_for_status()
        data = res.json()
        matches = data.get("matches", [])
        logging.info(f"{competition_code}: {len(matches)} live matches")
        return matches
    except Exception as e:
        logging.error(f"football-data error ({competition_code}): {e}")
        return []


def check_goals(match, league_name, flag):
    mid = str(match["id"])
    status = match.get("status", "")
    home_team = match["homeTeam"]["name"]
    away_team = match["awayTeam"]["name"]
    hs, as_ = get_score(match)
    minute = match.get("minute", "?")

    logging.info(f"  {home_team} vs {away_team} | {hs}-{as_} | status={status} | minute={minute}'")

    is_live = status in ["IN_PLAY", "PAUSED"]
    if not is_live:
        return

    prev = score_cache.get(mid)
    if prev is None:
        score_cache[mid] = {"home": hs, "away": as_}
        logging.info(f"  --> Now tracking at {hs}-{as_}")
        return

    home_goals = hs - prev["home"]
    away_goals = as_ - prev["away"]

    logging.info(f"  Score change: prev={prev['home']}-{prev['away']} now={hs}-{as_}")

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

    score_cache[mid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — polling every 15 seconds via football-data.org")
    while True:
        try:
            for comp in COMPETITIONS:
                matches = get_live_matches(comp["code"])
                for match in matches:
                    check_goals(match, comp["name"], comp["flag"])
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
