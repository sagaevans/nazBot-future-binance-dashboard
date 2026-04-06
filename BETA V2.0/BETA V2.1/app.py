# ==========================================
# BETA v2.1 — Sniper System (RESTORED EDITION)
# FILE: app.py
# FUNGSI: Server Dashboard, Saldo Dinamis, & API Ledger Grafik
# ==========================================

import os
import logging
import tempfile
from flask import Flask, jsonify, request, render_template
import bot_logic

# --- SILENCER: MEMBERSIHKAN CONSOLE ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("binance").setLevel(logging.WARNING)

app = Flask(__name__)
logger = logging.getLogger('dashboard')

def _atomic_write(filepath, content):
    """Menulis file status dengan aman agar tidak crash saat diakses bot."""
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(filepath))
    with os.fdopen(fd, 'w') as f: 
        f.write(content)
    os.replace(temp_path, filepath)

@app.route('/')
def index():
    """Memanggil file index.html dari dalam folder templates."""
    try:
        with open(bot_logic.STATE_FILE, 'r') as f: 
            status = f.read().strip() or "OFF"
    except: 
        status = "OFF"
    return render_template('index.html', bot_status=status)

@app.route('/api/data')
def get_data():
    """Endpoint utama Dashboard. Mengolah data dari Binance dan bot_logic."""
    try:
        # 1. Ambil data Saldo USDT dan Saldo Awal secara Dinamis (v2.1)
        usdt_balance = bot_logic.get_binance_balance()
        initial_balance = bot_logic.get_initial_balance()

        acc = bot_logic._api_call(bot_logic._client.futures_account)
        total_unrealized = float(acc['totalUnrealizedProfit'])

        # 2. Perhitungan Standar Akun
        net_profit = usdt_balance - initial_balance
        net_roi = (net_profit / initial_balance * 100) if initial_balance > 0 else 0.0
        floating_roe = (total_unrealized / initial_balance * 100) if initial_balance > 0 else 0.0
        total_equity = usdt_balance + total_unrealized

        # 3. Proses Posisi Aktif
        positions = bot_logic._api_call(bot_logic._client.futures_position_information)
        active_pos = []
        vip_c = alt_c = gold_c = 0
        accumulative_roe_margin = 0.0

        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol']
                mark_price = float(p['markPrice'])
                entry_price = float(p['entryPrice'])
                unrealized = float(p['unRealizedProfit'])
                leverage = float(p.get('leverage', bot_logic.TARGET_LEVERAGE))

                # Hitung ROE Murni terhadap Margin Aktual
                margin = (abs(amt) * mark_price) / leverage
                roe = (unrealized / margin * 100) if margin > 0 else 0
                accumulative_roe_margin += roe

                # Identifikasi Label Koin
                is_vip = symbol in bot_logic.VIP_SET
                is_gold = symbol in bot_logic.GOLD_SET

                if is_gold:
                    type_label = "GOLD"
                    gold_c += 1
                elif is_vip: 
                    type_label = "VIP"
                    vip_c += 1
                else: 
                    type_label = "ALT"
                    alt_c += 1

                active_pos.append({
                    "symbol": symbol, 
                    "side": "LONG" if amt > 0 else "SHORT",
                    "leverage": int(leverage), 
                    "margin": round(margin, 2),
                    "entryPrice": entry_price, 
                    "roe": round(roe, 2),
                    "unrealizedPNL": round(unrealized, 2), 
                    "type": type_label
                })

        # 4. Kirim Paket Data JSON ke Tampilan
        return jsonify({
            "status": "success", 
            "balance": usdt_balance, 
            "net_profit": net_profit,
            "net_roi": net_roi, 
            "total_unrealized": total_unrealized, 
            "floating_roe": floating_roe,
            "total_equity": total_equity, 
            "positions": active_pos, 
            "vip_count": vip_c, 
            "alt_count": alt_c,
            "gold_count": gold_c,
            "accumulative_roe_margin": accumulative_roe_margin,

            # FIXED: Mengambil ROE Akumulatif Excel Style dari bot_logic v2.1
            "total_closed_roe": bot_logic.get_last_ledger_totals(), 
            "total_success_trades": bot_logic.TOTAL_SUCCESS_TRADES,
            "closed_history": bot_logic.CLOSED_HISTORY
        })
    except Exception as e: 
        logger.error(f"Data API Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==========================================
# ENDPOINT JALUR DATA GRAFIK (LEDGER 8 KOLOM) - DIKEMBALIKAN!
# ==========================================
@app.route('/api/ledger')
def get_ledger_data():
    """Membaca file profit_ledger.txt dan mengirimkannya ke frontend."""
    ledger_data = []

    if not os.path.exists(bot_logic.LEDGER_FILE):
        return jsonify({"status": "success", "data": []})

    try:
        with open(bot_logic.LEDGER_FILE, 'r') as f:
            lines = f.readlines()

        for line in lines:
            if not line.strip() or 'TIME' in line or '---' in line:
                continue

            parts = [p.strip() for p in line.split('|')]

            if len(parts) >= 8:
                ledger_data.append({
                    "time": parts[0],
                    "pair": parts[1],
                    "profit_usd": parts[2],
                    "roe_percent": parts[3],
                    "total_pnl": parts[4],
                    "total_roe": parts[5],
                    "saldo_binance": parts[6],
                    "growth": parts[7]
                })

        return jsonify({"status": "success", "data": ledger_data})
    except Exception as e:
        logger.error(f"Gagal membaca ledger API: {e}")
        return jsonify({"status": "error", "message": "Gagal membaca ledger", "data": []})

@app.route('/api/toggle', methods=['POST'])
def toggle_bot():
    """Fungsi Start/Stop Bot via Tombol Dashboard"""
    new_status = request.get_json().get('status', 'OFF')
    _atomic_write(bot_logic.STATE_FILE, new_status)
    return jsonify({"status": "success", "bot_status": new_status})

# ==========================================
# TOMBOL PANIK CLOSE ALL - DIKEMBALIKAN!
# ==========================================
@app.route('/api/close_all', methods=['POST'])
def close_all_positions():
    """Fungsi Tombol Panik (Close All)"""
    try:
        positions = bot_logic._api_call(bot_logic._client.futures_position_information)
        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                bot_logic._api_call(
                    bot_logic._client.futures_create_order,
                    symbol=p['symbol'], 
                    side='SELL' if amt > 0 else 'BUY', 
                    type='MARKET', 
                    quantity=abs(amt), 
                    positionSide=p['positionSide']
                )
        return jsonify({"status": "success", "message": "🚨 Semua posisi berhasil ditutup!"})
    except Exception as e: 
        logger.error(f"Close All Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_web(): 
    """Dipanggil oleh main.py untuk menjalankan server."""
    app.run(host='0.0.0.0', port=8080, use_reloader=False)

if __name__ == '__main__': 
    run_web()
