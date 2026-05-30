import os
import telebot
import random
import threading
import time
import logging
from flask import Flask, request

# --- CONFIGURATION ---
# Load token from environment variable (Render standard)
TOKEN = os.environ.get('BOT_TOKEN')
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable not found.")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- GAME STATE & STORAGE ---
# Stores active game sessions. Key: Chat ID, Value: GameSession Object
active_games = {}
lock = threading.Lock() # Prevent race conditions during state updates

class GameSession:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.round = 1
        self.max_rounds = 10
        self.timeout = 30 # seconds
        self.scores = {}  # Key: User ID, Value: Score
        self.current_movie = ""
        self.is_active = True
        self.timer_thread = None
        self.lock = threading.Lock() # Lock for this specific game instance
        
        # Load movies
        self.all_movies = self.load_movies()
        random.shuffle(self.all_movies) # Shuffle initial pool

    def load_movies(self):
        try:
            with open('movies.txt', 'r', encoding='utf-8') as f:
                # Read lines, strip whitespace, filter empty
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            logging.error("movies.txt not found.")
            return ["Inception"] # Fallback

    def get_next_movie(self):
        if not self.all_movies:
            # Fallback if we run out of movies (unlikely with hundreds)
            return "Titanic"
        return self.all_movies.pop()

    def shuffle_word(self, word):
        # Remove spaces for shuffling, preserve logic
        chars = list(word.replace(" ", ""))
        random.shuffle(chars)
        return "".join(chars)

# --- UTILITIES ---

def escape_markdown(text):
    """Basic helper to escape reserved chars if needed, 
    though Telegram's MarkdownV2 is complex. 
    We will use basic Markdown for simplicity and compatibility."""
    return text

# --- BOT HANDLERS ---

@app.route('/' + TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def webhook_info():
    return "Movie Guess Bot is running!", 200

def set_webhook():
    # Render provides a public URL via RENDER_EXTERNAL_URL
    url = os.environ.get('RENDER_EXTERNAL_URL')
    if url:
        webhook_url = f"{url}/{TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        print(f"Webhook set to: {webhook_url}")
    else:
        print("Running locally, skipping webhook set.")

@bot.message_handler(commands=['start'])
def send_welcome(message):
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
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['startgame'])
def start_game(message):
    chat_id = message.chat.id
    
    # Check if game is already running
    with lock:
        if chat_id in active_games:
            bot.reply_to(message, "⚠️ A game is already in progress!")
            return
        
        # Initialize new game
        game = GameSession(chat_id)
        active_games[chat_id] = game

    start_round(game)

@bot.message_handler(func=lambda message: True)
def handle_guess(message):
    # Ignore commands in the main handler
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
        # If the round is already over (checked flag inside lock), ignore
        if not game.is_active:
            return

        # Validate Answer
        user_guess = message.text.strip().lower()
        correct_answer = game.current_movie.lower()

        if user_guess == correct_answer:
            # Correct Answer!
            game.is_active = False # Stop round immediately
            game.scores[user_id] = game.scores.get(user_id, 0) + 1
            
            # Cancel the timeout timer if it's pending
            # Note: The timer function checks 'is_active', so it will exit gracefully
            
            response = (
                f"✅ *Correct!*\n"
                f"🏆 Winner: {user_name}\n"
                f"🎬 The movie was: *{game.current_movie}*"
            )
            bot.send_message(chat_id, response, parse_mode='Markdown')
            
            # Wait a moment then next round
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

    # Start Timer in a separate thread
    t = threading.Thread(target=round_timer, args=(game,))
    t.start()

def round_timer(game):
    time.sleep(game.timeout)
    
    # Check if round is still active (might have been answered)
    with game.lock:
        if not game.is_active:
            return
        game.is_active = False # Round over due to timeout

    # Timeout reached
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
    
    # Sort leaderboard by score descending
    sorted_scores = sorted(game.scores.items(), key=lambda item: item[1], reverse=True)
    
    if not sorted_scores:
        final_msg = "🏁 *Game Over!*\n\nNo one scored any points. Better luck next time!"
    else:
        leaderboard_text = "🏆 *LEADERBOARD*\n\n"
        winner_id, winner_score = sorted_scores[0]
        winner_name = "Unknown"
        
        # Attempt to get winner name (might need to fetch from DB if not cached, 
        # but we used display name in scoring logic implicitly. 
        # Actually we stored ID in scores. Let's fetch chat member for top 3.)
        
        # Simple text output
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
    
    # Clean up
    with lock:
        if chat_id in active_games:
            del active_games[chat_id]

# --- MAIN ENTRY ---

if __name__ == '__main__':
    # Setup webhook on startup
    set_webhook()
    # Run Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
