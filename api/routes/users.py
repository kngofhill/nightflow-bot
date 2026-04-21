from flask import Blueprint, request, jsonify
import json
import sys

sys.path.append(".")

from shared.db import supabase_client, upsert_user
from api.request_util import get_user_from_request

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


def _normalize_notification_prefs(raw):
    if raw is None:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


@bp.route("/me", methods=["GET"])
def get_me():
    telegram_id = request.args.get("telegram_id")
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    user = supabase_client.table("users").select("*").eq("telegram_id", int(telegram_id)).execute()
    if not user.data:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.data[0])


@bp.route("/me", methods=["PATCH"])
def patch_me():
    user_id, err = get_user_from_request()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    user = supabase_client.table("users").select("*").eq("id", user_id).execute()
    if not user.data:
        return jsonify({"error": "User not found"}), 404

    row = user.data[0]
    updates = {}

    if "timezone" in data:
        tz = data.get("timezone")
        if isinstance(tz, str) and tz.strip():
            updates["timezone"] = tz.strip()

    if "notification_enabled" in data:
        updates["notification_enabled"] = bool(data["notification_enabled"])

    prefs = _normalize_notification_prefs(row.get("notification_prefs"))
    prefs_modified = False

    inc = data.get("notification_prefs")
    if isinstance(inc, dict):
        prefs.update(inc)
        prefs_modified = True

    if "transition_reminders" in data or "transitionReminders" in data:
        tr = data["transition_reminders"] if "transition_reminders" in data else data.get("transitionReminders")
        prefs["transitionReminders"] = bool(tr)
        prefs_modified = True
    if "transition_lead_days" in data or "transitionLeadDays" in data:
        tld = data["transition_lead_days"] if "transition_lead_days" in data else data.get("transitionLeadDays")
        prefs["transitionLeadDays"] = str(tld)
        prefs_modified = True

    if prefs_modified:
        updates["notification_prefs"] = prefs

    if not updates:
        return jsonify({"error": "No updatable fields provided"}), 400

    supabase_client.table("users").update(updates).eq("id", user_id).execute()
    refreshed = supabase_client.table("users").select("*").eq("id", user_id).execute()
    return jsonify(refreshed.data[0])


@bp.route("/me", methods=["POST"])
def create_or_update():
    data = request.get_json(silent=True) or {}
    telegram_id = data.get("telegram_id")
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400

    upsert_user(
        telegram_id=int(telegram_id),
        username=data.get("username", ""),
        first_name=data.get("first_name", ""),
        shift_type=data.get("shift_type"),
    )

    if data.get("timezone"):
        supabase_client.table("users").update({"timezone": data["timezone"]}).eq(
            "telegram_id", int(telegram_id)
        ).execute()

    return jsonify({"ok": True, "message": "User saved successfully"})
