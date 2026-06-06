import os
import logging
from flask import Flask
from bot import setup_bot

# Initialize Flask App
app = Flask(__name__)

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Bot Application globally
bot_app = None

def run_bot():
    """Starts the Telegram bot polling."""
    global bot_app
    if not bot_app:
        bot_app = setup_bot()
        logger.info("Starting Telegram Bot Polling...")
        bot_app.run_polling(drop_pending_updates=True)

@app.route('/')
def health_check():
    """Health check route for Render."""
    return "Bot Running"

# For Webhook mode (optional, but polling is easier for dynamic IP)
# @app.route('/webhook', methods=['POST'])
# def webhook():
#     flask_request = request.get_json(force=True)
#     update = Update.de_json(flask_request, bot_app.bot)
#     bot_app.process_update(update)
#     return "OK"

if __name__ == '__main__':
    # Start the bot in a separate thread or logic if using Webhooks
    # Since Render wants a web server, we start bot polling, but we must also run Flask.
    # However, run_polling() is blocking.
    # A common pattern for simple bots on Render is to use Webhooks, but for simplicity 
    # and reliability with Python-telegram-bot, we usually separate concerns.
    # 
    # For this specific requirement, we will use Threading to run Flask and Bot together,
    # OR rely on the fact that Render allows worker types (e.g. "Worker") instead of "Web Service".
    # 
    # Since you asked for "Flask server" and "PORT binding":
    
    from threading import Thread
    
    # Run bot in a separate thread so Flask can listen on the port
    bot_thread = Thread(target=run_bot)
    bot_thread.start()
    
    # Get port from environment variable (Render specific)
    port = int(os.environ.get('PORT', 5000))
    
    # Run Flask
    app.run(host='0.0.0.0', port=port)
