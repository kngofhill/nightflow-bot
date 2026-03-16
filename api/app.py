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
app.register_blueprint(users.bp)
app.register_blueprint(schedules.bp)

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
        return send_from_directory('static', 'index.html')
    except Exception as e:
        logger.error(f"Error serving frontend: {e}")
        return jsonify({
            "error": "Frontend not found",
            "message": "Static files may be missing"
        }), 404

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files."""
    try:
        return send_from_directory('static', path)
    except Exception as e:
        logger.error(f"Error serving static file {path}: {e}")
        return jsonify({
            "error": "File not found",
            "message": f"Could not find {path}"
        }), 404

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