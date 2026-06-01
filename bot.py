import logging
import os
import asyncio
from telegram import Update, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes
)
from telegram.error import TelegramError
from database import Database
from flask_app import run_flask
import threading

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "YOUR_TELEGRAM_USER_ID"))

db = Database()

# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def is_authorized(user_id: int) -> bool:
    return user_id == OWNER_ID or db.is_authorized(user_id)

async def get_target_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply se ya argument se target user nikalo"""
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user
    if context.args:
        try:
            user_id = int(context.args[0])
            chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
            return chat_member.user
        except Exception:
            await update.message.reply_text("❌ User nahi mila. Reply karo ya valid User ID do.")
            return None
    await update.message.reply_text("❌ Kisi message ko reply karo ya User ID do.")
    return None

async def check_auth(update: Update) -> bool:
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("🚫 Aapko ye command use karne ka permission nahi hai!")
        return False
    return True

async def is_group(update: Update) -> bool:
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Ye command sirf groups mein kaam karta hai.")
        return False
    return True

# ─────────────────────────────────────────────
# OWNER COMMANDS
# ─────────────────────────────────────────────

async def auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Ye command sirf owner use kar sakta hai!")
        return
    target = await get_target_user(update, context)
    if not target:
        return
    if target.id == OWNER_ID:
        await update.message.reply_text("Aap khud owner hain!")
        return
    db.add_authorized(target.id, target.full_name)
    await update.message.reply_text(f"✅ {target.mention_html()} ko authorize kar diya gaya!", parse_mode="HTML")

async def unauth_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Ye command sirf owner use kar sakta hai!")
        return
    target = await get_target_user(update, context)
    if not target:
        return
    db.remove_authorized(target.id)
    await update.message.reply_text(f"✅ {target.mention_html()} ki authorization hata di gayi!", parse_mode="HTML")

async def authlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🚫 Ye command sirf owner use kar sakta hai!")
        return
    auth_list = db.get_authorized_list()
    if not auth_list:
        await update.message.reply_text("📋 Koi authorized user nahi hai abhi.")
        return
    text = "📋 <b>Authorized Users:</b>\n"
    for uid, name in auth_list:
        text += f"• {name} (<code>{uid}</code>)\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ─────────────────────────────────────────────
# BAN / UNBAN
# ─────────────────────────────────────────────

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "No reason"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        db.log_action(update.effective_chat.id, target.id, "ban", update.effective_user.id, reason)
        await update.message.reply_text(
            f"🔨 {target.mention_html()} ko <b>ban</b> kar diya gaya!\n📝 Reason: {reason}",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, target.id, only_if_banned=True)
        db.log_action(update.effective_chat.id, target.id, "unban", update.effective_user.id)
        await update.message.reply_text(f"✅ {target.mention_html()} ka ban hata diya gaya!", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────────
# MUTE / UNMUTE
# ─────────────────────────────────────────────

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "No reason"
    try:
        perms = ChatPermissions(
            can_send_messages=False, can_send_polls=False,
            can_send_other_messages=False, can_add_web_page_previews=False,
            can_change_info=False, can_invite_users=False, can_pin_messages=False
        )
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        db.log_action(update.effective_chat.id, target.id, "mute", update.effective_user.id, reason)
        await update.message.reply_text(
            f"🔇 {target.mention_html()} ko <b>mute</b> kar diya gaya!\n📝 Reason: {reason}",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    try:
        perms = ChatPermissions(
            can_send_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=False, can_invite_users=True, can_pin_messages=False
        )
        await context.bot.restrict_chat_member(update.effective_chat.id, target.id, perms)
        db.log_action(update.effective_chat.id, target.id, "unmute", update.effective_user.id)
        await update.message.reply_text(f"🔊 {target.mention_html()} ka mute hata diya gaya!", parse_mode="HTML")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────────
# KICK
# ─────────────────────────────────────────────

async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "No reason"
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, target.id)
        await asyncio.sleep(1)
        await context.bot.unban_chat_member(update.effective_chat.id, target.id)
        db.log_action(update.effective_chat.id, target.id, "kick", update.effective_user.id, reason)
        await update.message.reply_text(
            f"👢 {target.mention_html()} ko <b>kick</b> kar diya gaya!\n📝 Reason: {reason}",
            parse_mode="HTML"
        )
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────────
# PUNISH / UNPUNISH
# ─────────────────────────────────────────────

async def punish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    reason = " ".join(context.args[1:]) if context.args and len(context.args) > 1 else "No reason"
    db.punish_user(update.effective_chat.id, target.id)
    db.log_action(update.effective_chat.id, target.id, "punish", update.effective_user.id, reason)
    await update.message.reply_text(
        f"⚠️ {target.mention_html()} ko <b>punish</b> kar diya gaya!\n"
        f"📝 Reason: {reason}\n"
        f"🗑 Ab inke saare messages automatically delete hote rahenge jab tak <code>/unpunish</code> na ho.",
        parse_mode="HTML"
    )

async def unpunish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    target = await get_target_user(update, context)
    if not target: return
    db.unpunish_user(update.effective_chat.id, target.id)
    db.log_action(update.effective_chat.id, target.id, "unpunish", update.effective_user.id)
    await update.message.reply_text(
        f"✅ {target.mention_html()} ki punishment hata di gayi! Ab inke messages delete nahi honge.",
        parse_mode="HTML"
    )

async def auto_delete_punished(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Punished users ke messages auto delete karo"""
    if not update.effective_chat or not update.effective_user:
        return
    if update.effective_chat.type == "private":
        return
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if db.is_punished(chat_id, user_id):
        try:
            await update.message.delete()
        except TelegramError:
            pass

# ─────────────────────────────────────────────
# PURGE
# ─────────────────────────────────────────────

async def purge_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Jis message se purge karna ho usse reply karo.")
        return
    start_id = update.message.reply_to_message.message_id
    end_id = update.message.message_id
    deleted = 0
    failed = 0
    msg_ids = list(range(start_id, end_id + 1))
    # Telegram allows bulk delete in batches of 100
    for i in range(0, len(msg_ids), 100):
        batch = msg_ids[i:i+100]
        try:
            await context.bot.delete_messages(update.effective_chat.id, batch)
            deleted += len(batch)
        except TelegramError:
            for mid in batch:
                try:
                    await context.bot.delete_message(update.effective_chat.id, mid)
                    deleted += 1
                except TelegramError:
                    failed += 1
    notice = await context.bot.send_message(
        update.effective_chat.id,
        f"🗑 <b>{deleted}</b> messages purge kar diye gaye!",
        parse_mode="HTML"
    )
    await asyncio.sleep(3)
    try:
        await notice.delete()
    except TelegramError:
        pass

# ─────────────────────────────────────────────
# PIN
# ─────────────────────────────────────────────

async def pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Jis message ko pin karna ho usse reply karo.")
        return
    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id,
            disable_notification=False
        )
        await update.message.reply_text("📌 Message pin kar diya gaya!")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def unpin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    try:
        if update.message.reply_to_message:
            await context.bot.unpin_chat_message(
                update.effective_chat.id,
                update.message.reply_to_message.message_id
            )
        else:
            await context.bot.unpin_chat_message(update.effective_chat.id)
        await update.message.reply_text("📌 Message unpin kar diya gaya!")
    except TelegramError as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ─────────────────────────────────────────────
# LOCK / UNLOCK
# ─────────────────────────────────────────────

LOCK_TYPES = {
    "text": "can_send_messages",
    "media": "can_send_other_messages",
    "photo": "can_send_other_messages",
    "video": "can_send_other_messages",
    "sticker": "can_send_other_messages",
    "gif": "can_send_other_messages",
    "poll": "can_send_polls",
    "link": "can_add_web_page_previews",
    "invite": "can_invite_users",
    "pin": "can_pin_messages",
    "info": "can_change_info",
}

async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    if not context.args:
        lock_list = "\n".join([f"• <code>{k}</code>" for k in LOCK_TYPES.keys()])
        await update.message.reply_text(
            f"🔒 <b>Lock karne ke types:</b>\n{lock_list}\n\nUsage: <code>/lock text</code>",
            parse_mode="HTML"
        )
        return
    lock_type = context.args[0].lower()
    if lock_type == "all":
        db.set_lock(update.effective_chat.id, "all", True)
        perms = ChatPermissions(
            can_send_messages=False, can_send_polls=False,
            can_send_other_messages=False, can_add_web_page_previews=False,
            can_change_info=False, can_invite_users=False, can_pin_messages=False
        )
        try:
            await context.bot.set_chat_permissions(update.effective_chat.id, perms)
            await update.message.reply_text("🔒 Group mein sab kuch lock kar diya gaya!")
        except TelegramError as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return
    if lock_type not in LOCK_TYPES:
        await update.message.reply_text(f"❌ Invalid lock type. Use /lock to see all types.")
        return
    db.set_lock(update.effective_chat.id, lock_type, True)
    await update.message.reply_text(f"🔒 <b>{lock_type}</b> lock kar diya gaya!", parse_mode="HTML")

async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    if not context.args:
        await update.message.reply_text("Usage: <code>/unlock text</code> ya <code>/unlock all</code>", parse_mode="HTML")
        return
    lock_type = context.args[0].lower()
    if lock_type == "all":
        db.set_lock(update.effective_chat.id, "all", False)
        perms = ChatPermissions(
            can_send_messages=True, can_send_polls=True,
            can_send_other_messages=True, can_add_web_page_previews=True,
            can_change_info=False, can_invite_users=True, can_pin_messages=False
        )
        try:
            await context.bot.set_chat_permissions(update.effective_chat.id, perms)
            await update.message.reply_text("🔓 Group mein sab kuch unlock kar diya gaya!")
        except TelegramError as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return
    if lock_type not in LOCK_TYPES:
        await update.message.reply_text("❌ Invalid lock type.")
        return
    db.set_lock(update.effective_chat.id, lock_type, False)
    await update.message.reply_text(f"🔓 <b>{lock_type}</b> unlock kar diya gaya!", parse_mode="HTML")

async def locks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_auth(update): return
    if not await is_group(update): return
    locks = db.get_locks(update.effective_chat.id)
    if not locks:
        await update.message.reply_text("🔓 Is group mein koi lock active nahi hai.")
        return
    text = "🔒 <b>Active Locks:</b>\n"
    for ltype in locks:
        text += f"• <code>{ltype}</code>\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def enforce_locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lock hone par messages delete karo"""
    if not update.effective_chat or not update.effective_user:
        return
    if update.effective_chat.type == "private":
        return
    user_id = update.effective_user.id
    if is_authorized(user_id):
        return  # Admins/authorized log bypass kar sakte hain
    chat_id = update.effective_chat.id
    msg = update.message
    if not msg:
        return
    locks = db.get_locks(chat_id)
    if not locks:
        return
    should_delete = False
    if "all" in locks:
        should_delete = True
    elif "text" in locks and msg.text and not msg.entities:
        should_delete = True
    elif "link" in locks and msg.entities:
        for ent in msg.entities:
            if ent.type in ("url", "text_link"):
                should_delete = True
                break
    elif any(t in locks for t in ["media", "photo", "video", "sticker", "gif"]):
        if msg.photo or msg.video or msg.sticker or msg.animation or msg.document:
            should_delete = True
    elif "poll" in locks and msg.poll:
        should_delete = True
    if should_delete:
        try:
            await msg.delete()
        except TelegramError:
            pass

# ─────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 <b>Group Management Bot</b> active hai!\n\n"
        "<code>/help</code> — sabhi commands dekho",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 <b>Group Management Bot — Commands</b>

<b>👑 Owner Only:</b>
/auth [reply/id] — User authorize karo
/unauth [reply/id] — Authorization hatao
/authlist — Authorized users dekho

<b>🔨 Moderation:</b>
/ban [reply/id] [reason] — User ban karo
/unban [reply/id] — Ban hatao
/mute [reply/id] [reason] — User mute karo
/unmute [reply/id] — Mute hatao
/kick [reply/id] [reason] — User kick karo

<b>⚠️ Punishment:</b>
/punish [reply/id] [reason] — Messages auto-delete honge
/unpunish [reply/id] — Punishment hatao

<b>🗑 Purge:</b>
/purge — Reply karo jis message se purge karna ho

<b>📌 Pin:</b>
/pin — Reply karo message ko pin karne ke liye
/unpin — Pinned message unpin karo

<b>🔒 Lock:</b>
/lock [type/all] — Lock karo (text, media, poll, link, sticker, gif, invite, pin, info)
/unlock [type/all] — Unlock karo
/locks — Active locks dekho
"""
    await update.message.reply_text(text, parse_mode="HTML")

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Owner commands
    app.add_handler(CommandHandler("auth", auth_command))
    app.add_handler(CommandHandler("unauth", unauth_command))
    app.add_handler(CommandHandler("authlist", authlist_command))

    # Moderation
    app.add_handler(CommandHandler("ban", ban_command))
    app.add_handler(CommandHandler("unban", unban_command))
    app.add_handler(CommandHandler("mute", mute_command))
    app.add_handler(CommandHandler("unmute", unmute_command))
    app.add_handler(CommandHandler("kick", kick_command))

    # Punish
    app.add_handler(CommandHandler("punish", punish_command))
    app.add_handler(CommandHandler("unpunish", unpunish_command))

    # Purge, Pin
    app.add_handler(CommandHandler("purge", purge_command))
    app.add_handler(CommandHandler("pin", pin_command))
    app.add_handler(CommandHandler("unpin", unpin_command))

    # Lock
    app.add_handler(CommandHandler("lock", lock_command))
    app.add_handler(CommandHandler("unlock", unlock_command))
    app.add_handler(CommandHandler("locks", locks_command))

    # Info
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))

    # Message handlers (punish + lock enforcement) — order matters
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, auto_delete_punished), group=1)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, enforce_locks), group=2)

    # Flask ko alag thread mein chalao — polling ke bilkul pehle
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    logger.info("Bot start ho raha hai...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
