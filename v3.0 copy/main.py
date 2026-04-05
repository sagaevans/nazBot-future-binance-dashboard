import threading
import time
import logging
from app import run_web
from bot_logic import run_bot

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('main')

def main():
    logger.info("🚀 Memulai nazBot Alpha 4.0 PRO System...")

    # Jalankan Bot Engine di background thread (daemon = True agar mati saat web mati)
    bot_thread = threading.Thread(target=run_bot, daemon=True, name="BotEngine")
    bot_thread.start()

    # Jalankan Flask Web Dashboard di main thread
    run_web()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🚨 Mematikan sistem secara paksa...")
