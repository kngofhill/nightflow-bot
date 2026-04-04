import os
import logging
import hmac
import hashlib
from urllib.parse import parse_qs
from functools import wraps
from flask import request, jsonify
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

def validate_init_data(init_data: str) -> bool:
    """Validate data received from Telegram WebApp."""
    try:
        if not init_data:
            return False
            
        parsed = parse_qs(init_data)
        if 'hash' not in parsed:
            return False
            
        hash_value = parsed.pop('hash')[0]
        items = []
        for key in sorted(parsed.keys()):
            if parsed[key]:
                items.append(f"{key}={parsed[key][0]}")
        
        data_check_string = "\n".join(items)
        
        # Get Telegram token from environment
        telegram_token = os.getenv('TELEGRAM_TOKEN')
        if not telegram_token:
            logger.error("TELEGRAM_TOKEN not found in environment")
            return False
            
        secret_key = hmac.new(b"WebAppData", telegram_token.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        return hmac.compare_digest(computed_hash, hash_value)
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False

def get_user_from_init_data(init_data: str) -> Optional[dict]:
    """Extract user data from Telegram WebApp init data."""
    try:
        parsed = parse_qs(init_data)
        user_data = parsed.get('user', [None])[0]
        if user_data:
            import json
            return json.loads(user_data)
        return None
    except Exception as e:
        logger.error(f"Error parsing user data: {e}")
        return None

def telegram_auth_required(f):
    """Decorator to require Telegram WebApp authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip auth for health checks and static files
        if request.path in ['/health', '/api/health', '/api/test', '/ping']:
            return f(*args, **kwargs)
            
        # Skip auth for static file serving
        if request.path.startswith('/') and not request.path.startswith('/api/'):
            return f(*args, **kwargs)
        
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Telegram '):
            logger.warning(f"Missing or invalid auth header for {request.path}")
            return jsonify({"error": "Unauthorized - missing Telegram auth"}), 401
        
        init_data = auth_header[9:]  # Remove 'Telegram ' prefix
        
        if not validate_init_data(init_data):
            logger.warning(f"Invalid Telegram data for {request.path}")
            return jsonify({"error": "Unauthorized - invalid Telegram data"}), 403
        
        # Extract user info and add to request context
        user_info = get_user_from_init_data(init_data)
        if user_info:
            request.current_user = user_info
        else:
            logger.warning(f"Could not extract user info for {request.path}")
            return jsonify({"error": "Unauthorized - invalid user data"}), 403
        
        return f(*args, **kwargs)
    return decorated_function

def get_user_id_from_request() -> Tuple[Optional[str], Optional[str]]:
    """Get user ID from authenticated request."""
    try:
        if hasattr(request, 'current_user') and request.current_user:
            return str(request.current_user.get('id')), None
        return None, "User not authenticated"
    except Exception as e:
        logger.error(f"Error getting user ID: {e}")
        return None, str(e)
