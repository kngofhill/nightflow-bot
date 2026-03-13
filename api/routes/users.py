from flask import Blueprint, request, jsonify
import sys
sys.path.append('.')

from shared.db import supabase_client, get_user_by_telegram_id, upsert_user
from shared.time_utils import DEFAULT_TIMEZONE

bp = Blueprint('users', __name__, url_prefix='/api/v1/users')

@bp.route('/me', methods=['GET'])
def get_me():
    telegram_id = request.args.get('telegram_id')
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    user = get_user_by_telegram_id(int(telegram_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Remove sensitive fields if any
    return jsonify(user)

@bp.route('/me', methods=['POST'])
def create_or_update():
    data = request.get_json()
    telegram_id = data.get('telegram_id')
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    # Upsert user
    upsert_user(
        telegram_id=int(telegram_id),
        username=data.get('username', ''),
        first_name=data.get('first_name', ''),
        shift_type=data.get('shift_type')
    )
    # Update timezone if provided
    if data.get('timezone'):
        supabase_client.table('users').update({"timezone": data['timezone']}).eq("telegram_id", telegram_id).execute()
    return jsonify({"success": True})