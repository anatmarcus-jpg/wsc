import time
import requests
import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C0AVATSHKNX"  # test-espnnl-goal
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

LEAGUES = [
    {"id": "ned.1", "name": "Eredivisie", "flag": "🇳🇱"},
    {"id": "ned.2", "name": "Eerste Divisie", "flag": "🇳🇱"},
]

POLL_INTERVAL = 30  # seconds
KEEPALIVE_INTERVAL = 600  # ping self every 10 minutes

score_cache = {}


# ── Health server ──────────────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


# ── Keep-alive ping ────────────────────────────────────────────
def keep_alive():
    while True:
        time.sleep(KEEPALIVE_INTERVAL)
        if RENDER_URL:
            try:
                requests.get(RENDER_URL, timeout=10)
                logging.info("Keep-alive ping sent.")
            except Exception as e:
                logging.warning(f"Keep-alive failed: {e}")


# ── Slack ──────────────────────────────────────────────────────
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
            logging.info("Slack message sent.")
    except Exception as e:
        logging.error(f"Slack request failed: {e}")


# ── ESPN ───────────────────────────────────────────────────────
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

    is_live = any(s in status for s in ["progress", "halftime", "period"])
    is_finished = any(s in status for s in ["final", "full time", "ft"])

    if not is_live and not is_finished:
        return

    prev = score_cache.get(gid)
    if prev is None:
        score_cache[gid] = {"home": hs, "away": as_}
        logging.info(f"Tracking: {game['home_team']} vs {game['away_team']} [{game['status']}]")
        return

    home_goals = hs - prev["home"]
    away_goals = as_ - prev["away"]

    for _ in range(max(0, home_goals)):
        send_slack_message(
            f"{league['flag']} *GOAL!* — {league['name']}\n"
            f"⚽ *{game['home_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    for _ in range(max(0, away_goals)):
        send_slack_message(
            f"{league['flag']} *GOAL!* — {league['name']}\n"
            f"⚽ *{game['away_team']}* score! ⏱️ {game['clock']}\n"
            f"📊 *{game['home_team']} {hs} – {as_} {game['away_team']}*"
        )

    score_cache[gid] = {"home": hs, "away": as_}


# ── Main loop ──────────────────────────────────────────────────
def poll_loop():
    send_slack_message("⚽ *Dutch Football Goal Alert Bot is live!*\nWatching Eredivisie & Eerste Divisie for goals... 🇳🇱")
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
            logging.error(f"Poll loop error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    # Health server
    threading.Thread(target=start_health_server, daemon=True).start()
    logging.info("Health server started.")

    # Keep-alive pinger
    threading.Thread(target=keep_alive, daemon=True).start()
    logging.info("Keep-alive thread started.")

    # Start polling
    poll_loop()
