from flask import Blueprint, request
import sys
sys.path.append('.')

from shared.db import supabase_client, get_user_by_telegram_id, upsert_user
from shared.time_utils import DEFAULT_TIMEZONE
from shared.error_handling import success_response, APIError

bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

@bp.route('/me', methods=['GET'])
def get_me():
    """Get current user profile."""
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        raise APIError("telegram_id required", 400)
    
    user = supabase_client.table('users').select('*').eq('telegram_id', int(telegram_id)).execute()
    if not user.data:
        raise APIError("User not found", 404)
    
    return success_response(user.data[0])

@bp.route('/me', methods=['POST'])
def create_or_update():
    """Create or update user."""
    data = request.get_json()
    telegram_id = data.get('telegram_id')
    if not telegram_id:
        raise APIError("telegram_id required", 400)
    
    upsert_user(
        telegram_id=int(telegram_id),
        username=data.get('username', ''),
        first_name=data.get('first_name', ''),
        shift_type=data.get('shift_type')
    )
    
    if data.get('timezone'):
        supabase_client.table('users').update({"timezone": data['timezone']}).eq("telegram_id", telegram_id).execute()
    
    return success_response(None, "User saved successfully")