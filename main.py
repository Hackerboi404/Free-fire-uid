import os
import time
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types
from dotenv import load_dotenv

# --- Configuration ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("Error: BOT_TOKEN not found in .env file")
    exit()

bot = telebot.TeleBot(BOT_TOKEN)

# --- Constants & Mapping ---
# Mapping Region Codes (User Selection) -> Garena Region Codes for URL
REGION_MAP = {
    "BD": "BD",  # Bangladesh
    "IND": "IN", # India
    "SG": "SG",  # Singapore
    "TH": "TH",  # Thailand
    "ID": "ID",  # Indonesia
    "BR": "BR",  # Brazil
    "CIS": "RU", # Russia/CIS (Uses RU code on stats site usually, or specific endpoint)
    "EU": "EU",  # Europe
    "ME": "NA"   # Middle East (Often grouped under NA or specific EU endpoints, using NA here as fallback)
}

# Headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

# --- Helper Functions ---

def get_region_keyboard():
    """Creates the inline keyboard for region selection."""
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = []
    for code, name in REGION_MAP.items():
        # Button label shows the code, callback data sends the code
        buttons.append(types.InlineKeyboardButton(text=code, callback_data=f"reg_{code}"))
    
    # Add buttons in rows
    markup.add(*buttons)
    return markup

def fetch_player_stats(uid, region_code):
    """
    Scrapes stats.garena.com for player data.
    No API Key required.
    """
    # Garena Stats URL Format
    # Note: If this specific URL structure changes, we update the base URL.
    # Base URL varies slightly by region, but usually follows this pattern or redirects.
    url = f"https://stats.garena.com/game/ff?uid={uid}&lang=en_US&region={region_code}"
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None, "Server error or invalid region."

        soup = BeautifulSoup(response.content, 'lxml')

        # The site usually renders data in a specific JSON structure or HTML divs.
        # For stats.garena.com, we often look for specific classes or the JSON script.
        # Since scraping DOMs is fragile, we look for common indicators.
        
        # Check if UID is invalid (usually the page says "Player not found" or similar)
        if "player not found" in response.text.lower() or "invalid uid" in response.text.lower():
             return None, "Invalid UID or Player does not exist."

        # Let's try to parse the HTML structure (Simulated based on common FF stat site layouts)
        # Note: Real-world scraping often requires inspecting the live site elements.
        # We will use a generic extractor approach.
        
        data = {}
        
        # 1. Player Name
        name_tag = soup.find('span', class_='player-name') or soup.find('h1', class_='name')
        data['name'] = name_tag.text.strip() if name_tag else "Unknown"

        # 2. Level
        lvl_tag = soup.find('span', class_='level') or soup.find('div', class_='lvl')
        data['level'] = lvl_tag.text.strip().replace('LV ', '') if lvl_tag else "0"

        # 3. Likes / Respect
        like_tag = soup.find('div', class_='likes') or soup.find('span', class_='like-count')
        data['likes'] = like_tag.text.strip() if like_tag else "0"
        
        # 4. Guild
        guild_tag = soup.find('div', class_='guild-name') or soup.find('span', class_='guild')
        data['guild'] = guild_tag.text.strip() if guild_tag else "No Guild"

        # 5. Ranks (Usually found in specific stat cards)
        # This is the trickiest part as classes change. We'll do a broad search for rank text.
        # Often BR Rank is displayed as a title or specific badge.
        data['br_rank'] = "Unranked"
        data['cs_rank'] = "Unranked"
        
        # Attempt to find rank via text content if specific classes fail
        all_text = soup.get_text()
        if "Heroic" in all_text: data['br_rank'] = "Heroic"
        elif "Master" in all_text: data['br_rank'] = "Master"
        # Add more logic as needed based on live inspection
        
        return data, None

    except Exception as e:
        return None, f"Scraping Error: {str(e)}"

# --- Bot Handlers ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "🔥 <b>Welcome to the Ultimate FF UID Checker!</b>\n\n"
        "I can fetch player stats without any API keys.\n"
        "Just click the button below to get started!"
    )
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("🚀 Check UID", callback_data="start_check")
    markup.add(btn)
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['uid'])
def ask_uid(message):
    msg = bot.send_message(message.chat.id, "🎮 <b>Send Free Fire UID</b>", parse_mode="HTML")
    bot.register_next_step_handler(msg, process_uid_step)

def process_uid_step(message):
    uid = message.text.strip()
    
    # Basic validation (FF UIDs are usually numeric, 8-12 digits)
    if not uid.isdigit() or len(uid) < 5:
        bot.reply_to(message, "❌ <b>Invalid UID!</b>\nPlease send a valid numeric UID.", parse_mode="HTML")
        return

    # Store UID temporarily in user step data (or database in production)
    # We pass it via the callback query data logic or cache. 
    # For simplicity, we ask for Region now and store UID in a simple dict if needed, 
    # but simpler is to ask region immediately.
    
    msg = bot.reply_to(message, f"✅ UID Received: <code>{uid}</code>\n\n🌍 <b>Select Region:</b>", parse_mode="HTML", reply_markup=get_region_keyboard())
    
    # We need to link this UID with the callback. 
    # Since Telebot handlers are separate, we can use a temporary cache dictionary.
    user_cache[message.chat.id] = uid

# Simple in-memory cache for UID during flow
user_cache = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith("reg_"))
def callback_region(call):
    region_code = call.data.split("_")[1]
    chat_id = call.message.chat.id
    
    # Retrieve UID
    uid = user_cache.get(chat_id)
    
    if not uid:
        bot.answer_callback_query(call.id, "Session expired. Please send /uid again.")
        return
    
    # Acknowledge button press
    bot.answer_callback_query(call.id, "Fetching data... ⏳")
    
    # Send loading message
    loading_msg = bot.send_message(chat_id, "🔄 <b>Connecting to server...</b>\n⚙️ Extracting player data...", parse_mode="HTML")
    
    # Fetch Data
    data, error = fetch_player_stats(uid, REGION_MAP[region_code])
    
    # Delete loading message
    try:
        bot.delete_message(chat_id, loading_msg.message_id)
    except:
        pass
        
    if error:
        bot.send_message(chat_id, f"❌ <b>Error:</b> {error}\n\nTry again with /uid", parse_mode="HTML")
    else:
        # Format the stylish response
        response_text = (
            "🎮 <b>FREE FIRE PLAYER INFO</b>\n\n"
            f"👤 <b>Name:</b> {data.get('name', 'Unknown')}\n"
            f"🆔 <b>UID:</b> {uid}\n"
            f"🌍 <b>Region:</b> {region_code}\n"
            f"⭐ <b>Level:</b> {data.get('level', '0')}\n"
            f"❤️ <b>Likes:</b> {data.get('likes', '0')}\n"
            f"🏆 <b>BR Rank:</b> {data.get('br_rank', 'N/A')}\n"
            f"⚔️ <b>CS Rank:</b> {data.get('cs_rank', 'N/A')}\n"
            f"👥 <b>Guild:</b> {data.get('guild', 'None')}\n\n"
            f"✨ <b>Powered by @YourBotUsername</b>"
        )
        
        # Optional: If you found an avatar image URL
        # img_url = data.get('avatar')
        # if img_url:
        #     bot.send_photo(chat_id, img_url, caption=response_text, parse_mode="HTML")
        # else:
        bot.send_message(chat_id, response_text, parse_mode="HTML")
    
    # Clean up cache
    if chat_id in user_cache:
        del user_cache[chat_id]

# --- Start Bot ---
print("Bot is running...")
bot.infinity_polling()
