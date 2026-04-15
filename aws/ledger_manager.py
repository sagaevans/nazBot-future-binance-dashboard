# ==========================================
# nazBot Sniper - Accountancy Module
# FILE: ledger_manager.py
# FUNGSI: Mengelola Saldo Awal & Pencatatan Buku Kas
# ==========================================

import os
import logging
from datetime import datetime
from typing import Tuple

logger = logging.getLogger('bot')

LEDGER_FILE = 'profit_ledger.txt'
START_FILE = 'start_balance.txt'

def get_initial_balance(current_api_balance: float) -> float:
    """
    Menentukan modal awal dengan urutan: Ledger -> Start File -> API Dashboard
    """
    # 1. Cek Saldo Terakhir di Ledger
    if os.path.exists(LEDGER_FILE) and os.path.getsize(LEDGER_FILE) > 0:
        try:
            with open(LEDGER_FILE, 'r') as f:
                lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
                if lines:
                    last_line = lines[-1]
                    parts = [p.strip() for p in last_line.split('|')]
                    if len(parts) >= 7:
                        last_bal = float(parts[6])
                        logger.info(f"[LEDGER] Melanjutkan dari saldo terakhir: ${last_bal}")
                        return last_bal
        except Exception:
            pass

    # 2. Cek Saldo di start_balance.txt
    if os.path.exists(START_FILE):
        try:
            with open(START_FILE, 'r') as f:
                val = float(f.read().strip())
                logger.info(f"[LEDGER] Menggunakan saldo awal permanen: ${val}")
                return val
        except Exception:
            pass

    # 3. Jika Baru Reset (Dihapus Semua), Ambil dari Dashboard Binance
    start_bal = current_api_balance if current_api_balance > 0 else 5000.0
    
    # Simpan sebagai patokan permanen
    with open(START_FILE, 'w') as f:
        f.write(str(start_bal))
        
    logger.info(f"[LEDGER] Reset Terdeteksi. Saldo awal baru: ${start_bal}")
    return start_bal

def get_last_total_stats() -> Tuple[float, float]:
    """Mengambil total profit USD dan total ROE dari baris terakhir ledger"""
    if not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0:
        return 0.0, 0.0
    try:
        with open(LEDGER_FILE, 'r') as f:
            lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
            if not lines: return 0.0, 0.0
            parts = [p.strip() for p in lines[-1].split('|')]
            if len(parts) >= 6:
                tot_pnl = float(parts[4].replace('$', '').replace('+', ''))
                tot_roe = float(parts[5].replace('%', '').replace('+', ''))
                return tot_pnl, tot_roe
    except: pass
    return 0.0, 0.0

def catat_transaksi_v2(symbol: str, pnl_usd: float, roe_percent: float, current_balance: float, start_balance: float):
    """Mencatat hasil trading ke profit_ledger.txt"""
    prev_tot_pnl, prev_tot_roe = get_last_total_stats()
    
    new_tot_pnl = prev_tot_pnl + pnl_usd
    new_tot_roe = prev_tot_roe + roe_percent
    
    # Hitung pertumbuhan persentase modal
    growth_pct = ((current_balance - start_balance) / start_balance) * 100 if start_balance > 0 else 0.0

    now = datetime.now().strftime("%H:%M:%S")
    log_line = (f"{now} | {symbol} | {pnl_usd:+.2f} | {roe_percent:+.2f}% | "
                f"{new_tot_pnl:+.2f} | {new_tot_roe:+.2f}% | "
                f"{current_balance:.2f} | {growth_pct:+.2f}%\n")

    is_new = not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0
    with open(LEDGER_FILE, 'a') as f:
        if is_new:
            f.write("TIME | PAIR | PROFIT $ | ROE % | TOTAL PNL $ | TOTAL ROE % | SALDO BINANCE | GROWTH %\n")
            f.write("-" * 115 + "\n")
        f.write(log_line)
    
    logger.info(f"[REPORT] {symbol} {'PROFIT' if pnl_usd > 0 else 'LOSS'}: ${pnl_usd:+.2f}")
