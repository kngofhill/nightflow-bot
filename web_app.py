import os
import threading
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Nightflow Bot is running!"

@app.route("/health")
def health():
    return "OK", 200

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_web_server():
    thread = threading.Thread(target=run_web, daemon=True)
    thread.start()