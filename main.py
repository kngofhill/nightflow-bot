import os
import logging
from datetime import datetime, time, timedelta, date
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import supabase
import os
from flask import Flask
import threading

# Add this - it keeps Render happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=os.getenv('PORT', 8080))

# Start web server in background
threading.Thread(target=run_web, daemon=True).start()

# Rest of your bot code continues here...
# Load environment variables
load_dotenv()

# Setup logging with more detail for production
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Add this for production - log when bot starts
logger.info("Starting Nightflow Bot...")

# Initialize Supabase
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase_client = supabase.create_client(supabase_url, supabase_key)

# Conversation states
AWAITING_CONSTANT, AWAITING_ROTATING = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    try:
        # Check if user exists
        result = supabase_client.table('users').select('*').eq('telegram_id', user.id).execute()
        
        if not result.data:
            # New user - start onboarding
            keyboard = [
                [InlineKeyboardButton("Constant Schedule", callback_data='shift_constant')],
                [InlineKeyboardButton("Rotating Schedule", callback_data='shift_rotating')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🌙 Welcome to Nightflow, {user.first_name}!\n\n"
                "I'll help you optimize your shift work schedule. "
                "First, tell me about your shift pattern:",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                "Welcome back! Use /schedule to see today's plan.\n"
                "Commands:\n"
                "/schedule - View today's schedule\n"
                "/dayoff - Take a day off\n"
                "/adjust - Adjust your schedule\n"
                "/report - View weekly report"
            )
    except Exception as e:
        logger.error(f"Error in start: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again.")

async def shift_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shift type selection"""
    query = update.callback_query
    await query.answer()
    
    try:
        user_id = update.effective_user.id
        shift_type = 'constant' if 'constant' in query.data else 'rotating'
        
        # Save user to database
        supabase_client.table('users').upsert({
            'telegram_id': user_id,
            'shift_type': shift_type,
            'username': update.effective_user.username,
            'first_name': update.effective_user.first_name
        }).execute()
        
        if shift_type == 'constant':
            await query.edit_message_text(
                "Great! Let's set up your constant schedule.\n\n"
                "Please enter your typical work hours (format: HH:MM-HH:MM)\n"
                "Example for night shift: 22:00-06:00\n"
                "Example for day shift: 09:00-17:00"
            )
            return AWAITING_CONSTANT
        else:
            await query.edit_message_text(
                "Let's set up your rotating schedule.\n\n"
                "Please describe your rotation pattern.\n"
                "Example: '2 days, 2 nights, 4 off'\n"
                "Or: 'Dupont schedule'"
            )
            return AWAITING_ROTATING
    except Exception as e:
        logger.error(f"Error in shift_type_handler: {e}")
        await query.edit_message_text("Sorry, something went wrong. Please try /start again.")
        return ConversationHandler.END

async def save_constant_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save constant schedule"""
    try:
        # Parse work hours
        work_hours = update.message.text.strip()
        start_str, end_str = work_hours.split('-')
        
        work_start = datetime.strptime(start_str.strip(), "%H:%M").time()
        work_end = datetime.strptime(end_str.strip(), "%H:%M").time()
        
        # Get user
        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("User not found. Please use /start again.")
            return ConversationHandler.END
            
        user_id = user_result.data[0]['id']
        
        # Calculate optimal schedule
        optimized = optimize_schedule(work_start, work_end)
        
        # Save to database
        supabase_client.table('constant_schedules').insert({
            'user_id': user_id,
            'work_start': str(work_start),
            'work_end': str(work_end),
            'sleep_start': str(optimized['sleep_start']),
            'sleep_end': str(optimized['sleep_end']),
            'coffee_windows': optimized['coffee_windows'],
            'meal_windows': optimized['meal_windows'],
            'brightness_windows': optimized['brightness_windows'],
            'active': True
        }).execute()
        
        # Generate daily schedule for today
        today = datetime.now().date()
        
        # Determine shift type
        if work_start.hour >= 20 or work_start.hour <= 5:
            shift_type = 'night'
        elif work_start.hour >= 12 and work_start.hour < 20:
            shift_type = 'evening'
        else:
            shift_type = 'day'
        
        supabase_client.table('daily_schedules').insert({
            'user_id': user_id,
            'date': str(today),
            'shift_type': shift_type,
            'work_start': str(work_start),
            'work_end': str(work_end),
            'sleep_start': str(optimized['sleep_start']),
            'sleep_end': str(optimized['sleep_end']),
            'is_custom': False
        }).execute()
        
        # Format coffee times for display
        coffee_times = [c['start'] for c in optimized['coffee_windows']]
        meal_times = [m['start'] for m in optimized['meal_windows']]
        
        # Show schedule to user
        schedule_msg = (
            f"✅ Your optimized schedule is ready!\n\n"
            f"Work: {work_start.strftime('%H:%M')} - {work_end.strftime('%H:%M')}\n"
            f"Sleep: {optimized['sleep_start'].strftime('%H:%M')} - {optimized['sleep_end'].strftime('%H:%M')}\n\n"
            f"Coffee times: {', '.join(coffee_times)}\n"
            f"Meal times: {', '.join(meal_times)}\n\n"
            f"I'll notify you before each important time!\n"
            f"Use /dayoff if you need a break."
        )
        
        await update.message.reply_text(schedule_msg)
        
    except ValueError as e:
        logger.error(f"Value error in save_constant_schedule: {e}")
        await update.message.reply_text(
            "Sorry, I couldn't understand that format. Please use HH:MM-HH:MM\n"
            "Example: 22:00-06:00"
        )
        return AWAITING_CONSTANT
    except Exception as e:
        logger.error(f"Error saving schedule: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        return ConversationHandler.END
    
    return ConversationHandler.END

async def save_rotating_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save rotating schedule (simplified version)"""
    try:
        pattern = update.message.text.strip()
        
        # Get user
        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("User not found. Please use /start again.")
            return ConversationHandler.END
            
        user_id = user_result.data[0]['id']
        
        # Save pattern (simplified - just store description for now)
        supabase_client.table('rotating_patterns').insert({
            'user_id': user_id,
            'pattern_name': 'custom',
            'cycle_days': 7,
            'shifts': {'description': pattern}
        }).execute()
        
        await update.message.reply_text(
            f"✅ Rotating schedule saved!\n\n"
            f"Pattern: {pattern}\n\n"
            f"I'll help you optimize your transitions between shifts.\n"
            f"Use /schedule to see today's plan."
        )
        
    except Exception as e:
        logger.error(f"Error saving rotating schedule: {e}")
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
    
    return ConversationHandler.END

def optimize_schedule(work_start, work_end):
    """Optimize sleep and activity times"""
    
    # Convert to datetime for calculations
    work_start_dt = datetime.combine(datetime.today(), work_start)
    work_end_dt = datetime.combine(datetime.today(), work_end)
    
    # If work end is before work start, it's next day
    if work_end_dt <= work_start_dt:
        work_end_dt += timedelta(days=1)
    
    # Calculate optimal sleep
    if work_start.hour >= 20 or work_start.hour <= 5:  # Night shift
        # Sleep right after work
        sleep_start = work_end_dt.time()
        # Wake up 1 hour before work
        wake_time = work_start_dt - timedelta(hours=1)
        sleep_end = wake_time.time()
    else:  # Day shift
        sleep_start = time(22, 0)  # 10 PM
        sleep_end = time(6, 0)     # 6 AM
    
    # Coffee windows (formatted as strings)
    coffee_windows = [
        {"start": (work_start_dt - timedelta(minutes=30)).strftime("%H:%M"), "type": "pre_work"},
        {"start": (work_start_dt + timedelta(hours=4)).strftime("%H:%M"), "type": "mid_shift"}
    ]
    
    # Meal windows
    meal_windows = [
        {"start": (work_start_dt - timedelta(hours=1)).strftime("%H:%M"), "type": "pre_work"},
        {"start": (work_start_dt + timedelta(hours=6)).strftime("%H:%M"), "type": "post_work"}
    ]
    
    # Brightness windows
    brightness_windows = [
        {"start": (work_start_dt - timedelta(hours=1)).strftime("%H:%M"), "level": "high"},
        {"start": (work_start_dt + timedelta(hours=8)).strftime("%H:%M"), "level": "low"}
    ]
    
    return {
        "sleep_start": sleep_start,
        "sleep_end": sleep_end,
        "coffee_windows": coffee_windows,
        "meal_windows": meal_windows,
        "brightness_windows": brightness_windows
    }

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's schedule"""
    try:
        # Get user
        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("Please use /start first to set up your account!")
            return
        
        user_id = user_result.data[0]['id']
        today = datetime.now().date()
        
        # Get today's schedule
        schedule_result = supabase_client.table('daily_schedules').select('*')\
            .eq('user_id', user_id)\
            .eq('date', str(today))\
            .execute()
        
        if schedule_result.data:
            s = schedule_result.data[0]
            custom_text = "⚠️ Custom schedule" if s.get('is_custom', False) else "✅ Optimized schedule"
            
            msg = (
                f"📅 Today's Schedule ({today})\n\n"
                f"Shift: {s['shift_type'].title()}\n"
                f"Work: {s['work_start']} - {s['work_end']}\n"
                f"Sleep: {s['sleep_start']} - {s['sleep_end']}\n\n"
                f"{custom_text}"
            )
            
            await update.message.reply_text(msg)
        else:
            # Try to get constant schedule and generate for today
            const_result = supabase_client.table('constant_schedules').select('*')\
                .eq('user_id', user_id)\
                .eq('active', True)\
                .execute()
            
            if const_result.data:
                s = const_result.data[0]
                msg = (
                    f"📅 Today's Schedule (from your constant schedule)\n\n"
                    f"Work: {s['work_start']} - {s['work_end']}\n"
                    f"Sleep: {s['sleep_start']} - {s['sleep_end']}\n\n"
                    f"Use /adjust to modify if needed."
                )
                await update.message.reply_text(msg)
            else:
                msg = "No schedule found. Please use /start to set up your schedule."
                await update.message.reply_text(msg)
        
    except Exception as e:
        logger.error(f"Error showing schedule: {e}")
        await update.message.reply_text("Sorry, couldn't fetch your schedule.")

async def dayoff_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle day off requests"""
    try:
        # Get user
        user_result = supabase_client.table('users').select('id').eq('telegram_id', update.effective_user.id).execute()
        if not user_result.data:
            await update.message.reply_text("Please use /start first!")
            return
        
        user_id = user_result.data[0]['id']
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
            [InlineKeyboardButton("Keep Day Off", callback_data='keep_off')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "✅ Day off noted! I've disabled notifications for today.\n"
            "Rest well! What would you like for tomorrow?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error setting day off: {e}")
        await update.message.reply_text("Sorry, couldn't set day off.")

async def adjust_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle adjust schedule command"""
    await update.message.reply_text(
        "You can adjust your schedule in the following ways:\n\n"
        "1. To change sleep time: /sleep HH:MM-HH:MM\n"
        "2. To add coffee time: /coffee HH:MM\n"
        "3. To reset to optimized: /reset\n\n"
        "Example: /sleep 23:00-07:00"
    )

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show weekly report"""
    await update.message.reply_text(
        "📊 Weekly Report Feature Coming Soon!\n\n"
        "This will show your schedule adherence and progress."
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel conversation"""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'resume_tomorrow':
        await query.edit_message_text("Great! I'll resume your normal schedule tomorrow.")
    elif query.data == 'keep_off':
        await query.edit_message_text("Okay, I'll keep today as a day off. Use /schedule to update when you're ready.")

def main():
    """Start the bot"""
    # Get token
    token = os.getenv('TELEGRAM_TOKEN')
    if not token:
        print("ERROR: TELEGRAM_TOKEN not found in .env file!")
        print("Please make sure your .env file contains: TELEGRAM_TOKEN=your_bot_token_here")
        return
    
    print(f"Using token: {token[:10]}...")  # Print first 10 chars for verification
    
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
            fallbacks=[CommandHandler('cancel', cancel)]
            per_message=True  # Add this line
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("schedule", schedule_command))
        application.add_handler(CommandHandler("dayoff", dayoff_command))
        application.add_handler(CommandHandler("adjust", adjust_command))
        application.add_handler(CommandHandler("report", report_command))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(conv_handler)
        application.add_handler(CallbackQueryHandler(handle_callback))
        
        # Start bot
        print("🤖 Nightflow Bot is starting...")
        print("Press Ctrl+C to stop")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        print(f"ERROR starting bot: {e}")
        logger.error(f"Failed to start bot: {e}")

if __name__ == '__main__':
    main()