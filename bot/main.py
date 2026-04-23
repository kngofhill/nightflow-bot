import os
import logging
import datetime as dt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json
import asyncio
import traceback 

from telegram import (
    Update,
    MenuButtonWebApp,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
import telegram.error as tg_error
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import MessageHandler, filters, PreCheckoutQueryHandler

from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import (
    supabase_client,
    get_user_by_telegram_id,
    upsert_user,
    update_last_active,
    insert_notification,
    apply_pro_subscription_from_payment,
    revoke_pro_subscription,
    mark_star_subscription_cancelled,
    record_pro_refund_for_rate_limit,
)
from shared.subscription import (
    INVOICE_PAYLOAD_NIGHTFLOW_PRO,
    MAX_PRO_REFUNDS_PER_UTC_MONTH,
    PRO_PRICE_STARS,
    SUBSCRIPTION_PERIOD_SECONDS,
    has_pro_entitlement,
    paid_pro_period_active,
    pro_refund_month_limit_reached,
    _parse_dt,
    within_refund_window,
    subscription_debug_summary,
    subscription_meta_for_user,
    explain_cannot_cancel_star_subscription,
    MSG_CANCEL_ONETIME_EXPLANATION,
    MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK,
    should_skip_telegram_star_cancel,
)
from shared.telegram_invoice import create_invoice_link
from shared.telegram_star_api import (
    format_telegram_cancel_subscription_error,
    is_telegram_charge_invalid_error,
)
from shared.time_utils import (
    get_user_now_from_timezone_name,
    DEFAULT_TIMEZONE
)
from shared.telegram_notify_schedule import (
    format_hhmm,
    parse_notification_prefs,
    fetch_today_sent_dedup_keys,
    fetch_effective_schedule_today,
    sleep_window_reminder_hhmm,
)

load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Your existing command handlers (start, pause, resume) remain the same
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message - menu button already opens mini-app."""
    user = update.effective_user
    logger.info(f"Start command from user {user.id}")
    
    # Ensure user exists in DB
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        upsert_user(user.id, user.username, user.first_name, None)
    update_last_active(user.id, datetime.now().isoformat())

    await update.message.reply_text(
        f"👋 Welcome to Nightflow, {user.first_name}!\n\n"
        f"Use the menu button below ⬇️ to open the app.\n\n"
        # TESTING ONLY — revert welcome copy before production (was 14-day trial, 50 Stars).
        f"🎁 New accounts get a short Pro trial (TESTING: ~5 minutes, full features).\n"
        f"After that, stay on Free (today’s basics) or subscribe with {PRO_PRICE_STARS} Stars / 30 days via /subscribe.\n\n"
        f"Commands:\n"
        f"/subscribe — Nightflow Pro (Telegram Stars)\n"
        f"/cancel — Stop Pro auto-renewal (same as app; keeps Pro until expiry)\n"
        f"/status — Trial / Pro debug (TESTING)\n"
        f"/refund — Refund Stars (within 3 days; max {MAX_PRO_REFUNDS_PER_UTC_MONTH}/month; revokes Pro)\n"
        f"/pause — Pause notifications (Pro)\n"
        f"/resume — Resume notifications"
    )

async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pause notifications."""
    user_id = update.effective_user.id
    supabase_client.table("users").update({"notification_enabled": False}).eq("telegram_id", user_id).execute()
    await update.message.reply_text("Notifications paused. Use /resume to enable again.")

async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resume notifications."""
    user_id = update.effective_user.id
    supabase_client.table("users").update({"notification_enabled": True}).eq("telegram_id", user_id).execute()
    await update.message.reply_text("Notifications resumed.")


class RefundedPaymentFilter(filters.BaseFilter):
    def check_update(self, update: Update):
        m = update.message
        return bool(m and getattr(m, "refunded_payment", None))


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recurring Nightflow Pro via ``createInvoiceLink`` + open URL (Bot API: subscription invoices are not for ``sendInvoice``)."""
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        await update.message.reply_text("Billing is not configured (TELEGRAM_TOKEN).")
        return
    tid = update.effective_user.id
    row = get_user_by_telegram_id(tid) or {}
    if paid_pro_period_active(row):
        pe = _parse_dt(row.get("pro_expires_at"))
        until = pe.strftime("%B %d, %Y %H:%M UTC") if pe else "your current period end"
        await update.message.reply_text(
            f"You already have an active Pro subscription until {until}. No need to subscribe again."
        )
        return
    # TESTING ONLY: price is PRO_PRICE_STARS (1 Star); production was 50.
    desc = (
        "Full schedule, weekly report, suggestions, settings editing, "
        f"check-ins, and all reminders. {PRO_PRICE_STARS} Stars every 30 days (renews until you cancel)."
    )
    prices = [{"label": "1 month", "amount": int(PRO_PRICE_STARS)}]
    link = create_invoice_link(
        token,
        title="Nightflow Pro",
        description=desc,
        payload=INVOICE_PAYLOAD_NIGHTFLOW_PRO,
        currency="XTR",
        prices=prices,
        provider_token=None,
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS,
        onetime_if_recurring_fails=False,
    )
    if not link:
        await update.message.reply_text(
            "Could not create a recurring Stars payment link. "
            "In BotFather, enable Stars + payments for this bot, then try again — "
            "or subscribe from the mini-app (Settings)."
        )
        return
    await update.message.reply_text(
        "Nightflow Pro renews every 30 days in Telegram (Stars). "
        "Tap the button, complete payment, and your Pro time will be applied here.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Pay — Nightflow Pro (30-day subscription)", url=link)]]
        ),
    )


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.pre_checkout_query
    if not q:
        return
    if q.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        await q.answer(ok=False, error_message="Unknown product")
        return
    await q.answer(ok=True)


async def on_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sp = update.message.successful_payment if update.message else None
    if not sp or sp.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        return
    tid = update.effective_user.id
    exp = sp.subscription_expiration_date
    ch = getattr(sp, "telegram_payment_charge_id", None)
    # Do not default to False — that always writes `last_payment_is_recurring` and fails if the column
    # is not deployed. Only set when Telegram sends the field (true/false for XTR / Stars).
    raw_recur = getattr(sp, "is_recurring", None)
    is_recurring = None if raw_recur is None else bool(raw_recur)
    had_active_paid = paid_pro_period_active(get_user_by_telegram_id(tid))
    try:
        apply_pro_subscription_from_payment(tid, exp, ch, is_recurring=is_recurring)
    except Exception as e:
        logger.exception("on_successful_payment DB update failed: %s", e)
        await update.message.reply_text(
            "Payment received, but saving your subscription in the database failed. "
            "Ask an admin to run the latest Supabase migration, then use /status or pay again."
        )
        return
    if had_active_paid:
        await update.message.reply_text(
            "Nightflow Pro was extended by 30 days. Your next renewal is handled in Telegram (Stars subscription)."
        )
    else:
        await update.message.reply_text(
            "Nightflow Pro is now active. Open the mini-app to use every feature."
        )


async def cmd_refund(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refunds Stars via ``refundStarPayment``, then clears Pro in DB. Same 3-day window as Telegram policy."""
    tid = update.effective_user.id
    try:
        row = get_user_by_telegram_id(tid)
        if not paid_pro_period_active(row):
            await update.message.reply_text(
                "No active paid Nightflow Pro subscription to refund. "
                "(Trial-only users are not charged; there is nothing to refund.)"
            )
            return
        if not within_refund_window(row):
            await update.message.reply_text(
                "Refunds are only allowed within the first 3 days after purchase."
            )
            return
        if pro_refund_month_limit_reached(row):
            await update.message.reply_text(
                f"You have already used the maximum of {MAX_PRO_REFUNDS_PER_UTC_MONTH} Pro (Stars) refunds "
                "in this calendar month (UTC). This limit prevents purchase–refund cycling. You can use /refund again "
                "next month, or contact support for genuine billing issues."
            )
            return

        charge_id = (row or {}).get("telegram_payment_charge_id")
        if not charge_id:
            # No charge id (e.g. paid before we stored it, or DB column missing and save skipped)
            logger.warning("refund: no telegram_payment_charge_id for user %s", tid)
            try:
                revoke_pro_subscription(tid)
            except Exception as e:
                logger.exception("revoke_pro_subscription: %s", e)
                await update.message.reply_text(
                    "Could not update the database. Run the Supabase migration that adds "
                    "users.telegram_payment_charge_id, then try /refund again."
                )
                return
            await update.message.reply_text(
                "Pro access was removed. There was no payment id on file, so the bot could not "
                "call Telegram to return Stars. After the DB migration, new payments will store the id for refunds."
            )
            return

        try:
            await context.bot.refund_star_payment(
                user_id=tid, telegram_payment_charge_id=str(charge_id)
            )
        except tg_error.TelegramError as e:
            err_s = str(e)
            low = err_s.lower()
            logger.warning("refund_star_payment failed: %s", e)
            if "already" in low or "repeated" in low or "was refunded" in low:
                try:
                    revoke_pro_subscription(tid)
                except Exception as db_e:
                    logger.exception("revoke after Telegram already-refunded: %s", db_e)
                    await update.message.reply_text(
                        f"Telegram says this was already refunded, but the database update failed: {str(db_e)[:200]}"
                    )
                    return
                await update.message.reply_text(
                    "This payment was already refunded in Telegram. Pro access is cleared to match your account."
                )
                return
            await update.message.reply_text(
                f"Could not refund Stars. Pro access is unchanged. Try again or use Telegram’s payment history. Details:\n{err_s[:500]}"
            )
            return

        try:
            revoke_pro_subscription(tid)
        except Exception as e:
            logger.exception("revoke after successful refund_star_payment: %s", e)
            await update.message.reply_text(
                "Stars were refunded in Telegram, but clearing Pro in the database failed. "
                "Run the Supabase migration, then an admin can fix the row or you can try /refund again."
            )
            return
        record_pro_refund_for_rate_limit(tid, str(charge_id))
        await update.message.reply_text("Stars refunded and Pro access removed.")
    except Exception as e:
        logger.exception("cmd_refund: %s", e)
        await update.message.reply_text(
            "Something went wrong processing /refund. Check server logs. "
            "If the database is missing the latest migration, apply it in Supabase and redeploy."
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """# TESTING ONLY — show trial / paid Pro timestamps for debugging."""
    tid = update.effective_user.id
    row = get_user_by_telegram_id(tid)
    if not row:
        upsert_user(tid, update.effective_user.username or "", update.effective_user.first_name or "", None)
        row = get_user_by_telegram_id(tid)
    text = subscription_debug_summary(row)
    await update.message.reply_text(text)


async def cmd_cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop Telegram Stars auto-renewal. Keeps Pro until pro_expires_at."""
    tid = update.effective_user.id
    row = get_user_by_telegram_id(tid) or {}
    meta = subscription_meta_for_user(row)
    if not meta.get("can_cancel_star_subscription"):
        await update.message.reply_text(explain_cannot_cancel_star_subscription(row, meta))
        return

    pe = meta.get("pro_expires_at") or "the end date in /status"

    if should_skip_telegram_star_cancel(row):
        m = mark_star_subscription_cancelled(tid)
        body = MSG_CANCEL_ONETIME_EXPLANATION.format(pro_exp=pe)
        if m is None:
            await update.message.reply_text(
                f"{body}\n\n"
                "Note: the database could not store the “cancelled” flag. "
                "Run Supabase migration `20260422120000_subscription_cancel_and_active.sql`."
            )
        else:
            await update.message.reply_text(body)
        return

    ch = row.get("telegram_payment_charge_id")
    if not ch:
        await update.message.reply_text(explain_cannot_cancel_star_subscription(row, meta))
        return

    try:
        await context.bot.edit_user_star_subscription(
            user_id=tid,
            telegram_payment_charge_id=str(ch),
            is_canceled=True,
        )
    except tg_error.TelegramError as e:
        logger.warning("edit_user_star_subscription: %s", e)
        if is_telegram_charge_invalid_error(e):
            m = mark_star_subscription_cancelled(tid)
            body = MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK.format(pro_exp=pe)
            if m is None:
                await update.message.reply_text(
                    f"{body}\n\n"
                    "The database could not store the “cancelled” flag — run migration 20260422120000."
                )
            else:
                await update.message.reply_text(body)
            return
        await update.message.reply_text(format_telegram_cancel_subscription_error(e))
        return
    except Exception as e:
        logger.exception("edit_user_star_subscription unexpected: %s", e)
        if is_telegram_charge_invalid_error(e):
            m = mark_star_subscription_cancelled(tid)
            body = MSG_CANCEL_TELEGRAM_CHARGE_INVALID_FALLBACK.format(pro_exp=pe)
            if m is None:
                await update.message.reply_text(
                    f"{body}\n\nThe database could not store the “cancelled” flag — run migration 20260422120000."
                )
            else:
                await update.message.reply_text(body)
            return
        await update.message.reply_text(
            f"Unexpected error talking to Telegram: {type(e).__name__}: {e!s}\n\n"
            f"{format_telegram_cancel_subscription_error(e)}"
        )
        return

    m = mark_star_subscription_cancelled(tid)
    if m is None:
        await update.message.reply_text(
            "Telegram accepted the cancellation, but the database could not store the “cancelled” flag. "
            "An admin should run Supabase migration `20260422120000_subscription_cancel_and_active.sql`. "
            f"Your Pro access should still be valid until {pe} if Telegram shows auto-renewal off."
        )
        return

    await update.message.reply_text(
        f"Auto-renewal is off. You keep Nightflow Pro until {pe} (no more automatic Star charges for this plan after that, unless you subscribe again)."
    )


async def on_refunded_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rp = update.message.refunded_payment if update.message else None
    if not rp or rp.invoice_payload != INVOICE_PAYLOAD_NIGHTFLOW_PRO:
        return
    tid = update.effective_user.id
    revoke_pro_subscription(tid)
    rch = getattr(rp, "telegram_payment_charge_id", None) if rp else None
    record_pro_refund_for_rate_limit(tid, str(rch) if rch is not None else None)
    await update.message.reply_text(
        "Your Stars payment was refunded. Pro access has been disabled immediately."
    )


def _dedup_key(db_type: str, kind: str, slot: str, local_s: str):
    return (str(db_type), str(kind or db_type), str(slot), str(local_s))


def _seconds_until_next_minute() -> float:
    n = dt.datetime.now()
    return max(0.5, 60.0 - n.second - n.microsecond / 1_000_000.0)


async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
    """
    Send schedule reminders in the user's local timezone.
    Uses a 60s tick aligned near the start of each minute so HH:MM slot times actually match.
    """
    try:
        users_result = (
            supabase_client.table("users")
            .select(
                "id, telegram_id, timezone, notification_enabled, "
                "trial_started_at, pro_expires_at, notification_prefs"
            )
            .eq("notification_enabled", True)
            .execute()
        )
        if not users_result.data:
            return

        for user in users_result.data:
            if not has_pro_entitlement(user):
                continue
            user_id = user["id"]
            timezone_name = user.get("timezone") or DEFAULT_TIMEZONE
            now_local = get_user_now_from_timezone_name(timezone_name)
            today_local = now_local.date()
            current_hhmm = now_local.strftime("%H:%M")
            today_s = str(today_local)
            sent_keys = fetch_today_sent_dedup_keys(user_id, today_local)
            prefs = parse_notification_prefs(user)
            st, sched = fetch_effective_schedule_today(user_id, today_s)
            if st == "no_constant" or st == "off" or not sched:
                continue

            async def fire(db_type, kind, slot, text):
                k = _dedup_key(db_type, kind, slot, today_s)
                if k in sent_keys:
                    return
                try:
                    await send_notification(
                        context,
                        user_id,
                        text,
                        db_type,
                        {
                            "slot": slot,
                            "local_date": today_s,
                            "kind": kind,
                        },
                    )
                    sent_keys.add(k)
                except Exception as ex:
                    logger.error("notify fire failed: %s", ex)

            if prefs.get("notifWork", True):
                wh = format_hhmm(sched.get("work_start"))
                if wh and wh == current_hhmm:
                    stype = (sched.get("shift_type") or "shift").upper()
                    await fire(
                        "custom",
                        "work_start",
                        current_hhmm,
                        f"🌙 Work starts at {wh} — time to start, {stype}.",
                    )
                wend = format_hhmm(sched.get("work_end"))
                if wend and wend == current_hhmm:
                    stype = (sched.get("shift_type") or "shift").upper()
                    await fire(
                        "custom",
                        "work_end",
                        current_hhmm,
                        f"🏁 Shift ends at {wend}. Wind down and prepare for recovery ({stype}).",
                    )

            if prefs.get("notifSummary", True) and current_hhmm:
                wend = format_hhmm(sched.get("work_end"))
                if wend and wend == current_hhmm:
                    await fire(
                        "custom",
                        "end_shift_checkin",
                        current_hhmm,
                        "📝 End of shift — open the Nightflow mini app to log your check-in and energy.",
                    )

            if prefs.get("notifCoffee", True):
                for w in sched.get("coffee_windows") or []:
                    t = format_hhmm(w.get("time"))
                    if t and t == current_hhmm:
                        await fire("coffee", "coffee", current_hhmm, w.get("message", "☕ Time for coffee!"))

            if prefs.get("notifMeal", True):
                for w in sched.get("meal_windows") or []:
                    t = format_hhmm(w.get("time"))
                    if t and t == current_hhmm:
                        await fire("meal", "meal", current_hhmm, w.get("message", "🍽️ Time to eat!"))

            if prefs.get("notifLight", True):
                for w in sched.get("brightness_windows") or []:
                    t = format_hhmm(w.get("time"))
                    if t and t == current_hhmm:
                        await fire(
                            "brightness",
                            "brightness",
                            current_hhmm,
                            w.get("message", "💡 Light reminder!"),
                        )

            if prefs.get("notifSleep", True) and sched.get("sleep_start"):
                ss = sched.get("sleep_start")
                r_at = sleep_window_reminder_hhmm(str(ss), today_local, timezone_name)
                if r_at and r_at == current_hhmm:
                    ssn = format_hhmm(ss) or str(ss)[:5]
                    await fire(
                        "sleep",
                        "sleep_30",
                        current_hhmm,
                        f"😴 30 minutes until sleep ({ssn}). Start winding down.",
                    )
    except Exception as e:
        logger.error("Error in notifications: %s", e, exc_info=True)

async def send_notification(context, user_id, message, ntype, metadata=None):
    """Send a Telegram message and log it."""
    try:
        user = supabase_client.table("users").select("telegram_id").eq("id", user_id).execute()
        if not user.data:
            return
        telegram_id = user.data[0]["telegram_id"]
        await context.bot.send_message(chat_id=telegram_id, text=message)
        supabase_client.table("notifications").insert({
            "user_id": user_id,
            "type": ntype,
            "scheduled_time": datetime.now(ZoneInfo("UTC")).isoformat(),
            "sent": True,
            "sent_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "message": message,
            "metadata": metadata or {}
        }).execute()
        logger.info(f"Sent {ntype} to user {user_id}")
    except Exception as e:
        logger.error(f"Error sending notification: {e}")

async def log_errors(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Avoid noisy tracebacks for common Telegram conflicts (two pollers / webhook race)."""
    err = context.error
    if isinstance(err, tg_error.Conflict):
        logger.warning(
            "Telegram getUpdates conflict (only one bot poller allowed per token): %s",
            err,
        )
        return
    logger.error("Unhandled bot error", exc_info=err)


async def post_init(application: Application):
    """Set menu button and ensure we're in polling mode."""
    try:
        # IMPORTANT: Delete any existing webhook FIRST
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook deleted - forcing polling mode")
        
        # Then set menu button (this doesn't affect polling)
        await application.bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🌙 Nightflow",
                web_app=WebAppInfo(url="https://nightflow-bot-production.up.railway.app")
            )
        )
        logger.info("✅ Menu button set successfully")
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")

def main():
    """Start the bot with polling (NOT webhook)."""
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("No TELEGRAM_TOKEN")
        return

    # Create application
    application = Application.builder().token(token).post_init(post_init).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("refund", cmd_refund))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("cancel", cmd_cancel_subscription))
    application.add_handler(PreCheckoutQueryHandler(precheckout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, on_successful_payment))
    application.add_handler(MessageHandler(RefundedPaymentFilter(), on_refunded_payment))
    application.add_error_handler(log_errors)

    # Schedule notifications (1-minute cadence, first tick near top of a clock minute for HH:MM matching)
    if application.job_queue:
        application.job_queue.run_repeating(
            check_scheduled_notifications,
            interval=60,
            first=_seconds_until_next_minute(),
        )
        logger.info("✅ Notification scheduler started (60s interval, aligned to minute)")

    logger.info("🚀 Nightflow bot starting with POLLING...")
    
    # Start polling (NOT webhook)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        traceback.print_exc()