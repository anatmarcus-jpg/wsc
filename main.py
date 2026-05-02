import requests
import os
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"

POLL_INTERVAL = 15
score_cache = {}

# Try multiple ESPN league IDs for Dutch football
ESPN_LEAGUES = [
    ("ned.1", "Eredivisie", "🇳🇱"),
    ("ned.2", "Eerste Divisie", "🇳🇱"),
    ("ned.3", "Eredivisie Playoffs", "🇳🇱"),
    ("ned.4", "Netherlands Cup", "🇳🇱"),
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


def get_espn_games(league_id):
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_id}/scoreboard"
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        events = res.json().get("events", [])
        return events
    except Exception as e:
        logging.error(f"ESPN error ({league_id}): {e}")
        return []


def parse_espn_game(event, league_name, flag):
    try:
        comp = event["competitions"][0]
        home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
        away = next(t for t in comp["competitors"] if t["homeAway"] == "away")
        status = event["status"]["type"]["description"]
        status_type = event["status"]["type"]["name"]
        
        # Get score from details if available
        home_score = int(home.get("score", 0) or 0)
        away_score = int(away.get("score", 0) or 0)
        
        # Try to get score from linescores
        if "linescores" in home:
            total = sum(int(ls.get("value", 0) or 0) for ls in home["linescores"])
            if total > 0:
                home_score = total
        if "linescores" in away:
            total = sum(int(ls.get("value", 0) or 0) for ls in away["linescores"])
            if total > 0:
                away_score = total

        return {
            "id": event["id"],
            "home": home["team"]["displayName"],
            "away": away["team"]["displayName"],
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "status_type": status_type,
            "clock": event["status"].get("displayClock", ""),
            "league": league_name,
            "flag": flag,
        }
    except Exception as e:
        logging.warning(f"Parse error: {e}")
        return None


def check_goals(game):
    gid = game["id"]
    hs = game["home_score"]
    as_ = game["away_score"]
    status = game["status"].lower()
    status_type = game["status_type"].lower()

    is_live = any(s in status for s in ["progress", "halftime", "half time"]) or \
              any(s in status_type for s in ["in", "progress", "half"])

    logging.info(f"  {game['home']} vs {game['away']} | {hs}-{as_} | {game['status']} | live={is_live}")

    if not is_live:
        return

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"  --> Tracking at {hs}-{as_}")
        return

    for _ in range(max(0, hs - prev["home"])):
        send_slack_message(
            f"{game['flag']} *GOAL!* — {game['league']}\n"
            f"⚽ *{game['home']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home']} {hs} – {as_} {game['away']}*"
        )

    for _ in range(max(0, as_ - prev["away"])):
        send_slack_message(
            f"{game['flag']} *GOAL!* — {game['league']}\n"
            f"⚽ *{game['away']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home']} {hs} – {as_} {game['away']}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


def main():
    logging.info("Bot started — ESPN multi-league polling every 15 seconds.")
    while True:
        try:
            for league_id, league_name, flag in ESPN_LEAGUES:
                events = get_espn_games(league_id)
                logging.info(f"{league_name}: {len(events)} games")
                for event in events:
                    game = parse_espn_game(event, league_name, flag)
                    if game:
                        check_goals(game)
        except Exception as e:
            logging.error(f"Poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
