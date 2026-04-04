import threading
import time
import logging
import signal
import sys
from app import run_web
from bot_logic import run_bot

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('main')

# Global flag for graceful shutdown
_shutdown_flag = False

def signal_handler(signum, frame):
    global _shutdown_flag
    logger.info("Received shutdown signal, exiting...")
    _shutdown_flag = True

def main():
    global _shutdown_flag
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Memulai Sistem nazBot Alpha 2.0 - S/R Sniper...")

    # 1. Start Flask Web Server Thread (daemon)
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("🌐 Web Dashboard aktif di port 8080")

    # 2. Start Trading Bot Thread (daemon)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("✅ Trading Thread Aktif")

    # Keep main thread alive until shutdown
    while not _shutdown_flag:
        time.sleep(1)

    logger.info("Main loop terminated. Goodbye.")
    sys.exit(0)

if __name__ == "__main__":
    main()
