import os
import sys
import logging
import hmac
import hashlib
from urllib.parse import parse_qs
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from config import TELEGRAM_TOKEN
from api.routes import users, schedules, summaries, reports

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
logger.info("Static files directory: %s", STATIC_DIR)


def validate_init_data(init_data: str) -> bool:
    """Validate data received from Telegram WebApp."""
    try:
        parsed = parse_qs(init_data)
        if "hash" not in parsed:
            return False

        hash_value = parsed.pop("hash")[0]
        items = []
        for key in sorted(parsed.keys()):
            if parsed[key]:
                items.append(f"{key}={parsed[key][0]}")

        data_check_string = "\n".join(items)
        secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        return hmac.compare_digest(computed_hash, hash_value)
    except Exception as e:
        logger.error("Telegram init_data validation error: %s", e)
        return False


@app.before_request
def verify_telegram_api():
    """Require valid Telegram WebApp init data for /api/v1/* (mini app)."""
    path = request.path or ""
    if not path.startswith("/api/v1/"):
        return None
    if path in ("/api/v1/health",):
        return None

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Telegram "):
        return jsonify({"error": "Unauthorized — missing Telegram init data"}), 401
    init_data = auth_header[len("Telegram ") :]
    if not validate_init_data(init_data):
        return jsonify({"error": "Unauthorized — invalid Telegram init data"}), 403
    return None


app.register_blueprint(users.bp)
app.register_blueprint(schedules.bp)
app.register_blueprint(summaries.bp)
app.register_blueprint(reports.bp)
logger.info("Blueprints registered")


@app.route("/ping")
def ping():
    return "pong", 200


@app.route("/health")
@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "message": "Nightflow API is running"}), 200


@app.route("/api/test")
def test():
    return jsonify({"status": "ok", "message": "API is working", "time": str(datetime.now())}), 200


@app.route("/")
def serve_index():
    try:
        return send_from_directory(STATIC_DIR, "index.html")
    except Exception as e:
        logger.error("Error serving index.html: %s", e)
        return jsonify({"error": "index.html not found", "path": STATIC_DIR}), 404


@app.route("/<path:filename>")
def serve_static(filename):
    try:
        return send_from_directory(STATIC_DIR, filename)
    except Exception as e:
        logger.error("Error serving %s: %s", filename, e)
        return jsonify({"error": f"{filename} not found"}), 404


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    return "OK", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info("Starting on port %s", port)
    app.run(host="0.0.0.0", port=port, debug=False)
