"""Require active Pro or trial for gated mini-app routes."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, Union

from flask import jsonify

from shared.db import supabase_client
from shared.subscription import has_pro_entitlement

ResponseTuple = Tuple[Any, int]


def fetch_user_row_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    try:
        r = supabase_client.table("users").select("*").eq("id", user_id).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return None


def require_pro_access(user_id: str) -> Optional[ResponseTuple]:
    """Return (jsonify(...), status) if access denied, else None."""
    row = fetch_user_row_by_id(user_id)
    if not row or not has_pro_entitlement(row):
        return (
            jsonify(
                {
                    "error": "Nightflow Pro or active trial required",
                    "code": "pro_required",
                }
            ),
            403,
        )
    return None


def user_has_active_constant_schedule(user_id: str) -> bool:
    try:
        r = (
            supabase_client.table("constant_schedules")
            .select("id")
            .eq("user_id", user_id)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        return bool(r.data)
    except Exception:
        return False
