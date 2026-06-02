import os
import logging
import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
# Render Environment Variables se token lenge
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
PORT = int(os.environ.get("PORT", "10000"))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL") 

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP (Thread-safe for Async) ---
DB_PATH = 'bot_data.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS auth_users (user_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS punished_users (chat_id INTEGER, user_id INTEGER, PRIMARY KEY (chat_id, user_id))''')
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database init error: {e}")

# Helper to run blocking sqlite calls in async
executor = ThreadPoolExecutor(max_workers=4)

async def run_db_query(query, args=(), fetchone=False, commit=False):
    def _query():
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, args)
        result = None
        if fetchone:
            result = cursor.fetchone()
        else:
            result = cursor.fetchall()
        if commit:
            conn.commit()
        conn.close()
        return result
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, _query)

# --- AUTH HELPERS ---
async def is_authorized(user_id):
    if user_id == OWNER_ID:
        return True
    result = await run_db_query("SELECT 1 FROM auth_users WHERE user_id=?", (user_id,), fetchone=True)
    return result is not None

async def add_auth(user_id):
    try:
        await run_db_query("INSERT INTO auth_users (user_id) VALUES (?)", (user_id,), commit=True)
        return True
    except sqlite3.IntegrityError:
        return False

async def remove_auth(user_id):
    await run_db_query("DELETE FROM auth_users WHERE user_id=?", (user_id,), commit=True)

async def is_punished(chat_id, user_id):
    result = await run_db_query("SELECT 1 FROM punished_users WHERE chat_id=? AND user_id=?", (chat_id, user_id), fetchone=True)
    return result is not None

async def punish_user_db(chat_id, user_id):
    try:
        await run_db_query("INSERT INTO punished_users (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id), commit=True)
    except:
        pass

async def unpunish_user_db(chat_id, user_id):
    await run_db_query("DELETE FROM punished_users WHERE chat_id=? AND user_id=?", (chat_id, user_id), commit=True)

# --- PERMISSION CHECK ---
async def check_permission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return False
    user_id = update.effective_user.id
    if await is_authorized(user_id):
        return True
    try:
        await update.message.reply_text("⛔ Aapko is command chalane ki anumati nahi hai.")
    except Exception:
        pass
    return False

# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot active hai! Commands use karne ke liye authorized rahiye.")

# Auth
async def auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /auth <user_id>")
        return
    try:
        uid = int(context.args[0])
        await add_auth(uid)
        await update.message.reply_text(f"✅ User {uid} ko authorize kar diya gaya.")
    except ValueError:
        await update.message.reply_text("Invalid ID.")

async def unauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if not context.args:
        return
    try:
        uid = int(context.args[0])
        await remove_auth(uid)
        await update.message.reply_text(f"❌ User {uid} ki authority hatayi gayi.")
    except ValueError:
        pass

# Ban/Unban
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            await update.message.reply_text(f"🚫 {user.first_name} ko ban kar diya gaya.")
        except Exception as e:
            logger.error(f"Ban error: {e}")
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("Kis user ko ban karna hai? Us message ko reply karein.")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        uid = int(context.args[0])
        await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=uid)
        await update.message.reply_text(f"✅ User {uid} ko unban kar diya.")
    except Exception as e:
        logger.error(f"Unban error: {e}")
        await update.message.reply_text("User ID galat hai ya error aayi.")

# Mute/Unmute
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        # V21 compatible permissions
        permissions = ChatPermissions(can_send_messages=False)
        try:
            await context.bot.restrict_chat_member(chat_id=update.effective_chat.id, user_id=user.id, permissions=permissions)
            await update.message.reply_text(f"🔇 {user.first_name} ko mute kar diya gaya.")
        except Exception as e:
            logger.error(f"Mute error: {e}")
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        # V21 compatible permissions (Enable all)
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True, # Stickers/GIFs
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        try:
            await context.bot.restrict_chat_member(chat_id=update.effective_chat.id, user_id=user.id, permissions=permissions)
            await update.message.reply_text(f"🔊 {user.first_name} ko unmute kar diya gaya.")
        except Exception as e:
            logger.error(f"Unmute error: {e}")
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

# Kick
async def kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            await context.bot.unban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            await update.message.reply_text(f"👢 {user.first_name} ko kick kar diya gaya.")
        except Exception as e:
            logger.error(f"Kick error: {e}")
            await update.message.reply_text(f"Error: {e}")
    else:
        await update.message.reply_text("User ko reply karein.")

# Punish/Unpunish
async def punish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        await punish_user_db(chat_id, user.id)
        await update.message.reply_text(f"👻 {user.first_name} ko punish kar diya. Ab se uske msgs delete honge.")
    else:
        await update.message.reply_text("User ko reply karein.")

async def unpunish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        chat_id = update.effective_chat.id
        await unpunish_user_db(chat_id, user.id)
        await update.message.reply_text(f"🔓 {user.first_name} ko unpunish kar diya.")
    else:
        await update.message.reply_text("User ko reply karein.")

# Auto-Delete Handler
async def auto_delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text and update.message.text.startswith('/'):
        return

    if update.effective_user and update.effective_chat:
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if await is_punished(chat_id, user_id):
            try:
                await update.message.delete()
            except Exception:
                pass 

# Purge
async def purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id
        
        # Delete command message first
        try:
            await update.message.delete()
        except:
            pass
        
        deleted_count = 0
        # Loop backwards for safety and order
        for msg_id in range(end_id, start_id - 1, -1):
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
                deleted_count += 1
            except Exception:
                pass
        
        try:
            msg = await context.bot.send_message(update.effective_chat.id, f"🗑️ {deleted_count} messages delete kiye gaye.")
            await asyncio.sleep(3)
            await msg.delete()
        except Exception:
            pass

# Pin
async def pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if update.message.reply_to_message:
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id, 
                message_id=update.message.reply_to_message.message_id, 
                disable_notification=True
            )
            await update.message.reply_text("📌 Message pin kar diya gaya.")
        except Exception as e:
            logger.error(f"Pin error: {e}")
            await update.message.reply_text(f"Error: {e}")

# Lock / Unlock (V21 Compatible)
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    if not context.args:
        await update.message.reply_text("Usage: /lock <text|media|stickers|all>")
        return
    
    item = context.args[0].lower()
    # Default: All Permissions True
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True, # Covers stickers/gifs
        can_add_web_page_previews=True
    )
    
    if item == "text":
        perms.can_send_messages = False
    elif item == "media":
        perms.can_send_audios = False
        perms.can_send_documents = False
        perms.can_send_photos = False
        perms.can_send_videos = False
        perms.can_send_video_notes = False
        perms.can_send_voice_notes = False
    elif item == "stickers":
        perms.can_send_other_messages = False
    elif item == "all":
        perms = ChatPermissions(can_send_messages=False)
    else:
        await update.message.reply_text("Invalid item. Use: text, media, stickers, all")
        return

    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=perms)
        await update.message.reply_text(f"🔒 Group ko {item} ke liye lock kar diya gaya.")
    except Exception as e:
        logger.error(f"Lock error: {e}")
        await update.message.reply_text(f"Error: {e}")

async def unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_permission(update, context): return
    perms = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    try:
        await context.bot.set_chat_permissions(chat_id=update.effective_chat.id, permissions=perms)
        await update.message.reply_text("🔓 Group ko unlock kar diya gaya.")
    except Exception as e:
        logger.error(f"Unlock error: {e}")
        await update.message.reply_text(f"Error: {e}")

# --- FLASK APP & WEBHOOK ---
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram se data receive karne ke liye endpoint."""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_json(force=True)
        update = Update.de_json(json_string, application.bot)
        if update:
            application.update_queue.put(update)
        return "OK"
    else:
        return "Invalid Content-Type", 403

# --- MAIN EXECUTION ---
def run_webhook():
    """Flask aur Webhook setup."""
    init_db()
    
    # Create Application
    global application
    application = Application.builder().token(BOT_TOKEN).build()

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("auth", auth))
    application.add_handler(CommandHandler("unauth", unauth))
    application.add_handler(CommandHandler("ban", ban))
    application.add_handler(CommandHandler("unban", unban))
    application.add_handler(CommandHandler("mute", mute))
    application.add_handler(CommandHandler("unmute", unmute))
    application.add_handler(CommandHandler("kick", kick))
    application.add_handler(CommandHandler("punish", punish))
    application.add_handler(CommandHandler("unpunish", unpunish))
    application.add_handler(CommandHandler("purge", purge))
    application.add_handler(CommandHandler("pin", pin))
    application.add_handler(CommandHandler("lock", lock))
    application.add_handler(CommandHandler("unlock", unlock))

    # Auto Delete Handler
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, auto_delete_handler), group=-1)

    # Initialize Application (Internal queue start karega)
    application.initialize()

    # Start Webhook
    if WEBHOOK_URL:
        logger.info(f"Setting webhook to: {WEBHOOK_URL}")
        application.bot.set_webhook(url=WEBHOOK_URL)
        # Updater start karna zaroori hai webhook mode mein nahi, 
        # lekin application startup ensure karein.
        application.start()
    else:
        logger.warning("WEBHOOK_URL not found. Running without webhook set.")
    
    # Flask ko run karein
    logger.info(f"Starting Flask server on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)

if __name__ == "__main__":
    run_webhook()
