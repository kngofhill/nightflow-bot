import os
import sys
import logging
import hmac
import hashlib
from urllib.parse import parse_qs
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from config import TELEGRAM_TOKEN
from api.routes import users, schedules
import sys
import traceback
import asyncio

# Add this right after your imports
print("🚀 Starting Flask app...")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in current dir: {os.listdir('.')}")
print(f"Files in api directory: {os.listdir('api') if os.path.exists('api') else 'api not found'}")
print(f"Files in api/static directory: {os.listdir('api/static') if os.path.exists('api/static') else 'static not found'}")

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
CORS(app)  # Allow mini‑app to call API

def validate_init_data(init_data: str) -> bool:
    """Validate data received from Telegram WebApp."""
    try:
        logger.info(f"Validating init_data (length: {len(init_data)})")
        
        # Parse the query string
        parsed = parse_qs(init_data)
        logger.info(f"Parsed keys: {list(parsed.keys())}")
        
        # Check if hash exists
        if 'hash' not in parsed:
            logger.error("No hash in init_data")
            return False
            
        hash_value = parsed.pop('hash')[0]
        
        # Create data check string
        items = []
        for key in sorted(parsed.keys()):
            if parsed[key]:  # Make sure there's a value
                items.append(f"{key}={parsed[key][0]}")
        
        data_check_string = "\n".join(items)
        logger.info(f"Data check string: {data_check_string[:100]}...")
        
        # Create secret key
        secret_key = hmac.new(
            b"WebAppData", 
            TELEGRAM_TOKEN.encode(), 
            hashlib.sha256
        ).digest()
        
        # Compute hash
        computed_hash = hmac.new(
            secret_key, 
            data_check_string.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        logger.info(f"Computed hash: {computed_hash}")
        logger.info(f"Received hash: {hash_value}")
        
        # Compare in constant time to avoid timing attacks
        result = hmac.compare_digest(computed_hash, hash_value)
        logger.info(f"Validation result: {result}")
        
        return result
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}", exc_info=True)
        return False

# @app.before_request
# def verify_telegram_data():
#     """Protect API routes with proper error handling."""
#     # Skip verification for non-API routes
#     if not request.path.startswith('/api/'):
#         return
    
#     # Special case for health check
#     if request.path == '/api/health':
#         return
    
#     auth = request.headers.get('Authorization')
#     logger.info(f"Auth header: {auth[:50] if auth else 'None'}...")
    
#     if not auth or not auth.startswith('Telegram '):
#         logger.warning(f"Missing or invalid auth header for {request.path}")
#         return jsonify({
#             "error": "Unauthorized",
#             "message": "Missing or invalid Authorization header"
#         }), 401
    
#     init_data = auth[9:]  # Remove 'Telegram ' prefix
    
#     if not validate_init_data(init_data):
#         logger.warning(f"Invalid init_data for {request.path}")
#         return jsonify({
#             "error": "Invalid data",
#             "message": "Telegram data validation failed"
#         }), 403
    
#     logger.info(f"Authentication successful for {request.path}")

# Register blueprints
try:
    # Register blueprints
    app.register_blueprint(users.bp)
    app.register_blueprint(schedules.bp)
    print("✅ Blueprints registered successfully")
except Exception as e:
    print(f"❌ Error registering blueprints: {e}")
    traceback.print_exc()

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "message": "Nightflow API is running"
    }), 200

@app.route('/api/health')
def api_health():
    """API health check endpoint."""
    return jsonify({
        "status": "ok",
        "message": "Nightflow API is running"
    }), 200

@app.route('/')
def serve_frontend():
    """Serve the mini-app frontend."""
    try:
        # Try multiple possible paths
        possible_paths = ['api/static/index.html', 'static/index.html', 'index.html']
        
        for path in possible_paths:
            try:
                return send_from_directory(os.path.dirname(path), os.path.basename(path))
            except:
                continue
        
        # If none work, list available files for debugging
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        files = os.listdir(static_dir) if os.path.exists(static_dir) else []
        return jsonify({
            "error": "Frontend not found",
            "message": f"Looking in: {static_dir}, found: {files}"
        }), 404
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/test')
def test():
    return jsonify({"status": "ok", "message": "API is working"}), 200
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Handle incoming Telegram updates via webhook."""
    try:
        update = Update.de_json(request.get_json(), application.bot)
        asyncio.run(application.process_update(update))
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'Error', 500
    
    return 'ok', 200
@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (JS, CSS, etc.)"""
    try:
        # Try multiple paths
        possible_paths = [
            os.path.join('api/static', path),
            os.path.join('static', path),
            path
        ]
        
        for static_path in possible_paths:
            full_path = os.path.join(os.path.dirname(__file__), '..', static_path)
            if os.path.exists(full_path):
                return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
        
        return jsonify({"error": f"File not found: {path}"}), 404
    except Exception as e:
        logger.error(f"Error serving static file {path}: {e}")
        return jsonify({"error": str(e)}), 404

# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        "error": "Not found",
        "message": "The requested URL was not found on the server"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "Something went wrong on the server"
    }), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting Nightflow API on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)