import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types
import time

# ==========================================
# ⚠️ YAHAN APNA BOT TOKEN DALAIN ⚠️
# ==========================================
BOT_TOKEN = "8715170557:AAEHZ9mfr93Hy2sVBh9ElD9qpTHXGYvFryc" 

# Bot ko initialize karein
bot = telebot.TeleBot(BOT_TOKEN)

# --- Constants & Mapping ---
# Region Codes mapping (Button Text -> Garena URL Code)
REGION_MAP = {
    "BD": "BD",  # Bangladesh
    "IND": "IN", # India
    "SG": "SG",  # Singapore
    "TH": "TH",  # Thailand
    "ID": "ID",  # Indonesia
    "BR": "BR",  # Brazil
    "CIS": "RU", # Russia/CIS
    "EU": "EU",  # Europe
    "ME": "NA"   # Middle East (Fallback)
}

# Browser jaisa dikhane ke liye Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# --- Helper Functions ---

def get_region_keyboard():
    """Region select karne ke liye buttons banata hai."""
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for code in REGION_MAP.keys():
        buttons.append(types.InlineKeyboardButton(text=code, callback_data=f"reg_{code}"))
    markup.add(*buttons)
    return markup

def fetch_player_stats(uid, region_code):
    """
    Stats site se data scrape karta hai bina API key ke.
    """
    # Garena Stats URL
    url = f"https://stats.garena.com/game/ff?uid={uid}&lang=en_US&region={region_code}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        
        # Agar site nahi khul rahi
        if response.status_code != 200:
            return None, "Server busy ho sakta hai. Thodi der baad try karein."

        soup = BeautifulSoup(response.content, 'lxml')
        page_text = response.text.lower()

        # Invalid UID check
        if "player not found" in page_text or "invalid" in page_text or "tidak ditemukan" in page_text:
             return None, "❌ Invalid UID ya account exist nahi karta."

        # Data Extraction (Yahan classes change ho sakti hain agar site update kare)
        data = {}
        
        # 1. Name Extraction
        name_tag = soup.find('span', class_='player-name') or soup.find('h1', class_='name')
        data['name'] = name_tag.text.strip() if name_tag else "Unknown Player"

        # 2. Level Extraction
        lvl_tag = soup.find('span', class_='level') or soup.find('div', class_='lvl')
        data['level'] = lvl_tag.text.strip().replace('LV ', '') if lvl_tag else "0"

        # 3. Likes Extraction
        like_tag = soup.find('div', class_='likes') or soup.find('span', class_='like-count')
        data['likes'] = like_tag.text.strip() if like_tag else "0"
        
        # 4. Guild Extraction
        guild_tag = soup.find('div', class_='guild-name') or soup.find('span', class_='guild')
        data['guild'] = guild_tag.text.strip() if guild_tag else "No Guild"

        # 5. Rank Extraction (Logic based)
        # Note: Scraping ranks is hard without specific classes. Hum generic logic use karenge.
        data['br_rank'] = "Unranked"
        data['cs_rank'] = "Unranked"
        
        full_text = soup.get_text()
        if "heroic" in full_text.lower(): data['br_rank'] = "Heroic"
        elif "grandmaster" in full_text.lower(): data['br_rank'] = "Grandmaster"
        elif "master" in full_text.lower(): data['br_rank'] = "Master"
        
        return data, None

    except Exception as e:
        return None, f"Error: {str(e)}"

# --- Bot Commands ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "🔥 <b>Welcome to FF UID Checker!</b>\n\n"
        "Main aapke liye player details la sakta hu bina kisi API key ke.\n"
        "Start karne ke liye neeche button dabayein."
    )
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🚀 Check UID", callback_data="start_check")
    markup.add(btn)
    bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['uid'])
def ask_uid(message):
    msg = bot.send_message(message.chat.id, "🎮 <b>Please send Free Fire UID</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_uid_step)

def process_uid_step(message):
    uid = message.text.strip()
    
    # Validation: Sirf numbers hona chahiye
    if not uid.isdigit() or len(uid) < 5:
        bot.reply_to(message, "❌ <b>Galat UID!</b>\nSirf numbers dalein (Jaise: 12345678).", parse_mode="HTML")
        return

    # UID save karein aur Region puchein
    user_cache[message.chat.id] = uid
    bot.reply_to(message, f"✅ UID: <code>{uid}</code>\n\n🌍 <b>Ab Region Select Karein:</b>", parse_mode="HTML", reply_markup=get_region_keyboard())

# Temporary storage for UIDs
user_cache = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith("reg_"))
def callback_region(call):
    region_code = call.data.split("_")[1]
    chat_id = call.message.chat.id
    
    # UID lo cache se
    uid = user_cache.get(chat_id)
    
    if not uid:
        bot.answer_callback_query(call.id, "Time out! Dobara /uid bhejein.")
        return
    
    bot.answer_callback_query(call.id, "Data aa raha hai... ⏳")
    
    # Loading message
    loading_msg = bot.send_message(chat_id, "🔄 <b>Server se data la raha hu...</b>\n⏳ Please wait...", parse_mode="HTML")
    
    # Data Fetch
    data, error = fetch_player_stats(uid, REGION_MAP[region_code])
    
    # Loading message hatao
    try:
        bot.delete_message(chat_id, loading_msg.message_id)
    except:
        pass
        
    if error:
        bot.send_message(chat_id, f"❌ <b>Problem aayi:</b>\n{error}", parse_mode="HTML")
    else:
        # Stylish Response
        msg = (
            "🎮 <b>FREE FIRE PLAYER INFO</b>\n\n"
            f"👤 <b>Name:</b> {data.get('name')}\n"
            f"🆔 <b>UID:</b> {uid}\n"
            f"🌍 <b>Region:</b> {region_code}\n"
            f"⭐ <b>Level:</b> {data.get('level')}\n"
            f"❤️ <b>Likes:</b> {data.get('likes')}\n"
            f"🏆 <b>BR Rank:</b> {data.get('br_rank')}\n"
            f"⚔️ <b>CS Rank:</b> {data.get('cs_rank')}\n"
            f"👥 <b>Guild:</b> {data.get('guild')}\n\n"
            "✨ <b>Powered by @YourBot</b>"
        )
        bot.send_message(chat_id, msg, parse_mode="HTML")
    
    # Cache clean
    if chat_id in user_cache:
        del user_cache[chat_id]

# Bot Start
print("Bot shuru ho gaya hai! Token check kar ra hu...")
if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
    print("❌ ERROR: Apna token code mein dhoona bhool gaye!")
else:
    print("✅ Bot Chal Raha Hai...")
    bot.infinity_polling()
