# app.py
from flask import Flask, render_template, jsonify, request
import os
import bot_logic
import logging

logger = logging.getLogger('app')

app = Flask(__name__)

# Simpan saldo awal secara statis untuk hitungan Net Profit
INITIAL_BALANCE = 5000.0

@app.route('/')
def index():
    # Memanggil file index.html yang ada di dalam folder templates
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    try:
        # 1. Ambil data akun (Saldo)
        acc = bot_logic._api_call(bot_logic._client.futures_account)
        total_balance = float(acc['totalWalletBalance'])
        total_pnl = float(acc['totalUnrealizedProfit'])
        equity = total_balance + total_pnl
        
        # 2. Ambil data posisi aktif
        pos = bot_logic._api_call(bot_logic._client.futures_position_information)
        active_positions = []
        cumulative_roe = 0.0
        
        for p in pos:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol']
                side = "LONG" if amt > 0 else "SHORT"
                unrealized = float(p['unRealizedProfit'])
                lev = int(p['leverage'])
                entry_price = float(p['entryPrice'])
                mark_price = float(p['markPrice'])
                
                # Hitung ROE Murni (%) berdasarkan Margin aktual
                current_margin = (abs(amt) * mark_price) / lev
                roe = (unrealized / current_margin) * 100 if current_margin > 0 else 0
                
                # Akumulasi ROE murni untuk ditampilkan di Dashboard
                cumulative_roe += roe 
                
                active_positions.append({
                    'symbol': symbol,
                    'side': side,
                    'lev': f"{lev}x",
                    'margin': f"${current_margin:.2f}",
                    'entry': f"{entry_price:.4g}",
                    'roe': f"{roe:+.2f}%",
                    'pnl': f"${unrealized:+.2f}",
                    'is_vip': symbol in bot_logic.VIP_SET
                })
        
        # 3. Hitung Net Profit dari modal awal ($5000)
        net_profit_usd = total_balance - INITIAL_BALANCE
        net_roi_percent = (net_profit_usd / INITIAL_BALANCE) * 100
        
        # 4. Ambil Status Bot (ON/OFF)
        bot_status = bot_logic._read_status()
        
        # 5. Kembalikan semua data dalam format JSON ke Dashboard
        return jsonify({
            'saldo_aktif': f"${total_balance:.2f}",
            'net_profit': f"${net_profit_usd:+.2f} ({net_roi_percent:+.2f}%)",
            'floating_pnl': f"${total_pnl:+.2f} ({cumulative_roe:+.2f}% ROE)",
            'total_ekuitas': f"${equity:.2f}",
            'positions': active_positions,
            'status': bot_status,
            
            # --- DATA PAPAN SKOR BARU (Dari bot_logic.py) ---
            'total_closed_roe': f"+{bot_logic.TOTAL_CLOSED_ROE:.2f}% ROE",
            'total_success_trades': f"{bot_logic.TOTAL_SUCCESS_TRADES} Trades",
            'closed_history': bot_logic.CLOSED_HISTORY
        })
    except Exception as e:
        logger.error(f"Error fetching data for dashboard: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/toggle', methods=['POST'])
def toggle_bot():
    status = request.json.get('status')
    try:
        with open(bot_logic.STATE_FILE, 'w') as f:
            f.write(status)
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error saving status: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/api/close_all', methods=['POST'])
def close_all():
    try:
        pos = bot_logic._api_call(bot_logic._client.futures_position_information)
        for p in pos:
            amt = float(p['positionAmt'])
            if amt != 0:
                side = 'SELL' if amt > 0 else 'BUY'
                bot_logic._api_call(
                    bot_logic._client.futures_create_order,
                    symbol=p['symbol'],
                    side=side,
                    type='MARKET',
                    quantity=abs(amt),
                    positionSide=p['positionSide']
                )
        return jsonify({'status': 'success'})
    except Exception as e:
        logger.error(f"Error closing all positions: {e}")
        return jsonify({'status': str(e)}), 500

# FUNGSI WAJIB UNTUK DIPANGGIL OLEH MAIN.PY
def run_web():
    app.run(host='0.0.0.0', port=8080)

if __name__ == '__main__':
    run_web()