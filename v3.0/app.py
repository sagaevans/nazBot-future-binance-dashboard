import os, logging, tempfile
from flask import Flask, jsonify, request, render_template_string
from binance.client import Client

app = Flask(__name__)
logger = logging.getLogger('dashboard')

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')
client = Client(API_KEY, API_SECRET, testnet=True)

STATE_FILE = 'status.txt'
INITIAL_BALANCE = 5000.0 

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>nazBot Alpha 2.0</title>
    <style>
        body { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 20px; margin-bottom: 20px; flex-wrap: wrap; gap: 15px; }
        .header h1 { margin: 0; color: #38bdf8; font-size: 24px; }
        .controls { display: flex; gap: 15px; }
        button { padding: 10px 20px; border: none; border-radius: 6px; font-weight: bold; font-size: 14px; cursor: pointer; transition: 0.2s; }
        .btn-start { background-color: #eab308; color: #1e293b; }
        .btn-stop { background-color: #ef4444; color: #f8fafc; }
        .btn-close-all { background-color: #dc2626; color: #f8fafc; }
        .btn-close-all:hover { background-color: #b91c1c; }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background-color: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; text-align: center; }
        .stat-card h3 { margin: 0 0 10px 0; color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }
        .stat-card h2 { margin: 0; font-size: 26px; font-weight: bold;}
        .text-green { color: #4ade80 !important; }
        .text-red { color: #f87171 !important; }
        .text-white { color: #f8fafc !important; }
        .table-container { background-color: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; overflow-x: auto; margin-bottom: 20px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th, td { padding: 12px 15px; border-bottom: 1px solid #334155; }
        th { color: #94a3b8; font-weight: 600; font-size: 14px; text-transform: uppercase; }
        tbody tr:hover { background-color: #334155; }
        .badge-long { background-color: rgba(74, 222, 128, 0.2); color: #4ade80; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px;}
        .slot-tracker { display: inline-block; background-color: #0f172a; padding: 5px 12px; border-radius: 6px; font-size: 13px; color: #38bdf8; border: 1px solid #334155; margin-left: 15px; vertical-align: middle; }
        .slot-tracker span { font-weight: bold; color: #f8fafc; }
        .badge-lev { background-color: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 3px 6px; border-radius: 4px; font-weight: bold; font-size: 11px; margin-left: 10px;}
    </style>
</head>
<body>

    <div class="header">
        <h1>🎯 nazBot Alpha 2.0 
            <span style="font-size: 14px; color:#94a3b8;">| Sniper Mode: NO-SL</span>
            <span class="badge-lev">⚡ MAX LEVERAGE: 50x (Auto-Adjust)</span>
        </h1>
        <div class="controls">
            <button id="toggleBtn" onclick="toggleBot()">LOADING...</button>
            <button class="btn-close-all" onclick="closeAllPositions()">🚨 CLOSE ALL POSITIONS</button>
        </div>
    </div>

    <div class="dashboard-grid">
        <div class="stat-card">
            <h3>Saldo USDT Aktif</h3>
            <h2 id="balance" class="text-white">Loading...</h2>
        </div>
        <div class="stat-card">
            <h3>Net Profit / ROI</h3>
            <h2 id="net_roi">Loading...</h2>
        </div>
        <div class="stat-card">
            <h3>Floating PNL / ROE</h3>
            <h2 id="floating_pnl">Loading...</h2>
        </div>
        <div class="stat-card">
            <h3>Total Ekuitas</h3>
            <h2 id="total_equity" class="text-white">Loading...</h2>
        </div>
    </div>

    <div class="table-container">
        <h3 style="margin-top:0; color:#eab308; display: flex; align-items: center;">
            👑 VIP Positions (<span id="vip_count">0</span>/6)
        </h3>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Lev</th>
                    <th>Margin</th>
                    <th>Entry Price</th>
                    <th>ROE (%)</th>
                    <th>Unrealized PNL ($)</th>
                </tr>
            </thead>
            <tbody id="vip-table">
                <tr><td colspan="7" style="text-align:center; color:#94a3b8;">Fetching live data...</td></tr>
            </tbody>
        </table>
    </div>

    <div class="table-container">
        <h3 style="margin-top:0; color:#38bdf8; display: flex; align-items: center;">
            🚀 Altcoin Positions (<span id="alt_count">0</span>/8)
        </h3>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Lev</th>
                    <th>Margin</th>
                    <th>Entry Price</th>
                    <th>ROE (%)</th>
                    <th>Unrealized PNL ($)</th>
                </tr>
            </thead>
            <tbody id="alt-table">
                <tr><td colspan="7" style="text-align:center; color:#94a3b8;">Fetching live data...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        let currentStatus = '{{ bot_status }}';

        function updateToggleButton() {
            const btn = document.getElementById('toggleBtn');
            if(currentStatus === 'ON') {
                btn.innerText = '⏸️ STOP BOT';
                btn.className = 'btn-stop';
            } else {
                btn.innerText = '▶️ START BOT';
                btn.className = 'btn-start';
            }
        }

        async function toggleBot() {
            const newStatus = currentStatus === 'ON' ? 'OFF' : 'ON';
            try {
                const res = await fetch('/api/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ status: newStatus })
                });
                const data = await res.json();
                if(data.status === 'success') {
                    currentStatus = data.bot_status;
                    updateToggleButton();
                }
            } catch(e) { alert('Gagal mengubah status bot!'); }
        }

        async function closeAllPositions() {
            if(!confirm("Yakin ingin MENUTUP SEMUA POSISI secara paksa (Market Order)?")) return;
            try {
                const res = await fetch('/api/close_all', { method: 'POST' });
                const data = await res.json();
                alert(data.message);
                fetchDashboardData();
            } catch(e) { alert('Gagal menutup posisi!'); }
        }

        async function fetchDashboardData() {
            try {
                const response = await fetch('/api/data');
                const data = await response.json();

                if(data.status === 'success') {
                    document.getElementById('balance').innerText = '$' + data.balance.toFixed(2);

                    const roiElem = document.getElementById('net_roi');
                    const netSign = data.net_profit >= 0 ? '+' : '-';
                    roiElem.innerHTML = `${netSign}$${Math.abs(data.net_profit).toFixed(2)} <span style="font-size:16px; font-weight:normal; color:#cbd5e1;">(${netSign}${Math.abs(data.net_roi).toFixed(2)}%)</span>`;
                    roiElem.className = data.net_profit >= 0 ? 'text-green' : 'text-red';

                    const floatElem = document.getElementById('floating_pnl');
                    if (data.total_unrealized === 0) {
                        floatElem.innerHTML = `+$0.00 <span style="font-size:16px; font-weight:normal; color:#cbd5e1;">(0.00%)</span>`;
                        floatElem.className = 'text-white';
                    } else {
                        const floatSign = data.total_unrealized > 0 ? '+' : '-';
                        floatElem.innerHTML = `${floatSign}$${Math.abs(data.total_unrealized).toFixed(2)} <span style="font-size:16px; font-weight:normal; color:#cbd5e1;">(${floatSign}${Math.abs(data.floating_roe).toFixed(2)}%)</span>`;
                        floatElem.className = data.total_unrealized > 0 ? 'text-green' : 'text-red';
                    }

                    document.getElementById('total_equity').innerText = '$' + data.total_equity.toFixed(2);
                    document.getElementById('vip_count').innerText = data.vip_count;
                    document.getElementById('alt_count').innerText = data.alt_count;

                    const vipTbody = document.getElementById('vip-table');
                    const altTbody = document.getElementById('alt-table');

                    let vipHtml = '';
                    let altHtml = '';

                    data.positions.forEach(pos => {
                        const sideBadge = pos.side === 'LONG' ? '<span class="badge-long">LONG</span>' : '<span class="badge-long">LONG</span>';
                        const colorClass = pos.roe >= 0 ? 'text-green' : 'text-red';

                        const rowHtml = `<tr>
                            <td style="font-weight:bold; color:#f8fafc;">${pos.symbol}</td>
                            <td>${sideBadge}</td>
                            <td style="color:#38bdf8; font-weight:bold;">${pos.leverage}x</td>
                            <td style="color:#cbd5e1;">$${pos.margin.toFixed(2)}</td>
                            <td style="color:#cbd5e1;">$${pos.entryPrice}</td>
                            <td class="${colorClass}" style="font-weight:bold;">${pos.roe.toFixed(2)}%</td>
                            <td class="${colorClass}" style="font-weight:bold;">$${pos.unrealizedPNL.toFixed(2)}</td>
                        </tr>`;

                        if (pos.type === 'VIP') {
                            vipHtml += rowHtml;
                        } else {
                            altHtml += rowHtml;
                        }
                    });

                    vipTbody.innerHTML = vipHtml || '<tr><td colspan="7" style="text-align:center; color:#94a3b8;">Tidak ada posisi VIP aktif. Mengintai market... 👀</td></tr>';
                    altTbody.innerHTML = altHtml || '<tr><td colspan="7" style="text-align:center; color:#94a3b8;">Tidak ada posisi Altcoin aktif. Mengintai market... 👀</td></tr>';
                }
            } catch (error) {
                console.error("Gagal mengambil data:", error);
            }
        }

        updateToggleButton();
        setInterval(fetchDashboardData, 3000);
        fetchDashboardData();
    </script>
</body>
</html>
"""

def _atomic_write(filepath, content):
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(filepath))
    with os.fdopen(fd, 'w') as f:
        f.write(content)
    os.replace(temp_path, filepath)

@app.route('/')
def index():
    try:
        with open(STATE_FILE, 'r') as f: status = f.read().strip() or "OFF"
    except: status = "OFF"
    return render_template_string(HTML_TEMPLATE, bot_status=status)

@app.route('/api/data')
def get_data():
    try:
        balances = client.futures_account_balance()
        usdt_balance = next((float(b['balance']) for b in balances if b['asset'] == 'USDT'), 0.0)
        acc = client.futures_account()
        total_unrealized = float(acc['totalUnrealizedProfit'])

        net_profit = usdt_balance - INITIAL_BALANCE
        net_roi = (net_profit / INITIAL_BALANCE) * 100
        floating_roe = (total_unrealized / INITIAL_BALANCE) * 100
        total_equity = usdt_balance + total_unrealized

        positions = client.futures_position_information()
        active_pos = []
        vip_c = 0
        alt_c = 0

        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                symbol = p['symbol']
                mark_price = float(p['markPrice'])
                entry_price = float(p['entryPrice'])
                unrealized = float(p['unRealizedProfit'])

                leverage = float(p.get('leverage', 50))
                margin = (abs(amt) * mark_price) / leverage
                roe = (unrealized / margin * 100) if margin > 0 else 0

                is_vip = symbol in VIP_SYMBOLS
                if is_vip: vip_c += 1
                else: alt_c += 1

                active_pos.append({
                    "symbol": symbol,
                    "side": "LONG",
                    "leverage": int(leverage),
                    "margin": round(margin, 2),
                    "entryPrice": entry_price,
                    "roe": round(roe, 2),
                    "unrealizedPNL": round(unrealized, 2),
                    "type": "VIP" if is_vip else "ALT"
                })

        return jsonify({
            "status": "success", "balance": round(usdt_balance, 2), "net_profit": round(net_profit, 2),
            "net_roi": round(net_roi, 2), "total_unrealized": round(total_unrealized, 2),
            "floating_roe": round(floating_roe, 2), "total_equity": round(total_equity, 2),
            "positions": active_pos, "vip_count": vip_c, "alt_count": alt_c
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/toggle', methods=['POST'])
def toggle_bot():
    new_status = request.get_json().get('status', 'OFF')
    _atomic_write(STATE_FILE, new_status)
    return jsonify({"status": "success", "bot_status": new_status})

@app.route('/api/close_all', methods=['POST'])
def close_all_positions():
    try:
        positions = client.futures_position_information()
        for p in positions:
            amt = float(p['positionAmt'])
            if amt != 0:
                client.futures_create_order(symbol=p['symbol'], side='SELL' if amt > 0 else 'BUY', type='MARKET', quantity=abs(amt), positionSide=p['positionSide'])
        return jsonify({"status": "success", "message": "Semua posisi ditutup."})
    except Exception as e: return jsonify({"status": "error"}), 500

def run_web(): app.run(host='0.0.0.0', port=8080, use_reloader=False)

if __name__ == '__main__': run_web()
