import requests
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

LEAGUES = [
    {"id": "ned.1", "name": "Eredivisie", "flag": "🇳🇱"},
    {"id": "ned.2", "name": "Eerste Divisie", "flag": "🇳🇱"},
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


def check_goals(game, league):
    gid = game["id"]
    hs = game["home_score"]
    as_ = game["away_score"]
    status = game["status"].lower()
    status_type = game["status_type"].lower()

    # Log every game status so we can debug
    logging.info(f"  {game['home_team']} vs {game['away_team']} | {hs}-{as_} | status={game['status']} | type={game['status_type']}")

    # Accept any non-scheduled, non-postponed status as potentially live
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
            f"{league['flag']} *GOAL!* — {league['name']}\n"
            f"⚽ *{game['home_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    for _ in range(max(0, as_ - prev["away"])):
        send_slack_message(
            f"{league['flag']} *GOAL!* — {league['name']}\n"
            f"⚽ *{game['away_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — polling every 15 seconds.")
    while True:
        try:
            for league in LEAGUES:
                events = get_games(league["id"])
                logging.info(f"{league['name']}: {len(events)} games")
                for event in events:
                    game = parse_game(event)
                    if game:
                        check_goals(game, league)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
