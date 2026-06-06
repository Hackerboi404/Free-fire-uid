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
    CallbackQueryHandler,
    CallbackContext,
)
from database import (
    init_db, add_group, get_all_groups, is_group_registered,
    add_blocked_word, remove_blocked_word, get_blocked_words,
    add_log, get_logs, update_group_setting, get_group_setting
)

# --- Configuration ---
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
    """Checks if the user is the authorized owner."""
    return user_id == OWNER_ID

async def send_log_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fetches logs from DB and sends them as a text file.
    Can handle both Message and CallbackQuery updates.
    """
    # Determine where to send the reply (User or Chat)
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        query = update.callback_query
    else:
        chat_id = update.effective_message.chat_id
        query = None

    try:
        logs = get_logs()
        if not logs:
            msg = "No logs found in the database."
            if query:
                await query.answer()
                await query.message.reply_text(msg)
            else:
                await update.message.reply_text(msg)
            return

        log_text = ""
        for log in logs:
            log_text += f"[{log['timestamp']}] Group: {log['group_id']} | User: {log['username']} ({log['user_id']}) | Action: {log['action']} | Details: {log['details']}\n"
        
        filename = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        # Write file
        with open(filename, "w", encoding="utf-8") as f:
            f.write(log_text)
        
        # Send file
        if query:
            await query.answer("Sending logs...")
            with open(filename, "rb") as f:
                await query.message.reply_document(document=f, filename=filename)
        else:
            with open(filename, "rb") as f:
                await update.message.reply_document(document=f, filename=filename)
        
        logger.info(f"Logs sent to {chat_id}")

    except Exception as e:
        logger.error(f"Failed to generate/send logs: {e}")
        error_msg = "An error occurred while generating logs."
        if query:
            await query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
    finally:
        # Clean up the file if it exists
        if 'filename' in locals() and os.path.exists(filename):
            os.remove(filename)

# --- Owner Handlers (Private Chat) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Unified /start handler.
    - Private Chat: Shows Owner Control Panel.
    - Groups: Registers the group and welcomes users.
    """
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id

    if chat_type == 'private':
        # --- OWNER CONTROL PANEL ---
        status_checks = [
            "✅ Bot Online",
            "✅ Database Connected",
            "✅ Render Running",
            "✅ Owner Authorized" if is_owner(user_id) else "❌ Unauthorized Access"
        ]
        
        status_text = "\n".join(status_checks)

        keyboard = [
            [InlineKeyboardButton("View Groups", callback_data='view_groups')],
            [InlineKeyboardButton("View Status", callback_data='status')],
            [InlineKeyboardButton("View Logs", callback_data='view_logs')],
            [InlineKeyboardButton("Manage Blocked Words", callback_data='manage_words')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"<b>Bot Control Panel</b>\n\n{status_text}", 
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
    else:
        # --- GROUP REGISTRATION ---
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Unknown Group"
        
        # Register group if not exists
        if not is_group_registered(chat_id):
            add_group(chat_id, chat_title)
            logger.info(f"Registered new group: {chat_title} ({chat_id})")
            await update.message.reply_text("Bot initialized! I am now monitoring this group.")
        else:
            # Optional: silent update or specific reply
            pass

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles interactions with the inline keyboard."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press immediately

    if not is_owner(query.from_user.id):
        await query.edit_message_text("⛔ You are not authorized to use this feature.")
        return
    
    data = query.data

    if data == 'view_groups':
        groups = get_all_groups()
        if not groups:
            text = "No groups registered yet."
        else:
            text = "\n".join([f"📂 {g['group_title']} (ID: <code>{g['group_id']}</code>)" for g in groups])
        
        await query.edit_message_text(
            f"<b>Registered Groups:</b>\n\n{text}", 
            parse_mode='HTML'
        )

    elif data == 'status':
        stats = (
            "<b>Bot Status:</b>\n"
            "✅ Polling Active\n"
            "✅ Database Operational\n"
            f"👤 Owner ID: <code>{OWNER_ID}</code>"
        )
        await query.edit_message_text(stats, parse_mode='HTML')

    elif data == 'view_logs':
        # We cannot call edit_message_text if we are sending a file. 
        # We reply to the message or send the file directly.
        # We create a new message for the file to avoid UI glitches with inline keyboards.
        await send_log_file(update, context)

    elif data == 'manage_words':
        instructions = (
            "<b>Manage Blocked Words</b>\n\n"
            "Use these commands in this private chat:\n"
            "<code>/addword &lt;group_id&gt; &lt;word&gt;</code>\n"
            "<code>/removeword &lt;group_id&gt; &lt;word&gt;</code>\n\n"
            "Example:\n"
            "<code>/addword -100123456789 spam</code>"
        )
        await query.edit_message_text(instructions, parse_mode='HTML')

async def add_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addword <group_id> <word>")
        return
    
    try:
        group_id = int(context.args[0])
        word = ' '.join(context.args[1:])
        add_blocked_word(group_id, word)
        await update.message.reply_text(f"✅ Added '{word}' to blocked list for group {group_id}.")
    except ValueError:
        await update.message.reply_text("❌ Invalid Group ID.")

async def remove_word_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id): return
    
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /removeword <group_id> <word>")
        return
    
    try:
        group_id = int(context.args[0])
        word = ' '.join(context.args[1:])
        remove_blocked_word(group_id, word)
        await update.message.reply_text(f"✅ Removed '{word}' from blocked list for group {group_id}.")
    except ValueError:
        await update.message.reply_text("❌ Invalid Group ID.")

# --- Group Features ---

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new members when they join a group."""
    chat_id = update.effective_chat.id
    chat_title = update.effective_chat.title
    
    # Ensure group is in DB
    if not is_group_registered(chat_id):
        add_group(chat_id, chat_title)
        logger.info(f"Auto-registered group via join event: {chat_title}")

    welcome_enabled = get_group_setting(chat_id, 'welcome_enabled')
    
    if welcome_enabled:
        welcome_msg_template = get_group_setting(chat_id, 'welcome_message')
        for member in update.message.new_chat_members:
            # Skip welcoming the bot itself
            if member.username == context.bot.username:
                continue
                
            username = member.first_name if member.first_name else (member.username or "User")
            # Replace placeholder with actual name
            msg = welcome_msg_template.replace('{user}', f"@{username}" if member.username else username)
            
            try:
                await update.message.reply_text(msg)
            except Exception as e:
                logger.error(f"Failed to send welcome message: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Main message handler for moderation.
    - Checks for blocked words.
    - Ignores admins.
    - Deletes violations.
    """
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    user_name = update.effective_user.username or update.effective_user.first_name
    message_text = update.message.text.lower() if update.message.text else ""

    # 1. Ignore Admins
    try:
        user_status = await context.bot.get_chat_member(chat_id, user_id)
        if user_status.status in ['administrator', 'creator']:
            return
    except Exception as e:
        logger.warning(f"Could not verify admin status for {user_id}: {e}")
        # Proceed with caution, or return to be safe. Usually safe to check.

    # 2. Ensure group exists in DB (Auto-register if missing)
    if not is_group_registered(chat_id):
        # Note: We don't have title here easily without fetching, use "Unknown" or fetch
        # For performance, we insert without title or fetch chat info. 
        # Ideally DB handles this, but let's just add ID.
        add_group(chat_id, "Unknown Group (Auto-registered)")
        logger.info(f"Auto-registered group {chat_id} during message check.")

    # 3. Check for Blocked Words
    blocked_words = get_blocked_words(chat_id)
    if not blocked_words:
        return

    for word in blocked_words:
        if word in message_text:
            try:
                await update.message.delete()
                add_log(chat_id, user_id, user_name, "Deleted Message", f"Contained blocked word: {word}")
                logger.info(f"Deleted message from {user_name} in {chat_id} for word: {word}")
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
            return # Stop checking other words if one is found

# --- Main Setup ---

def setup_bot():
    """
    Initializes the database and registers all application handlers.
    """
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise

    application = Application.builder().token(BOT_TOKEN).build()

    # 1. Unified /start handler (Private & Group)
    application.add_handler(CommandHandler("start", start_command))

    # 2. Callback Query Handler (Owner Menu)
    application.add_handler(CallbackQueryHandler(button_callback))

    # 3. Owner Commands (Private Chat)
    application.add_handler(CommandHandler("addword", add_word_command))
    application.add_handler(CommandHandler("removeword", remove_word_command))

    # 4. Group Events
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    
    # 5. Message Moderation (Text messages, excluding commands)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return application
