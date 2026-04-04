"""
bot_logic.py — nazBot Alpha 2.0 (LONG ONLY, 50x Auto-Lev, DCA Berlapis + 4th Wall S/R)
- Mode: LONG ONLY (VIP & ALT)
- Leverage: 50x (Auto turun ke batas maksimal jika ditolak)
- Base Margin: $5
- TP Target: 100% ROE
- DCA Trigger: Tahap 1 (-100% = $3), Tahap 2 (-150% = $3), Tahap 3 (-300% = $10)
- Entry Logic: 3 Tembok Dinamis (EMA/SMA/BB) ATAU 1 Tembok Statis (Historical Support)
- Stop Loss: DISABLED (No SL / Mode HODL)
"""

from __future__ import annotations
import math, os, time, logging
from typing import Optional
import pandas as pd
from ta.trend import ema_indicator, sma_indicator
from ta.volatility import BollingerBands
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger('bot')

API_KEY    = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

# --- PENGATURAN MUTLAK BOT ---
LEVERAGE      = 50
BASE_MARGIN   = 5.0      # Margin Awal
TP_TARGET_ROE = 1.00     # 100% TP

# --- LOGIKA DCA BERTAHAP ---
DCA_1_TRIGGER = -1.00    # -100% ROE
DCA_1_AMOUNT  = 3.0      # Tembak $3

DCA_2_TRIGGER = -1.50    # -150% ROE
DCA_2_AMOUNT  = 3.0      # Tembak $3

DCA_3_TRIGGER = -3.00    # -300% ROE
DCA_3_AMOUNT  = 10.0     # Tembak $10

MAX_VIP       = 6
MAX_ALT       = 8

EMA_TREND     = 200
MA_STRUCT     = 99
BB_WINDOW     = 20
VOL_LOOKBACK  = 5

VIP_SYMBOLS   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT", "DOTUSDT"]
VIP_TF        = '15m'
ALT_TFS       = ['1m', '3m', '5m', '15m', '1h', '4h']
TOP_ALT_LIMIT = 50

STATE_FILE    = 'status.txt'
PROXIMITY_PCT = 0.003

_client = Client(API_KEY, API_SECRET, testnet=True)
_exchange_filter_cache: dict[str, dict] = {}

# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════
def _api_call(fn, *args, max_retries: int = 5, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code in (-1003, -2019, -1102, -2021, -4005, -2027, -2011, -4028):
                raise
            wait = 2 ** attempt
            logger.warning(f"API Retry {attempt+1}/{max_retries} [{e.code}]: {e.message}")
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            time.sleep(wait)
    raise RuntimeError(f"API call gagal: {fn.__name__}")

def _get_exchange_filters(symbol: str) -> dict:
    if symbol not in _exchange_filter_cache:
        info = _api_call(_client.futures_exchange_info)
        for s in info['symbols']:
            _exchange_filter_cache[s['symbol']] = {x['filterType']: x for x in s['filters']}
    return _exchange_filter_cache[symbol]

def _read_status() -> str:
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                return f.read().strip() or 'OFF'
    except OSError: pass
    return 'OFF'

def _active_keys(positions: list[dict]) -> list[str]:
    return [f"{p['symbol']}_{p['positionSide']}" for p in positions if float(p['positionAmt']) != 0]

def setup_account_environment() -> None:
    try: _client.futures_change_position_mode(dualSidePosition=True)
    except Exception: pass

# ══════════════════════════════════════════════════════════════
# AUTO-LEVERAGE (MENCEGAH ERROR -4028)
# ══════════════════════════════════════════════════════════════
def _set_safe_leverage(symbol: str, target_lev: int) -> int:
    try:
        _client.futures_change_leverage(symbol=symbol, leverage=target_lev)
        return target_lev
    except BinanceAPIException as e:
        if e.code == -4028:  
            try:
                brackets = _client.futures_leverage_bracket(symbol=symbol)
                max_lev = int(brackets[0]['brackets'][0]['initialLeverage'])
                _client.futures_change_leverage(symbol=symbol, leverage=max_lev)
                logger.info(f"⚠️ Leverage {target_lev}x ditolak untuk {symbol}. Otomatis pakai mentok: {max_lev}x")
                return max_lev
            except Exception: return target_lev
        return target_lev
    except Exception: return target_lev

# ══════════════════════════════════════════════════════════════
# SIGNAL LOGIC (4 TEMBOK: DINAMIS + STATIS HISTORIS)
# ══════════════════════════════════════════════════════════════
def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])[['open','high','low','close','volume']].astype(float)

        if len(df) < EMA_TREND + 1: return None

        close = df['close']
        ema200 = ema_indicator(close, window=EMA_TREND)
        ma99 = sma_indicator(close, window=MA_STRUCT)
        bb = BollingerBands(close=close, window=BB_WINDOW, window_dev=2)

        df['vol_ma'] = df['volume'].shift(1).rolling(window=VOL_LOOKBACK).mean()
        df.bfill(inplace=True)

        idx_curr, idx_prev = len(df) - 1, len(df) - 2
        c_close, c_low = close.iat[idx_curr], df['low'].iat[idx_curr]
        c_ema200, c_ma99, c_bb_dn = ema200.iat[idx_curr], ma99.iat[idx_curr], bb.bollinger_lband().iat[idx_curr]
        p_open, p_close, p_low = df['open'].iat[idx_prev], close.iat[idx_prev], df['low'].iat[idx_prev]

        is_vol_exhausted = df['volume'].iat[idx_prev] < df['vol_ma'].iat[idx_prev]    
        shadow_req = 2.0 if is_vip else 0.8

        # Tembok 1, 2, 3 (Dinamis: EMA, SMA, BB)
        dynamic_floors = [t for t in [c_ema200, c_ma99, c_bb_dn] if t < c_close]
        closest_dynamic = max(dynamic_floors) if dynamic_floors else 0
        hit_dynamic = closest_dynamic > 0 and (abs(c_low - closest_dynamic) / closest_dynamic) <= PROXIMITY_PCT

        # Tembok 4 (Statis/Historis: Titik Support Terendah dari 100 candle, abaikan 5 candle terakhir)
        static_support = df['low'].iloc[-100:-5].min()
        hit_static = static_support > 0 and (abs(c_low - static_support) / static_support) <= PROXIMITY_PCT

        # Evaluasi (Pilih jalur mana saja yang kena)
        if hit_dynamic or hit_static:
            if is_vol_exhausted and p_close > p_open:  # Candle Rejection Bullish
                body = abs(p_close - p_open) or 0.00000001
                if ((min(p_open, p_close) - p_low) / body) >= shadow_req:
                    # Tentukan alasan mantul untuk dicatat di log
                    reason = "Tembok Dinamis (EMA/SMA/BB)" if hit_dynamic else "Tembok Statis (Historical Support)"
                    return {'side': 'LONG', 'reason': reason}
        return None
    except Exception: return None

# ══════════════════════════════════════════════════════════════
# EXECUTION
# ══════════════════════════════════════════════════════════════
def execute_order(symbol: str, side: str, position_side: str, margin_to_use: float, is_dca: bool = False) -> bool:
    try:
        f = _get_exchange_filters(symbol)
        qty_step, min_qty, max_qty = float(f['LOT_SIZE']['stepSize']), float(f['LOT_SIZE']['minQty']), float(f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])['maxQty'])
        tick = float(f['PRICE_FILTER']['tickSize'])

        actual_lev = _set_safe_leverage(symbol, LEVERAGE)
        curr_price = float(_api_call(_client.futures_symbol_ticker, symbol=symbol)['price'])

        raw_qty = (margin_to_use * actual_lev) / curr_price
        qty = round(math.floor(raw_qty / qty_step) * qty_step, 8)
        qty = min(max_qty, max(min_qty, qty))
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')

        _api_call(_client.futures_create_order, symbol=symbol, side=side, type='MARKET', quantity=qty_str, positionSide=position_side)

        # Hanya set TP saat Entry pertama
        if not is_dca:
            price_move = TP_TARGET_ROE / actual_lev
            tp_raw = curr_price * (1 + price_move)
            price_precision = max(0, -int(math.floor(math.log10(tick))))
            tp_str = f"{round(round(tp_raw / tick) * tick, price_precision):.{price_precision}f}"
            try:
                _api_call(_client.futures_create_order, symbol=symbol, side='SELL', 
                          type='TAKE_PROFIT_MARKET', stopPrice=tp_str, closePosition=True, 
                          positionSide=position_side, timeInForce='GTE_GTC', workingType='MARK_PRICE')
            except BinanceAPIException as tp_err:
                _api_call(_client.futures_create_order, symbol=symbol, side='SELL', 
                          type='LIMIT', price=tp_str, quantity=qty_str, positionSide=position_side, timeInForce='GTC')

        logger.info(f"🚀 {'DCA' if is_dca else 'ENTRY'} [{symbol} {position_side}] Margin: ${margin_to_use} | Lev: {actual_lev}x | Harga: {curr_price}")
        return True
    except Exception as e:
        logger.error(f"Order Fail [{symbol}]: {e}")
        return False

# ══════════════════════════════════════════════════════════════
# DCA MONITOR (3 TAHAP: $3, $3, $10)
# ══════════════════════════════════════════════════════════════
def _monitor_positions(positions: list[dict]):
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0: continue

        symbol = p['symbol']
        unrealized = float(p['unRealizedProfit'])
        mark_price = float(p['markPrice'])
        actual_lev = float(p.get('leverage', LEVERAGE))

        current_margin = (abs(amt) * mark_price) / actual_lev
        roe = (unrealized / current_margin) if current_margin > 0 else 0

        # TAHAP 1 (-100%) -> Jika margin masih di kisaran margin awal ($5)
        if roe <= DCA_1_TRIGGER and current_margin < (BASE_MARGIN + 2.0):
            logger.info(f"💉 DCA TAHAP 1 (-100% ROE) untuk {symbol}. Nembak ${DCA_1_AMOUNT}!")
            execute_order(symbol, 'BUY', 'LONG', DCA_1_AMOUNT, is_dca=True)

        # TAHAP 2 (-150%) -> Jika margin di kisaran setelah DCA 1 ($5 + $3 = $8)
        elif roe <= DCA_2_TRIGGER and current_margin < (BASE_MARGIN + DCA_1_AMOUNT + 2.0):
            logger.info(f"💉 DCA TAHAP 2 (-150% ROE) untuk {symbol}. Nembak ${DCA_2_AMOUNT}!")
            execute_order(symbol, 'BUY', 'LONG', DCA_2_AMOUNT, is_dca=True)

        # TAHAP 3 (-300%) -> Jika margin di kisaran setelah DCA 2 ($5 + $3 + $3 = $11)
        elif roe <= DCA_3_TRIGGER and current_margin < (BASE_MARGIN + DCA_1_AMOUNT + DCA_2_AMOUNT + 2.0):
            logger.info(f"🔥 DCA TAHAP 3 TERAKHIR (-300% ROE) untuk {symbol}. Nembak ${DCA_3_AMOUNT}!")
            execute_order(symbol, 'BUY', 'LONG', DCA_3_AMOUNT, is_dca=True)

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

            pos = _api_call(_client.futures_position_information)
            _monitor_positions(pos)

            active_keys = _active_keys(pos)
            vip_count = sum(1 for k in active_keys if k.split('_')[0] in VIP_SYMBOLS)
            alt_count = sum(1 for k in active_keys if k.split('_')[0] not in VIP_SYMBOLS)

            # --- VIP SCAN ---
            for symbol in VIP_SYMBOLS:
                if vip_count >= MAX_VIP: break
                if f"{symbol}_LONG" not in active_keys:
                    sig = get_adaptive_signal(symbol, VIP_TF, is_vip=True)
                    if sig:
                        logger.info(f"🎯 Sinyal Ditemukan [{symbol}] via {sig['reason']}")
                        if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                            vip_count += 1
                            active_keys.append(f"{symbol}_LONG")

            # --- ALT SCAN ---
            tickers = _api_call(_client.futures_ticker)
            alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True) if t['symbol'].endswith('USDT') and t['symbol'] not in VIP_SYMBOLS][:TOP_ALT_LIMIT]

            for symbol in alts:
                if alt_count >= MAX_ALT: break
                if f"{symbol}_LONG" in active_keys: continue 

                for tf in ALT_TFS:
                    sig = get_adaptive_signal(symbol, tf, is_vip=False)
                    if sig:
                        logger.info(f"🎯 Sinyal Ditemukan [{symbol} di TF {tf}] via {sig['reason']}")
                        if execute_order(symbol, 'BUY', 'LONG', BASE_MARGIN):
                            alt_count += 1
                            active_keys.append(f"{symbol}_LONG")
                        break
                    time.sleep(0.2)
            time.sleep(15)
        except Exception as e:
            logger.error(f"Loop Error: {e}", exc_info=True)
            time.sleep(10)

if __name__ == "__main__":
    run_bot()
