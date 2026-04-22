"""Telegram Stars subscription helpers for the mini-app."""

import sys

sys.path.append(".")

from flask import Blueprint, jsonify

from config import TELEGRAM_TOKEN
from api.request_util import get_user_from_request
from shared.db import supabase_client, mark_star_subscription_cancelled
from shared.subscription import (
    INVOICE_PAYLOAD_NIGHTFLOW_PRO,
    PRO_PRICE_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
    MSG_CANCEL_ONETIME_EXPLANATION,
    MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK,
    explain_cannot_cancel_star_subscription,
    subscription_meta_for_user,
    should_skip_telegram_star_cancel,
)
from shared.telegram_invoice import create_invoice_link
from shared.telegram_star_api import (
    edit_user_star_subscription as call_edit_user_star_subscription,
    format_telegram_cancel_subscription_error,
    is_telegram_charge_invalid_error,
)

bp = Blueprint("subscription", __name__, url_prefix="/api/v1")


@bp.route("/subscription/invoice-link", methods=["POST"])
def create_stars_invoice_link():
    """Return invoice URL for Nightflow Pro (XTR / 30 days). # TESTING ONLY: 1 Star via PRO_PRICE_STARS."""
    _, err = get_user_from_request()
    if err:
        return err

    if not TELEGRAM_TOKEN:
        return jsonify({"error": "Billing is not configured"}), 503

    prices = [{"label": "1 month", "amount": PRO_PRICE_STARS}]
    url = create_invoice_link(
        TELEGRAM_TOKEN,
        title="Nightflow Pro",
        description=(
            "Full schedule, weekly report, suggestions, settings editing, "
            "check-ins, and all reminders. Renews every 30 days."
        ),
        payload=INVOICE_PAYLOAD_NIGHTFLOW_PRO,
        currency="XTR",
        prices=prices,
        provider_token=None,
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
    )
    if not url:
        return jsonify({"error": "Could not create invoice link"}), 502
    return jsonify({"url": url})


@bp.route("/cancel-subscription", methods=["POST"])
def cancel_star_subscription():
    """
    Stops future Telegram Stars renewals. Pro stays until pro_expires_at.
    """
    from api.routes.users import _public_user_row

    user_id, err = get_user_from_request()
    if err:
        return err

    if not TELEGRAM_TOKEN:
        return jsonify({"error": "Billing is not configured"}), 503

    urow = supabase_client.table("users").select("*").eq("id", user_id).execute()
    if not urow.data:
        return jsonify({"error": "User not found"}), 404
    row = urow.data[0]
    telegram_id = int(row["telegram_id"])
    meta = subscription_meta_for_user(row)
    if not meta.get("can_cancel_star_subscription"):
        return jsonify(
            {
                "error": "Cannot cancel subscription from the app right now",
                "code": "cancel_forbidden",
                "explanation": explain_cannot_cancel_star_subscription(row, meta),
            }
        ), 403

    pro_exp = meta.get("pro_expires_at", "") or ""

    if should_skip_telegram_star_cancel(row):
        m = mark_star_subscription_cancelled(telegram_id)
        msg = MSG_CANCEL_ONETIME_EXPLANATION.format(pro_exp=pro_exp or "your current period end")
        if m is None:
            return jsonify(
                {
                    "ok": True,
                    "warning": "Database missing subscription flags; run migration 20260422120000",
                    "message": msg,
                    "pro_expires_at": pro_exp,
                    "telegram": "skipped_one_time",
                }
            )
        refreshed = supabase_client.table("users").select("*").eq("id", user_id).execute()
        u = refreshed.data[0] if refreshed.data else row
        return jsonify(
            {
                "ok": True,
                "message": msg,
                "user": _public_user_row(u),
                "telegram": "skipped_one_time",
            }
        )

    ch = row.get("telegram_payment_charge_id")
    if not ch:
        return jsonify(
            {
                "error": "No payment id on file",
                "explanation": explain_cannot_cancel_star_subscription(row, meta),
            }
        ), 400

    ok, raw = call_edit_user_star_subscription(
        TELEGRAM_TOKEN, user_id=telegram_id, telegram_payment_charge_id=str(ch), is_canceled=True
    )
    if not ok:
        desc = (raw or {}).get("description", str(raw)) if isinstance(raw, dict) else str(raw)
        if is_telegram_charge_invalid_error(str(desc)):
            m = mark_star_subscription_cancelled(telegram_id)
            msg = MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK.format(
                pro_exp=pro_exp or "your current period end"
            )
            if m is None:
                return jsonify(
                    {
                        "ok": True,
                        "warning": "Database missing subscription flags; run migration 20260422120000",
                        "message": msg,
                        "pro_expires_at": pro_exp,
                        "code": "telegram_charge_invalid_app_cancelled",
                        "details": desc,
                    }
                )
            refreshed = supabase_client.table("users").select("*").eq("id", user_id).execute()
            u = refreshed.data[0] if refreshed.data else row
            return jsonify(
                {
                    "ok": True,
                    "message": msg,
                    "user": _public_user_row(u),
                    "code": "telegram_charge_invalid_app_cancelled",
                }
            )
        return jsonify(
            {
                "error": "Telegram did not accept cancellation",
                "code": "telegram_rejected",
                "details": desc,
                "explanation": format_telegram_cancel_subscription_error(str(desc)),
            }
        ), 502

    m = mark_star_subscription_cancelled(telegram_id)
    msg = (
        f"Your subscription will not auto-renew. You keep Pro access until {pro_exp}."
    )
    if m is None:
        return jsonify(
            {
                "ok": True,
                "warning": "Database missing subscription flags; run migration 20260422120000",
                "message": msg,
                "pro_expires_at": pro_exp,
            }
        )

    refreshed = supabase_client.table("users").select("*").eq("id", user_id).execute()
    u = refreshed.data[0] if refreshed.data else row
    return jsonify({"ok": True, "message": msg, "user": _public_user_row(u)})
