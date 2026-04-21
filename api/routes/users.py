from flask import Blueprint, request, jsonify
import sys

sys.path.append(".")

from shared.db import supabase_client, upsert_user

bp = Blueprint("users", __name__, url_prefix="/api/v1/users")


@bp.route("/me", methods=["GET"])
def get_me():
    telegram_id = request.args.get("telegram_id")
    if not telegram_id:
        return jsonify({"error": "telegram_id required"}), 400
    user = supabase_client.table("users").select("*").eq("telegram_id", int(telegram_id)).execute()
    if not user.data:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user.data[0])


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
