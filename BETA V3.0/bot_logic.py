# ==========================================
# nazBot Sniper System [BETA v3.1.5 - ULTIMATE HYBRID]
# FILE: bot_logic.py
# FUNGSI: Custom 5-Confluence, Memory PNL, & Hybrid TP/SL
# ==========================================

from __future__ import annotations
import math
import os
import time
import logging
import random
import threading
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from ta.trend import ema_indicator, sma_indicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger('bot')

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# --- PENGATURAN MUTLAK PRO ---
TARGET_LEVERAGE = 50
BASE_MARGIN = 5.0
TP_TARGET_ROE = 1.00       # Target 100% ROE (Double Modal)
SHORT_SL_ROE = 1.50        # Stop Loss Khusus SHORT (-150%)

# --- PENGATURAN VOLUME FILTER (CUSTOM USER) ---
VOL_MA_PERIOD = 20         
VOL_MULTIPLIER = 1.2       # Sudah dilonggarkan jadi 1.2x

# --- PENGATURAN DCA DINAMIS 3-TAHAP (HANYA LONG) ---
DCA_1_DROP_PERCENT = 2.0  
DCA_2_DROP_PERCENT = 3.0  
DCA_3_DROP_PERCENT = 4.0  

DCA_1_MARGIN_RATIO = 0.50  
DCA_2_MARGIN_RATIO = 0.50  
DCA_3_MARGIN_RATIO = 1.00  

MAX_VIP, MAX_ALT = 8, 8
EMA_TREND, MA_STRUCT, BB_WINDOW = 200, 99, 20
ATR_WINDOW = 14

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"]
VIP_SET = set(VIP_SYMBOLS)
VIP_TFS = ['15m', '1h', '4h']

ALT_TFS_FAST = ['5m', '15m', '1h', '4h']
ALT_TFS_SAFE = ['15m', '1h', '4h']
ALT_TF_ORDER = ['5m', '15m', '1h', '4h'] 

TOP_ALT_LIMIT = 50
STATE_FILE = 'status.txt'

GOLD_PAIRS = ["PAXGUSDT"]
GOLD_SET = set(GOLD_PAIRS)
GOLD_TFS = ['15m', '1h', '4h']

LEDGER_FILE = 'profit_ledger.txt'

# --- VARIABEL GLOBAL PAPAN SKOR & MEMORI PNL ---
TOTAL_CLOSED_ROE = 0.0
TOTAL_CLOSED_ROE_PERCENT = 0.0 
TOTAL_SUCCESS_TRADES = 0
CLOSED_HISTORY = []
_coin_escalation_level: Dict[str, int] = {} 
_position_memory: Dict[str, float] = {}  # Memori PNL detik terakhir

_client = Client(API_KEY, API_SECRET, testnet=True) 

# ---------- PERFORMANCE CACHING ----------
_exchange_filter_cache: Dict[str, dict] = {}
_ticker_cache: Dict[str, Any] = {"data": None, "timestamp": 0}
_TICKER_CACHE_TTL = 5.0

_RATE_LIMIT_CALLS, _RATE_LIMIT_PERIOD = 20, 1.0
_last_call_time = 0.0
_rate_limit_lock = threading.Lock()

def _rate_limit():
    global _last_call_time
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_call_time
        min_interval = _RATE_LIMIT_PERIOD / _RATE_LIMIT_CALLS
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        _last_call_time = time.monotonic()

def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    for attempt in range(max_retries):
        _rate_limit()
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code != -1121:
                logger.warning(f"⚠️ Binance Error [{fn.__name__}]: {e.message}")
            if e.code in (-1121, -4028, -2011, -2021, -2019):
                raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: {fn.__name__}")

# ========== FUNGSI GRAFIK SALDO & LEDGER DINAMIS ==========
def get_binance_balance() -> float:
    try:
        account_info = _api_call(_client.futures_account)
        for asset in account_info.get('assets', []):
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
    except Exception: pass
    return 0.0

def get_initial_balance() -> float:
    is_new = not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0
    if is_new:
        start_bal = get_binance_balance()
        if start_bal == 0: start_bal = 5000.0
        with open('start_balance.txt', 'w') as f:
            f.write(str(start_bal))
        return start_bal
    else:
        if os.path.exists('start_balance.txt'):
            with open('start_balance.txt', 'r') as f:
                try: return float(f.read().strip())
                except: pass
        return 5000.0

def _fetch_realized_pnl_fallback(symbol: str) -> float:
    try:
        income_data = _api_call(_client.futures_income_history, symbol=symbol, incomeType="REALIZED_PNL", limit=1)
        if income_data:
            return float(income_data[0]['income'])
    except Exception: pass
    return (BASE_MARGIN * TP_TARGET_ROE)

def get_last_ledger_data() -> Tuple[float, float]:
    if not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0:
        return 0.0, 0.0
    try:
        with open(LEDGER_FILE, 'r') as f:
            lines = [l for l in f.readlines() if '|' in l and 'TIME' not in l and '---' not in l]
            if not lines: return 0.0, 0.0
            last_line = lines[-1]
            parts = [p.strip() for p in last_line.split('|')]
            if len(parts) >= 8:
                tot_pnl = float(parts[4].replace('$', '').replace('+', ''))
                tot_roe = float(parts[5].replace('%', '').replace('+', ''))
                return tot_pnl, tot_roe
    except: pass
    return 0.0, 0.0

def catat_transaksi_v2(symbol: str, pnl_usd: float, roe_percent: float):
    prev_tot_pnl, prev_tot_roe = get_last_ledger_data()
    new_tot_pnl = prev_tot_pnl + pnl_usd
    new_tot_roe = prev_tot_roe + roe_percent

    current_balance = get_binance_balance()
    start_balance = get_initial_balance()
    growth_pct = ((current_balance - start_balance) / start_balance) * 100 if start_balance > 0 else 0.0

    now = datetime.now().strftime("%H:%M:%S")
    log_line = (f"{now} | {symbol} | {pnl_usd:+.2f} | {roe_percent:+.2f}% | "
                f"{new_tot_pnl:+.2f} | {new_tot_roe:+.2f}% | "
                f"{current_balance:.2f} | {growth_pct:+.2f}%\n")

    is_new = not os.path.exists(LEDGER_FILE) or os.path.getsize(LEDGER_FILE) == 0
    with open(LEDGER_FILE, 'a') as f:
        if is_new:
            f.write("TIME | PAIR | PROFIT $ | ROE % | TOTAL PNL $ | TOTAL ROE % | SALDO BINANCE | GROWTH %\n")
            f.write("-" * 110 + "\n")
        f.write(log_line)
    logger.info(f"💾 [LEDGER] {symbol} Terekam! Saldo: ${current_balance:.2f} (Growth: {growth_pct:+.2f}%)")

def _get_exchange_filters(symbol: str) -> dict:
    if symbol not in _exchange_filter_cache:
        info = _api_call(_client.futures_exchange_info)
        for s in info['symbols']:
            _exchange_filter_cache[s['symbol']] = {x['filterType']: x for x in s['filters']}
    return _exchange_filter_cache[symbol]

def _get_cached_ticker() -> List[dict]:
    global _ticker_cache
    now = time.time()
    if _ticker_cache["data"] is None or (now - _ticker_cache["timestamp"]) > _TICKER_CACHE_TTL:
        _ticker_cache["data"] = _api_call(_client.futures_ticker)
        _ticker_cache["timestamp"] = now
    return _ticker_cache["data"]

def _read_status() -> str:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return f.read().strip() or 'OFF'
    except Exception: pass
    return 'OFF'

def setup_account_environment() -> None:
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception: pass

def _get_dynamic_leverage_and_margin(symbol: str, target_margin: float) -> Tuple[int, float]:
    target_notional = target_margin * TARGET_LEVERAGE
    try:
        _client.futures_change_leverage(symbol=symbol, leverage=TARGET_LEVERAGE)
        return TARGET_LEVERAGE, target_margin
    except BinanceAPIException as e:
        if e.code == -4028:
            try:
                brackets = _client.futures_leverage_bracket(symbol=symbol)
                max_lev = int(brackets[0]['brackets'][0]['initialLeverage'])
                _client.futures_change_leverage(symbol=symbol, leverage=max_lev)
                adjusted_margin = target_notional / max_lev
                return max_lev, adjusted_margin
            except Exception: return TARGET_LEVERAGE, target_margin
        return TARGET_LEVERAGE, target_margin
    except Exception: return TARGET_LEVERAGE, target_margin

def _is_trend_aligned(symbol: str, side: str) -> bool:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval='15m', limit=210)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])
        close = df['close'].astype(float)
        ema200 = float(ema_indicator(close, window=200).iloc[-1])
        current_price = float(close.iloc[-1])

        if side == 'LONG': return current_price > ema200
        if side == 'SHORT': return current_price < ema200
        return False
    except Exception: return False

# ========== 5-CONFLUENCE SIGNAL LOGIC (CUSTOM USER) ==========
def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])[['open','high','low','close','volume']].astype(float)

        if len(df) < EMA_TREND + 1: return None

        close, high, low, open_px = df['close'], df['high'], df['low'], df['open']

        ema200 = ema_indicator(close, window=EMA_TREND)
        ma99 = sma_indicator(close, window=MA_STRUCT)
        bb = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)
        atr = AverageTrueRange(high, low, close, window=ATR_WINDOW).average_true_range()

        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_MA_PERIOD).mean()
        df.bfill(inplace=True)

        idx_curr, idx_prev = len(df) - 1, len(df) - 2
        c_close, c_low, c_high, c_atr = close.iat[idx_curr], low.iat[idx_curr], high.iat[idx_curr], atr.iat[idx_curr]
        p_open, p_close, p_low, p_high = open_px.iat[idx_prev], close.iat[idx_prev], low.iat[idx_prev], high.iat[idx_prev]

        p_vol = df['volume'].iat[idx_prev]
        vol_ma = df['vol_ma'].iat[idx_prev]

        if p_vol < (vol_ma * VOL_MULTIPLIER): return None 

        c_ema200 = ema200.iat[idx_curr]
        if p_close > p_open and c_close < c_ema200: return None 
        if p_close < p_open and c_close > c_ema200: return None 

        # CUSTOM PROXIMITY & SHADOW
        dynamic_proximity = c_atr * 0.35
        shadow_req = 1.5 if is_vip else 1.0
        c_ma99 = ma99.iat[idx_curr]
        c_bb_dn, c_bb_up = bb.bollinger_lband().iat[idx_curr], bb.bollinger_hband().iat[idx_curr]

        static_support = low.iloc[-100:-2].min()
        static_resistance = high.iloc[-100:-2].max()

        if p_close > p_open: 
            body = abs(p_close - p_open) or 0.00000001
            lower_shadow = min(p_open, p_close) - p_low
            if (lower_shadow / body) >= shadow_req:
                dynamic_floors = [t for t in [c_ema200, c_ma99, c_bb_dn] if t < c_close]
                closest_dynamic = max(dynamic_floors) if dynamic_floors else 0
                hit_dynamic = closest_dynamic > 0 and (abs(c_low - closest_dynamic)) <= dynamic_proximity
                hit_static = static_support > 0 and (abs(c_low - static_support)) <= dynamic_proximity
                if hit_dynamic or hit_static:
                    return {'side': 'LONG', 'reason': f'{"Static Support" if hit_static else "Dynamic Wall"} + Vol Spike'}

        if p_close < p_open: 
            body = abs(p_open - p_close) or 0.00000001
            upper_shadow = p_high - max(p_open, p_close)
            if (upper_shadow / body) >= shadow_req:
                dynamic_ceilings = [t for t in [c_ema200, c_ma99, c_bb_up] if t > c_close]
                closest_dynamic = min(dynamic_ceilings) if dynamic_ceilings else float('inf')
                hit_dynamic = closest_dynamic != float('inf') and (abs(c_high - closest_dynamic)) <= dynamic_proximity
                hit_static = static_resistance > 0 and (abs(c_high - static_resistance)) <= dynamic_proximity
                if hit_dynamic or hit_static:
                    return {'side': 'SHORT', 'reason': f'{"Static Resist" if hit_static else "Dynamic Wall"} + Vol Spike'}

        return None
    except Exception: return None

# ========== EXECUTION ENGINE (INSTANT LIMIT TP) ==========
def execute_order(symbol: str, order_side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
    try:
        f = _get_exchange_filters(symbol)
        qty_step = float(f['LOT_SIZE']['stepSize'])
        min_qty = float(f['LOT_SIZE']['minQty'])
        max_qty = float(f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])['maxQty'])
        tick = float(f['PRICE_FILTER']['tickSize'])
        curr_price = float(_api_call(_client.futures_symbol_ticker, symbol=symbol)['price'])

        actual_lev, adjusted_margin = _get_dynamic_leverage_and_margin(symbol, margin_to_use)

        raw_qty = (adjusted_margin * actual_lev) / curr_price
        qty = round(round(raw_qty / qty_step) * qty_step, 8)
        qty = min(max_qty, max(min_qty, qty))
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')

        # 1. Market Entry
        _api_call(_client.futures_create_order, symbol=symbol, side=order_side, type='MARKET', quantity=qty_str, positionSide=position_side)

        # 2. Instant Limit TP/SL
        if not is_dca:
            price_precision = max(0, -int(math.floor(math.log10(tick))))
            if position_side == 'LONG':
                tp_raw = curr_price * (1 + (TP_TARGET_ROE / actual_lev))
                tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
                try: _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')
                except Exception: pass
            elif position_side == 'SHORT':
                tp_raw = curr_price * (1 - (TP_TARGET_ROE / actual_lev))
                sl_raw = curr_price * (1 + (SHORT_SL_ROE / actual_lev))
                tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
                sl_str = f"{round(round(sl_raw / tick) * tick, price_precision):.{price_precision}f}"
                try:
                    _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')
                    _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=sl_str, closePosition=True, positionSide=position_side, timeInForce='GTC', workingType='MARK_PRICE')
                except Exception: pass

        logger.info(f"🚀 {'DCA' if is_dca else 'ENTRY'} [{position_side}] {symbol} | Margin: ${adjusted_margin:.2f}")
        return True
    except Exception as e: return False

# ========== MONITORING (DCA & VIRTUAL FAILSAFE) ==========
def _monitor_positions(positions: List[dict]):
    global _position_memory
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0: continue 

        symbol, unrealized, mark_price = p['symbol'], float(p['unRealizedProfit']), float(p['markPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))
        pos_side = p['positionSide']

        current_margin = (abs(amt) * mark_price) / actual_lev
        roe_percent = (unrealized / current_margin * 100) if current_margin > 0 else 0
        _, base_adj = _get_dynamic_leverage_and_margin(symbol, BASE_MARGIN)

        key = f"{symbol}_{pos_side}"
        _position_memory[key] = unrealized

        # --- 1. FAILSAFE VIRTUAL TAKE PROFIT (+100%) ---
        if roe_percent >= (TP_TARGET_ROE * 100):
            logger.info(f"💰 VIRTUAL TP TRIGGERED [{symbol}] {roe_percent:.2f}%! Market Close paksa.")
            try:
                close_side = 'SELL' if amt > 0 else 'BUY'
                _api_call(_client.futures_cancel_all_open_orders, symbol=symbol)
                _api_call(_client.futures_create_order, symbol=symbol, side=close_side, type='MARKET', quantity=abs(amt), positionSide=pos_side)
            except Exception as e:
                logger.error(f"Gagal Failsafe TP {symbol}: {e}")
            continue

        # --- 2. FAILSAFE VIRTUAL STOP LOSS SHORT (-150%) ---
        if amt < 0 and roe_percent <= -(SHORT_SL_ROE * 100):
            logger.info(f"🛑 VIRTUAL SL TRIGGERED [{symbol}] {roe_percent:.2f}%! Market Close paksa.")
            try:
                _api_call(_client.futures_cancel_all_open_orders, symbol=symbol)
                _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='MARKET', quantity=abs(amt), positionSide=pos_side)
            except Exception: pass
            continue

        # --- 3. DCA KHUSUS LONG ---
        if amt > 0:
            if roe_percent <= -(DCA_1_DROP_PERCENT * actual_lev) and current_margin < (base_adj + 2.0):
                execute_order(symbol, 'BUY', 'LONG', base_adj * DCA_1_MARGIN_RATIO, is_dca=True)
            elif roe_percent <= -(DCA_2_DROP_PERCENT * actual_lev) and current_margin < (base_adj * (1 + DCA_1_MARGIN_RATIO) + 2.0):
                execute_order(symbol, 'BUY', 'LONG', base_adj * DCA_2_MARGIN_RATIO, is_dca=True)
            elif roe_percent <= -(DCA_3_DROP_PERCENT * actual_lev) and current_margin < (base_adj * (1 + DCA_1_MARGIN_RATIO + DCA_2_MARGIN_RATIO) + 2.0):
                execute_order(symbol, 'BUY', 'LONG', base_adj * DCA_3_MARGIN_RATIO, is_dca=True)

# ---------- SCANNER & MAIN LOOP ----------
def _scan_single_alt(symbol: str, active_keys: List[str], allowed_tfs: List[str]) -> Optional[Tuple[str, dict]]:
    if f"{symbol}_LONG" in active_keys or f"{symbol}_SHORT" in active_keys: return None
    for tf in allowed_tfs:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            if _is_trend_aligned(symbol, sig['side']): return (symbol, sig)
    return None

_stop_event = None
def shutdown_bot():
    global _stop_event
    if _stop_event: _stop_event.set()

def run_bot(stop_event: threading.Event) -> None:
    global _stop_event, TOTAL_CLOSED_ROE, TOTAL_CLOSED_ROE_PERCENT, TOTAL_SUCCESS_TRADES, CLOSED_HISTORY, _coin_escalation_level, _position_memory
    _stop_event = stop_event
    setup_account_environment()
    get_initial_balance() 

    executor = ThreadPoolExecutor(max_workers=5)
    _previous_active_keys = set()
    first_run = True
    _last_heartbeat_time = 0.0

    try:
        while not _stop_event.is_set():
            try:
                if _read_status() != 'ON':
                    time.sleep(10)
                    continue

                pos = _api_call(_client.futures_position_information)
                _monitor_positions(pos)

                active_keys = []
                current_active_set = set()

                for p in pos:
                    amt = float(p['positionAmt'])
                    if amt != 0:
                        key = f"{p['symbol']}_{p['positionSide']}"
                        active_keys.append(key)
                        current_active_set.add(key)

                if not first_run:
                    closed_keys = _previous_active_keys - current_active_set
                    for k in closed_keys:
                        symbol = k.split('_')[0]

                        # Ambil dari Memori
                        pnl_usd = _position_memory.get(k, None)
                        if pnl_usd is None: 
                            pnl_usd = _fetch_realized_pnl_fallback(symbol)

                        roe_percent = (pnl_usd / BASE_MARGIN) * 100 
                        catat_transaksi_v2(symbol, pnl_usd, roe_percent)

                        if k in _position_memory:
                            del _position_memory[k]

                        TOTAL_CLOSED_ROE += roe_percent
                        TOTAL_CLOSED_ROE_PERCENT += roe_percent
                        TOTAL_SUCCESS_TRADES += 1

                        if symbol not in VIP_SET and symbol not in GOLD_SET:
                            curr_level = _coin_escalation_level.get(symbol, 0)
                            _coin_escalation_level[symbol] = curr_level + 1

                        now_str = datetime.now().strftime("%H:%M:%S")
                        CLOSED_HISTORY.insert(0, {'time': now_str, 'symbol': symbol, 'roe': f"{pnl_usd:+.2f}$"})
                        if len(CLOSED_HISTORY) > 20: CLOSED_HISTORY.pop()

                _previous_active_keys = current_active_set
                first_run = False

                vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SET)
                alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SET and k.split('_')[0] not in GOLD_SET)
                gold_active_count = sum(1 for k in active_keys if k.split('_')[0] in GOLD_SET)

                if gold_active_count == 0 and not _stop_event.is_set():
                    for symbol in GOLD_PAIRS:
                        if f"{symbol}_LONG" not in active_keys and f"{symbol}_SHORT" not in active_keys:
                            for tf in GOLD_TFS:
                                sig = get_adaptive_signal(symbol, tf, is_vip=True)
                                if sig:
                                    execute_order(symbol, 'BUY' if sig['side']=='LONG' else 'SELL', sig['side'], BASE_MARGIN)
                                    break 
                            if gold_active_count > 0: break 

                for symbol in VIP_SYMBOLS:
                    if _stop_event.is_set() or vip_count >= MAX_VIP: break
                    if f"{symbol}_LONG" not in active_keys and f"{symbol}_SHORT" not in active_keys:
                        for tf in VIP_TFS:
                            sig = get_adaptive_signal(symbol, tf, is_vip=True)
                            if sig:
                                if execute_order(symbol, 'BUY' if sig['side']=='LONG' else 'SELL', sig['side'], BASE_MARGIN):
                                    vip_count += 1
                                    break

                if alt_count < MAX_ALT and not _stop_event.is_set():
                    tickers = _get_cached_ticker()
                    alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
                            if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SET and t['symbol'] not in GOLD_SET][:TOP_ALT_LIMIT]

                    futures = []
                    for s in alts:
                        base_tfs = ALT_TFS_FAST if alt_count < 4 else ALT_TFS_SAFE
                        esc_level = _coin_escalation_level.get(s, 0)
                        if esc_level >= len(ALT_TF_ORDER): continue
                        valid_tfs = [tf for tf in base_tfs if ALT_TF_ORDER.index(tf) >= esc_level]
                        if not valid_tfs: continue 
                        futures.append(executor.submit(_scan_single_alt, s, active_keys, valid_tfs))

                    for future in as_completed(futures):
                        if _stop_event.is_set(): break
                        res = future.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            if execute_order(symbol, 'BUY' if sig['side']=='LONG' else 'SELL', sig['side'], BASE_MARGIN):
                                alt_count += 1
                                active_keys.append(f"{symbol}_{sig['side']}")
                                current_active_set.add(f"{symbol}_{sig['side']}")
                                _previous_active_keys = current_active_set

                current_time = time.time()
                if current_time - _last_heartbeat_time >= 60.0:
                    logger.info(f"👀 System OK [BETA v3.1.5] | VIP: {vip_count}/{MAX_VIP} | ALT: {alt_count}/{MAX_ALT} | GOLD: {gold_active_count}")
                    _last_heartbeat_time = current_time

                for _ in range(15):
                    if _stop_event.is_set(): break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"Loop Error: {e}")
                time.sleep(10)
    finally:
        executor.shutdown(wait=True)
        logger.info("Bot engine stopped.")

if __name__ == "__main__":
    shutdown_event = threading.Event()
    run_bot(shutdown_event)
