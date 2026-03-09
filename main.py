import os
import traceback
import logging
import asyncio
from datetime import datetime, time, timedelta, date
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from telegram.constants import ParseMode
import supabase
from flask import Flask
import threading
import json
import re
from typing import Dict, Any, Optional, List, Union

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Flask web server for Render/Railway
app = Flask(__name__)

@app.route('/')
def home():
    return "Nightflow Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Start web server in background
threading.Thread(target=run_web, daemon=True).start()

# Initialize Supabase
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase_client = supabase.create_client(supabase_url, supabase_key)

# Test Supabase connection
try:
    test_result = supabase_client.table('users').select('count', count='exact').execute()
    logger.info("✅ Supabase connected successfully")
except Exception as e:
    logger.error(f"❌ Supabase connection failed: {e}")

# Conversation states
AWAITING_CONSTANT, AWAITING_ROTATING, AWAITING_CUSTOM_SLEEP, AWAITING_SHIFT_CHANGE = range(4)

# ==================== HELPER FUNCTIONS ====================

def get_user_id(telegram_id: int) -> Optional[str]:
    """Get internal user ID from telegram ID"""
    try:
        result = supabase_client.table('users').select('id').eq('telegram_id', telegram_id).execute()
        if result.data:
            return result.data[0]['id']
        return None
    except Exception as e:
        logger.error(f"Error getting user ID: {e}")
        return None

def get_user_settings(telegram_id: int) -> Optional[Dict]:
    """Get user settings including schedule"""
    try:
        user_id = get_user_id(telegram_id)
        if not user_id:
            return None
        
        # Get user
        user_result = supabase_client.table('users').select('*').eq('id', user_id).execute()
        if not user_result.data:
            return None
        
        user = user_result.data[0]
        
        # Get active schedule
        schedule_result = supabase_client.table('constant_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        if schedule_result.data:
            user['schedule'] = schedule_result.data[0]
        
        return user
    except Exception as e:
        logger.error(f"Error getting user settings: {e}")
        return None

def time_to_str(t: Union[time, str]) -> str:
    """Convert time to HH:MM string"""
    if isinstance(t, time):
        return t.strftime("%H:%M")
    return str(t)

def str_to_time(time_str: str) -> Optional[time]:
    """Convert HH:MM string to time object"""
    try:
        return datetime.strptime(time_str.strip(), "%H:%M").time()
    except:
        return None

def safe_json_parse(data: Any) -> Any:
    """Safely parse JSON data that might be string or already parsed"""
    if data is None:
        return []
    if isinstance(data, str):
        try:
            return json.loads(data)
        except:
            return []
    return data

def calculate_optimal_schedule(work_start: time, work_end: time) -> Dict:
    """Calculate optimal sleep, coffee, meal, and brightness times"""
    
    # Convert to datetime for calculations
    today = date.today()
    work_start_dt = datetime.combine(today, work_start)
    work_end_dt = datetime.combine(today, work_end)
    
    # If work end is before work start, it's next day
    if work_end_dt <= work_start_dt:
        work_end_dt += timedelta(days=1)
    
    # Determine shift type
    if work_start.hour >= 20 or work_start.hour <= 4:
        shift_type = 'night'
    elif work_start.hour >= 12 and work_start.hour < 20:
        shift_type = 'evening'
    else:
        shift_type = 'day'
    
    # Calculate sleep times based on shift type
    if shift_type == 'night':
        # Night shift: sleep right after work
        sleep_start = work_end_dt.time()
        # Wake up 1.5 hours before shift
        wake_dt = work_start_dt - timedelta(hours=1, minutes=30)
        sleep_end = wake_dt.time()
    elif shift_type == 'evening':
        # Evening shift: sleep before shift
        sleep_start = time(2, 0)  # 2 AM
        sleep_end = time(10, 0)    # 10 AM
    else:
        # Day shift: normal sleep
        sleep_start = time(22, 0)  # 10 PM
        sleep_end = time(6, 0)      # 6 AM
    
    # Calculate caffeine windows
    coffee_windows = []
    
    # Pre-work coffee (30 min before)
    pre_work_coffee = work_start_dt - timedelta(minutes=30)
    coffee_windows.append({
        "time": pre_work_coffee.strftime("%H:%M"),
        "message": "☕ Pre-shift coffee. Perfect timing to start alert.",
        "type": "pre_work"
    })
    
    # Mid-shift coffee (3-4 hours in)
    mid_coffee = work_start_dt + timedelta(hours=3, minutes=30)
    coffee_windows.append({
        "time": mid_coffee.strftime("%H:%M"),
        "message": "☕ Mid-shift boost. You're halfway there.",
        "type": "mid_shift"
    })
    
    # Calculate meal windows
    meal_windows = []
    
    # Pre-work meal (1.5 hours before)
    pre_meal = work_start_dt - timedelta(hours=1, minutes=30)
    meal_windows.append({
        "time": pre_meal.strftime("%H:%M"),
        "message": "🍽️ Pre-shift meal. Protein + complex carbs for steady energy.",
        "type": "pre_work"
    })
    
    # Mid-shift meal (4 hours in)
    mid_meal = work_start_dt + timedelta(hours=4)
    meal_windows.append({
        "time": mid_meal.strftime("%H:%M"),
        "message": "🥗 Mid-shift fuel. Avoid heavy/greasy food.",
        "type": "mid_shift"
    })
    
    # Post-shift snack (light)
    post_meal = work_end_dt
    meal_windows.append({
        "time": post_meal.strftime("%H:%M"),
        "message": "🍌 Post-shift snack. Light before sleep. Banana is perfect.",
        "type": "post_work"
    })
    
    # Calculate brightness windows
    brightness_windows = []
    
    # Pre-work: bright light exposure
    pre_bright = work_start_dt - timedelta(minutes=15)
    brightness_windows.append({
        "time": pre_bright.strftime("%H:%M"),
        "message": "☀️ Bright light time. Tell your brain: wake up!",
        "type": "bright",
        "action": "increase_light"
    })
    
    # 2 hours before sleep: dim lights
    sleep_start_dt = datetime.combine(today, sleep_start)
    if sleep_start_dt <= work_end_dt and shift_type == 'night':
        sleep_start_dt += timedelta(days=1)
    
    dim_time = sleep_start_dt - timedelta(hours=2)
    brightness_windows.append({
        "time": dim_time.strftime("%H:%M"),
        "message": "🌙 Time to dim lights. Tell your brain: sleep is coming.",
        "type": "dim",
        "action": "dim_lights"
    })
    
    # 30 min before sleep: no screens
    no_screens = sleep_start_dt - timedelta(minutes=30)
    brightness_windows.append({
        "time": no_screens.strftime("%H:%M"),
        "message": "📵 30 min until sleep. Put devices away. Read a book.",
        "type": "no_screens",
        "action": "no_screens"
    })
    
    # Post-work light management (for night shifts)
    if shift_type == 'night':
        commute_time = work_end_dt + timedelta(minutes=30)
        brightness_windows.append({
            "time": commute_time.strftime("%H:%M"),
            "message": "🕶️ On the way home? Wear sunglasses. Blue light blockers help.",
            "type": "blue_block",
            "action": "wear_sunglasses"
        })
    
    return {
        "sleep_start": time_to_str(sleep_start),
        "sleep_end": time_to_str(sleep_end),
        "coffee_windows": coffee_windows,
        "meal_windows": meal_windows,
        "brightness_windows": brightness_windows,
        "shift_type": shift_type
    }

def is_within_caffeine_window(sleep_start: time, current_time: time) -> bool:
    """Return True if current time is inside the no-caffeine window (6h before sleep)."""
    sleep_start_dt = datetime.combine(date.today(), sleep_start)
    current_dt = datetime.combine(date.today(), current_time)

    if sleep_start_dt <= current_dt:
        sleep_start_dt += timedelta(days=1)

    cutoff_dt = sleep_start_dt - timedelta(hours=6)
    return current_dt >= cutoff_dt

def generate_transition_advice(old_work_start: time, old_work_end: time, 
                               new_work_start: time, new_work_end: time,
                               days_until_change: int) -> str:
    """Generate advice for transitioning between shift patterns"""
    
    # Calculate shift difference
    old_start_dt = datetime.combine(date.today(), old_work_start)
    new_start_dt = datetime.combine(date.today(), new_work_start)
    
    if new_start_dt <= old_start_dt:
        new_start_dt += timedelta(days=1)
    
    hours_diff = (new_start_dt - old_start_dt).total_seconds() / 3600
    
    advice = f"🔄 **Shift Change Preparation**\n\n"
    advice += f"Moving from {time_to_str(old_work_start)}-{time_to_str(old_work_end)} "
    advice += f"to {time_to_str(new_work_start)}-{time_to_str(new_work_end)}\n\n"
    
    if hours_diff > 0:
        advice += f"Your new shift starts {hours_diff:.1f} hours later.\n\n"
        
        if hours_diff <= 3:
            advice += "✅ Small adjustment. Stay up a bit later each night."
        elif hours_diff <= 6:
            advice += "⚡ Medium shift. Consider a split sleep schedule:\n"
            advice += "• Nap 3-4 hours before first new shift\n"
            advice += "• Then sleep 4-5 hours after shift"
        else:
            advice += "⚠️ Large shift change. This will take a few days to adjust:\n"
            advice += "• Day 1: Stay up 2 hours later than usual\n"
            advice += "• Day 2: Stay up 4 hours later\n"
            advice += "• Day 3: Full adjustment"
    else:
        advice += f"Your new shift starts {abs(hours_diff):.1f} hours earlier.\n\n"
        advice += "Early transition strategy:\n"
        advice += "• Go to bed earlier each night\n"
        advice += "• Get bright light exposure immediately upon waking\n"
        advice += "• Avoid caffeine 6 hours before new bedtime"
    
    advice += "\n\nI'll send you daily transition reminders."
    
    return advice

# ==================== NOTIFICATION FUNCTIONS ====================

async def send_notification(context: ContextTypes.DEFAULT_TYPE, user_id: str, message: str, notification_type: str):
    """Send notification to user and log it."""
    try:
        result = supabase_client.table('users').select('telegram_id').eq('id', user_id).execute()
        if not result.data:
            return

        telegram_id = result.data[0]['telegram_id']

        await context.bot.send_message(chat_id=telegram_id, text=message)

        supabase_client.table('notifications').insert({
            'user_id': user_id,
            'type': notification_type,
            'scheduled_time': datetime.now().isoformat(),
            'sent': True,
            'sent_at': datetime.now().isoformat(),
            'message': message
        }).execute()

        logger.info(f"Sent {notification_type} notification to user {user_id}")

    except Exception as e:
        logger.error(f"Error sending notification: {e}")
        logger.error(traceback.format_exc())

async def check_scheduled_notifications(context: ContextTypes.DEFAULT_TYPE):
    """Job to check and send scheduled notifications."""
    try:
        now = datetime.now()
        today = now.date()
        current_hour_min = now.strftime("%H:%M")

        users_result = supabase_client.table('users').select('id')\
            .eq('notification_enabled', True)\
            .execute()

        for user in users_result.data:
            user_id = user['id']

            # Skip if today is marked as off
            daily_result = supabase_client.table('daily_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('date', str(today))\
                .execute()

            if daily_result.data:
                daily = daily_result.data[0]
                if daily.get('shift_type') == 'off':
                    continue

            schedule_result = supabase_client.table('constant_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('active', True)\
                .execute()

            if not schedule_result.data:
                continue

            schedule = schedule_result.data[0]

            if schedule.get('coffee_windows'):
                coffee_windows = safe_json_parse(schedule['coffee_windows'])
                for window in coffee_windows:
                    if window.get('time') == current_hour_min:
                        await send_notification(
                            context,
                            user_id,
                            window.get('message', 'Time for coffee!'),
                            'coffee'
                        )

            if schedule.get('meal_windows'):
                meal_windows = safe_json_parse(schedule['meal_windows'])
                for window in meal_windows:
                    if window.get('time') == current_hour_min:
                        await send_notification(
                            context,
                            user_id,
                            window.get('message', 'Time to eat!'),
                            'meal'
                        )

            if schedule.get('brightness_windows'):
                brightness_windows = safe_json_parse(schedule['brightness_windows'])
                for window in brightness_windows:
                    if window.get('time') == current_hour_min:
                        await send_notification(
                            context,
                            user_id,
                            window.get('message', 'Light reminder!'),
                            'brightness'
                        )

            if schedule.get('sleep_start'):
                sleep_start = str_to_time(schedule['sleep_start'])
                if sleep_start:
                    sleep_dt = datetime.combine(today, sleep_start)
                    if sleep_dt <= now:
                        sleep_dt += timedelta(days=1)

                    reminder_dt = sleep_dt - timedelta(minutes=30)
                    if reminder_dt.strftime("%H:%M") == current_hour_min:
                        await send_notification(
                            context,
                            user_id,
                            f"😴 30 minutes until sleep time ({schedule['sleep_start']}). Start winding down.",
                            'sleep'
                        )

    except Exception as e:
        logger.error(f"Error in scheduled notifications: {e}")
        logger.error(traceback.format_exc())

async def caffeine_advice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /caffeine command - check if coffee is safe now."""
    try:
        user_id = get_user_id(update.effective_user.id)
        if not user_id:
            await update.message.reply_text("Please use /start first to set up your account!")
            return

        schedule_result = supabase_client.table('constant_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()

        if not schedule_result.data:
            await update.message.reply_text("Please set up your schedule first using /start")
            return

        schedule = schedule_result.data[0]
        sleep_start = str_to_time(schedule['sleep_start'])

        if not sleep_start:
            await update.message.reply_text("Sleep schedule not configured properly.")
            return

        now = datetime.now().time()

        sleep_start_dt = datetime.combine(date.today(), sleep_start)
        now_dt = datetime.combine(date.today(), now)

        if sleep_start_dt <= now_dt:
            sleep_start_dt += timedelta(days=1)

        cutoff_dt = sleep_start_dt - timedelta(hours=6)

        if is_within_caffeine_window(sleep_start, now):
            minutes_left = int((cutoff_dt - now_dt).total_seconds() / 60)

            if minutes_left > 0:
                await update.message.reply_text(
                    f"⚠️ **Caffeine Warning**\n\n"
                    f"You have {minutes_left} minutes left for caffeine today.\n"
                    f"After {cutoff_dt.strftime('%H:%M')}, caffeine will disrupt your sleep.\n\n"
                    f"Last call: {cutoff_dt.strftime('%H:%M')}",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    f"🚫 **Caffeine window closed**\n\n"
                    f"You're within 6 hours of your sleep time ({schedule['sleep_start']}).\n"
                    f"Coffee now will make falling asleep harder.\n"
                    f"Try herbal tea or water instead.",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            await update.message.reply_text(
                f"✅ **Safe for caffeine**\n\n"
                f"You're outside the 6-hour sleep window.\n"
                f"Enjoy your coffee! Remember: last call is {cutoff_dt.strftime('%H:%M')}",
                parse_mode=ParseMode.MARKDOWN
            )

    except Exception as e:
        logger.error(f"Error in caffeine_advice: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("Sorry, couldn't check caffeine safety.")
# ==================== COMMAND HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler."""
    user = update.effective_user

    try:
        result = supabase_client.table('users').select('*').eq('telegram_id', user.id).execute()

        if not result.data:
            keyboard = [
                [InlineKeyboardButton("Constant Schedule", callback_data='shift_constant')],
                [InlineKeyboardButton("Rotating Schedule", callback_data='shift_rotating')],
                [InlineKeyboardButton("Learn More First", callback_data='learn_more')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            welcome_msg = (
                f"🌙 **Welcome to Nightflow, {user.first_name}!**\n\n"
                f"I'm your personal night shift companion. I'll help you:\n"
                f"• Optimize your sleep schedule\n"
                f"• Time your caffeine perfectly\n"
                f"• Remember to eat and hydrate\n"
                f"• Manage light exposure\n"
                f"• Adapt to shift changes\n\n"
                f"First, tell me about your shift pattern:"
            )

            await update.message.reply_text(welcome_msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
            return

        db_user = result.data[0]

        supabase_client.table('users').update({
            'last_active': datetime.now().isoformat()
        }).eq('telegram_id', user.id).execute()

        const_result = supabase_client.table('constant_schedules').select('id')\
            .eq('user_id', db_user['id'])\
            .eq('active', True)\
            .execute()

        rotating_result = supabase_client.table('rotating_patterns').select('id')\
            .eq('user_id', db_user['id'])\
            .eq('active', True)\
            .execute()

        has_schedule = bool(const_result.data or rotating_result.data)

        if not has_schedule:
            keyboard = [
                [InlineKeyboardButton("Constant Schedule", callback_data='shift_constant')],
                [InlineKeyboardButton("Rotating Schedule", callback_data='shift_rotating')],
                [InlineKeyboardButton("Learn More First", callback_data='learn_more')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "It looks like setup wasn't finished. Please choose your shift pattern again:",
                reply_markup=reply_markup
            )
            return

        keyboard = [
            [InlineKeyboardButton("📅 Today's Schedule", callback_data='show_schedule')],
            [InlineKeyboardButton("☕ Caffeine Check", callback_data='caffeine_check')],
            [InlineKeyboardButton("😴 Day Off", callback_data='day_off')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Welcome back, {user.first_name}! What would you like to do?",
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Error in start: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("Sorry, something went wrong. Please try again.")

async def shift_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shift type selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = update.effective_user.id
        
        if query.data == 'learn_more':
            await query.edit_message_text(
                "🌙 **About Nightflow**\n\n"
                "Nightflow is designed specifically for night shift workers.\n\n"
                "**Key features:**\n"
                "• **Sleep optimization** - When to sleep for maximum rest\n"
                "• **Caffeine timing** - Never drink coffee at the wrong time again\n"
                "• **Meal reminders** - Stay fueled without the crash\n"
                "• **Light management** - Train your body when to be awake\n"
                "• **Shift transitions** - Adapt smoothly to schedule changes\n\n"
                "Ready to set up? Use /start again and choose your schedule type.",
                parse_mode=ParseMode.MARKDOWN
            )
            return ConversationHandler.END
        
        shift_type = 'constant' if 'constant' in query.data else 'rotating'
        
        # Save user to database
        supabase_client.table('users').upsert({
            'telegram_id': user_id,
            'shift_type': shift_type,
            'username': update.effective_user.username,
            'first_name': update.effective_user.first_name,
            'last_active': datetime.now().isoformat()
        }).execute()
        
        if shift_type == 'constant':
            await query.edit_message_text(
                "✅ **Constant Schedule Selected**\n\n"
                "Please enter your typical work hours in this format:\n"
                "`HH:MM-HH:MM`\n\n"
                "Examples:\n"
                "• Night shift: `22:00-06:00`\n"
                "• Day shift: `09:00-17:00`\n"
                "• Evening shift: `16:00-00:00`\n\n"
                "Reply with your hours:",
                parse_mode=ParseMode.MARKDOWN
            )
            return AWAITING_CONSTANT
        else:
            await query.edit_message_text(
                "🔄 **Rotating Schedule Selected**\n\n"
                "Please describe your rotation pattern.\n\n"
                "Examples:\n"
                "• `2 days, 2 nights, 4 off`\n"
                "• `Dupont schedule` (12-hour shifts)\n"
                "• `Week of nights, week of days`\n\n"
                "Reply with your pattern:",
                parse_mode=ParseMode.MARKDOWN
            )
            return AWAITING_ROTATING
            
    except Exception as e:
        logger.error(f"Error in shift_type_handler: {e}")
        await query.edit_message_text("Sorry, something went wrong. Please try /start again.")
        return ConversationHandler.END

async def save_constant_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save constant schedule."""
    try:
        work_hours = update.message.text.strip().replace(" ", "")
        if '-' not in work_hours:
            raise ValueError("Missing hyphen")

        start_str, end_str = work_hours.split('-')

        work_start = str_to_time(start_str)
        work_end = str_to_time(end_str)

        if not work_start or not work_end:
            raise ValueError("Invalid time format")

        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("User not found. Please use /start again.")
            return ConversationHandler.END

        user_id = user_result.data[0]['id']
        optimized = calculate_optimal_schedule(work_start, work_end)

        supabase_client.table('constant_schedules').update({'active': False})\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()

        supabase_client.table('constant_schedules').insert({
            'user_id': user_id,
            'work_start': time_to_str(work_start),
            'work_end': time_to_str(work_end),
            'sleep_start': optimized['sleep_start'],
            'sleep_end': optimized['sleep_end'],
            'coffee_windows': json.dumps(optimized['coffee_windows']),
            'meal_windows': json.dumps(optimized['meal_windows']),
            'brightness_windows': json.dumps(optimized['brightness_windows']),
            'shift_type': optimized['shift_type'],
            'active': True
        }).execute()

        today = datetime.now().date()

        existing = supabase_client.table('daily_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('date', str(today))\
            .execute()

        if existing.data:
            supabase_client.table('daily_schedules').update({
                'shift_type': optimized['shift_type'],
                'work_start': time_to_str(work_start),
                'work_end': time_to_str(work_end),
                'sleep_start': optimized['sleep_start'],
                'sleep_end': optimized['sleep_end'],
                'is_custom': False
            }).eq('id', existing.data[0]['id']).execute()
        else:
            supabase_client.table('daily_schedules').insert({
                'user_id': user_id,
                'date': str(today),
                'shift_type': optimized['shift_type'],
                'work_start': time_to_str(work_start),
                'work_end': time_to_str(work_end),
                'sleep_start': optimized['sleep_start'],
                'sleep_end': optimized['sleep_end'],
                'is_custom': False
            }).execute()

        coffee_times = [c['time'] for c in optimized['coffee_windows']]
        meal_times = [m['time'] for m in optimized['meal_windows']]
        brightness_times = [b['time'] for b in optimized['brightness_windows']]

        schedule_msg = (
            f"✅ **Your optimized schedule is ready!**\n\n"
            f"**Work:** {time_to_str(work_start)} - {time_to_str(work_end)} ({optimized['shift_type']} shift)\n"
            f"**Sleep:** {optimized['sleep_start']} - {optimized['sleep_end']}\n\n"
            f"**Coffee times:** {', '.join(coffee_times)}\n"
            f"**Meal times:** {', '.join(meal_times)}\n"
            f"**Light reminders:** {', '.join(brightness_times)}\n\n"
            f"I'll notify you before each important time!\n\n"
            f"**Commands:**\n"
            f"/schedule - View today's schedule\n"
            f"/caffeine - Check if coffee is safe now\n"
            f"/dayoff - Take a day off\n"
            f"/change - Adjust for shift changes\n"
            f"/report - View weekly report"
        )

        await update.message.reply_text(schedule_msg, parse_mode=ParseMode.MARKDOWN)
        return ConversationHandler.END

    except ValueError as e:
        logger.error(f"Value error in save_constant_schedule: {e}")
        await update.message.reply_text(
            "❌ I couldn't understand that format.\n\n"
            "Please use `HH:MM-HH:MM`\n"
            "Example: `22:00-06:00`",
            parse_mode=ParseMode.MARKDOWN
        )
        return AWAITING_CONSTANT

    except Exception as e:
        logger.error(f"Error saving schedule: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        return ConversationHandler.END

async def save_rotating_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save rotating schedule"""
    try:
        pattern = update.message.text.strip()
        
        # Get user
        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("User not found. Please use /start again.")
            return ConversationHandler.END
            
        user_id = user_result.data[0]['id']
        
        # Deactivate old patterns
        supabase_client.table('rotating_patterns').update({'active': False})\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        # Save pattern
        supabase_client.table('rotating_patterns').insert({
            'user_id': user_id,
            'pattern_name': 'custom',
            'cycle_days': 7,
            'shifts': json.dumps({'description': pattern}),
            'active': True
        }).execute()
        
        await update.message.reply_text(
            f"✅ **Rotating schedule saved!**\n\n"
            f"Pattern: {pattern}\n\n"
            f"I'll help you optimize your transitions between shifts.\n"
            f"Use /schedule to see today's plan.\n\n"
            f"**Note:** For rotating schedules, you'll need to update me when your pattern changes.",
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error saving rotating schedule: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
    
    return ConversationHandler.END
async def send_schedule_message(chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Send today's schedule to a chat."""
    try:
        user_id = get_user_id(telegram_user_id)
        if not user_id:
            await context.bot.send_message(chat_id=chat_id, text="Please use /start first to set up your account!")
            return

        today = datetime.now().date()

        schedule_result = supabase_client.table('daily_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('date', str(today))\
            .execute()

        if schedule_result.data:
            s = schedule_result.data[0]
            custom_text = "⚠️ Custom schedule" if s.get('is_custom', False) else "✅ Optimized schedule"

            msg = (
                f"📅 **Today's Schedule** ({today})\n\n"
                f"**Shift:** {s.get('shift_type', 'unknown').title() if s.get('shift_type') else 'Unknown'}\n"
                f"**Work:** {s.get('work_start', '--')} - {s.get('work_end', '--')}\n"
                f"**Sleep:** {s.get('sleep_start', '--')} - {s.get('sleep_end', '--')}\n\n"
                f"{custom_text}"
            )
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
            return

        const_result = supabase_client.table('constant_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()

        if const_result.data:
            s = const_result.data[0]
            msg = (
                f"📅 **Today's Schedule** (from your constant schedule)\n\n"
                f"**Work:** {s['work_start']} - {s['work_end']}\n"
                f"**Sleep:** {s['sleep_start']} - {s['sleep_end']}\n\n"
                f"Use /change to modify if needed."
            )
            await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.MARKDOWN)
        else:
            await context.bot.send_message(chat_id=chat_id, text="No schedule found. Please use /start to set up your schedule.")

    except Exception as e:
        logger.error(f"Error in send_schedule_message: {e}")
        logger.error(traceback.format_exc())
        await context.bot.send_message(chat_id=chat_id, text="Sorry, couldn't fetch your schedule.")


async def send_report_message(chat_id: int, telegram_user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Send weekly report to a chat."""
    try:
        user_id = get_user_id(telegram_user_id)
        if not user_id:
            await context.bot.send_message(chat_id=chat_id, text="Please use /start first!")
            return

        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=7)

        schedules = supabase_client.table('daily_schedules').select('*')\
            .eq('user_id', user_id)\
            .gte('date', str(start_date))\
            .lte('date', str(end_date))\
            .execute()

        if not schedules.data:
            await context.bot.send_message(chat_id=chat_id, text="Not enough data for a report yet. Check back in a week!")
            return

        total_days = len(schedules.data)
        work_days = sum(1 for s in schedules.data if s.get('shift_type') != 'off')
        off_days = total_days - work_days
        consistent_days = sum(1 for s in schedules.data if not s.get('is_custom', False))
        consistency_score = (consistent_days / total_days * 100) if total_days > 0 else 0

        night_shifts = sum(1 for s in schedules.data if s.get('shift_type') == 'night')
        day_shifts = sum(1 for s in schedules.data if s.get('shift_type') == 'day')
        evening_shifts = sum(1 for s in schedules.data if s.get('shift_type') == 'evening')

        report = (
            f"📊 **Weekly Report**\n"
            f"{start_date} to {end_date}\n\n"
            f"**Overview:**\n"
            f"• Total days: {total_days}\n"
            f"• Work days: {work_days}\n"
            f"• Days off: {off_days}\n\n"
            f"**Shift Breakdown:**\n"
            f"• Night shifts: {night_shifts}\n"
            f"• Day shifts: {day_shifts}\n"
            f"• Evening shifts: {evening_shifts}\n\n"
            f"**Consistency:** {consistency_score:.1f}%\n\n"
        )

        if consistency_score < 50:
            report += "⚠️ Your schedule has been irregular. Use /change to get transition help."
        elif consistency_score < 80:
            report += "👍 Pretty consistent! A few adjustments could help."
        else:
            report += "🌟 Excellent consistency! Your body thanks you."

        await context.bot.send_message(chat_id=chat_id, text=report, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error in send_report_message: {e}")
        logger.error(traceback.format_exc())
        await context.bot.send_message(chat_id=chat_id, text="Sorry, couldn't generate report.")
async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's schedule."""
    await send_schedule_message(update.effective_chat.id, update.effective_user.id, context)

async def dayoff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle day off requests"""
    try:
        user_id = get_user_id(update.effective_user.id)
        if not user_id:
            await update.message.reply_text("Please use /start first!")
            return
        
        today = datetime.now().date()
        
        # Check if schedule exists for today
        existing = supabase_client.table('daily_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('date', str(today))\
            .execute()
        
        if existing.data:
            # Update existing
            supabase_client.table('daily_schedules').update({
                'shift_type': 'off',
                'is_custom': True
            }).eq('id', existing.data[0]['id']).execute()
        else:
            # Insert new
            supabase_client.table('daily_schedules').insert({
                'user_id': user_id,
                'date': str(today),
                'shift_type': 'off',
                'is_custom': True
            }).execute()
        
        keyboard = [
            [InlineKeyboardButton("Resume Tomorrow", callback_data='resume_tomorrow')],
            [InlineKeyboardButton("Keep Day Off", callback_data='keep_off')],
            [InlineKeyboardButton("Back to Work Today", callback_data='back_to_work')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ **Day off noted!**\n\n"
            "I've disabled notifications for today.\n"
            "Rest well! What would you like for tomorrow?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error setting day off: {e}")
        await update.message.reply_text("Sorry, couldn't set day off.")

async def change_shift_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shift change command"""
    try:
        args = context.args
        if not args:
            await update.message.reply_text(
                "📅 **Shift Change Helper**\n\n"
                "Use this command when your schedule changes.\n\n"
                "**Usage:**\n"
                "`/change HH:MM-HH:MM [days]`\n\n"
                "**Examples:**\n"
                "• `/change 23:00-07:00 tomorrow`\n"
                "• `/change 20:00-04:00 in 2 days`\n"
                "• `/change 18:00-02:00 today`\n\n"
                "I'll give you personalized transition advice.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Parse command
        shift_time = args[0]  # "22:00-06:00"
        
        # Parse days
        days_until = 1  # default to tomorrow
        if len(args) >= 2:
            day_text = ' '.join(args[1:]).lower()
            if 'today' in day_text:
                days_until = 0
            elif 'tomorrow' in day_text:
                days_until = 1
            else:
                # Try to extract number
                numbers = re.findall(r'\d+', day_text)
                if numbers:
                    days_until = int(numbers[0])
        
        # Parse new shift times
        if '-' not in shift_time:
            await update.message.reply_text("❌ Invalid format. Use HH:MM-HH:MM")
            return
            
        start_str, end_str = shift_time.split('-')
        new_start = str_to_time(start_str)
        new_end = str_to_time(end_str)
        
        if not new_start or not new_end:
            await update.message.reply_text("❌ Invalid time format. Use HH:MM-HH:MM")
            return
        
        # Get current schedule
        user_id = get_user_id(update.effective_user.id)
        if not user_id:
            await update.message.reply_text("Please use /start first!")
            return
        
        schedule_result = supabase_client.table('constant_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('active', True)\
            .execute()
        
        if not schedule_result.data:
            await update.message.reply_text("No schedule found. Use /start to set up first.")
            return
        
        current = schedule_result.data[0]
        old_start = str_to_time(current['work_start'])
        old_end = str_to_time(current['work_end'])
        
        if not old_start or not old_end:
            await update.message.reply_text("Current schedule is invalid.")
            return
        
        # Generate transition advice
        advice = generate_transition_advice(
            old_start, old_end,
            new_start, new_end,
            days_until
        )
        
        # Ask if they want to update permanently
        keyboard = [
            [InlineKeyboardButton("✅ Update to New Schedule", callback_data=f"update_shift_{shift_time}")],
            [InlineKeyboardButton("❌ Keep Current Schedule", callback_data="keep_current")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            advice + "\n\nWould you like to update your permanent schedule?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Error in change_shift: {e}")
        await update.message.reply_text("Sorry, couldn't process shift change.")
async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show weekly report."""
    await send_report_message(update.effective_chat.id, update.effective_user.id, context)

async def adjust_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirect to change command (for backward compatibility)"""
    await update.message.reply_text(
        "ℹ️ The `/adjust` command has been replaced with `/change`\n"
        "Please use `/change HH:MM-HH:MM` to modify your schedule.",
        parse_mode=ParseMode.MARKDOWN
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries."""
    query = update.callback_query
    await query.answer()

    try:
        if query.data == 'show_schedule':
            await send_schedule_message(query.message.chat_id, query.from_user.id, context)

        elif query.data == 'caffeine_check':
            user_id = get_user_id(query.from_user.id)
            if not user_id:
                await query.message.reply_text("Please use /start first to set up your account!")
                return

            schedule_result = supabase_client.table('constant_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('active', True)\
                .execute()

            if not schedule_result.data:
                await query.message.reply_text("Please set up your schedule first using /start")
                return

            schedule = schedule_result.data[0]
            sleep_start = str_to_time(schedule['sleep_start'])

            if not sleep_start:
                await query.message.reply_text("Sleep schedule not configured properly.")
                return

            now = datetime.now().time()
            sleep_start_dt = datetime.combine(date.today(), sleep_start)
            now_dt = datetime.combine(date.today(), now)

            if sleep_start_dt <= now_dt:
                sleep_start_dt += timedelta(days=1)

            cutoff_dt = sleep_start_dt - timedelta(hours=6)

            if is_within_caffeine_window(sleep_start, now):
                minutes_left = int((cutoff_dt - now_dt).total_seconds() / 60)

                if minutes_left > 0:
                    msg = (
                        f"⚠️ **Caffeine Warning**\n\n"
                        f"You have {minutes_left} minutes left for caffeine today.\n"
                        f"After {cutoff_dt.strftime('%H:%M')}, caffeine will disrupt your sleep.\n\n"
                        f"Last call: {cutoff_dt.strftime('%H:%M')}"
                    )
                else:
                    msg = (
                        f"🚫 **Caffeine window closed**\n\n"
                        f"You're within 6 hours of your sleep time ({schedule['sleep_start']}).\n"
                        f"Coffee now will make falling asleep harder.\n"
                        f"Try herbal tea or water instead."
                    )
            else:
                msg = (
                    f"✅ **Safe for caffeine**\n\n"
                    f"You're outside the 6-hour sleep window.\n"
                    f"Enjoy your coffee! Remember: last call is {cutoff_dt.strftime('%H:%M')}"
                )

            await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

        elif query.data == 'day_off':
            user_id = get_user_id(query.from_user.id)
            if not user_id:
                await query.message.reply_text("Please use /start first!")
                return

            today = datetime.now().date()

            existing = supabase_client.table('daily_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('date', str(today))\
                .execute()

            if existing.data:
                supabase_client.table('daily_schedules').update({
                    'shift_type': 'off',
                    'work_start': None,
                    'work_end': None,
                    'sleep_start': None,
                    'sleep_end': None,
                    'is_custom': True
                }).eq('id', existing.data[0]['id']).execute()
            else:
                supabase_client.table('daily_schedules').insert({
                    'user_id': user_id,
                    'date': str(today),
                    'shift_type': 'off',
                    'work_start': None,
                    'work_end': None,
                    'sleep_start': None,
                    'sleep_end': None,
                    'is_custom': True
                }).execute()

            keyboard = [
                [InlineKeyboardButton("Resume Tomorrow", callback_data='resume_tomorrow')],
                [InlineKeyboardButton("Keep Day Off", callback_data='keep_off')],
                [InlineKeyboardButton("Back to Work Today", callback_data='back_to_work')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.message.reply_text(
                "✅ **Day off noted!**\n\n"
                "I've disabled notifications for today.\n"
                "Rest well! What would you like for tomorrow?",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )

        elif query.data == 'settings':
            keyboard = [
                [InlineKeyboardButton("🔔 Toggle Notifications", callback_data='toggle_notifications')],
                [InlineKeyboardButton("📊 View Report", callback_data='view_report')],
                [InlineKeyboardButton("🔙 Back", callback_data='back_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("⚙️ **Settings**", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

        elif query.data == 'toggle_notifications':
            user_id = get_user_id(query.from_user.id)
            if user_id:
                user = supabase_client.table('users').select('notification_enabled').eq('id', user_id).execute()
                if user.data:
                    current = user.data[0].get('notification_enabled', True)
                    supabase_client.table('users').update({'notification_enabled': not current}).eq('id', user_id).execute()
                    status = "enabled" if not current else "disabled"
                    await query.edit_message_text(f"✅ Notifications {status}!")

        elif query.data == 'view_report':
            await send_report_message(query.message.chat_id, query.from_user.id, context)

        elif query.data == 'back_main':
            keyboard = [
                [InlineKeyboardButton("📅 Today's Schedule", callback_data='show_schedule')],
                [InlineKeyboardButton("☕ Caffeine Check", callback_data='caffeine_check')],
                [InlineKeyboardButton("😴 Day Off", callback_data='day_off')],
                [InlineKeyboardButton("⚙️ Settings", callback_data='settings')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Welcome back! What would you like to do?",
                reply_markup=reply_markup
            )

        elif query.data == 'resume_tomorrow':
            await query.edit_message_text("Great! I'll resume your normal schedule tomorrow.")

        elif query.data == 'keep_off':
            await query.edit_message_text("Okay, I'll keep today as a day off. Use /schedule to update when you're ready.")

        elif query.data == 'back_to_work':
            user_id = get_user_id(query.from_user.id)
            if not user_id:
                await query.edit_message_text("Please use /start first!")
                return

            today = datetime.now().date()

            const_result = supabase_client.table('constant_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('active', True)\
                .execute()

            if const_result.data:
                s = const_result.data[0]

                existing = supabase_client.table('daily_schedules').select('*')\
                    .eq('user_id', user_id)\
                    .eq('date', str(today))\
                    .execute()

                payload = {
                    'user_id': user_id,
                    'date': str(today),
                    'shift_type': s['shift_type'],
                    'work_start': s['work_start'],
                    'work_end': s['work_end'],
                    'sleep_start': s['sleep_start'],
                    'sleep_end': s['sleep_end'],
                    'is_custom': False
                }

                if existing.data:
                    supabase_client.table('daily_schedules').update({
                        'shift_type': s['shift_type'],
                        'work_start': s['work_start'],
                        'work_end': s['work_end'],
                        'sleep_start': s['sleep_start'],
                        'sleep_end': s['sleep_end'],
                        'is_custom': False
                    }).eq('id', existing.data[0]['id']).execute()
                else:
                    supabase_client.table('daily_schedules').insert(payload).execute()

                await query.edit_message_text("✅ Back to work! I've restored your regular schedule for today.")
            else:
                supabase_client.table('daily_schedules').delete()\
                    .eq('user_id', user_id)\
                    .eq('date', str(today))\
                    .execute()
                await query.edit_message_text("✅ Back to work! No constant schedule found, so I removed the day-off override.")

        elif query.data.startswith('update_shift_'):
            shift_time = query.data.replace('update_shift_', '')
            if '-' in shift_time:
                start_str, end_str = shift_time.split('-')

                user_id = get_user_id(query.from_user.id)
                if user_id:
                    work_start = str_to_time(start_str)
                    work_end = str_to_time(end_str)

                    if work_start and work_end:
                        optimized = calculate_optimal_schedule(work_start, work_end)

                        supabase_client.table('constant_schedules').update({'active': False})\
                            .eq('user_id', user_id)\
                            .eq('active', True)\
                            .execute()

                        supabase_client.table('constant_schedules').insert({
                            'user_id': user_id,
                            'work_start': time_to_str(work_start),
                            'work_end': time_to_str(work_end),
                            'sleep_start': optimized['sleep_start'],
                            'sleep_end': optimized['sleep_end'],
                            'coffee_windows': json.dumps(optimized['coffee_windows']),
                            'meal_windows': json.dumps(optimized['meal_windows']),
                            'brightness_windows': json.dumps(optimized['brightness_windows']),
                            'shift_type': optimized['shift_type'],
                            'active': True
                        }).execute()

                        today = datetime.now().date()
                        existing = supabase_client.table('daily_schedules').select('*')\
                            .eq('user_id', user_id)\
                            .eq('date', str(today))\
                            .execute()

                        if existing.data:
                            supabase_client.table('daily_schedules').update({
                                'shift_type': optimized['shift_type'],
                                'work_start': time_to_str(work_start),
                                'work_end': time_to_str(work_end),
                                'sleep_start': optimized['sleep_start'],
                                'sleep_end': optimized['sleep_end'],
                                'is_custom': False
                            }).eq('id', existing.data[0]['id']).execute()
                        else:
                            supabase_client.table('daily_schedules').insert({
                                'user_id': user_id,
                                'date': str(today),
                                'shift_type': optimized['shift_type'],
                                'work_start': time_to_str(work_start),
                                'work_end': time_to_str(work_end),
                                'sleep_start': optimized['sleep_start'],
                                'sleep_end': optimized['sleep_end'],
                                'is_custom': False
                            }).execute()

                        await query.edit_message_text(
                            f"✅ **Schedule Updated!**\n\n"
                            f"New work hours: {time_to_str(work_start)}-{time_to_str(work_end)}\n"
                            f"Sleep: {optimized['sleep_start']}-{optimized['sleep_end']}\n\n"
                            f"Your notifications and today's schedule have been adjusted.",
                            parse_mode=ParseMode.MARKDOWN
                        )
                    else:
                        await query.edit_message_text("❌ Invalid time format.")

        elif query.data == 'keep_current':
            await query.edit_message_text("✅ Keeping your current schedule. Let me know if you need anything else!")

    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        logger.error(traceback.format_exc())
        await query.edit_message_text("Sorry, something went wrong.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

# ==================== MAIN FUNCTION ====================

def main():
    """Start the bot"""
    # Get token
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        logger.error("TELEGRAM_TOKEN not found in environment variables!")
        return
    
    logger.info("Starting Nightflow Bot...")
    
    try:
        # Create application
        application = Application.builder().token(token).build()
        
        # Create conversation handler for onboarding
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(shift_type_handler, pattern='^shift_')],
            states={
                AWAITING_CONSTANT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_constant_schedule)],
                AWAITING_ROTATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rotating_schedule)],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CommandHandler('start', start),
            ],
            allow_reentry=True
        )
                
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("schedule", schedule_command))
        application.add_handler(CommandHandler("caffeine", caffeine_advice_command))
        application.add_handler(CommandHandler("dayoff", dayoff_command))
        application.add_handler(CommandHandler("change", change_shift_command))
        application.add_handler(CommandHandler("report", report_command))
        application.add_handler(CommandHandler("adjust", adjust_command))  # For backward compatibility
        application.add_handler(CommandHandler("cancel", cancel))
        
        # Add conversation handler
        application.add_handler(conv_handler)
        
        # Add callback query handler
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Set up job queue for notifications
        job_queue = application.job_queue
        if job_queue:
            # Check notifications every minute
            job_queue.run_repeating(check_scheduled_notifications, interval=60, first=10)
            logger.info("Notification job scheduled")
        
        # Start bot
        logger.info("Bot is ready and polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()