from flask import Blueprint, request
import sys
sys.path.append('.')

from shared.db import supabase_client, get_user_by_telegram_id, upsert_user
from shared.time_utils import DEFAULT_TIMEZONE
from shared.auth import get_user_id_from_request
from shared.error_handling import success_response, APIError, validate_request_data
from shared.validation import UserUpdate

bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

@bp.route('/me', methods=['GET'])
def get_me():
    """Get current user profile."""
    user_id, err = get_user_id_from_request()
    if err:
        raise APIError(err, 401)
    user = supabase_client.table('users').select('*').eq('telegram_id', telegram_id).execute()    
    if not user.data:
        raise APIError("User not found", 404)
    
    return success_response(user.data[0])

@bp.route('/me', methods=['PUT'])
@validate_request_data(UserUpdate)
def update_me():
    """Update current user profile."""
    user_id, err = get_user_id_from_request()
    if err:
        raise APIError(err, 401)
    
    validated_data = request.validated_data
    update_data = validated_data.dict(exclude_unset=True)
    
    if not update_data:
        raise APIError("No valid fields to update", 400)
    
    result = supabase_client.table('users').update(update_data).eq('id', user_id).execute()
    if not result.data:
        raise APIError("Failed to update user", 500)
    
    return success_response(result.data[0], "Profile updated successfully")