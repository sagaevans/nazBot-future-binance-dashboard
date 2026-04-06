# ==========================================
# nazBot Sniper System [BETA v2.1]
# FILE: main.py
# FUNGSI: Menjalankan Web Dashboard (Flask) dan Bot Engine (Thread)
# ==========================================

import threading
import logging
import os
from app import app
from bot_logic import run_bot, shutdown_bot

# --- Konfigurasi Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('main')

def initialize_system():
    """Mereset status bot menjadi OFF saat server baru menyala agar aman"""
    try:
        with open('status.txt', 'w') as f:
            f.write('OFF')
        logger.info("Status bot direset ke OFF (Standby Mode).")
    except Exception as e:
        logger.error(f"Gagal mereset status.txt: {e}")

if __name__ == "__main__":
    logger.info("🔥 Memulai Sistem nazBot Sniper...")

    # 1. Inisialisasi awal
    initialize_system()

    # 2. Siapkan event untuk mengontrol bot (On/Off switch)
    shutdown_event = threading.Event()

    # 3. Jalankan Bot Engine di background thread
    bot_thread = threading.Thread(target=run_bot, args=(shutdown_event,))
    bot_thread.daemon = True  # Thread akan otomatis mati jika program utama (Flask) berhenti
    bot_thread.start()
    logger.info("⚙️ Bot Engine berjalan di background thread.")

    # 4. Jalankan Web Dashboard (Flask) di main thread
    try:
        logger.info("🌐 Menjalankan Web Dashboard di port 8080...")
        # use_reloader=False sangat penting agar bot_thread tidak dijalankan dua kali oleh Flask
        app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        logger.info("Sistem dimatikan oleh user...")
    finally:
        # 5. Keamanan tingkat tinggi: Pastikan bot berhenti dengan aman saat web server mati
        logger.info("🛑 Mengirim sinyal shutdown ke Bot Engine...")
        shutdown_event.set()
        shutdown_bot()
        bot_thread.join(timeout=5)
        logger.info("Sistem nazBot Sniper berhasil dimatikan secara aman. Sampai jumpa, Bos!")
