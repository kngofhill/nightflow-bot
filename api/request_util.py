"""Minimal helpers for Flask routes (no extra frameworks)."""

from flask import request, jsonify

from shared.db import get_user_id


def get_user_from_request():
    """
    Resolve Supabase users.id from telegram_id (query string or JSON body).
    Returns (user_id, None) or (None, (response, status_code)).
    """
    telegram_id = request.args.get("telegram_id")
    if not telegram_id and request.is_json:
        body = request.get_json(silent=True) or {}
        telegram_id = body.get("telegram_id")
    if not telegram_id:
        return None, (jsonify({"error": "telegram_id required"}), 400)
    try:
        tid = int(telegram_id)
    except (TypeError, ValueError):
        return None, (jsonify({"error": "Invalid telegram_id"}), 400)
    uid = get_user_id(tid)
    if not uid:
        return None, (jsonify({"error": "User not found"}), 404)
    return uid, None
