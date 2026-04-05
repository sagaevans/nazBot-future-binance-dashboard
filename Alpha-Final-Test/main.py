# main.py
import signal
import sys
import threading
import time
import logging
from app import run_web
from bot_logic import run_bot, shutdown_bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('main')

# Global shutdown event
shutdown_event = threading.Event()

def signal_handler(signum, frame):
    logger.info("🚨 Received shutdown signal. Stopping bot gracefully...")
    shutdown_event.set()
    shutdown_bot()  # Signal bot_logic to stop

def main():
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Memulai nazBot Alpha 4.0 PRO System...")

    # Bot thread (non-daemon to allow clean shutdown)
    bot_thread = threading.Thread(target=run_bot, args=(shutdown_event,), name="BotEngine")
    bot_thread.start()

    # Flask runs in a daemon thread (will be killed when main exits)
    flask_thread = threading.Thread(target=run_web, daemon=True, name="FlaskDashboard")
    flask_thread.start()

    # Wait for shutdown signal
    try:
        while not shutdown_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        logger.info("Waiting for bot thread to finish...")
        bot_thread.join(timeout=10)
        if bot_thread.is_alive():
            logger.warning("Bot thread did not finish in time, forcing exit.")
        logger.info("System shutdown complete.")

if __name__ == "__main__":
    main()