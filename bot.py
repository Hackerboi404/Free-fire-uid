import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackContext,
)
from database import (
    init_db, add_group, get_all_groups, is_group_registered,
    add_blocked_word, remove_blocked_word, get_blocked_words,
    add_log, get_logs, update_group_setting, get_group_setting
)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
OWNER_ID = int(os.environ.get('OWNER_ID'))

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions ---

def is_owner(user_id):
    return user_id == OWNER_ID

async def send_log_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Helper to send logs as a text file to the owner."""
    logs = get_logs()
    if not logs:
        await update.message.reply_text("No logs found.")
        return

    log_text = ""
    for log in logs:
        log_text += f"[{log['timestamp']}] Group: {log['group_id']} | User: {log['username']} ({log['user_id']}) | Action: {log['action']} | Details: {log['details']}\n"
    
    filename = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(log_text)
    
    with open(filename, "rb") as f:
        await update.message.reply_document(document=f, filename=filename)
    
    # Clean up
    os.remove(filename)

# --- Owner Handlers (Private Chat) ---

async def start_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("You are not authorized to use this bot.")
        return

    keyboard = [
        [InlineKeyboardButton("View Registered Groups", callback_data='view_groups')],
        [InlineKeyboardButton("View Bot Status", callback_data='status')],
        [InlineKeyboardButton("View Logs", callback_data='view_logs')],
        [InlineKeyboardButton("Manage Blocked Words", callback_data='manage_words')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Owner Control Panel:", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_owner(query.from_user.id):
        await query.answer("Unauthorized.")
        return
    
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat_id

    if data == 'view_groups':
        groups = get_all_groups()
        if not groups:
            text = "No groups registered yet."
        else:
            text = "\n".join([f"- {g['group_title']} (ID: {g['group_id']})" for g in groups])
        await query.message.reply_text(f"Registered Groups:\n{text}")

    elif data == 'status':
        await query.message.reply_text("Bot is running and operational.")

    elif data == 'view_logs':
        await send_log_file(query, context)

    elif data == 'manage_words':
        # This is a simplified flow. In a real app, you might ask for group ID first.
        # Here we assume management implies viewing all or by specific group logic.
        await query.message.reply_text("To manage blocked words, use /addword <group_id> <word> and /removeword <group_id> <word>")

async def add_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addword <group_id> <word>")
        return
    
    try:
        group_id = int(context.args[0])
        word = ' '.join(context.args[1:])
        add_blocked_word(group_id, word)
        await update.message.reply_text(f"Added '{word}' to blocked list for group {group_id}.")
    except ValueError:
        await update.message.reply_text("Invalid Group ID.")

async def remove_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removeword <group_id> <word>")
        return
    
    try:
        group_id = int(context.args[0])
        word = ' '.join(context.args[1:])
        remove_blocked_word(group_id, word)
        await update.message.reply_text(f"Removed '{word}' from blocked list for group {group_id}.")
    except ValueError:
        await update.message.reply_text("Invalid Group ID.")

# --- Group Handlers ---

async def group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called when bot is added to a group or /start is sent in a group."""
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    
    # Register group if not exists
    if not is_group_registered(chat_id):
        add_group(chat_id, chat_title)
        await update.message.reply_text("Bot initialized! I will now moderate this group based on global settings.")

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members."""
    chat_id = update.effective_chat.id
    
    # Ensure group is in DB
    if not is_group_registered(chat_id):
        group_start(update, context)

    welcome_enabled = get_group_setting(chat_id, 'welcome_enabled')
    
    if welcome_enabled:
        welcome_msg_template = get_group_setting(chat_id, 'welcome_message')
        for member in update.message.new_chat_members:
            username = member.first_name if member.first_name else member.username
            msg = welcome_msg_template.replace('{user}', f"@{username}" if member.username else username)
            await update.message.reply_text(msg)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler for moderation."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name
    message_text = update.message.text.lower() if update.message.text else ""

    # Ignore admins
    user_status = await context.bot.get_chat_member(chat_id, user_id)
    if user_status.status in ['administrator', 'creator']:
        return

    # Ensure group exists
    if not is_group_registered(chat_id):
        add_group(chat_id, update.effective_chat.title)

    # Check for blocked words
    blocked_words = get_blocked_words(chat_id)
    for word in blocked_words:
        if word in message_text:
            try:
                await update.message.delete()
                add_log(chat_id, user_id, user_name, "Deleted Message", f"Contained blocked word: {word}")
                logger.info(f"Deleted message from {user_name} in {chat_id} for word: {word}")
                
                # Optional: Send warning
                # await context.bot.send_message(chat_id, f"{user_name}, your message contained a blocked word.")
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
            return # Stop checking other words if one is found

    # Anti-Spam: Check message frequency (Simple implementation per user)
    # A more robust solution would use Redis or a dictionary with timestamps in memory
    # Here we just log it for the "Log Moderation Actions" requirement
    if len(message_text) > 0: 
        # Placeholder for anti-spam logic
        pass

# --- Main Setup ---

def setup_bot():
    """Initialize and return the Application."""
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()

    # Owner Commands
    application.add_handler(CommandHandler("start", start_owner))
    application.add_handler(CommandHandler("addword", add_word_command))
    application.add_handler(CommandHandler("removeword", remove_word_command))
    application.add_handler(CommandHandler("logs", start_owner)) # Reuse start for menu or specific logs handler
    
    # Callback Query Handler
    application.add_handler(CallbackQueryHandler(button_callback))

    # Group Commands & Events
    application.add_handler(CommandHandler("start", group_start))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application
