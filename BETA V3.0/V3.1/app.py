# ==========================================
# nazBot Sniper System [BETA v3.1] - FLASK DASHBOARD
# FILE: app.py
# FUNGSI: Web UI, Real-time Data, Panic Button (Mendukung Long & Short)
# ==========================================

import os
import time
import json
import logging
from flask import Flask, render_template, jsonify, request
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Matikan log bawaan Flask agar console tidak spam
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# Gunakan testnet=True. Ubah ke False jika pindah ke Real Account
client = Client(API_KEY, API_SECRET, testnet=True)

STATE_FILE = 'status.txt'
LEDGER_FILE = 'profit_ledger.txt'

VIP_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"}
GOLD_PAIRS = {"PAXGUSDT"} # Hanya PAXG sesuai update v3.1

def read_bot_status():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return f.read().strip()
    return 'OFF'

def write_bot_status(status):
    with open(STATE_FILE, 'w') as f:
        f.write(status)

def parse_ledger():
    """Membaca 8 Kolom Ledger v3.1"""
    history = []
    if os.path.exists(LEDGER_FILE) and os.path.getsize(LEDGER_FILE) > 0:
        with open(LEDGER_FILE, 'r') as f:
            lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
            for line in reversed(lines[-20:]): # Ambil 20 transaksi terakhir
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 8:
                    history.append({
                        'time': parts[0],
                        'symbol': parts[1],
                        'profit': parts[2],
                        'roe': parts[3],
                        'tot_pnl': parts[4],
                        'tot_roe': parts[5],
                        'saldo': parts[6],
                        'growth': parts[7]
                    })
    return history

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    try:
        # 1. Ambil Saldo Riil
        account_info = client.futures_account()
        wallet_balance = 0.0
        for asset in account_info.get('assets', []):
            if asset['asset'] == 'USDT':
                wallet_balance = float(asset['walletBalance'])

        # 2. Ambil Posisi Aktif
        positions = client.futures_position_information()
        active_positions = []
        total_unrealized = 0.0
        total_margin = 0.0

        vip_positions = []
        alt_positions = []
        gold_positions = []

        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol']
                unrealized = float(p['unRealizedProfit'])
                mark_price = float(p['markPrice'])
                entry_price = float(p['entryPrice'])
                leverage = float(p.get('leverage', 50))
                pos_side = p['positionSide']

                # Penentuan Arah (LONG/SHORT)
                if pos_side == 'BOTH':
                    actual_side = 'LONG' if amt > 0 else 'SHORT'
                else:
                    actual_side = pos_side

                # Kalkulasi Margin Aktual
                margin = (abs(amt) * mark_price) / leverage
                roe_percent = (unrealized / margin) * 100 if margin > 0 else 0

                total_unrealized += unrealized
                total_margin += margin

                pos_data = {
                    'symbol': symbol,
                    'side': actual_side,
                    'leverage': int(leverage),
                    'margin': margin,
                    'entry_price': entry_price,
                    'mark_price': mark_price,
                    'roe': roe_percent,
                    'unrealized': unrealized
                }

                if symbol in GOLD_PAIRS:
                    gold_positions.append(pos_data)
                elif symbol in VIP_SYMBOLS:
                    vip_positions.append(pos_data)
                else:
                    alt_positions.append(pos_data)

        # 3. Hitung Ekuitas (Saldo + Floating)
        equity = wallet_balance + total_unrealized
        
        # Total ROE Aktif (Persentase Floating Keseluruhan)
        total_active_roe = (total_unrealized / total_margin) * 100 if total_margin > 0 else 0.0

        # 4. Baca Ledger Terakhir
        ledger_data = parse_ledger()
        net_profit_str = ledger_data[0]['tot_pnl'] if ledger_data else "+0.00"
        net_roe_str = ledger_data[0]['tot_roe'] if ledger_data else "+0.00%"

        return jsonify({
            'status': 'success',
            'bot_status': read_bot_status(),
            'wallet_balance': wallet_balance,
            'equity': equity,
            'net_profit': net_profit_str,
            'net_roe': net_roe_str,
            'total_unrealized': total_unrealized,
            'total_active_roe': total_active_roe,
            'vip_positions': vip_positions,
            'alt_positions': alt_positions,
            'gold_positions': gold_positions,
            'ledger': ledger_data
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/toggle', methods=['POST'])
def toggle_bot():
    current_status = read_bot_status()
    new_status = 'ON' if current_status == 'OFF' else 'OFF'
    write_bot_status(new_status)
    return jsonify({'status': 'success', 'bot_status': new_status})

@app.route('/api/close_all', methods=['POST'])
def close_all():
    try:
        # PENTING: Matikan bot dulu agar tidak auto-open saat proses close
        write_bot_status('OFF')
        
        positions = client.futures_position_information()
        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol']
                pos_side = p['positionSide']
                
                # 1. Batalkan semua antrean LIMIT TP dan STOP LOSS untuk koin ini
                try:
                    client.futures_cancel_all_open_orders(symbol=symbol)
                except Exception as e:
                    print(f"Gagal membatalkan order open {symbol}: {e}")

                # 2. Tutup Posisi (LONG ditutup dengan SELL, SHORT ditutup dengan BUY)
                action_side = 'SELL' if amt > 0 else 'BUY'
                
                # Karena kita pakai Dual-Side Mode, pos_side harus presisi
                try:
                    client.futures_create_order(
                        symbol=symbol,
                        side=action_side,
                        type='MARKET',
                        quantity=abs(amt),
                        positionSide=pos_side
                    )
                except Exception as e:
                    print(f"Gagal Close {symbol}: {e}")

        return jsonify({'status': 'success', 'message': 'Semua posisi ditutup dan order dibatalkan.'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    # Pastikan status default adalah OFF saat server baru menyala
    write_bot_status('OFF')
    # Jalankan server Flask (Listen to all interfaces for Replit)
    app.run(host='0.0.0.0', port=8080, debug=False)
