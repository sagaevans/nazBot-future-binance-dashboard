"""
bot_logic.py — nazBot Alpha 4.0 PRO
Fitur: Concurrency, ATR Dynamic Support, & Dynamic Margin Balancing.
"""

from __future__ import annotations
import math, os, time, logging, random
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
TP_TARGET_ROE = 1.00

# DCA Levels (Absolut USD Power yang diinginkan)
DCA_1_TRIGGER, DCA_1_AMOUNT = -1.00, 3.0
DCA_2_TRIGGER, DCA_2_AMOUNT = -1.50, 3.0
DCA_3_TRIGGER, DCA_3_AMOUNT = -3.00, 10.0

MAX_VIP, MAX_ALT = 8, 8
EMA_TREND, MA_STRUCT, BB_WINDOW, VOL_LOOKBACK = 200, 99, 20, 5
ATR_WINDOW = 14

VIP_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT", "XRPUSDT", "ALICEUSDT"]
VIP_SET = set(VIP_SYMBOLS)
VIP_TFS = ['15m', '1h', '4h']
ALT_TFS = ['5m', '15m', '1h', '4h']

TOP_ALT_LIMIT = 50
STATE_FILE = 'status.txt'

_client = Client(API_KEY, API_SECRET, testnet=True)

# ---------- PERFORMANCE CACHING ----------
_exchange_filter_cache: Dict[str, dict] = {}
_ticker_cache: Dict[str, Any] = {"data": None, "timestamp": 0}
_TICKER_CACHE_TTL = 5.0

_RATE_LIMIT_CALLS, _RATE_LIMIT_PERIOD = 20, 1.0 
_last_call_time = 0.0

def _rate_limit():
    global _last_call_time
    now = time.monotonic()
    elapsed = now - _last_call_time
    if elapsed < _RATE_LIMIT_PERIOD / _RATE_LIMIT_CALLS:
        time.sleep((_RATE_LIMIT_PERIOD / _RATE_LIMIT_CALLS) - elapsed)
    _last_call_time = time.monotonic()

def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    for attempt in range(max_retries):
        _rate_limit()
        try: return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code in (-4028, -2011, -2021): raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception: time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: {fn.__name__}")

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
            with open(STATE_FILE, 'r') as f: return f.read().strip() or 'OFF'
    except Exception: pass
    return 'OFF'

def setup_account_environment() -> None:
    try: _client.futures_change_position_mode(dualSidePosition=True)
    except Exception: pass

def _get_dynamic_leverage_and_margin(symbol: str, target_margin: float) -> Tuple[int, float]:
    """Mengunci Notional Value agar ukuran barang yang dibeli selalu sama meski leverage turun."""
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

# ========== PRO SIGNAL LOGIC (ATR & 4 WALLS) ==========
def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])[['open','high','low','close','volume']].astype(float)

        if len(df) < EMA_TREND + 1: return None

        close, high, low = df['close'], df['high'], df['low']
        ema200 = ema_indicator(close, window=EMA_TREND)
        ma99 = sma_indicator(close, window=MA_STRUCT)
        bb = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)
        rsi = RSIIndicator(close, window=14).rsi()
        atr = AverageTrueRange(high, low, close, window=ATR_WINDOW).average_true_range()

        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_LOOKBACK).mean()
        df.bfill(inplace=True)

        idx_curr, idx_prev = len(df) - 1, len(df) - 2
        c_close, c_low, c_atr = close.iat[idx_curr], low.iat[idx_curr], atr.iat[idx_curr]
        p_open, p_close, p_low = df['open'].iat[idx_prev], close.iat[idx_prev], low.iat[idx_prev]

        # 1. VOLUME EXHAUSTION
        if df['volume'].iat[idx_prev] >= df['vol_ma'].iat[idx_prev]: return None

        # 2. CANDLE REJECTION (Shadow)
        if p_close <= p_open: return None
        body = abs(p_close - p_open) or 0.00000001
        shadow_req = 2.0 if is_vip else 1.2
        if ((min(p_open, p_close) - p_low) / body) < shadow_req: return None

        # 3. ATR DYNAMIC PROXIMITY
        dynamic_proximity = c_atr * 0.15

        c_ema200, c_ma99, c_bb_dn = ema200.iat[idx_curr], ma99.iat[idx_curr], bb.bollinger_lband().iat[idx_curr]
        dynamic_floors = [t for t in [c_ema200, c_ma99, c_bb_dn] if t < c_close]
        closest_dynamic = max(dynamic_floors) if dynamic_floors else 0
        hit_dynamic = closest_dynamic > 0 and (abs(c_low - closest_dynamic)) <= dynamic_proximity

        static_support = low.iloc[-100:-5].min()
        hit_static = static_support > 0 and (abs(c_low - static_support)) <= dynamic_proximity

        if hit_dynamic or hit_static:
            reason = "Dynamic Wall" if hit_dynamic else "Static Support"
            if rsi.iat[idx_curr] < 35: reason += " + OVERSOLD"
            return {'side': 'LONG', 'reason': reason}

        return None
    except Exception: return None

# ---------- EXECUTION ENGINE ----------
def execute_order(symbol: str, side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
    try:
        f = _get_exchange_filters(symbol)
        qty_step = float(f['LOT_SIZE']['stepSize'])
        min_qty = float(f['LOT_SIZE']['minQty'])
        max_qty = float(f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])['maxQty'])
        tick = float(f['PRICE_FILTER']['tickSize'])
        curr_price = float(_api_call(_client.futures_symbol_ticker, symbol=symbol)['price'])

        # DYNAMIC MARGIN CALCULATION
        actual_lev, adjusted_margin = _get_dynamic_leverage_and_margin(symbol, margin_to_use)

        raw_qty = (adjusted_margin * actual_lev) / curr_price
        qty = round(round(raw_qty / qty_step) * qty_step, 8)
        qty = min(max_qty, max(min_qty, qty))
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')

        _api_call(_client.futures_create_order, symbol=symbol, side=side, type='MARKET', quantity=qty_str, positionSide=position_side)

        if not is_dca:
            tp_raw = curr_price * (1 + (TP_TARGET_ROE / actual_lev))
            price_precision = max(0, -int(math.floor(math.log10(tick))))
            tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
            try: _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=tp_str, closePosition=True, positionSide=position_side, timeInForce='GTE_GTC', workingType='MARK_PRICE')
            except Exception: _api_call(_client.futures_create_order, symbol=symbol, side='SELL', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')

        logger.info(f"🚀 {'DCA' if is_dca else 'ENTRY'} [{symbol}] Margin Terpakai: ${adjusted_margin:.2f} | Lev: {actual_lev}x")
        return True
    except Exception as e:
        logger.error(f"Order Gagal [{symbol}]: {e}")
        return False

# ---------- DCA MONITOR ----------
def _monitor_positions(positions: List[dict]):
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0: continue
        symbol, unrealized, mark_price = p['symbol'], float(p['unRealizedProfit']), float(p['markPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))

        # Hitung Margin berdasarkan Lot yang dibeli (bukan sekadar baca angka margin)
        current_margin = (abs(amt) * mark_price) / actual_lev
        roe = (unrealized / current_margin) if current_margin > 0 else 0

        # Kompensasi Nilai Margin DCA agar sinkron dengan limit Leverage
        _, dca1_adj = _get_dynamic_leverage_and_margin(symbol, DCA_1_AMOUNT)
        _, dca2_adj = _get_dynamic_leverage_and_margin(symbol, DCA_2_AMOUNT)
        _, dca3_adj = _get_dynamic_leverage_and_margin(symbol, DCA_3_AMOUNT)
        _, base_adj = _get_dynamic_leverage_and_margin(symbol, BASE_MARGIN)

        if roe <= DCA_1_TRIGGER and current_margin < (base_adj + 2.0):
            logger.info(f"💉 DCA TAHAP 1 untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_1_AMOUNT, is_dca=True)
        elif roe <= DCA_2_TRIGGER and current_margin < (base_adj + dca1_adj + 2.0):
            logger.info(f"💉 DCA TAHAP 2 untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_2_AMOUNT, is_dca=True)
        elif roe <= DCA_3_TRIGGER and current_margin < (base_adj + dca1_adj + dca2_adj + 2.0):
            logger.info(f"🔥 DCA TAHAP 3 TERAKHIR untuk {symbol}")
            execute_order(symbol, 'BUY', 'LONG', DCA_3_AMOUNT, is_dca=True)

# ---------- PARALLEL SCANNER ----------
def _scan_single_alt(symbol: str, active_keys: List[str]):
    if f"{symbol}_LONG" in active_keys: return None
    for tf in ALT_TFS:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            logger.info(f"🎯 PRO Sinyal {symbol} ({tf}) via {sig['reason']}")
            return (symbol, sig)
    return None

# ---------- MAIN LOOP ----------
def run_bot() -> None:
    setup_account_environment()
    while True:
        try:
            if _read_status() != 'ON':
                time.sleep(10); continue

            pos = _api_call(_client.futures_position_information)
            _monitor_positions(pos)
            active_keys = [f"{p['symbol']}_{p['positionSide']}" for p in pos if float(p['positionAmt']) != 0]

            vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SET)
            alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SET)

            # VIP SCAN (Parallel TFs per symbol)
            for symbol in VIP_SYMBOLS:
                if vip_count >= MAX_VIP: break
                if f"{symbol}_LONG" not in active_keys:
                    for tf in VIP_TFS:
                        sig = get_adaptive_signal(symbol, tf, is_vip=True)
                        if sig:
                            logger.info(f"👑 VIP Sinyal {symbol} ({tf}) via {sig['reason']}")
                            if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                vip_count += 1; active_keys.append(f"{symbol}_LONG")
                                break

            # ALT SCAN (Parallel ThreadPool Executor)
            if alt_count < MAX_ALT:
                tickers = _get_cached_ticker()
                alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True) if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SET][:TOP_ALT_LIMIT]

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(_scan_single_alt, s, active_keys) for s in alts]
                    for f in as_completed(futures):
                        res = f.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                                alt_count += 1; active_keys.append(f"{symbol}_LONG")

            time.sleep(15)
        except Exception as e:
            logger.error(f"Loop Error: {e}"); time.sleep(10)

if __name__ == "__main__":
    run_bot()
