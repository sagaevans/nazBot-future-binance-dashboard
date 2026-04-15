# ==========================================
# nazBot Sniper System [RC v5.2 - REAL ACCOUNT MODE]
# FILE: main.py
# FUNGSI: Menjalankan Web Dashboard (Flask) dan Bot Engine (Thread)
# ==========================================

import threading
import logging
import os
from app import app  # Mengambil instance Flask dari app.py
from bot_logic import run_bot, shutdown_bot

# --- Konfigurasi Logging (Auto Save ke log.txt) ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler("log.txt"), # Mencatat semua log ke dalam file ini otomatis
        logging.StreamHandler()         # Tetap menampilkan log di layar hitam
    ]
)
logger = logging.getLogger('main')

def initialize_system():
    """Mereset status bot menjadi OFF saat server baru menyala agar aman"""
    try:
        with open('status.txt', 'w') as f:
            f.write('OFF')
        logger.info("[SYSTEM] Status bot direset ke OFF (Standby Mode).")
    except Exception as e:
        logger.error(f"[ERROR] Gagal mereset status.txt: {e}")

if __name__ == "__main__":
    logger.info("[SYSTEM] Memulai Sistem nazBot Sniper di Server AWS...")

    # 1. Inisialisasi awal
    initialize_system()

    # 2. Siapkan event untuk mengontrol bot (On/Off switch)
    shutdown_event = threading.Event()

    # 3. Jalankan Bot Engine di background thread
    bot_thread = threading.Thread(target=run_bot, args=(shutdown_event,))
    # daemon=True: Thread otomatis mati jika program utama (Flask) berhenti
    bot_thread.daemon = True  
    bot_thread.start()
    logger.info("[SYSTEM] Bot Engine berjalan di background thread.")

    # 4. Jalankan Web Dashboard (Flask) di main thread
    try:
        # --- UBAHAN PORT UNTUK PC WINDOWS & AWS ---
        port = int(os.environ.get("PORT", 5000))
        logger.info(f"[SYSTEM] Menjalankan Web Dashboard di port {port}...")

        # use_reloader=False sangat penting agar bot_thread tidak dijalankan dua kali oleh Flask
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    except KeyboardInterrupt:
        logger.info("[SYSTEM] Sistem dimatikan secara manual oleh user...")

    finally:
        # 5. Keamanan tingkat tinggi: Pastikan bot berhenti dengan aman saat web server mati
        logger.info("[SYSTEM] Mengirim sinyal shutdown ke Bot Engine...")
        shutdown_event.set()
        shutdown_bot()
        bot_thread.join(timeout=5)
        logger.info("[SYSTEM] Sistem nazBot Sniper berhasil dimatikan secara aman. Sampai jumpa, Bos!")
