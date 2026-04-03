"""
bot_logic.py — nazBot Alpha 2.0 Core Trading Logic
Optimizations (strategy/formulas/conditions UNTOUCHED):
  1. [PERF]  get_adaptive_signal: semua kolom TA dihitung sekali di akhir slice
  2. [PERF]  DataFrame hanya menyimpan 5 kolom yang dibutuhkan.
  3. [API]   _api_call(): generic retry wrapper dengan exponential backoff.
  4. [API]   _get_exchange_filters(): cache info exchange per-symbol.
  5. [STATE] _read_status(): baca status.txt dengan aman.
  6. [STRUCT] run_bot dipecah ke helper (_scan_vip, _scan_alts).
  7. [TYPE]  Seluruh fungsi publik diberi type hints.
  8. [SAFE]  (Suntikan nazBot) MaxQty Filter, TP Limit Fallback, & VIP Exclusion di Alts.
"""

from __future__ import annotations

import math
import os
import time
import logging
from typing import Optional

import pandas as pd
from ta.trend import ema_indicator, sma_indicator
from ta.volatility import BollingerBands
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger('bot')

# ══════════════════════════════════════════════════════════════
# PARAMETER nazBot Alpha 2.0 (FLEXIBLE ALTS 8 SLOTS + VIP LONG)
# ══════════════════════════════════════════════════════════════
API_KEY    = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

LEVERAGE      = 25
BASE_MARGIN   = 15.0
TP_TARGET_ROE = 0.50

MAX_VIP       = 6   # VIP HANYA LONG
MAX_ALT       = 8   # Altcoin FLEKSIBEL (Total maksimal 8 posisi, bebas LONG/SHORT)

EMA_TREND     = 200
MA_STRUCT     = 99
BB_WINDOW     = 20
VOL_LOOKBACK  = 5

VIP_SYMBOLS   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]
VIP_TF        = '15m'
ALT_TFS       = ['1m', '3m', '5m', '15m', '1h', '4h']   # URUTAN INI TIDAK DIUBAH
TOP_ALT_LIMIT = 50

STATE_FILE    = 'status.txt'
HISTORY_FILE  = 'trades_history.json'

PROXIMITY_PCT = 0.003

_client = Client(API_KEY, API_SECRET, testnet=True)
_exchange_filter_cache: dict[str, dict] = {}


# ══════════════════════════════════════════════════════════════
# HELPERS: API ROBUSTNESS
# ══════════════════════════════════════════════════════════════

def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            # FIX: Tambahkan error mutlak agar tidak di-retry (-2021 TP, -4005 MaxQty, -2027 MaxPos)
            if e.code in (-1003, -2019, -1102, -2021, -4005, -2027, -2011):
                raise
            wait = 2 ** attempt
            logger.warning(f"BinanceAPIException (code {e.code}) — retry {attempt+1}/{max_retries} dalam {wait}s: {e.message}")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"API error — retry {attempt+1}/{max_retries} dalam {wait}s: {e}")
            time.sleep(wait)
    raise RuntimeError(f"API call gagal setelah {max_retries} percobaan: {fn.__name__}")


def _get_exchange_filters(symbol: str) -> dict:
    if symbol not in _exchange_filter_cache:
        info = _api_call(_client.futures_exchange_info)
        for s in info['symbols']:
            filters = {x['filterType']: x for x in s['filters']}
            _exchange_filter_cache[s['symbol']] = filters
    return _exchange_filter_cache[symbol]


# ══════════════════════════════════════════════════════════════
# HELPERS: STATE
# ══════════════════════════════════════════════════════════════

def _read_status() -> str:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return f.read().strip() or 'OFF'
    except OSError:
        pass
    return 'OFF'

def _active_keys(positions: list[dict]) -> list[str]:
    return [
        f"{p['symbol']}_{p['positionSide']}"
        for p in positions
        if float(p['positionAmt']) != 0
    ]

def setup_account_environment() -> None:
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
# CORE SIGNAL LOGIC
# ══════════════════════════════════════════════════════════════

def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[str]:
    try:
        bars = _api_call(
            _client.futures_klines,
            symbol=symbol, interval=tf, limit=300
        )

        df = pd.DataFrame(bars, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            'ct', 'qv', 'tr', 'tb', 'tq', 'i'
        ])[['open', 'high', 'low', 'close', 'volume']].astype(float)

        if len(df) < EMA_TREND + 1:
            return None

        close       = df['close']
        ema200      = ema_indicator(close, window=EMA_TREND)
        ma99        = sma_indicator(close, window=MA_STRUCT)
        bb          = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)
        bb_up_s     = bb.bollinger_hband()
        bb_dn_s     = bb.bollinger_lband()

        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_LOOKBACK).mean()
        df.bfill(inplace=True)

        idx_curr = len(df) - 1
        idx_prev = idx_curr - 1

        c_close  = close.iat[idx_curr]
        c_low    = df['low'].iat[idx_curr]
        c_high   = df['high'].iat[idx_curr]
        c_ema200 = ema200.iat[idx_curr]
        c_ma99   = ma99.iat[idx_curr]
        c_bb_dn  = bb_dn_s.iat[idx_curr]
        c_bb_up  = bb_up_s.iat[idx_curr]

        p_open   = df['open'].iat[idx_prev]
        p_close  = close.iat[idx_prev]
        p_high   = df['high'].iat[idx_prev]
        p_low    = df['low'].iat[idx_prev]
        p_volume = df['volume'].iat[idx_prev]
        p_vol_ma = df['vol_ma'].iat[idx_prev]

        is_uptrend       = c_close > c_ema200
        is_downtrend     = c_close < c_ema200
        is_vol_exhausted = p_volume < p_vol_ma    

        shadow_req = 2.0 if is_vip else 0.8

        # LONG LOGIC
        if is_uptrend:
            tembok_bawah = [c_ema200, c_ma99, c_bb_dn]
            floors = [t for t in tembok_bawah if t < c_close]
            closest_floor = max(floors) if floors else 0

            if closest_floor > 0:
                dist = abs(c_low - closest_floor) / closest_floor

                if dist <= PROXIMITY_PCT and is_vol_exhausted and p_close > p_open:
                    lower_shadow = min(p_open, p_close) - p_low
                    body = abs(p_close - p_open) or 0.00000001
                    if (lower_shadow / body) >= shadow_req:
                        return 'LONG'

        # SHORT LOGIC
        if is_downtrend and not is_vip:
            tembok_atas = [c_ema200, c_ma99, c_bb_up]
            ceilings = [t for t in tembok_atas if t > c_close]
            closest_ceiling = min(ceilings) if ceilings else 9_999_999

            if closest_ceiling < 9_999_999:
                dist = abs(c_high - closest_ceiling) / closest_ceiling

                if dist <= PROXIMITY_PCT and is_vol_exhausted and p_close < p_open:
                    upper_shadow = p_high - max(p_open, p_close)
                    body = abs(p_close - p_open) or 0.00000001
                    if (upper_shadow / body) >= shadow_req:
                        return 'SHORT'

        return None

    except Exception as e:
        logger.error(f"Error Analisa [{symbol} TF {tf}]: {e}")
        return None


# ══════════════════════════════════════════════════════════════
# ORDER EXECUTION
# ══════════════════════════════════════════════════════════════

def execute_adaptive_order(symbol: str, side: str, position_side: str, tf: str) -> bool:
    try:
        f = _get_exchange_filters(symbol)

        # FIX: Max Qty Filter dari Market Lot Size
        qty_step = float(f['LOT_SIZE']['stepSize'])
        min_qty  = float(f['LOT_SIZE']['minQty'])
        market_lot = f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])
        max_qty  = float(market_lot['maxQty'])
        tick     = float(f['PRICE_FILTER']['tickSize'])

        try:
            _api_call(_client.futures_change_leverage, symbol=symbol, leverage=LEVERAGE)
        except Exception:
            pass

        curr_price = float(
            _api_call(_client.futures_symbol_ticker, symbol=symbol)['price']
        )

        raw_qty = (BASE_MARGIN * LEVERAGE) / curr_price
        qty = round(math.floor(raw_qty / qty_step) * qty_step, 8)
        
        # FIX: Menjepit kuantitas agar sesuai aturan bursa
        qty = min(max_qty, max(min_qty, qty))

        price_move = TP_TARGET_ROE / LEVERAGE
        tp_raw = (
            curr_price * (1 + price_move) if side == 'BUY'
            else curr_price * (1 - price_move)
        )

        price_precision = max(0, -int(math.floor(math.log10(tick))))
        tp_final = round(round(tp_raw / tick) * tick, price_precision)
        tp_str   = f"{tp_final:.{price_precision}f}"
        qty_str  = f"{qty:.8f}".rstrip('0').rstrip('.')

        # 1. Entry Market
        _api_call(
            _client.futures_create_order,
            symbol=symbol, side=side, type='MARKET',
            quantity=qty_str, positionSide=position_side
        )

        # 2. TP dengan Fallback System
        try:
            _api_call(
                _client.futures_create_order,
                symbol=symbol,
                side='SELL' if side == 'BUY' else 'BUY',
                type='TAKE_PROFIT_MARKET',
                stopPrice=tp_str,
                closePosition=True,
                positionSide=position_side,
                timeInForce='GTE_GTC',
                workingType='MARK_PRICE'
            )
        except BinanceAPIException as tp_err:
            if tp_err.code == -2021 or '-2021' in str(tp_err):
                logger.warning(f"⚠️ Market terlalu cepat untuk {symbol}, pakai TP Limit Fallback.")
                _api_call(
                    _client.futures_create_order,
                    symbol=symbol,
                    side='SELL' if side == 'BUY' else 'BUY',
                    type='LIMIT',
                    price=tp_str,
                    quantity=qty_str,
                    positionSide=position_side,
                    timeInForce='GTC'
                )
            else:
                raise tp_err

        mode_text = "VIP LONG" if symbol in VIP_SYMBOLS else "ALT SCALP"
        logger.info(f"🎯 {mode_text} [{symbol} {position_side}] di TF {tf} | 3-Walls Adaptive")
        return True

    except Exception as e:
        logger.error(f"Order Fail [{symbol}]: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# SCAN HELPERS
# ══════════════════════════════════════════════════════════════

def _scan_vip(active_keys: list[str], vip_count: int) -> tuple[list[str], int]:
    for symbol in VIP_SYMBOLS:
        if vip_count >= MAX_VIP:
            break
        if f"{symbol}_LONG" in active_keys:
            continue

        signal = get_adaptive_signal(symbol, VIP_TF, is_vip=True)
        if signal == 'LONG':
            if execute_adaptive_order(symbol, 'BUY', 'LONG', VIP_TF):
                vip_count += 1
                active_keys.append(f"{symbol}_LONG")
        time.sleep(0.5)

    return active_keys, vip_count


def _scan_alts(active_keys: list[str], alt_count: int) -> tuple[list[str], int]:
    tickers = _api_call(_client.futures_ticker)
    
    # FIX: Pastikan VIP_SYMBOLS tidak ikut di-scan di Hunter Squad (Altcoin)
    alts = [
        t['symbol']
        for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
        if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SYMBOLS
    ][:TOP_ALT_LIMIT]

    for symbol in alts:
        if alt_count >= MAX_ALT:
            break
        if f"{symbol}_LONG" in active_keys or f"{symbol}_SHORT" in active_keys:
            continue

        for tf in ALT_TFS:
            signal = get_adaptive_signal(symbol, tf, is_vip=False)
            if signal:
                side = 'BUY' if signal == 'LONG' else 'SELL'
                if execute_adaptive_order(symbol, side, signal, tf):
                    alt_count += 1
                    active_keys.append(f"{symbol}_{signal}")
                break
            time.sleep(0.2)

    return active_keys, alt_count


# ══════════════════════════════════════════════════════════════
# MAIN BOT LOOP
# ══════════════════════════════════════════════════════════════

def run_bot() -> None:
    setup_account_environment()

    while True:
        try:
            if _read_status() != 'ON':
                time.sleep(10)
                continue

            pos         = _api_call(_client.futures_position_information)
            active_keys = _active_keys(pos)

            vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SYMBOLS)
            alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SYMBOLS)

            if vip_count < MAX_VIP:
                active_keys, vip_count = _scan_vip(active_keys, vip_count)

            if alt_count < MAX_ALT:
                active_keys, alt_count = _scan_alts(active_keys, alt_count)

            time.sleep(15)

        except Exception as e:
            logger.error(f"Loop Error: {e}", exc_info=True)
            time.sleep(10)
