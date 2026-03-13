# # ============================================================
# # NIGHTFLOW BOT PROJECT STRUCTURE
# # ------------------------------------------------------------
# # main.py
# #   Main entry point of the bot.
# #   Keeps the core bot logic in one place:
# #   - Telegram command handlers
# #   - callback button handlers
# #   - notification loop
# #   - helper functions that are still small enough to keep here
# #   - bot startup / polling
# #
# # db.py
# #   Database layer for Supabase.
# #   Stores reusable database functions so main.py does not need
# #   to repeat raw queries everywhere.
# #   Examples:
# #   - get user by Telegram ID
# #   - fetch active schedule
# #   - update daily schedule
# #   - insert notifications
# #
# # schedule_utils.py
# #   Pure schedule/time logic.
# #   Contains reusable functions that do calculations but do not
# #   talk to Telegram or Supabase directly.
# #   Examples:
# #   - parse time strings
# #   - format times
# #   - calculate optimal schedule
# #   - caffeine window logic
# #   - shift transition advice
# #
# # web_app.py
# #   Small Flask health server used for hosting platforms like
# #   Render / Railway so the service has a web endpoint and
# #   health check route.
# #
# # Design choice:
# #   We are not splitting the project into many tiny files yet.
# #   Small and closely related bot logic stays in main.py for speed.
# #   Bigger reusable parts are moved out:
# #   - database code -> db.py
# #   - scheduling logic -> schedule_utils.py
# #   - health/web server -> web_app.py
# #
# # Rule of thumb:
# #   If a function is mostly about Telegram flow, keep it in main.py.
# #   If a function is reused or is mostly database logic, move it to db.py.
# #   If a function is pure time/schedule calculation, move it to schedule_utils.py.
# # ============================================================


# import os
# import traceback
# import logging
# import json
# import re
# from datetime import datetime, timedelta, date
# from zoneinfo import ZoneInfo


# from dotenv import load_dotenv
# from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
# from telegram.ext import (
#     Application, CommandHandler, CallbackQueryHandler,
#     MessageHandler, filters, ContextTypes, ConversationHandler
# )
# from telegram.constants import ParseMode

# from shared.db import (
#     supabase_client,
#     test_connection,
#     get_user_id,
#     get_user_by_telegram_id,
#     upsert_user,
#     update_last_active,
#     get_active_constant_schedule,
#     deactivate_constant_schedules,
#     insert_constant_schedule,
#     get_daily_schedule,
#     insert_daily_schedule,
#     update_daily_schedule,
#     get_notification_enabled,
#     set_notification_enabled,
#     get_users_with_notifications_enabled,
#     insert_notification,
# )

# from shared.schedule_utils import (
#     time_to_str,
#     str_to_time,
#     safe_json_parse,
#     calculate_optimal_schedule,
#     is_within_caffeine_window,
#     generate_transition_advice,
# )

# from web_app import start_web_server
# DEFAULT_TIMEZONE = "Asia/Tashkent"

# def get_timezone_name_from_user_row(user_row: dict) -> str:
#     tz = user_row.get("timezone")
#     return tz if tz else DEFAULT_TIMEZONE

# def get_user_now_from_timezone_name(timezone_name: str) -> datetime:
#     try:
#         return datetime.now(ZoneInfo(timezone_name))
#     except Exception:
#         return datetime.now(ZoneInfo(DEFAULT_TIMEZONE))

# def combine_local_date_and_time(local_date, time_value, timezone_name: str) -> datetime | None:
#     t = str_to_time(str(time_value)) if time_value else None
#     if not t:
#         return None
#     return datetime.combine(local_date, t, tzinfo=ZoneInfo(timezone_name))

# def get_next_local_time_occurrence(time_str: str, timezone_name: str, now_local: datetime) -> datetime | None:
#     t = str_to_time(time_str)
#     if not t:
#         return None

#     candidate = datetime.combine(now_local.date(), t, tzinfo=ZoneInfo(timezone_name))
#     if candidate < now_local:
#         candidate += timedelta(days=1)
#     return candidate


# load_dotenv()

# logging.basicConfig(
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     level=logging.INFO
# )
# logger = logging.getLogger(__name__)

# test_connection()
# start_web_server()

# AWAITING_CONSTANT, AWAITING_ROTATING = range(2)



# def get_active_schedule_or_none(user_id: str):
#     result = (
#         supabase_client.table("constant_schedules")
#         .select("*")
#         .eq("user_id", user_id)
#         .eq("active", True)
#         .execute()
#     )
#     if not result.data:
#         return None
#     return result.data[0]


# def get_today_daily_schedule_or_none(user_id: str, timezone_name: str):
#     today = str(get_user_now_from_timezone_name(timezone_name).date())
#     result = (
#         supabase_client.table("daily_schedules")
#         .select("*")
#         .eq("user_id", user_id)
#         .eq("date", today)
#         .execute()
#     )
#     if not result.data:
#         return None
#     return result.data[0]

# def build_caffeine_message(schedule: dict, timezone_name: str) -> str:
#     sleep_start = str_to_time(str(schedule.get("sleep_start")))
#     if not sleep_start:
#         return "Sleep schedule not configured properly."

#     now_local = get_user_now_from_timezone_name(timezone_name)

#     sleep_start_dt = datetime.combine(
#         now_local.date(),
#         sleep_start,
#         tzinfo=ZoneInfo(timezone_name)
#     )

#     if sleep_start_dt <= now_local:
#         sleep_start_dt += timedelta(days=1)

#     cutoff_dt = sleep_start_dt - timedelta(hours=6)

#     if now_local < cutoff_dt:
#         minutes_left = int((cutoff_dt - now_local).total_seconds() / 60)
#         return (
#             f"✅ **Safe for caffeine**\n\n"
#             f"You're outside the 6-hour sleep window.\n"
#             f"You have about {minutes_left} minutes left.\n\n"
#             f"Last call: {cutoff_dt.strftime('%H:%M')}"
#         )
#     else:
#         return (
#             f"🚫 **Caffeine window closed**\n\n"
#             f"You're within 6 hours of your sleep time ({time_to_str(schedule['sleep_start'])}).\n"
#             f"Coffee now may make sleep harder.\n\n"
#             f"Cutoff was: {cutoff_dt.strftime('%H:%M')}"
#         )


# def get_upcoming_meal(schedule: dict, timezone_name: str):
#     meal_windows = safe_json_parse(schedule.get("meal_windows"))
#     if not meal_windows:
#         return None

#     now_local = get_user_now_from_timezone_name(timezone_name)

#     best_meal = None
#     best_dt = None

#     for meal in meal_windows:
#         meal_time = meal.get("time")
#         if not meal_time:
#             continue

#         candidate = get_next_local_time_occurrence(meal_time, timezone_name, now_local)
#         if not candidate:
#             continue

#         if best_dt is None or candidate < best_dt:
#             best_dt = candidate
#             best_meal = meal

#     return best_meal

# def set_day_off_for_today(user_id: str, timezone_name: str):
#     today = str(get_user_now_from_timezone_name(timezone_name).date())

#     existing = (
#         supabase_client.table("daily_schedules")
#         .select("*")
#         .eq("user_id", user_id)
#         .eq("date", today)
#         .execute()
#     )

#     payload = {
#         "shift_type": "off",
#         "work_start": None,
#         "work_end": None,
#         "sleep_start": None,
#         "sleep_end": None,
#         "is_custom": True
#     }

#     if existing.data:
#         supabase_client.table("daily_schedules").update(payload).eq("id", existing.data[0]["id"]).execute()
#     else:
#         payload["user_id"] = user_id
#         payload["date"] = today
#         supabase_client.table("daily_schedules").insert(payload).execute()



# async def send_notification(context, user_id: str, message: str, notification_type: str, metadata: dict | None = None):
#     try:
#         result = (
#             supabase_client.table("users")
#             .select("telegram_id, timezone")
#             .eq("id", user_id)
#             .execute()
#         )

#         if not result.data:
#             return

#         user_row = result.data[0]
#         telegram_id = user_row["telegram_id"]
#         timezone_name = user_row.get("timezone") or "Asia/Tashkent"
#         now_local = get_user_now_from_timezone_name(timezone_name)

#         await context.bot.send_message(chat_id=telegram_id, text=message)

#         supabase_client.table("notifications").insert({
#             "user_id": user_id,
#             "type": notification_type,
#             "scheduled_time": now_local.astimezone(ZoneInfo("UTC")).isoformat(),
#             "sent": True,
#             "sent_at": datetime.now(ZoneInfo("UTC")).isoformat(),
#             "message": message,
#             "metadata": metadata or {}
#         }).execute()

#         logger.info(f"Sent {notification_type} notification to user {user_id}")

#     except Exception as e:
#         logger.error(f"Error sending notification: {e}")
#         logger.error(traceback.format_exc())

# async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
#     try:
#         users_result = (
#             supabase_client.table('users')
#             .select('id, telegram_id, timezone, notification_enabled')
#             .eq('notification_enabled', True)
#             .execute()
#         )

#         if not users_result.data:
#             return

#         for user in users_result.data:
#             user_id = user['id']
#             timezone_name = user.get('timezone') or 'Asia/Tashkent'
#             now_local = get_user_now_from_timezone_name(timezone_name)
#             today_local = now_local.date()
#             current_hour_min = now_local.strftime("%H:%M")

#             daily_result = (
#                 supabase_client.table('daily_schedules')
#                 .select('*')
#                 .eq('user_id', user_id)
#                 .eq('date', str(today_local))
#                 .execute()
#             )

#             if daily_result.data and daily_result.data[0].get('shift_type') == 'off':
#                 continue

#             schedule_result = (
#                 supabase_client.table('constant_schedules')
#                 .select('*')
#                 .eq('user_id', user_id)
#                 .eq('active', True)
#                 .execute()
#             )

#             if not schedule_result.data:
#                 continue

#             schedule = schedule_result.data[0]

#             coffee_windows = safe_json_parse(schedule.get('coffee_windows'))
#             meal_windows = safe_json_parse(schedule.get('meal_windows'))
#             brightness_windows = safe_json_parse(schedule.get('brightness_windows'))

#             for window in coffee_windows or []:
#                 if window.get('time') == current_hour_min:
#                     await send_notification_once(
#                         context, user_id, 'coffee', current_hour_min, today_local,
#                         window.get('message', 'Time for coffee!')
#                     )

#             for window in meal_windows or []:
#                 if window.get('time') == current_hour_min:
#                     await send_notification_once(
#                         context, user_id, 'meal', current_hour_min, today_local,
#                         window.get('message', 'Time to eat!')
#                     )

#             for window in brightness_windows or []:
#                 if window.get('time') == current_hour_min:
#                     await send_notification_once(
#                         context, user_id, 'brightness', current_hour_min, today_local,
#                         window.get('message', 'Light reminder!')
#                     )

#             sleep_start = schedule.get('sleep_start')
#             sleep_dt = combine_local_date_and_time(today_local, sleep_start, timezone_name)

#             if sleep_dt:
#                 if sleep_dt <= now_local:
#                     sleep_dt += timedelta(days=1)

#                 reminder_dt = sleep_dt - timedelta(minutes=30)
#                 if reminder_dt.strftime("%H:%M") == current_hour_min:
#                     await send_notification_once(
#                         context,
#                         user_id,
#                         'sleep',
#                         current_hour_min,
#                         today_local,
#                         f"😴 30 minutes until sleep time ({schedule['sleep_start']}). Start winding down."
#                     )

#     except Exception as e:
#         logger.error(f"Error in scheduled notifications: {e}")
#         logger.error(traceback.format_exc())
# async def send_notification_once(context, user_id: str, notification_type: str, hhmm: str, local_date, message: str):
#     try:
#         already = (
#             supabase_client.table("notifications")
#             .select("id")
#             .eq("user_id", user_id)
#             .eq("type", notification_type)
#             .eq("sent", True)
#             .contains("metadata", {"slot": hhmm, "local_date": str(local_date)})
#             .execute()
#         )

#         if already.data:
#             return

#         await send_notification(
#             context=context,
#             user_id=user_id,
#             message=message,
#             notification_type=notification_type,
#             metadata={"slot": hhmm, "local_date": str(local_date)}
#         )
#     except Exception as e:
#         logger.error(f"Error in send_notification_once: {e}")
#         logger.error(traceback.format_exc())
# async def caffeine_advice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         result = supabase_client.table("users").select("id, timezone").eq("telegram_id", update.effective_user.id).execute()
#         if not result.data:
#             await update.message.reply_text("Please use /start first to set up your account!")
#             return

#         user_row = result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone", "Asia/Tashkent")

#         schedule = get_active_schedule_or_none(user_id)
#         if not schedule:
#             await update.message.reply_text("Please set up your schedule first using /start")
#             return

#         msg = build_caffeine_message(schedule, timezone_name)
#         await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

#     except Exception as e:
#         logger.error(f"Error in caffeine_advice: {e}")
#         logger.error(traceback.format_exc())
#         await update.message.reply_text("Sorry, couldn't check caffeine safety.")

# def build_main_menu():
#     """Build main menu keyboard."""
#     keyboard = [
#         [InlineKeyboardButton("📅 Today", callback_data='show_today')],
#         [InlineKeyboardButton("☕ Caffeine Check", callback_data='caffeine_check')],
#         [InlineKeyboardButton("🍽️ Meal Advice", callback_data='meal_check')],
#         [InlineKeyboardButton("🔄 Change Shift", callback_data='change_shift_help')],
#         [InlineKeyboardButton("😴 Day Off", callback_data='day_off')],
#         [InlineKeyboardButton("⚙️ Settings", callback_data='settings')],
#         [InlineKeyboardButton("📋 Report", callback_data='view_report')],
#     ]
#     return InlineKeyboardMarkup(keyboard)

# async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Start command handler."""
#     user = update.effective_user

#     try:
#         result = supabase_client.table('users').select('*').eq('telegram_id', user.id).execute()

#         # Brand new user
#         if not result.data:
#             keyboard = [
#                 [InlineKeyboardButton("🌙 Constant Schedule", callback_data='shift_constant')],
#                 [InlineKeyboardButton("🔄 Rotating Schedule", callback_data='shift_rotating')],
#                 [InlineKeyboardButton("ℹ️ Learn More", callback_data='learn_more')]
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)

#             welcome_msg = (
#                 f"🌙 **Welcome to Nightflow, {user.first_name}!**\n\n"
#                 f"Nightflow helps shift workers manage:\n"
#                 f"• sleep timing\n"
#                 f"• caffeine timing\n"
#                 f"• meal timing\n"
#                 f"• light exposure\n"
#                 f"• shift transitions\n\n"
#                 f"Choose your schedule type to get started:"
#             )

#             await update.message.reply_text(
#                 welcome_msg,
#                 reply_markup=reply_markup,
#                 parse_mode=ParseMode.MARKDOWN
#             )
#             return

#         db_user = result.data[0]

#         update_last_active(db_user['id'], datetime.now().isoformat())

#         const_result = supabase_client.table('constant_schedules').select('id')\
#             .eq('user_id', db_user['id'])\
#             .eq('active', True)\
#             .execute()

#         rotating_result = supabase_client.table('rotating_patterns').select('id')\
#             .eq('user_id', db_user['id'])\
#             .eq('active', True)\
#             .execute()

#         has_schedule = bool(const_result.data or rotating_result.data)

#         # Existing user but no active schedule
#         if not has_schedule:
#             keyboard = [
#                 [InlineKeyboardButton("🌙 Constant Schedule", callback_data='shift_constant')],
#                 [InlineKeyboardButton("🔄 Rotating Schedule", callback_data='shift_rotating')],
#                 [InlineKeyboardButton("ℹ️ Learn More", callback_data='learn_more')]
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)

#             await update.message.reply_text(
#                 "It looks like setup wasn't finished. Choose your schedule type:",
#                 reply_markup=reply_markup
#             )
#             return

#         # Existing user with schedule
#         reply_markup = build_main_menu()

#         welcome_back_msg = (
#             f"Welcome back, {user.first_name}.\n\n"
#             f"Your shift assistant is ready. Choose an option:"
#         )

#         await update.message.reply_text(
#             welcome_back_msg,
#             reply_markup=reply_markup
#         )

#     except Exception as e:
#         logger.error(f"Error in start: {e}")
#         logger.error(traceback.format_exc())
#         await update.message.reply_text("Sorry, something went wrong. Please try again.")

# async def send_today_summary(chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", telegram_user_id).execute()
#         if not user_result.data:
#             await context.bot.send_message(chat_id=chat_id, text="Please use /start first to set up your account!")
#             return

#         user_row = user_result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#         now_local = get_user_now_from_timezone_name(timezone_name)
#         today = now_local.date()

#         daily_result = supabase_client.table('daily_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('date', str(today))\
#             .execute()

#         if daily_result.data:
#             s = daily_result.data[0]
#             shift_type = s.get('shift_type', 'unknown')
#             work_start = s.get('work_start')
#             work_end = s.get('work_end')
#             sleep_start = s.get('sleep_start')
#             sleep_end = s.get('sleep_end')
#         else:
#             const_result = supabase_client.table('constant_schedules').select('*')\
#                 .eq('user_id', user_id)\
#                 .eq('active', True)\
#                 .execute()

#             if not const_result.data:
#                 await context.bot.send_message(chat_id=chat_id, text="No schedule found. Please use /start to set up your schedule.")
#                 return

#             s = const_result.data[0]
#             shift_type = s.get('shift_type', 'unknown')
#             work_start = s.get('work_start')
#             work_end = s.get('work_end')
#             sleep_start = s.get('sleep_start')
#             sleep_end = s.get('sleep_end')

#         if shift_type == 'off':
#             msg = (
#                 f"📋 **Today's Plan** ({today})\n\n"
#                 f"**Status:** Day off\n"
#                 f"Take it easy today.\n\n"
#                 f"Use /start if you want the main menu."
#             )
#             await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
#             return

#         const_result = supabase_client.table('constant_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('active', True)\
#             .execute()

#         next_coffee = "—"
#         next_meal = "—"
#         next_light = "—"
#         caffeine_cutoff = "—"

#         if const_result.data:
#             const_schedule = const_result.data[0]

#             coffee_windows = safe_json_parse(const_schedule.get('coffee_windows'))
#             meal_windows = safe_json_parse(const_schedule.get('meal_windows'))
#             brightness_windows = safe_json_parse(const_schedule.get('brightness_windows'))

#             if coffee_windows:
#                 next_coffee = coffee_windows[0].get('time', '—')
#             if meal_windows:
#                 next_meal = meal_windows[0].get('time', '—')
#             if brightness_windows:
#                 next_light = brightness_windows[0].get('time', '—')

#             sleep_start_time = str_to_time(str(sleep_start)) if sleep_start else None
#             if sleep_start_time:
#                 cutoff_dt = datetime.combine(today, sleep_start_time) - timedelta(hours=6)
#                 caffeine_cutoff = cutoff_dt.strftime("%H:%M")

#         msg = (
#             f"📋 **Today's Plan** ({today})\n\n"
#             f"**Shift:** {str(shift_type).title()}\n"
#             f"**Work:** {time_to_str(work_start)} - {time_to_str(work_end)}\n"
#             f"**Sleep:** {time_to_str(sleep_start)} - {time_to_str(sleep_end)}\n\n"
#             f"**Next coffee:** {next_coffee}\n"
#             f"**Next meal:** {next_meal}\n"
#             f"**Next light reminder:** {next_light}\n"
#             f"**Caffeine cutoff:** {caffeine_cutoff}\n\n"
#             f"Use /caffeine for a live caffeine check."
#         )

#         await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)

#     except Exception as e:
#         logger.error(f"Error in send_today_summary: {e}")
#         logger.error(traceback.format_exc())
#         await context.bot.send_message(chat_id=chat_id, text="Sorry, couldn't build today's summary.")

# async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Show today's summary."""
#     await send_today_summary(update.effective_chat.id, update.effective_user.id, context)

# async def meal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         result = supabase_client.table("users").select("id, timezone").eq("telegram_id", update.effective_user.id).execute()
#         if not result.data:
#             await update.message.reply_text("Please use /start first to set up your account!")
#             return

#         user_row = result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#         schedule = get_active_schedule_or_none(user_id)
#         if not schedule:
#             await update.message.reply_text("Please set up your schedule first using /start")
#             return

#         upcoming = get_upcoming_meal(schedule, timezone_name)
#         if not upcoming:
#             await update.message.reply_text("No meal reminders found yet.")
#             return

#         await update.message.reply_text(
#             f"🍽️ **Next meal reminder**\n\n"
#             f"**Time:** {upcoming.get('time', '—')}\n"
#             f"{upcoming.get('message', 'Time to eat!')}",
#             parse_mode=ParseMode.MARKDOWN
#         )

#     except Exception as e:
#         logger.error(f"Error in meal_command: {e}")
#         logger.error(traceback.format_exc())
#         await update.message.reply_text("Sorry, couldn't fetch meal advice.")

# async def shift_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle shift type selection"""
#     query = update.callback_query
#     await query.answer()
    
#     try:
#         user_id = update.effective_user.id
        
#         if query.data == 'learn_more':
#             await query.edit_message_text(
#                 "🌙 **About Nightflow**\n\n"
#                 "Nightflow is designed specifically for night shift workers.\n\n"
#                 "**Key features:**\n"
#                 "• **Sleep optimization** - When to sleep for maximum rest\n"
#                 "• **Caffeine timing** - Never drink coffee at the wrong time again\n"
#                 "• **Meal reminders** - Stay fueled without the crash\n"
#                 "• **Light management** - Train your body when to be awake\n"
#                 "• **Shift transitions** - Adapt smoothly to schedule changes\n\n"
#                 "Ready to set up? Use /start again and choose your schedule type.",
#                 parse_mode=ParseMode.MARKDOWN
#             )
#             return ConversationHandler.END
        
#         shift_type = 'constant' if 'constant' in query.data else 'rotating'
        
#         # Save user to database
#         supabase_client.table('users').upsert({
#             'telegram_id': user_id,
#             'shift_type': shift_type,
#             'username': update.effective_user.username,
#             'first_name': update.effective_user.first_name,
#             'last_active': datetime.now().isoformat()
#         }).execute()
        
#         if shift_type == 'constant':
#             await query.edit_message_text(
#                 "✅ **Constant Schedule Selected**\n\n"
#                 "Please enter your typical work hours in this format:\n"
#                 "`HH:MM-HH:MM`\n\n"
#                 "Examples:\n"
#                 "• Night shift: `22:00-06:00`\n"
#                 "• Day shift: `09:00-17:00`\n"
#                 "• Evening shift: `16:00-00:00`\n\n"
#                 "Reply with your hours:",
#                 parse_mode=ParseMode.MARKDOWN
#             )
#             return AWAITING_CONSTANT
#         else:
#             await query.edit_message_text(
#                 "🔄 **Rotating Schedule Selected**\n\n"
#                 "Please describe your rotation pattern.\n\n"
#                 "Examples:\n"
#                 "• `2 days, 2 nights, 4 off`\n"
#                 "• `Dupont schedule` (12-hour shifts)\n"
#                 "• `Week of nights, week of days`\n\n"
#                 "Reply with your pattern:",
#                 parse_mode=ParseMode.MARKDOWN
#             )
#             return AWAITING_ROTATING
            
#     except Exception as e:
#         logger.error(f"Error in shift_type_handler: {e}")
#         await query.edit_message_text("Sorry, something went wrong. Please try /start again.")
#         return ConversationHandler.END

# async def save_constant_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Save constant schedule."""
#     try:
#         work_hours = update.message.text.strip().replace(" ", "")
#         if '-' not in work_hours:
#             raise ValueError("Missing hyphen")

#         start_str, end_str = work_hours.split('-')

#         work_start = str_to_time(start_str)
#         work_end = str_to_time(end_str)

#         if not work_start or not work_end:
#             raise ValueError("Invalid time format")

#         user_result = supabase_client.table('users').select('id, timezone').eq('telegram_id', update.effective_user.id).execute()
#         if not user_result.data:
#             await update.message.reply_text("User not found. Please use /start again.")
#             return ConversationHandler.END

#         user_row = user_result.data[0]
#         user_id = user_row['id']
#         timezone_name = user_row.get('timezone') or DEFAULT_TIMEZONE
#         optimized = calculate_optimal_schedule(work_start, work_end)
#         supabase_client.table('constant_schedules').update({'active': False})\
#             .eq('user_id', user_id)\
#             .eq('active', True)\
#             .execute()

#         supabase_client.table('constant_schedules').insert({
#             'user_id': user_id,
#             'work_start': time_to_str(work_start),
#             'work_end': time_to_str(work_end),
#             'sleep_start': optimized['sleep_start'],
#             'sleep_end': optimized['sleep_end'],
#             'coffee_windows': json.dumps(optimized['coffee_windows']),
#             'meal_windows': json.dumps(optimized['meal_windows']),
#             'brightness_windows': json.dumps(optimized['brightness_windows']),
#             'shift_type': optimized['shift_type'],
#             'active': True
#         }).execute()

#         now_local = get_user_now_from_timezone_name(timezone_name)
#         today = now_local.date()

#         existing = supabase_client.table('daily_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('date', str(today))\
#             .execute()

#         if existing.data:
#             supabase_client.table('daily_schedules').update({
#                 'shift_type': optimized['shift_type'],
#                 'work_start': time_to_str(work_start),
#                 'work_end': time_to_str(work_end),
#                 'sleep_start': optimized['sleep_start'],
#                 'sleep_end': optimized['sleep_end'],
#                 'is_custom': False
#             }).eq('id', existing.data[0]['id']).execute()
#         else:
#             supabase_client.table('daily_schedules').insert({
#                 'user_id': user_id,
#                 'date': str(today),
#                 'shift_type': optimized['shift_type'],
#                 'work_start': time_to_str(work_start),
#                 'work_end': time_to_str(work_end),
#                 'sleep_start': optimized['sleep_start'],
#                 'sleep_end': optimized['sleep_end'],
#                 'is_custom': False
#             }).execute()

#         coffee_times = [c['time'] for c in optimized['coffee_windows']]
#         meal_times = [m['time'] for m in optimized['meal_windows']]
#         brightness_times = [b['time'] for b in optimized['brightness_windows']]

#         schedule_msg = (
#             f"✅ **Your optimized schedule is ready!**\n\n"
#             f"**Work:** {time_to_str(work_start)} - {time_to_str(work_end)} ({optimized['shift_type']} shift)\n"
#             f"**Sleep:** {optimized['sleep_start']} - {optimized['sleep_end']}\n\n"
#             f"**Coffee times:** {', '.join(coffee_times)}\n"
#             f"**Meal times:** {', '.join(meal_times)}\n"
#             f"**Light reminders:** {', '.join(brightness_times)}\n\n"
#             f"I'll notify you before each important time!\n\n"
#             f"**Commands:**\n"
#             f"/today - View today's schedule\n"
#             f"/caffeine - Check if coffee is safe now\n"
#             f"/meal- Check the meal schdeule\n"
#             f"/change - Adjust for shift changes\n"
#             f"/dayoff - Take a day off\n"
#             f"/report - View weekly report"
#         )

#         await update.message.reply_text(schedule_msg, parse_mode=ParseMode.MARKDOWN)
#         return ConversationHandler.END

#     except ValueError as e:
#         logger.error(f"Value error in save_constant_schedule: {e}")
#         await update.message.reply_text(
#             "❌ I couldn't understand that format.\n\n"
#             "Please use `HH:MM-HH:MM`\n"
#             "Example: `22:00-06:00`",
#             parse_mode=ParseMode.MARKDOWN
#         )
#         return AWAITING_CONSTANT

#     except Exception as e:
#         logger.error(f"Error saving schedule: {e}")
#         logger.error(traceback.format_exc())
#         await update.message.reply_text("Sorry, something went wrong. Please try again.")
#         return ConversationHandler.END

# async def save_rotating_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Save rotating schedule"""
#     try:
#         pattern = update.message.text.strip()
        
#         # Get user
#         user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
#         if not user_result.data:
#             await update.message.reply_text("User not found. Please use /start again.")
#             return ConversationHandler.END
            
#         user_id = user_result.data[0]['id']
        
#         # Deactivate old patterns
#         supabase_client.table('rotating_patterns').update({'active': False})\
#             .eq('user_id', user_id)\
#             .eq('active', True)\
#             .execute()
        
#         # Save pattern
#         supabase_client.table('rotating_patterns').insert({
#             'user_id': user_id,
#             'pattern_name': 'custom',
#             'cycle_days': 7,
#             'shifts': json.dumps({'description': pattern}),
#             'active': True
#         }).execute()
        
#         await update.message.reply_text(
#             f"✅ **Rotating schedule saved!**\n\n"
#             f"Pattern: {pattern}\n\n"
#             f"I'll help you optimize your transitions between shifts.\n"
#             f"Use /schedule to see today's plan.\n\n"
#             f"**Note:** For rotating schedules, you'll need to update me when your pattern changes.",
#             parse_mode=ParseMode.MARKDOWN
#         )
        
#     except Exception as e:
#         logger.error(f"Error saving rotating schedule: {e}")
#         await update.message.reply_text("Sorry, something went wrong. Please try again.")
    
#     return ConversationHandler.END


# async def send_schedule_message(chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", telegram_user_id).execute()
#         if not user_result.data:
#             await context.bot.send_message(chat_id=chat_id, text="Please use /start first to set up your account!")
#             return

#         user_row = user_result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#         now_local = get_user_now_from_timezone_name(timezone_name)
#         today = now_local.date()

#         schedule_result = supabase_client.table('daily_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('date', str(today))\
#             .execute()

#         if schedule_result.data:
#             s = schedule_result.data[0]
#             custom_text = "⚠️ Custom schedule" if s.get('is_custom', False) else "✅ Optimized schedule"

#             msg = (
#                 f"📅 **Today's Schedule** ({today})\n\n"
#                 f"**Shift:** {s.get('shift_type', 'unknown').title() if s.get('shift_type') else 'Unknown'}\n"
#                 f"**Work:** {time_to_str(s.get('work_start', '--'))} - {time_to_str(s.get('work_end', '--'))}\n"
#                 f"**Sleep:** {time_to_str(s.get('sleep_start', '--'))} - {time_to_str(s.get('sleep_end', '--'))}\n\n"
#                 f"{custom_text}"
#             )
#             await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
#             return

#         const_result = supabase_client.table('constant_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('active', True)\
#             .execute()

#         if const_result.data:
#             s = const_result.data[0]
#             msg = (
#                 f"📅 **Today's Schedule** (from your constant schedule)\n\n"
#                 f"**Work:** {time_to_str(s['work_start'])} - {time_to_str(s['work_end'])}\n"
#                 f"**Sleep:** {time_to_str(s['sleep_start'])} - {time_to_str(s['sleep_end'])}\n\n"
#                 f"Use /change to modify if needed."
#             )
#             await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
#         else:
#             await context.bot.send_message(chat_id=chat_id, text="No schedule found. Please use /start to set up your schedule.")

#     except Exception as e:
#         logger.error(f"Error in send_schedule_message: {e}")
#         logger.error(traceback.format_exc())
#         await context.bot.send_message(chat_id=chat_id, text="Sorry, couldn't fetch your schedule.")
# async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Show today's schedule."""
#     await send_schedule_message(update.effective_chat.id, update.effective_user.id, context)

# async def dayoff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         result = supabase_client.table("users").select("id, timezone").eq("telegram_id", update.effective_user.id).execute()
#         if not result.data:
#             await update.message.reply_text("Please use /start first!")
#             return

#         user_row = result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#         set_day_off_for_today(user_id, timezone_name)

#         keyboard = [
#             [InlineKeyboardButton("Resume Tomorrow", callback_data='resume_tomorrow')],
#             [InlineKeyboardButton("Keep Day Off", callback_data='keep_off')],
#             [InlineKeyboardButton("Back to Work Today", callback_data='back_to_work')]
#         ]
#         reply_markup = InlineKeyboardMarkup(keyboard)

#         await update.message.reply_text(
#             "✅ **Day off noted!**\n\n"
#             "I've disabled notifications for today.\n"
#             "Rest well! What would you like for tomorrow?",
#             reply_markup=reply_markup,
#             parse_mode=ParseMode.MARKDOWN
#         )

#     except Exception as e:
#         logger.error(f"Error setting day off: {e}")
#         logger.error(traceback.format_exc())
#         await update.message.reply_text("Sorry, couldn't set day off.")

# async def change_shift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle shift change command"""
#     try:
#         args = context.args
#         if not args:
#             await update.message.reply_text(
#                 "📅 **Shift Change Helper**\n\n"
#                 "Use this command when your schedule changes.\n\n"
#                 "**Usage:**\n"
#                 "`/change HH:MM-HH:MM [days]`\n\n"
#                 "**Examples:**\n"
#                 "• `/change 23:00-07:00 tomorrow`\n"
#                 "• `/change 20:00-04:00 in 2 days`\n"
#                 "• `/change 18:00-02:00 today`\n\n"
#                 "I'll give you personalized transition advice.",
#                 parse_mode=ParseMode.MARKDOWN
#             )
#             return
        
#         # Parse command
#         shift_time = args[0]  # "22:00-06:00"
        
#         # Parse days
#         days_until = 1  # default to tomorrow
#         if len(args) >= 2:
#             day_text = ' '.join(args[1:]).lower()
#             if 'today' in day_text:
#                 days_until = 0
#             elif 'tomorrow' in day_text:
#                 days_until = 1
#             else:
#                 # Try to extract number
#                 numbers = re.findall(r'\d+', day_text)
#                 if numbers:
#                     days_until = int(numbers[0])
        
#         # Parse new shift times
#         if '-' not in shift_time:
#             await update.message.reply_text("❌ Invalid format. Use HH:MM-HH:MM")
#             return
            
#         start_str, end_str = shift_time.split('-')
#         new_start = str_to_time(start_str)
#         new_end = str_to_time(end_str)
        
#         if not new_start or not new_end:
#             await update.message.reply_text("❌ Invalid time format. Use HH:MM-HH:MM")
#             return
        
#         # Get current schedule
#         user_id = get_user_id(update.effective_user.id)
#         if not user_id:
#             await update.message.reply_text("Please use /start first!")
#             return
        
#         schedule_result = supabase_client.table('constant_schedules').select('*')\
#             .eq('user_id', user_id)\
#             .eq('active', True)\
#             .execute()
        
#         if not schedule_result.data:
#             await update.message.reply_text("No schedule found. Use /start to set up first.")
#             return
        
#         current = schedule_result.data[0]
#         old_start = str_to_time(current['work_start'])
#         old_end = str_to_time(current['work_end'])
        
#         if not old_start or not old_end:
#             await update.message.reply_text("Current schedule is invalid.")
#             return
        
#         # Generate transition advice
#         advice = generate_transition_advice(
#             old_start, old_end,
#             new_start, new_end,
#             days_until
#         )
        
#         # Ask if they want to update permanently
#         keyboard = [
#             [InlineKeyboardButton("✅ Update to New Schedule", callback_data=f"update_shift_{shift_time}")],
#             [InlineKeyboardButton("❌ Keep Current Schedule", callback_data="keep_current")]
#         ]
#         reply_markup = InlineKeyboardMarkup(keyboard)
        
#         await update.message.reply_text(
#             advice + "\n\nWould you like to update your permanent schedule?",
#             reply_markup=reply_markup,
#             parse_mode=ParseMode.MARKDOWN
#         )
        
#     except Exception as e:
#         logger.error(f"Error in change_shift: {e}")
#         await update.message.reply_text("Sorry, couldn't process shift change.")


# async def send_report_message(chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE):
#     try:
#         user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", telegram_user_id).execute()
#         if not user_result.data:
#             await context.bot.send_message(chat_id=chat_id, text="Please use /start first!")
#             return

#         user_row = user_result.data[0]
#         user_id = user_row["id"]
#         timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#         now_local = get_user_now_from_timezone_name(timezone_name)
#         end_date = now_local.date()
#         start_date = end_date - timedelta(days=7)

#         result = (
#             supabase_client.table("daily_schedules")
#             .select("*")
#             .eq("user_id", user_id)
#             .gte("date", str(start_date))
#             .lte("date", str(end_date))
#             .execute()
#         )

#         schedules = result.data or []
#         if not schedules:
#             await context.bot.send_message(
#                 chat_id=chat_id,
#                 text="Not enough data for a report yet. Check back in a week!"
#             )
#             return

#         total_days = len(schedules)
#         work_days = sum(1 for s in schedules if s.get("shift_type") != "off")
#         off_days = total_days - work_days
#         consistent_days = sum(1 for s in schedules if not s.get("is_custom", False))
#         consistency_score = (consistent_days / total_days * 100) if total_days else 0

#         shift_counts = {
#             "night": sum(1 for s in schedules if s.get("shift_type") == "night"),
#             "day": sum(1 for s in schedules if s.get("shift_type") == "day"),
#             "evening": sum(1 for s in schedules if s.get("shift_type") == "evening"),
#         }

#         if consistency_score < 50:
#             consistency_note = "⚠️ Your schedule has been irregular. Use /change to get transition help."
#         elif consistency_score < 80:
#             consistency_note = "👍 Pretty consistent! A few adjustments could help."
#         else:
#             consistency_note = "🌟 Excellent consistency! Your body thanks you."

#         report = (
#             f"📊 **Weekly Report**\n"
#             f"{start_date} to {end_date}\n\n"
#             f"**Overview:**\n"
#             f"• Total days: {total_days}\n"
#             f"• Work days: {work_days}\n"
#             f"• Days off: {off_days}\n\n"
#             f"**Shift Breakdown:**\n"
#             f"• Night shifts: {shift_counts['night']}\n"
#             f"• Day shifts: {shift_counts['day']}\n"
#             f"• Evening shifts: {shift_counts['evening']}\n\n"
#             f"**Consistency:** {consistency_score:.1f}%\n\n"
#             f"{consistency_note}"
#         )

#         await context.bot.send_message(
#             chat_id=chat_id,
#             text=report,
#             parse_mode=ParseMode.MARKDOWN
#         )

#     except Exception as e:
#         logger.error(f"Error in send_report_message: {e}")
#         logger.error(traceback.format_exc())
#         await context.bot.send_message(
#             chat_id=chat_id,
#             text="Sorry, couldn't generate report."
#         )


# async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Handle callback queries."""
#     query = update.callback_query
#     await query.answer()

#     try:
#         if query.data == 'show_today':
#             await send_today_summary(query.message.chat_id, query.from_user.id, context)

#         elif query.data == 'show_schedule':
#             await send_schedule_message(query.message.chat_id, query.from_user.id, context)

#         elif query.data == 'change_shift_help':
#             await query.message.reply_text(
#                 "🔄 **Shift Change Helper**\n\n"
#                 "Use this command when your schedule changes.\n\n"
#                 "**Usage:**\n"
#                 "`/change HH:MM-HH:MM [days]`\n\n"
#                 "**Examples:**\n"
#                 "• `/change 23:00-07:00 tomorrow`\n"
#                 "• `/change 20:00-04:00 in 2 days`\n"
#                 "• `/change 18:00-02:00 today`\n\n"
#                 "I'll give you personalized transition advice.",
#                 parse_mode=ParseMode.MARKDOWN
#             )

#         elif query.data == 'caffeine_check':
#             user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", query.from_user.id).execute()
#             if not user_result.data:
#                 await query.message.reply_text("Please use /start first to set up your account!")
#                 return

#             user_row = user_result.data[0]
#             user_id = user_row["id"]
#             timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#             schedule = get_active_schedule_or_none(user_id)
#             if not schedule:
#                 await query.message.reply_text("Please set up your schedule first using /start")
#                 return

#             msg = build_caffeine_message(schedule, timezone_name)
#             await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

#         elif query.data == 'meal_check':
#             user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", query.from_user.id).execute()
#             if not user_result.data:
#                 await query.message.reply_text("Please use /start first to set up your account!")
#                 return

#             user_row = user_result.data[0]
#             user_id = user_row["id"]
#             timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#             schedule = get_active_schedule_or_none(user_id)
#             if not schedule:
#                 await query.message.reply_text("Please set up your schedule first using /start")
#                 return

#             upcoming = get_upcoming_meal(schedule, timezone_name)
#             if not upcoming:
#                 await query.message.reply_text("No meal reminders found yet.")
#                 return

#             await query.message.reply_text(
#                 f"🍽️ **Next meal reminder**\n\n"
#                 f"**Time:** {upcoming.get('time', '—')}\n"
#                 f"{upcoming.get('message', 'Time to eat!')}",
#                 parse_mode=ParseMode.MARKDOWN
#             )

#         elif query.data == 'day_off':
#             user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", query.from_user.id).execute()
#             if not user_result.data:
#                 await query.message.reply_text("Please use /start first!")
#                 return

#             user_row = user_result.data[0]
#             user_id = user_row["id"]
#             timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#             set_day_off_for_today(user_id, timezone_name)

#             keyboard = [
#                 [InlineKeyboardButton("Resume Tomorrow", callback_data='resume_tomorrow')],
#                 [InlineKeyboardButton("Keep Day Off", callback_data='keep_off')],
#                 [InlineKeyboardButton("Back to Work Today", callback_data='back_to_work')]
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)

#             await query.message.reply_text(
#                 "✅ **Day off noted!**\n\n"
#                 "I've disabled notifications for today.\n"
#                 "Rest well! What would you like for tomorrow?",
#                 reply_markup=reply_markup,
#                 parse_mode=ParseMode.MARKDOWN
#             )

#         elif query.data == 'settings':
#             keyboard = [
#                 [InlineKeyboardButton("🔔 Toggle Notifications", callback_data='toggle_notifications')],
#                 [InlineKeyboardButton("📊 View Report", callback_data='view_report')],
#                 [InlineKeyboardButton("🔙 Back", callback_data='back_main')]
#             ]
#             reply_markup = InlineKeyboardMarkup(keyboard)
#             await query.edit_message_text(
#                 "⚙️ **Settings**",
#                 reply_markup=reply_markup,
#                 parse_mode=ParseMode.MARKDOWN
#             )

#         elif query.data == 'toggle_notifications':
#             user_id = get_user_id(query.from_user.id)
#             if not user_id:
#                 await query.edit_message_text("Please use /start first!")
#                 return

#             user = supabase_client.table('users').select('notification_enabled').eq('id', user_id).execute()
#             if user.data:
#                 current = user.data[0].get('notification_enabled', True)
#                 supabase_client.table('users').update({
#                     'notification_enabled': not current
#                 }).eq('id', user_id).execute()

#                 status = "enabled" if not current else "disabled"
#                 await query.edit_message_text(f"✅ Notifications {status}!")

#         elif query.data == 'view_report':
#             await send_report_message(query.message.chat_id, query.from_user.id, context)

#         elif query.data == 'back_main':
#             await query.edit_message_text(
#                 "Welcome back! What would you like to do?",
#                 reply_markup=build_main_menu()
#             )

#         elif query.data == 'resume_tomorrow':
#             await query.edit_message_text("Great! I'll resume your normal schedule tomorrow.")

#         elif query.data == 'keep_off':
#             await query.edit_message_text("Okay, I'll keep today as a day off. Use /schedule to update when you're ready.")

#         elif query.data == 'back_to_work':
#             user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", query.from_user.id).execute()
#             if not user_result.data:
#                 await query.edit_message_text("Please use /start first!")
#                 return

#             user_row = user_result.data[0]
#             user_id = user_row["id"]
#             timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE

#             now_local = get_user_now_from_timezone_name(timezone_name)
#             today = now_local.date()
#             const_result = supabase_client.table('constant_schedules').select('*')\
#                 .eq('user_id', user_id)\
#                 .eq('active', True)\
#                 .execute()

#             if const_result.data:
#                 s = const_result.data[0]

#                 existing = supabase_client.table('daily_schedules').select('*')\
#                     .eq('user_id', user_id)\
#                     .eq('date', str(today))\
#                     .execute()

#                 payload = {
#                     'user_id': user_id,
#                     'date': str(today),
#                     'shift_type': s['shift_type'],
#                     'work_start': s['work_start'],
#                     'work_end': s['work_end'],
#                     'sleep_start': s['sleep_start'],
#                     'sleep_end': s['sleep_end'],
#                     'is_custom': False
#                 }

#                 if existing.data:
#                     supabase_client.table('daily_schedules').update({
#                         'shift_type': s['shift_type'],
#                         'work_start': s['work_start'],
#                         'work_end': s['work_end'],
#                         'sleep_start': s['sleep_start'],
#                         'sleep_end': s['sleep_end'],
#                         'is_custom': False
#                     }).eq('id', existing.data[0]['id']).execute()
#                 else:
#                     supabase_client.table('daily_schedules').insert(payload).execute()

#                 await query.edit_message_text("✅ Back to work! I've restored your regular schedule for today.")
#             else:
#                 supabase_client.table('daily_schedules').delete()\
#                     .eq('user_id', user_id)\
#                     .eq('date', str(today))\
#                     .execute()
#                 await query.edit_message_text("✅ Back to work! No constant schedule found, so I removed the day-off override.")

#         elif query.data.startswith('update_shift_'):
#             shift_time = query.data.replace('update_shift_', '')
#             if '-' in shift_time:
#                 start_str, end_str = shift_time.split('-')
#                 user_result = supabase_client.table("users").select("id, timezone").eq("telegram_id", query.from_user.id).execute()
#                 if not user_result.data:
#                     await query.edit_message_text("Please use /start first!")
#                     return

#                 user_row = user_result.data[0]
#                 user_id = user_row["id"]
#                 timezone_name = user_row.get("timezone") or DEFAULT_TIMEZONE
                
#                 if user_id:
#                     work_start = str_to_time(start_str)
#                     work_end = str_to_time(end_str)

#                     if work_start and work_end:
#                         optimized = calculate_optimal_schedule(work_start, work_end)

#                         supabase_client.table('constant_schedules').update({'active': False})\
#                             .eq('user_id', user_id)\
#                             .eq('active', True)\
#                             .execute()

#                         supabase_client.table('constant_schedules').insert({
#                             'user_id': user_id,
#                             'work_start': time_to_str(work_start),
#                             'work_end': time_to_str(work_end),
#                             'sleep_start': optimized['sleep_start'],
#                             'sleep_end': optimized['sleep_end'],
#                             'coffee_windows': json.dumps(optimized['coffee_windows']),
#                             'meal_windows': json.dumps(optimized['meal_windows']),
#                             'brightness_windows': json.dumps(optimized['brightness_windows']),
#                             'shift_type': optimized['shift_type'],
#                             'active': True
#                         }).execute()

#                         now_local = get_user_now_from_timezone_name(timezone_name)
#                         today = now_local.date()
#                         existing = supabase_client.table('daily_schedules').select('*')\
#                             .eq('user_id', user_id)\
#                             .eq('date', str(today))\
#                             .execute()

#                         if existing.data:
#                             supabase_client.table('daily_schedules').update({
#                                 'shift_type': optimized['shift_type'],
#                                 'work_start': time_to_str(work_start),
#                                 'work_end': time_to_str(work_end),
#                                 'sleep_start': optimized['sleep_start'],
#                                 'sleep_end': optimized['sleep_end'],
#                                 'is_custom': False
#                             }).eq('id', existing.data[0]['id']).execute()
#                         else:
#                             supabase_client.table('daily_schedules').insert({
#                                 'user_id': user_id,
#                                 'date': str(today),
#                                 'shift_type': optimized['shift_type'],
#                                 'work_start': time_to_str(work_start),
#                                 'work_end': time_to_str(work_end),
#                                 'sleep_start': optimized['sleep_start'],
#                                 'sleep_end': optimized['sleep_end'],
#                                 'is_custom': False
#                             }).execute()

#                         await query.edit_message_text(
#                             f"✅ **Schedule Updated!**\n\n"
#                             f"New work hours: {time_to_str(work_start)}-{time_to_str(work_end)}\n"
#                             f"Sleep: {optimized['sleep_start']}-{optimized['sleep_end']}\n\n"
#                             f"Your notifications and today's schedule have been adjusted.",
#                             parse_mode=ParseMode.MARKDOWN
#                         )
#                     else:
#                         await query.edit_message_text("❌ Invalid time format.")

#         elif query.data == 'keep_current':
#             await query.edit_message_text("✅ Keeping your current schedule. Let me know if you need anything else!")

#     except Exception as e:
#         logger.error(f"Error in callback handler: {e}")
#         logger.error(traceback.format_exc())
#         await query.edit_message_text("Sorry, something went wrong.")

# async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Cancel conversation."""
#     await update.message.reply_text("Operation cancelled.")
#     return ConversationHandler.END


# async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Show weekly report."""
#     await send_report_message(update.effective_chat.id, update.effective_user.id, context)


# async def adjust_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     """Redirect to change command (for backward compatibility)."""
#     await update.message.reply_text(
#         "ℹ️ The `/adjust` command has been replaced with `/change`\n"
#         "Please use `/change HH:MM-HH:MM` to modify your schedule.",
#         parse_mode=ParseMode.MARKDOWN
#     )
# # ==================== MAIN FUNCTION ====================

# def main():
#     """Start the bot"""
#     # Get token
#     token = os.getenv('TELEGRAM_TOKEN')
#     if not token:
#         logger.error("TELEGRAM_TOKEN not found in environment variables!")
#         return
    
#     logger.info("Starting Nightflow Bot...")
    
#     try:
#         # Create application
#         application = Application.builder().token(token).build()
        
#         # Create conversation handler for onboarding
#         conv_handler = ConversationHandler(
#             entry_points=[CallbackQueryHandler(shift_type_handler, pattern='^(shift_constant|shift_rotating|learn_more)$')],
#             states={
#                 AWAITING_CONSTANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_constant_schedule)],
#                 AWAITING_ROTATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rotating_schedule)],
#             },
#             fallbacks=[
#                 CommandHandler('cancel', cancel),
#                 CommandHandler('start', start),
#             ],
#             allow_reentry=True
#         )
                
#         # Add command handlers
#         application.add_handler(CommandHandler("start", start))
#         application.add_handler(CommandHandler("schedule", schedule_command))
#         application.add_handler(CommandHandler("today", today_command))
#         application.add_handler(CommandHandler("meal", meal_command))
#         application.add_handler(CommandHandler("caffeine", caffeine_advice_command))
#         application.add_handler(CommandHandler("dayoff", dayoff_command))
#         application.add_handler(CommandHandler("change", change_shift_command))
#         application.add_handler(CommandHandler("report", report_command))
#         application.add_handler(CommandHandler("adjust", adjust_command))  # For backward compatibility
#         application.add_handler(CommandHandler("cancel", cancel))
        
#         # Add conversation handler
#         application.add_handler(conv_handler)
        
#         # Add callback query handler
#         application.add_handler(CallbackQueryHandler(handle_callback))
        
#         # Set up job queue for notifications
#         job_queue = application.job_queue
#         if job_queue:
#             # Check notifications every minute
#             job_queue.run_repeating(check_scheduled_notifications, interval=60, first=10)
#             logger.info("Notification job scheduled")
        
#         # Start bot
#         logger.info("Bot is ready and polling...")
#         application.run_polling(allowed_updates=Update.ALL_TYPES)
        
#     except Exception as e:
#         logger.error(f"Failed to start bot: {e}")

# if __name__ == '__main__':
#     main()


# bot/main.py
import os
import logging
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import json

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.db import (
    supabase_client,
    get_user_by_telegram_id,
    upsert_user,
    update_last_active,
    get_users_with_notifications_enabled,
    insert_notification,
)
from shared.time_utils import (
    get_user_now_from_timezone_name,
    combine_local_date_and_time,
    DEFAULT_TIMEZONE
)
from shared.schedule_utils import safe_json_parse

load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message with a button that opens the mini‑app."""
    user = update.effective_user
    # Ensure user exists in DB (if not, create a placeholder)
    db_user = get_user_by_telegram_id(user.id)
    if not db_user:
        upsert_user(user.id, user.username, user.first_name, None)
    update_last_active(user.id, datetime.now().isoformat())

    # Mini‑app button
    keyboard = [[InlineKeyboardButton("🌙 Open Nightflow", web_app={"url": "https://your-app-url.com"})]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Welcome, {user.first_name}! Click below to open the Nightflow mini‑app.",
        reply_markup=reply_markup
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

async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Background job – exactly as you had, but using shared functions."""
    try:
        users_result = (
            supabase_client.table('users')
            .select('id, telegram_id, timezone, notification_enabled')
            .eq('notification_enabled', True)
            .execute()
        )
        if not users_result.data:
            return

        for user in users_result.data:
            user_id = user['id']
            timezone_name = user.get('timezone') or DEFAULT_TIMEZONE
            now_local = get_user_now_from_timezone_name(timezone_name)
            today_local = now_local.date()
            current_hour_min = now_local.strftime("%H:%M")

            # Check if today is a day off (daily override)
            daily = supabase_client.table('daily_schedules').select('shift_type').eq('user_id', user_id).eq('date', str(today_local)).execute()
            if daily.data and daily.data[0].get('shift_type') == 'off':
                continue

            # Get active constant schedule
            const = supabase_client.table('constant_schedules').select('*').eq('user_id', user_id).eq('active', True).execute()
            if not const.data:
                continue
            schedule = const.data[0]

            coffee = safe_json_parse(schedule.get('coffee_windows'))
            meal = safe_json_parse(schedule.get('meal_windows'))
            bright = safe_json_parse(schedule.get('brightness_windows'))

            for w in coffee or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'coffee', current_hour_min, today_local, w.get('message', '☕ Time for coffee!'))

            for w in meal or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'meal', current_hour_min, today_local, w.get('message', '🍽️ Time to eat!'))

            for w in bright or []:
                if w.get('time') == current_hour_min:
                    await send_notification_once(context, user_id, 'brightness', current_hour_min, today_local, w.get('message', '💡 Light reminder!'))

            sleep_start = schedule.get('sleep_start')
            if sleep_start:
                sleep_dt = combine_local_date_and_time(today_local, sleep_start, timezone_name)
                if sleep_dt and sleep_dt <= now_local:
                    sleep_dt += timedelta(days=1)
                if sleep_dt and (sleep_dt - timedelta(minutes=30)).strftime("%H:%M") == current_hour_min:
                    await send_notification_once(context, user_id, 'sleep', current_hour_min, today_local, f"😴 30 minutes until sleep time ({sleep_start}). Wind down.")
    except Exception as e:
        logger.error(f"Error in notifications: {e}")

async def send_notification_once(context, user_id, ntype, hhmm, local_date, message):
    """Helper to avoid duplicate notifications."""
    try:
        already = supabase_client.table("notifications").select("id").eq("user_id", user_id).eq("type", ntype).eq("sent", True).contains("metadata", {"slot": hhmm, "local_date": str(local_date)}).execute()
        if already.data:
            return
        await send_notification(context, user_id, message, ntype, {"slot": hhmm, "local_date": str(local_date)})
    except Exception as e:
        logger.error(f"Error in send_notification_once: {e}")

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

def main():
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("No TELEGRAM_TOKEN")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("pause", pause))
    app.add_handler(CommandHandler("resume", resume))

    if app.job_queue:
        app.job_queue.run_repeating(check_scheduled_notifications, interval=60, first=10)

    logger.info("Bot started")
    app.run_polling()

if __name__ == '__main__':
    main()



