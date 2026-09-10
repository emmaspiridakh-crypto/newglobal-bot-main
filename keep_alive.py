import threading

from flask import Flask

import config

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is alive."


def _run():
    # host 0.0.0.0 so Render can actually reach it
    app.run(host="0.0.0.0", port=config.KEEP_ALIVE_PORT)


def keep_alive() -> None:
    """Starts the Flask app in a background thread so it doesn't block the bot."""
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
