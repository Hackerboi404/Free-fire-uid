import os
import telebot
import random
import threading
import time
import logging
from flask import Flask, request

# Enable detailed logging for debugging
logging.basicConfig(level=logging.INFO)

# --- CONFIGURATION ---
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    # Log error if token is missing
    logging.error("CRITICAL: BOT_TOKEN environment variable not found.")
else:
    logging.info(f"Bot Token loaded: {TOKEN[:10]}...")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- GAME STATE & STORAGE ---
active_games = {}
lock = threading.Lock() 

class GameSession:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.round = 1
        self.max_rounds = 10
        self.timeout = 30 
        self.scores = {} 
        self.current_movie = ""
        self.is_active = True
        self.timer_thread = None
        self.lock = threading.Lock()
        
        self.all_movies = self.load_movies()
        random.shuffle(self.all_movies)

    def load_movies(self):
        try:
            with open('movies.txt', 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            logging.error("movies.txt not found.")
            return ["Inception"] 

    def get_next_movie(self):
        if not self.all_movies:
            return "Titanic"
        return self.all_movies.pop()

    def shuffle_word(self, word):
        chars = list(word.replace(" ", ""))
        random.shuffle(chars)
        return "".join(chars)

# --- FLASK ROUTES ---

@app.route('/' + TOKEN, methods=['POST'])
def get_message():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        if update:
            bot.process_new_updates([update])
        return "OK", 200
    except Exception as e:
        logging.error(f"Error processing update: {e}")
        return "Error", 500

@app.route("/")
def webhook_info():
    return "Movie Guess Bot is running on Render!", 200

def set_webhook():
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if url:
        webhook_url = f"{url}/{TOKEN}"
        try:
            # Force delete existing webhook to avoid conflicts
            bot.delete_webhook()
            time.sleep(1)
            bot.set_webhook(url=webhook_url)
            logging.info(f"✅ Webhook set successfully to: {webhook_url}")
        except Exception as e:
            logging.error(f"❌ Failed to set webhook: {e}")
    else:
        logging.warning("⚠️ RENDER_EXTERNAL_URL not found. Running in local mode (no webhook).")

# --- BOT HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    logging.info(f"Received /start from user {message.from_user.id}")
    welcome_text = (
        "🎥 *Welcome to Movie Guess Bot!*\n\n"
        "📝 *Rules:*\n"
        "• Guess the movie name from shuffled letters.\n"
        "• First correct answer gets +1 point.\n"
        "• 10 total rounds.\n"
        "• 30 seconds per round.\n"
        "• Hollywood and Bollywood movies included.\n\n"
        "▶️ Use /startgame to begin."
    )
    try:
        bot.reply_to(message, welcome_text, parse_mode='Markdown')
    except Exception as e:
        logging.error(f"Error sending welcome: {e}")

@bot.message_handler(commands=['startgame'])
def start_game(message):
    chat_id = message.chat.id
    logging.info(f"Received /startgame in chat {chat_id}")
    
    with lock:
        if chat_id in active_games:
            bot.reply_to(message, "⚠️ A game is already in progress!")
            return
        
        game = GameSession(chat_id)
        active_games[chat_id] = game

    start_round(game)

@bot.message_handler(func=lambda message: True)
def handle_guess(message):
    if message.text.startswith('/'):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    with lock:
        game = active_games.get(chat_id)
        if not game or not game.is_active:
            return

    with game.lock:
        if not game.is_active:
            return

        user_guess = message.text.strip().lower()
        correct_answer = game.current_movie.lower()

        if user_guess == correct_answer:
            game.is_active = False
            game.scores[user_id] = game.scores.get(user_id, 0) + 1
            
            response = (
                f"✅ *Correct!*\n"
                f"🏆 Winner: {user_name}\n"
                f"🎬 The movie was: *{game.current_movie}*"
            )
            bot.send_message(chat_id, response, parse_mode='Markdown')
            
            time.sleep(2)
            next_round(game)

# --- GAME LOGIC FUNCTIONS ---

def start_round(game):
    if game.round > game.max_rounds:
        end_game(game)
        return

    with game.lock:
        game.is_active = True
        movie = game.get_next_movie()
        game.current_movie = movie
        shuffled = game.shuffle_word(movie)
    
    header = "🎬 *MOVIE GUESS CHALLENGE*"
    body = (
        f"\n🔀 Shuffled Movie:\n\"*{shuffled}*\"\n\n"
        f"⏳ Time Left: {game.timeout} Seconds\n"
        f"💡 First correct answer gets 1 point!\n\n"
        f"🔥 Round {game.round}/{game.max_rounds}"
    )
    
    bot.send_message(game.chat_id, header + body, parse_mode='Markdown')
    t = threading.Thread(target=round_timer, args=(game,))
    t.start()

def round_timer(game):
    time.sleep(game.timeout)
    
    with game.lock:
        if not game.is_active:
            return
        game.is_active = False 

    timeout_msg = (
        f"⌛ *Time's Up!*\n\n"
        f"❌ Nobody guessed it.\n"
        f"🎬 The movie was: *{game.current_movie}*"
    )
    bot.send_message(game.chat_id, timeout_msg, parse_mode='Markdown')
    
    time.sleep(2)
    next_round(game)

def next_round(game):
    game.round += 1
    start_round(game)

def end_game(game):
    chat_id = game.chat_id
    sorted_scores = sorted(game.scores.items(), key=lambda item: item[1], reverse=True)
    
    if not sorted_scores:
        final_msg = "🏁 *Game Over!*\n\nNo one scored any points. Better luck next time!"
    else:
        leaderboard_text = "🏆 *LEADERBOARD*\n\n"
        for rank, (uid, score) in enumerate(sorted_scores, 1):
            try:
                member = bot.get_chat_member(chat_id, uid)
                name = member.user.first_name
            except:
                name = "User"
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉"
            leaderboard_text += f"{medal} {name}: {score} pts\n"

        final_msg = (
            f"🏁 *Game Over!*\n\n"
            f"{leaderboard_text}\n"
            f"🎉 Congratulations to the winners!\n"
            f"▶️ Play again with /startgame"
        )

    bot.send_message(chat_id, final_msg, parse_mode='Markdown')
    
    with lock:
        if chat_id in active_games:
            del active_games[chat_id]

if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 5000))
    # Use threaded=True to handle requests properly
    app.run(host='0.0.0.0', port=port, threaded=True)
