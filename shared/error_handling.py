import logging
import traceback
from functools import wraps
from flask import jsonify, request
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class APIError(Exception):
    """Custom API error class."""
    def __init__(self, message: str, status_code: int = 400, payload: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}

def handle_api_errors(app):
    """Register error handlers for the Flask app."""
    
    @app.errorhandler(APIError)
    def handle_api_error(error):
        """Handle custom API errors."""
        response = {
            "error": error.message,
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        if error.payload:
            response.update(error.payload)
        
        logger.error(f"API Error: {error.message} | Path: {request.path} | Status: {error.status_code}")
        return jsonify(response), error.status_code
    
    @app.errorhandler(400)
    def handle_bad_request(error):
        """Handle 400 Bad Request errors."""
        response = {
            "error": "Bad request",
            "message": "The request was invalid or cannot be served",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"400 Bad Request | Path: {request.path}")
        return jsonify(response), 400
    
    @app.errorhandler(401)
    def handle_unauthorized(error):
        """Handle 401 Unauthorized errors."""
        response = {
            "error": "Unauthorized",
            "message": "Authentication is required for this endpoint",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"401 Unauthorized | Path: {request.path}")
        return jsonify(response), 401
    
    @app.errorhandler(403)
    def handle_forbidden(error):
        """Handle 403 Forbidden errors."""
        response = {
            "error": "Forbidden",
            "message": "You don't have permission to access this resource",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"403 Forbidden | Path: {request.path}")
        return jsonify(response), 403
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 Not Found errors."""
        response = {
            "error": "Not found",
            "message": "The requested resource was not found",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"404 Not Found | Path: {request.path}")
        return jsonify(response), 404
    
    @app.errorhandler(405)
    def handle_method_not_allowed(error):
        """Handle 405 Method Not Allowed errors."""
        response = {
            "error": "Method not allowed",
            "message": f"Method {request.method} is not allowed for this endpoint",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"405 Method Not Allowed | Path: {request.path} | Method: {request.method}")
        return jsonify(response), 405
    
    @app.errorhandler(429)
    def handle_rate_limit(error):
        """Handle 429 Rate Limit errors."""
        response = {
            "error": "Rate limit exceeded",
            "message": "Too many requests, please try again later",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.warning(f"429 Rate Limit | Path: {request.path}")
        return jsonify(response), 429
    
    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle 500 Internal Server Error."""
        response = {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        logger.error(f"500 Internal Error | Path: {request.path} | Error: {str(error)}")
        return jsonify(response), 500
    
    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        """Handle unexpected errors."""
        logger.error(f"Unexpected error: {str(error)} | Path: {request.path} | Traceback: {traceback.format_exc()}")
        response = {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "status": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "path": request.path
        }
        return jsonify(response), 500

def validate_request_data(schema_class):
    """Decorator to validate request data against a Pydantic schema."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                if request.is_json:
                    data = request.get_json() or {}
                else:
                    data = request.form.to_dict()
                
                validated_data = schema_class(**data)
                request.validated_data = validated_data
                return f(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Validation error for {request.path}: {str(e)}")
                raise APIError(f"Validation error: {str(e)}", 400)
        return decorated_function
    return decorator

def success_response(data: Any = None, message: str = "Success", status_code: int = 200) -> tuple:
    """Create a standardized success response."""
    response = {
        "status": "success",
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "data": data
    }
    return jsonify(response), status_code
