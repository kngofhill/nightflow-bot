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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Get the absolute path to the api/static directory
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
logger.info(f"📁 Static files directory: {STATIC_DIR}")
logger.info(f"📄 Files in static: {os.listdir(STATIC_DIR) if os.path.exists(STATIC_DIR) else 'NOT FOUND'}")

def validate_init_data(init_data: str) -> bool:
    """Validate data received from Telegram WebApp."""
    try:
        parsed = parse_qs(init_data)
        if 'hash' not in parsed:
            return False
            
        hash_value = parsed.pop('hash')[0]
        items = []
        for key in sorted(parsed.keys()):
            if parsed[key]:
                items.append(f"{key}={parsed[key][0]}")
        
        data_check_string = "\n".join(items)
        secret_key = hmac.new(b"WebAppData", TELEGRAM_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(computed_hash, hash_value)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False
@app.route('/ping')
def ping():
    return "pong", 200
# @app.before_request
# def verify_telegram_data():
#     """Protect API routes."""
#     if not request.path.startswith('/api/'):
#         return
    
#     if request.path == '/api/health' or request.path == '/api/test':
#         return
    
#     auth = request.headers.get('Authorization')
#     if not auth or not auth.startswith('Telegram '):
#         return jsonify({"error": "Unauthorized"}), 401
    
#     if not validate_init_data(auth[9:]):
#         return jsonify({"error": "Invalid data"}), 403

# Register blueprints
app.register_blueprint(users.bp)
app.register_blueprint(schedules.bp)
app.register_blueprint(summaries.bp)
app.register_blueprint(reports.bp)
logger.info("✅ Blueprints registered")

# Simple routes first
@app.route('/health')
@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "message": "Nightflow API is running"}), 200

@app.route('/api/test')
def test():
    return jsonify({"status": "ok", "message": "API is working", "time": str(datetime.now())}), 200

# Serve static files - SIMPLE AND DIRECT
@app.route('/')
def serve_index():
    """Serve the main HTML file."""
    try:
        return send_from_directory(STATIC_DIR, 'index.html')
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return jsonify({"error": "index.html not found", "path": STATIC_DIR}), 404

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve all static files."""
    try:
        return send_from_directory(STATIC_DIR, filename)
    except Exception as e:
        logger.error(f"Error serving {filename}: {e}")
        return jsonify({"error": f"{filename} not found"}), 404

# Webhook for Telegram bot
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Handle Telegram updates."""
    # You'll need to import your bot application here
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🚀 Starting on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)