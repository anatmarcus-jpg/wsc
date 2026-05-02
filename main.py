import requests
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

# Multiple league IDs to cover all Dutch football
LEAGUES = [
    {"id": "ned.1", "name": "Eredivisie", "flag": "🇳🇱"},
    {"id": "ned.2", "name": "Eerste Divisie", "flag": "🇳🇱"},
    {"id": "ned.3", "name": "Netherlands 3rd", "flag": "🇳🇱"},
]

# Also try these ESPN game IDs directly for Ajax vs PSV
DIRECT_GAME_IDS = [
    "741256",  # Ajax vs PSV from ESPN URL
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


def get_games(league_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/scoreboard"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.json().get("events", [])
    except Exception as e:
        logging.error(f"ESPN error ({league_id}): {e}")
        return []


def get_game_direct(game_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/ned.1/summary?event={game_id}"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        # Extract game info from summary
        header = data.get("header", {})
        competitions = header.get("competitions", [])
        if competitions:
            comp = competitions[0]
            home = next((t for t in comp["competitors"] if t["homeAway"] == "home"), None)
            away = next((t for t in comp["competitors"] if t["homeAway"] == "away"), None)
            if home and away:
                game = {
                    "id": game_id,
                    "home_team": home["team"]["displayName"],
                    "away_team": away["team"]["displayName"],
                    "home_score": int(home.get("score", 0) or 0),
                    "away_score": int(away.get("score", 0) or 0),
                    "status": comp.get("status", {}).get("type", {}).get("description", ""),
                    "status_type": comp.get("status", {}).get("type", {}).get("name", ""),
                    "clock": comp.get("status", {}).get("displayClock", ""),
                }
                logging.info(f"  DIRECT: {game['home_team']} vs {game['away_team']} | {game['home_score']}-{game['away_score']} | status={game['status']} | type={game['status_type']}")
                return game
    except Exception as e:
        logging.error(f"Direct game fetch error ({game_id}): {e}")
    return None


def parse_game(event):
    try:
        comp = event["competitions"][0]
        home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
        away = next(t for t in comp["competitors"] if t["homeAway"] == "away")
        return {
            "id": event["id"],
            "home_team": home["team"]["displayName"],
            "away_team": away["team"]["displayName"],
            "home_score": int(home.get("score", 0) or 0),
            "away_score": int(away.get("score", 0) or 0),
            "status": event["status"]["type"]["description"],
            "status_type": event["status"]["type"]["name"],
            "clock": event["status"].get("displayClock", ""),
        }
    except Exception as e:
        logging.warning(f"Parse error: {e}")
        return None


def check_goals(game, league_name, flag):
    gid = game["id"]
    hs = game["home_score"]
    as_ = game["away_score"]
    status = game["status"].lower()
    status_type = game["status_type"].lower()

    logging.info(f"  {game['home_team']} vs {game['away_team']} | {hs}-{as_} | status={game['status']} | type={game['status_type']}")

    is_live = (
        any(s in status for s in ["progress", "halftime", "period", "live"]) or
        any(s in status_type for s in ["in", "progress", "live", "half"])
    )

    if not is_live:
        return

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"  --> Now tracking!")
        return

    for _ in range(max(0, hs - prev["home"])):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{game['home_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    for _ in range(max(0, as_ - prev["away"])):
        send_slack_message(
            f"{flag} *GOAL!* — {league_name}\n"
            f"⚽ *{game['away_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — polling every 15 seconds.")
    while True:
        try:
            # Poll all leagues
            for league in LEAGUES:
                events = get_games(league["id"])
                logging.info(f"{league['name']}: {len(events)} games")
                for event in events:
                    game = parse_game(event)
                    if game:
                        check_goals(game, league["name"], league["flag"])

            # Also check direct game IDs
            for game_id in DIRECT_GAME_IDS:
                game = get_game_direct(game_id)
                if game:
                    check_goals(game, "Eredivisie", "🇳🇱")

        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
