# api/app.py
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify
from flask_cors import CORS
import hmac
import hashlib
from urllib.parse import parse_qs
from flask import send_from_directory


from config import TELEGRAM_TOKEN
from api.routes import users, schedules

app = Flask(__name__)
CORS(app)  # Allow mini‑app to call API

def validate_init_data(init_data: str) -> bool:
    """Validate data received from Telegram WebApp."""
    try:
        parsed = parse_qs(init_data)
        hash_value = parsed.pop('hash')[0]
        data_check_string = '\n'.join(f"{k}={v[0]}" for k in sorted(parsed))
        secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return computed_hash == hash_value
    except Exception:
        return False

@app.before_request
def verify_telegram_data():
    """Protect API routes (except maybe public ones)."""
    if request.path.startswith('/api/'):
        auth = request.headers.get('Authorization')
        if not auth or not auth.startswith('Telegram '):
            return jsonify({"error": "Unauthorized"}), 401
        init_data = auth[9:]
        if not validate_init_data(init_data):
            return jsonify({"error": "Invalid data"}), 403

# Register blueprints
app.register_blueprint(users.bp)
app.register_blueprint(schedules.bp)

@app.route('/health')
def health():
    return "OK", 200

@app.route('/')
def serve_frontend():
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)