from flask import Blueprint, request
from datetime import date, datetime
import sys
import json

sys.path.append('.')

from shared.db import supabase_client, get_user_id
from shared.time_utils import get_user_now_from_timezone_name, DEFAULT_TIMEZONE
from shared.auth import get_user_id_from_request
from shared.error_handling import success_response, APIError, validate_request_data
from shared.validation import WeeklySummaryRequest

bp = Blueprint('summaries', __name__, url_prefix='/api/v1')


def _parse_json_or_obj(v, default):
    if v is None:
        return default
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return default
    if isinstance(v, dict):
        return v
    return default


@bp.route('/summaries', methods=['POST'])
def post_shift_summary():
    """Submit shift summary data."""
    user_id, err = get_user_id_from_request()
    if err:
        raise APIError(err, 401)
    
    payload = request.get_json(silent=True) or {}

    # Client sends date as local calendar date (YYYY-MM-DD)
    date_str = payload.get('date') or payload.get('local_date')
    if not date_str:
        user = supabase_client.table('users').select('timezone').eq('id', user_id).execute()
        tz = user.data[0].get('timezone') if user.data else DEFAULT_TIMEZONE
        date_str = str(get_user_now_from_timezone_name(tz).date())

    try:
        local_date = date.fromisoformat(str(date_str))
        local_date_str = str(local_date)
    except Exception:
        raise APIError("Invalid date; expected YYYY-MM-DD", 400)

    energy = payload.get('energy')
    sleep_quality = payload.get('sleep_quality')
    responses = _parse_json_or_obj(payload.get('responses'), default={})

    # Fetch existing row to update/insert (avoid upsert ambiguity on composite keys)
    existing = (
        supabase_client.table('shift_summaries')
        .select('id')
        .eq('user_id', user_id)
        .eq('local_date', local_date_str)
        .execute()
    )

    row_payload = {
        'user_id': user_id,
        'local_date': local_date_str,
        'energy': energy,
        'sleep_quality': sleep_quality,
        'responses': responses,
    }

    if existing.data:
        supabase_client.table('shift_summaries').update(row_payload).eq('id', existing.data[0]['id']).execute()
    else:
        supabase_client.table('shift_summaries').insert(row_payload).execute()

    return success_response(None, "Summary saved successfully")

