"""Telegram Stars subscription helpers for the mini-app."""

import sys

sys.path.append(".")

from flask import Blueprint, jsonify

from config import TELEGRAM_TOKEN
from api.request_util import get_user_from_request
from shared.subscription import (
    INVOICE_PAYLOAD_NIGHTFLOW_PRO,
    PRO_PRICE_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
)
from shared.telegram_invoice import create_invoice_link

bp = Blueprint("subscription", __name__, url_prefix="/api/v1")


@bp.route("/subscription/invoice-link", methods=["POST"])
def create_stars_invoice_link():
    """Return a Telegram invoice URL for Nightflow Pro (50 Stars / 30 days, recurring)."""
    _, err = get_user_from_request()
    if err:
        return err

    if not TELEGRAM_TOKEN:
        return jsonify({"error": "Billing is not configured"}), 503

    prices = [{"label": "Nightflow Pro (30 days)", "amount": PRO_PRICE_STARS}]
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
