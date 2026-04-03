"""
main.py — nazBot Alpha 2.0 Entry Point
Optimizations:
  - Watchdog now uses threading.Event for clean shutdown signaling
  - BOT_RUNNING Event replaces nonlocal thread reference (thread-safe)
  - Graceful SIGINT/SIGTERM handler added for clean Replit shutdown
"""

import threading
import time
import os
import logging
import sys
import signal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('main')

_shutdown_event = threading.Event()


def _jalankan_trading() -> None:
    """Wrapper untuk run_bot dengan penanganan error level atas."""
    try:
        from bot_logic import run_bot
        run_bot()
    except Exception as e:
        logger.critical(f"Trading thread crash: {e}", exc_info=True)


def _make_trading_thread() -> threading.Thread:
    """Factory — buat trading thread baru yang siap distart."""
    return threading.Thread(target=_jalankan_trading, name='TradingThread', daemon=True)


def _watchdog(get_thread_fn, set_thread_fn) -> None:
    """
    Watchdog: restart trading thread jika mati.
    Menggunakan _shutdown_event agar ikut berhenti saat proses dimatikan.
    """
    while not _shutdown_event.wait(timeout=30):
        t = get_thread_fn()
        if not t.is_alive():
            logger.warning("⚠️ Trading thread mati — restart dalam 10 detik...")
            _shutdown_event.wait(timeout=10)
            if _shutdown_event.is_set():
                break
            new_t = _make_trading_thread()
            new_t.start()
            set_thread_fn(new_t)
            logger.info("✅ Trading Thread berhasil direstart")


def main() -> None:
    logger.info("🚀 Memulai Sistem nazBot Alpha 2.0 - S/R Sniper...")

    # Inisialisasi status file jika belum ada
    if not os.path.exists('status.txt'):
        with open('status.txt', 'w') as f:
            f.write('OFF')

    # ── Container thread (mutable via closure) ───────────────
    _thread_holder: list[threading.Thread] = []

    trading_thread = _make_trading_thread()
    trading_thread.start()
    _thread_holder.append(trading_thread)
    logger.info("✅ Trading Thread Aktif")

    # ── Graceful shutdown handler ─────────────────────────────
    def _handle_shutdown(signum, frame):  # noqa: ANN001
        logger.info(f"Signal {signum} diterima — menutup bot...")
        _shutdown_event.set()

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    # ── Watchdog thread ───────────────────────────────────────
    watchdog_thread = threading.Thread(
        target=_watchdog,
        args=(lambda: _thread_holder[0], lambda t: _thread_holder.__setitem__(0, t)),
        name='Watchdog',
        daemon=True
    )
    watchdog_thread.start()
    logger.info("🛡️ Watchdog Thread Aktif")

    # ── Flask dashboard di main thread ───────────────────────
    logger.info("🌐 Web Dashboard aktif di port 8080")
    from app import run_web
    run_web()


if __name__ == '__main__':
    main()
