import os, json
from flask import Flask, render_template_string, request, redirect, url_for
from binance.client import Client

app = Flask(__name__)
client = Client(os.environ.get('BINANCE_API_KEY'), os.environ.get('BINANCE_API_SECRET'), testnet=True)

STATE_FILE = 'status.txt'
HISTORY_FILE = 'trades_history.json'
VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>nazBot Alpha 2.0 - Ultimate Hybrid</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="10">
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: 'Segoe UI', sans-serif; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .card { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; border: 1px solid #334155; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        .grid-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }
        .stat-box { background: #334155; padding: 15px; border-radius: 10px; text-align: center; border-left: 4px solid #3b82f6; }
        .stat-box h4 { margin: 0 0 5px 0; color: #94a3b8; font-size: 0.85em; text-transform: uppercase;}
        .stat-box h2 { margin: 0; font-size: 1.8em; }
        .btn { padding: 12px 25px; border-radius: 8px; border: none; cursor: pointer; font-weight: bold; font-size: 1em; }
        .btn-start { background: #10b981; color: white; }
        .btn-stop { background: #ef4444; color: white; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.95em; }
        th, td { text-align: left; padding: 12px; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; }
        .text-green { color: #10b981; } .text-red { color: #ef4444; } .text-gold { color: #f59e0b; }
        .badge { padding: 4px 8px; border-radius: 6px; font-size: 0.8em; font-weight: bold; border: 1px solid; }
        .bg-long { background: rgba(16, 185, 129, 0.1); color: #10b981; border-color: #10b981; }
        .bg-short { background: rgba(239, 68, 68, 0.1); color: #ef4444; border-color: #ef4444; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1 style="margin:0; color: #38bdf8;">🎯 nazBot Alpha 2.0</h1>
                <p style="margin:5px 0 0 0; color: #94a3b8;">Hybrid Sniper | TP Fixed 50% | No SL (DCA Ready)</p>
            </div>
            <form action="/toggle" method="post">
                {% if status == 'OFF' %}
                    <button name="action" value="ON" class="btn btn-start">▶ START BOT</button>
                {% else %}
                    <button name="action" value="OFF" class="btn btn-stop">⏸ STOP BOT</button>
                {% endif %}
            </form>
        </div>

        <div class="grid-stats">
            <div class="stat-box" style="border-color: #f59e0b;"><h4>Balance</h4><h2>${{ balance }}</h2></div>
            <div class="stat-box" style="border-color: #06b6d4;">
                <h4>Total Floating ROE</h4>
                <h2 class="{{ 'text-green' if total_roe > 0 else 'text-red' if total_roe < 0 else '' }}">
                    {{ "%.2f"|format(total_roe) }}%
                </h2>
            </div>
            <div class="stat-box" style="border-color: #10b981;">
                <h4>Total Net PNL</h4>
                <h2 class="{{ 'text-green' if total_pnl > 0 else 'text-red' if total_pnl < 0 else '' }}">
                    ${{ "%.2f"|format(total_pnl) }}
                </h2>
            </div>
        </div>

        <div class="card">
            <h3 class="text-gold">⭐ VIP Squad ({{ vip_positions|length }} / 6 Posisi)</h3>
            <table>
                <thead>
                    <tr><th>Symbol</th><th>Side</th><th>Lev</th><th>Margin</th><th>Entry Price</th><th>ROE (%)</th><th>Unrealized PNL</th></tr>
                </thead>
                <tbody>
                    {% for p in vip_positions %}
                    <tr>
                        <td><b>{{ p['symbol'] }}</b></td>
                        <td><span class="badge {{ 'bg-long' if p['side'] == 'LONG' else 'bg-short' }}">{{ p['side'] }}</span></td>
                        <td>{{ p['leverage'] }}x</td>
                        <td>${{ "%.2f"|format(p['margin']) }}</td>
                        <td style="color:#cbd5e1;">${{ p['entry'] }}</td>
                        <td class="{{ 'text-green' if p['roe'] > 0 else 'text-red' }}"><b>{{ "%.2f"|format(p['roe']) }}%</b></td>
                        <td class="{{ 'text-green' if p['pnl'] > 0 else 'text-red' }}">${{ "%.2f"|format(p['pnl']) }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="7" style="text-align: center; color: #94a3b8; padding: 20px;">VIP sedang mengintai di TF 15m... 👁️</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h3 style="color: #ef4444;">🐺 Hunter Squad - Alts ({{ alt_positions|length }} / 8 Posisi)</h3>
            <table>
                <thead>
                    <tr><th>Symbol</th><th>Side</th><th>Lev</th><th>Margin</th><th>Entry Price</th><th>ROE (%)</th><th>Unrealized PNL</th></tr>
                </thead>
                <tbody>
                    {% for p in alt_positions %}
                    <tr>
                        <td><b>{{ p['symbol'] }}</b></td>
                        <td><span class="badge {{ 'bg-long' if p['side'] == 'LONG' else 'bg-short' }}">{{ p['side'] }}</span></td>
                        <td>{{ p['leverage'] }}x</td>
                        <td>${{ "%.2f"|format(p['margin']) }}</td>
                        <td style="color:#cbd5e1;">${{ p['entry'] }}</td>
                        <td class="{{ 'text-green' if p['roe'] > 0 else 'text-red' }}"><b>{{ "%.2f"|format(p['roe']) }}%</b></td>
                        <td class="{{ 'text-green' if p['pnl'] > 0 else 'text-red' }}">${{ "%.2f"|format(p['pnl']) }}</td>
                    </tr>
                    {% else %}
                    <tr><td colspan="7" style="text-align: center; color: #94a3b8; padding: 20px;">Pemburu sedang men-scan Altcoin liar... 🐺</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="card">
            <h3 style="color: #10b981;">📜 History Panen TP (Last 50)</h3>
            <table>
                <thead>
                    <tr><th>Waktu (WIB)</th><th>Symbol</th><th>Side</th><th>Harga Entry</th><th>Target TP Terpasang</th><th>Status</th></tr>
                </thead>
                <tbody>
                    {% for h in history %}
                    <tr>
                        <td style="color:#cbd5e1; font-size: 0.9em;">{{ h['time'] }}</td>
                        <td><b>{{ h['symbol'] }}</b></td>
                        <td><span class="badge {{ 'bg-long' if h['side'] == 'LONG' else 'bg-short' }}">{{ h['side'] }}</span></td>
                        <td>${{ h['entry'] }}</td>
                        <td class="text-green">${{ h['exit'] }}</td>
                        <td><span class="badge bg-long">Menunggu TP {{ h['profit'] }}</span></td>
                    </tr>
                    {% else %}
                    <tr><td colspan="6" style="text-align: center; color: #94a3b8; padding: 20px;">Belum ada sejarah panen tercatat. Bot baru saja dinyalakan.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

    </div>
</body>
</html>
"""

@app.route('/')
def index():
    status = "OFF"
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f: status = f.read().strip() or "OFF"
    except: pass

    balance, vip_positions, alt_positions = 0.0, [], []
    total_margin, total_unrealized = 0.0, 0.0

    try:
        acc = client.futures_account(recvWindow=6000)
        balance = round(float(next(a['walletBalance'] for a in acc['assets'] if a['asset'] == 'USDT')), 2)
        all_pos = client.futures_position_information(recvWindow=6000)

        for p in all_pos:
            amt = float(p['positionAmt'])
            if abs(amt) > 0:
                sym, side = p['symbol'], p['positionSide']
                unrealized = float(p['unRealizedProfit'])
                entry_price = float(p['entryPrice'])
                lev = int(p.get('leverage', 25))

                margin_used = (abs(amt) * entry_price) / lev
                roe = (unrealized / margin_used) * 100 if margin_used > 0 else 0

                total_margin += margin_used
                total_unrealized += unrealized

                pos_data = {
                    'symbol': sym, 'side': side, 'margin': margin_used,
                    'entry': entry_price, 'roe': roe, 'pnl': unrealized, 'leverage': lev
                }

                if sym in VIP_SYMBOLS: vip_positions.append(pos_data)
                else: alt_positions.append(pos_data)

    except Exception as e: print(f"Dashboard Error: {e}")

    total_roe = (total_unrealized / total_margin) * 100 if total_margin > 0 else 0.0
    vip_positions.sort(key=lambda x: x['roe'], reverse=True)
    alt_positions.sort(key=lambda x: x['roe'], reverse=True)

    history_data = []
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f: history_data = json.load(f)
    except: pass

    return render_template_string(
        HTML_TEMPLATE, status=status, balance=balance, 
        vip_positions=vip_positions, alt_positions=alt_positions, 
        total_roe=total_roe, total_pnl=total_unrealized, history=history_data
    )

@app.route('/toggle', methods=['POST'])
def toggle():
    new_status = request.form.get('action', 'OFF')
    with open(STATE_FILE, 'w') as f: f.write(new_status)
    return redirect(url_for('index'))

def run_web():
    app.run(host='0.0.0.0', port=8080, threaded=True)
