import requests
import os
import logging
import time
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

POLL_INTERVAL = 15
score_cache = {}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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


def get_live_scores():
    """Scrape live scores from sofascore API - free and real-time."""
    games = []
    
    # Sofascore has a public API that powers their website
    # Get today's Eredivisie (tournament ID 37) and Eerste Divisie (tournament ID 38)
    for tournament_id, league_name in [("37", "Eredivisie"), ("38", "Eerste Divisie")]:
        try:
            url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/today"
            res = requests.get(url, headers=HEADERS, timeout=10)
            res.raise_for_status()
            data = res.json()
            events = data.get("events", [])
            
            for event in events:
                tournament = event.get("tournament", {})
                if tournament.get("uniqueTournament", {}).get("id") in [37, 38, 1390, 1391]:
                    home = event.get("homeTeam", {}).get("name", "")
                    away = event.get("awayTeam", {}).get("name", "")
                    hs = event.get("homeScore", {}).get("current", 0) or 0
                    as_ = event.get("awayScore", {}).get("current", 0) or 0
                    status = event.get("status", {}).get("type", "")
                    minute = event.get("time", {}).get("currentPeriodStartTimestamp", "")
                    game_id = str(event.get("id", ""))
                    league = event.get("tournament", {}).get("name", league_name)
                    
                    if status in ["inprogress"]:
                        games.append({
                            "id": game_id,
                            "home": home,
                            "away": away,
                            "home_score": int(hs),
                            "away_score": int(as_),
                            "status": status,
                            "minute": event.get("time", {}).get("played", "?"),
                            "league": league,
                            "flag": "🇳🇱"
                        })
                        logging.info(f"  {home} vs {away} | {hs}-{as_} | {status}")
            break  # Only need to call once, filter by tournament
        except Exception as e:
            logging.error(f"Sofascore error: {e}")
    
    return games


def get_live_scores_v2():
    """Use Sofascore's tournament-specific endpoint."""
    games = []
    
    # Eredivisie tournament ID on Sofascore = 37
    # Eerste Divisie = 38
    for tid, name, flag in [(37, "Eredivisie", "🇳🇱"), (38, "Eerste Divisie", "🇳🇱")]:
        try:
            from datetime import datetime
            today = datetime.utcnow().strftime("%Y-%m-%d")
            url = f"https://api.sofascore.com/api/v1/unique-tournament/{tid}/events/live"
            res = requests.get(url, headers=HEADERS, timeout=10)
            
            if res.status_code == 200:
                data = res.json()
                events = data.get("events", [])
                logging.info(f"{name}: {len(events)} live events")
                
                for event in events:
                    home = event.get("homeTeam", {}).get("name", "")
                    away = event.get("awayTeam", {}).get("name", "")
                    hs = event.get("homeScore", {}).get("current", 0) or 0
                    as_ = event.get("awayScore", {}).get("current", 0) or 0
                    status = event.get("status", {}).get("type", "")
                    minute = event.get("time", {}).get("played", "?")
                    game_id = str(event.get("id", ""))
                    
                    logging.info(f"  {home} vs {away} | {hs}-{as_} | {status} | {minute}'")
                    
                    games.append({
                        "id": game_id,
                        "home": home,
                        "away": away,
                        "home_score": int(hs),
                        "away_score": int(as_),
                        "status": status,
                        "minute": minute,
                        "league": name,
                        "flag": flag
                    })
        except Exception as e:
            logging.error(f"Sofascore error ({name}): {e}")
    
    return games


def check_goals(game):
    gid = game["id"]
    hs = game["home_score"]
    as_ = game["away_score"]

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"  --> Now tracking at {hs}-{as_}")
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
    logging.info("Bot started — using Sofascore live data, polling every 15 seconds.")
    while True:
        try:
            games = get_live_scores_v2()
            logging.info(f"Total live games: {len(games)}")
            for game in games:
                check_goals(game)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
