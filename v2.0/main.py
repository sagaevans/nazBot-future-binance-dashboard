import threading
import time
import logging
from app import run_web
from bot_logic import run_bot

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('main')

def main():
    logger.info("🚀 Memulai Sistem nazBot Alpha 2.0 - S/R Sniper...")

    # 1. Start Flask Web Server Thread
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("🌐 Web Dashboard aktif di port 8080")

    # 2. Start Trading Bot Thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Trading Thread Aktif")

    # Keep main thread alive
    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
