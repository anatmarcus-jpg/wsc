import requests
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

POLL_INTERVAL = 15
score_cache = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/"
}

# Sofascore tournament IDs
TOURNAMENTS = [
    (37, "Eredivisie", "🇳🇱"),
    (38, "Eerste Divisie", "🇳🇱"),
]


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


def get_live_games():
    """Get all live Dutch football games from Sofascore."""
    games = []
    
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    for tid, name, flag in TOURNAMENTS:
        try:
            # Use scheduled events for today filtered by tournament
            url = f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/events/live"
            res = requests.get(url, headers=HEADERS, timeout=10)
            logging.info(f"{name} (live endpoint): status={res.status_code}")
            
            if res.status_code == 200:
                data = res.json()
                events = data.get("events", [])
                logging.info(f"{name}: {len(events)} live events")
                for e in events:
                    hs = e.get("homeScore", {}).get("current", 0) or 0
                    as_ = e.get("awayScore", {}).get("current", 0) or 0
                    minute = e.get("time", {}).get("played", "?")
                    games.append({
                        "id": str(e["id"]),
                        "home": e["homeTeam"]["name"],
                        "away": e["awayTeam"]["name"],
                        "home_score": int(hs),
                        "away_score": int(as_),
                        "minute": minute,
                        "league": name,
                        "flag": flag,
                    })
                    logging.info(f"  {e['homeTeam']['name']} vs {e['awayTeam']['name']} | {hs}-{as_} | {minute}'")
            else:
                # Try scheduled events for today as fallback
                url2 = f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/season/current/events/last/0"
                res2 = requests.get(url2, headers=HEADERS, timeout=10)
                logging.info(f"{name} (fallback): status={res2.status_code}")
                
        except Exception as ex:
            logging.error(f"Error fetching {name}: {ex}")
    
    return games


def check_goals(game):
    gid = game["id"]
    hs = game["home_score"]
    as_ = game["away_score"]

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"  --> Now tracking {game['home']} vs {game['away']} at {hs}-{as_}")
        return

    home_goals = hs - prev["home"]
    away_goals = as_ - prev["away"]

    for _ in range(max(0, home_goals)):
        send_slack_message(
            f"{game['flag']} *GOAL!* — {game['league']}\n"
            f"⚽ *{game['home']}* score! ⏱️ {game['minute']}'\n"
            f"📊 *{game['home']} {hs} – {as_} {game['away']}*"
        )

    for _ in range(max(0, away_goals)):
        send_slack_message(
            f"{game['flag']} *GOAL!* — {game['league']}\n"
            f"⚽ *{game['away']}* score! ⏱️ {game['minute']}'\n"
            f"📊 *{game['home']} {hs} – {as_} {game['away']}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — Sofascore live data, polling every 15 seconds.")
    while True:
        try:
            games = get_live_games()
            logging.info(f"Total live games: {len(games)}")
            for game in games:
                check_goals(game)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
