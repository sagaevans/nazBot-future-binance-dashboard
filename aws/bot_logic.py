# ==========================================
# nazBot Sniper System [RC v5.2 - REAL ACCOUNT MODE]
# FILE: bot_logic.py
# FUNGSI: Fixed Notional 50 USDT, Smart Limit Maker, Order Upgrading, Fear & Greed
# ==========================================

from __future__ import annotations
import math
import os
import time
import logging
import random
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from ta.trend import ema_indicator, sma_indicator
from ta.volatility import BollingerBands, AverageTrueRange
from ta.momentum import RSIIndicator
from binance.client import Client
from binance.exceptions import BinanceAPIException

# --- IMPOR AKUNTAN (LEDGER MANAGER) ---
from ledger_manager import get_initial_balance, catat_transaksi_v2

logger = logging.getLogger('bot')

API_KEY = os.environ.get('BINANCE_API_KEY', '')
API_SECRET = os.environ.get('BINANCE_API_SECRET', '')

TARGET_LEVERAGE = 50
TARGET_NOTIONAL_SIZE = 50.0
BASE_MARGIN = TARGET_NOTIONAL_SIZE / TARGET_LEVERAGE
TP_TARGET_ROE = 1.00
SHORT_SL_ROE = 1.00
MAX_FEAR_SCORE_FOR_VIP = 45
VOL_MA_PERIOD = 20
VOL_MULTIPLIER = 1.2
MIN_24H_VOLUME = 1_000_000.0

DCA_STAGES = [
    (-100.0, 1.0),
    (-200.0, 1.0),
    (-300.0, 2.0),
    (-400.0, 4.0),
    (-600.0, 5.0),
    (-800.0, 7.0),
    (-1000.0, 10.0)
]

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

TOTAL_CLOSED_ROE = 0.0
TOTAL_CLOSED_ROE_PERCENT = 0.0
TOTAL_SUCCESS_TRADES = 0
CLOSED_HISTORY = []
_coin_escalation_level: Dict[str, int] = {}
_position_memory: Dict[str, float] = {}
_limit_order_memory: Dict[str, str] = {}

_fear_greed_score: int = 50
_fear_greed_last_update: float = 0.0

_client = Client(API_KEY, API_SECRET, testnet=True)

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
                logger.warning(f"[WARNING] Binance Error [{fn.__name__}]: {e.message}")
            if e.code in (-1121, -4028, -2011, -2021, -2019):
                raise
            time.sleep(2 ** attempt + random.uniform(0, 1))
        except Exception:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"API Error: {fn.__name__}")

def update_fear_greed_index() -> int:
    global _fear_greed_score, _fear_greed_last_update
    current_time = time.time()
    if current_time - _fear_greed_last_update > 3600:
        try:
            response = requests.get('https://api.alternative.me/fng/?limit=1')
            if response.status_code == 200:
                data = response.json()
                _fear_greed_score = int(data['data'][0]['value'])
                _fear_greed_last_update = current_time
                logger.info(f"[SENTIMEN] Fear & Greed Score = {_fear_greed_score}")
        except Exception as e:
            logger.error(f"Gagal mengambil data Fear & Greed: {e}")
    return _fear_greed_score

def get_binance_balance() -> float:
    try:
        account_info = _api_call(_client.futures_account)
        for asset in account_info.get('assets', []):
            if asset['asset'] == 'USDT':
                return float(asset['walletBalance'])
    except Exception:
        pass
    return 0.0

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
    except Exception:
        pass
    return 'OFF'

def setup_account_environment() -> None:
    try:
        _client.futures_change_position_mode(dualSidePosition=True)
    except Exception:
        pass

def _is_trend_aligned(symbol: str, side: str) -> bool:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval='15m', limit=210)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])
        close = df['close'].astype(float)
        ema200 = float(ema_indicator(close, window=200).iloc[-1])
        current_price = float(close.iloc[-1])
        if side == 'LONG':
            return current_price > ema200
        if side == 'SHORT':
            return current_price < ema200
        return False
    except Exception:
        return False

def get_adaptive_signal(symbol: str, tf: str, is_vip: bool) -> Optional[dict]:
    try:
        bars = _api_call(_client.futures_klines, symbol=symbol, interval=tf, limit=300)
        df = pd.DataFrame(bars, columns=['time','open','high','low','close','volume','ct','qv','tr','tb','tq','i'])[['open','high','low','close','volume']].astype(float)

        if len(df) < EMA_TREND + 1:
            return None

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

        if p_vol < (vol_ma * VOL_MULTIPLIER):
            return None

        c_ema200 = ema200.iat[idx_curr]
        if p_close > p_open and c_close < c_ema200:
            return None
        if p_close < p_open and c_close > c_ema200:
            return None

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
                    if is_vip:
                        current_fear_score = update_fear_greed_index()
                        if current_fear_score > MAX_FEAR_SCORE_FOR_VIP:
                            return None
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
                    if is_vip:
                        return None
                    return {'side': 'SHORT', 'reason': f'{"Static Resist" if hit_static else "Dynamic Wall"} + Vol Spike'}

        return None
    except Exception:
        return None

def execute_order(symbol: str, order_side: str, position_side: str, is_dca: bool = False, dca_margin: float = 0.0) -> bool:
    try:
        curr_price = float(_api_call(_client.futures_symbol_ticker, symbol=symbol)['price'])

        if not is_dca:
            open_orders = _api_call(_client.futures_get_open_orders, symbol=symbol)
            entry_orders = [o for o in open_orders if o['positionSide'] == position_side and str(o.get('reduceOnly', 'False')).lower() == 'false' and o['type'] == 'LIMIT']

            if entry_orders:
                old_order = entry_orders[0]
                old_price = float(old_order['price'])
                is_better = False
                if order_side == 'BUY' and curr_price < old_price:
                    is_better = True
                elif order_side == 'SELL' and curr_price > old_price:
                    is_better = True

                if is_better:
                    logger.info(f"[ORDER UPGRADE] [{symbol}] Batal antrean lama ({old_price}) -> harga baru ({curr_price})")
                    _api_call(_client.futures_cancel_order, symbol=symbol, orderId=old_order['orderId'])
                    time.sleep(0.5)
                else:
                    logger.debug(f"[SKIP] {symbol}. Antrean lama ({old_price}) masih terpasang.")
                    return False

        try:
            _client.futures_change_leverage(symbol=symbol, leverage=TARGET_LEVERAGE)
            actual_lev = TARGET_LEVERAGE
        except BinanceAPIException as e:
            if e.code == -4028:
                brackets = _client.futures_leverage_bracket(symbol=symbol)
                actual_lev = int(brackets[0]['brackets'][0]['initialLeverage'])
                _client.futures_change_leverage(symbol=symbol, leverage=actual_lev)
            else:
                actual_lev = TARGET_LEVERAGE

        if is_dca:
            target_notional = dca_margin * actual_lev
            margin_to_use = dca_margin
        else:
            target_notional = TARGET_NOTIONAL_SIZE
            margin_to_use = target_notional / actual_lev

        f = _get_exchange_filters(symbol)
        qty_step = float(f['LOT_SIZE']['stepSize'])
        min_qty = float(f['LOT_SIZE']['minQty'])
        max_qty = float(f.get('MARKET_LOT_SIZE', f['LOT_SIZE'])['maxQty'])
        tick = float(f['PRICE_FILTER']['tickSize'])
        price_prec = max(0, -int(math.floor(math.log10(tick))))

        raw_qty = target_notional / curr_price
        qty = round(round(raw_qty / qty_step) * qty_step, 8)
        qty = min(max_qty, max(min_qty, qty))
        qty_str = f"{qty:.8f}".rstrip('0').rstrip('.')
        limit_price_str = f"{round(round(curr_price / tick) * tick, price_prec):.{price_prec}f}"

        _api_call(_client.futures_create_order,
                  symbol=symbol,
                  side=order_side,
                  type='LIMIT',
                  price=limit_price_str,
                  quantity=qty_str,
                  positionSide=position_side,
                  timeInForce='GTC')

        mode_text = 'DCA LIMIT' if is_dca else 'ENTRY LIMIT'
        logger.info(f"[{mode_text}] [{position_side}] {symbol} | Notional: ${target_notional:.2f} | Margin: ~${margin_to_use:.2f} | Lev: {actual_lev}x")
        return True
    except Exception as e:
        logger.error(f"Gagal eksekusi Limit Order {symbol}: {e}")
        return False

def _monitor_positions(positions: List[dict]):
    global _position_memory, _limit_order_memory
    for p in positions:
        amt = float(p['positionAmt'])
        if amt == 0:
            continue

        symbol, unrealized, mark_price = p['symbol'], float(p['unRealizedProfit']), float(p['markPrice'])
        entry_price = float(p['entryPrice'])
        actual_lev = float(p.get('leverage', TARGET_LEVERAGE))
        pos_side = p['positionSide']

        current_margin = (abs(amt) * entry_price) / actual_lev
        roe_percent = (unrealized / current_margin * 100) if current_margin > 0 else 0
        base_adj = TARGET_NOTIONAL_SIZE / actual_lev

        key = f"{symbol}_{pos_side}"
        _position_memory[key] = unrealized

        current_tp_target = 100.0
        mode_str = "NORMAL (100%)"

        if current_margin > (base_adj + 2.5):
            current_tp_target = 15.0
            mode_str = "RECOVERY DCA-3+ (15%)"
        elif current_margin > (base_adj + 1.5):
            current_tp_target = 50.0
            mode_str = "DCA-2 (50%)"
        elif current_margin > (base_adj + 0.5):
            current_tp_target = 100.0
            mode_str = "DCA-1 (100%)"

        state_key = f"{abs(amt):.8f}_{current_tp_target}"
        if _limit_order_memory.get(key) != state_key:
            try:
                _client.futures_cancel_all_open_orders(symbol=symbol)
                time.sleep(0.5)

                f = _get_exchange_filters(symbol)
                tick = float(f['PRICE_FILTER']['tickSize'])
                price_prec = max(0, -int(math.floor(math.log10(tick))))
                qty_str = f"{abs(amt):.8f}".rstrip('0').rstrip('.')

                if pos_side == 'LONG':
                    tp_raw = entry_price * (1 + ((current_tp_target / 100.0) / actual_lev))
                    tp_str = f"{round(round(tp_raw / tick) * tick, price_prec):.{price_prec}f}"
                    _client.futures_create_order(symbol=symbol, side='SELL', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=pos_side, timeInForce='GTC')
                elif pos_side == 'SHORT':
                    tp_raw = entry_price * (1 - ((current_tp_target / 100.0) / actual_lev))
                    sl_raw = entry_price * (1 + (SHORT_SL_ROE / actual_lev))
                    tp_str = f"{round(round(tp_raw / tick) * tick, price_prec):.{price_prec}f}"
                    sl_str = f"{round(round(sl_raw / tick) * tick, price_prec):.{price_prec}f}"
                    _client.futures_create_order(symbol=symbol, side='BUY', type='LIMIT', price=tp_str, quantity=qty_str, positionSide=pos_side, timeInForce='GTC')
                    _client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=sl_str, closePosition=True, positionSide=pos_side, timeInForce='GTC', workingType='MARK_PRICE')

                _limit_order_memory[key] = state_key
                logger.info(f"[JARING] [{symbol}] Target: {mode_str} | Entry: {entry_price}")
            except Exception:
                pass

        if roe_percent >= current_tp_target:
            logger.info(f"[VIRTUAL TP] {mode_str} [{symbol}] {roe_percent:.2f}% - Market Close!")
            try:
                close_side = 'SELL' if amt > 0 else 'BUY'
                _api_call(_client.futures_cancel_all_open_orders, symbol=symbol)
                _api_call(_client.futures_create_order, symbol=symbol, side=close_side, type='MARKET', quantity=abs(amt), positionSide=pos_side)
            except Exception:
                pass
            continue

        if amt < 0 and roe_percent <= -(SHORT_SL_ROE * 100):
            logger.info(f"[VIRTUAL SL] [{symbol}] {roe_percent:.2f}% - Market Close!")
            try:
                _api_call(_client.futures_cancel_all_open_orders, symbol=symbol)
                _api_call(_client.futures_create_order, symbol=symbol, side='BUY', type='MARKET', quantity=abs(amt), positionSide=pos_side)
            except Exception:
                pass
            continue

        if amt > 0:
            expected_total_margin = base_adj
            for i, (trigger_roe, dca_amount) in enumerate(DCA_STAGES):
                expected_margin_threshold = expected_total_margin + (dca_amount * 0.5)
                if roe_percent <= trigger_roe and current_margin < expected_margin_threshold:
                    logger.info(f"[DCA LAPIS {i+1}] [{symbol}] Trigger: {trigger_roe}% | Suntikan: ${dca_amount}")
                    execute_order(symbol, 'BUY', 'LONG', is_dca=True, dca_margin=dca_amount)
                    break
                expected_total_margin += dca_amount

def _scan_single_alt(symbol: str, active_keys: List[str], allowed_tfs: List[str]) -> Optional[Tuple[str, dict]]:
    if f"{symbol}_LONG" in active_keys or f"{symbol}_SHORT" in active_keys:
        return None
    for tf in allowed_tfs:
        sig = get_adaptive_signal(symbol, tf, is_vip=False)
        if sig:
            if _is_trend_aligned(symbol, sig['side']):
                return (symbol, sig)
    return None

_stop_event = None

def shutdown_bot():
    global _stop_event
    if _stop_event:
        _stop_event.set()

def run_bot(stop_event: threading.Event) -> None:
    global _stop_event, TOTAL_CLOSED_ROE, TOTAL_CLOSED_ROE_PERCENT, TOTAL_SUCCESS_TRADES, CLOSED_HISTORY, _coin_escalation_level, _position_memory, _limit_order_memory
    _stop_event = stop_event
    
    setup_account_environment()
    
    # --- INISIALISASI SALDO DENGAN LEDGER MANAGER ---
    start_balance = get_initial_balance(get_binance_balance())
    
    update_fear_greed_index()

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
                    
                    # FIX: Update memory before processing to avoid duplicates
                    _previous_active_keys = set(current_active_set)
                    
                    for k in closed_keys:
                        symbol = k.split('_')[0]

                        try:
                            _client.futures_cancel_all_open_orders(symbol=symbol)
                        except:
                            pass
                        if k in _limit_order_memory:
                            del _limit_order_memory[k]

                        # --- PENCATATAN PROFIT MURNI DARI DASHBOARD RAM ---
                        pnl_usd = _position_memory.get(k, 0.0)
                        roe_percent = (pnl_usd / BASE_MARGIN) * 100
                        
                        # Setor ke Akuntan (ledger_manager)
                        curr_bal = get_binance_balance()
                        catat_transaksi_v2(symbol, pnl_usd, roe_percent, curr_bal, start_balance)

                        if k in _position_memory:
                            del _position_memory[k]
                        # --------------------------------------------------

                        TOTAL_CLOSED_ROE += roe_percent
                        TOTAL_CLOSED_ROE_PERCENT += roe_percent
                        TOTAL_SUCCESS_TRADES += 1

                        if symbol not in VIP_SET and symbol not in GOLD_SET:
                            curr_level = _coin_escalation_level.get(symbol, 0)
                            _coin_escalation_level[symbol] = curr_level + 1

                        now_str = datetime.now().strftime("%H:%M:%S")
                        CLOSED_HISTORY.insert(0, {'time': now_str, 'symbol': symbol, 'profit': pnl_usd, 'roe': roe_percent})
                        if len(CLOSED_HISTORY) > 20:
                            CLOSED_HISTORY.pop()
                else:
                    _previous_active_keys = set(current_active_set)
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
                                    execute_order(symbol, 'BUY' if sig['side'] == 'LONG' else 'SELL', sig['side'])
                                    break

                for symbol in VIP_SYMBOLS:
                    if _stop_event.is_set() or vip_count >= MAX_VIP:
                        break
                    if f"{symbol}_LONG" not in active_keys and f"{symbol}_SHORT" not in active_keys:
                        for tf in VIP_TFS:
                            sig = get_adaptive_signal(symbol, tf, is_vip=True)
                            if sig:
                                if execute_order(symbol, 'BUY' if sig['side'] == 'LONG' else 'SELL', sig['side']):
                                    vip_count += 1
                                    break

                if alt_count < MAX_ALT and not _stop_event.is_set():
                    tickers = _get_cached_ticker()
                    alts = [t['symbol'] for t in sorted(tickers, key=lambda x: float(x['quoteVolume']), reverse=True)
                            if t['symbol'].endswith('USDT')
                            and float(t['quoteVolume']) >= MIN_24H_VOLUME
                            and t['symbol'] not in VIP_SET
                            and t['symbol'] not in GOLD_SET][:TOP_ALT_LIMIT]

                    futures = []
                    for s in alts:
                        base_tfs = ALT_TFS_FAST if alt_count < 4 else ALT_TFS_SAFE
                        esc_level = _coin_escalation_level.get(s, 0)
                        if esc_level >= len(ALT_TF_ORDER):
                            continue
                        valid_tfs = [tf for tf in base_tfs if ALT_TF_ORDER.index(tf) >= esc_level]
                        if not valid_tfs:
                            continue
                        futures.append(executor.submit(_scan_single_alt, s, active_keys, valid_tfs))

                    for future in as_completed(futures):
                        if _stop_event.is_set():
                            break
                        res = future.result()
                        if res and alt_count < MAX_ALT:
                            symbol, sig = res
                            if execute_order(symbol, 'BUY' if sig['side'] == 'LONG' else 'SELL', sig['side']):
                                alt_count += 1
                                active_keys.append(f"{symbol}_{sig['side']}")
                                current_active_set.add(f"{symbol}_{sig['side']}")
                                _previous_active_keys = current_active_set

                current_time = time.time()
                if current_time - _last_heartbeat_time >= 60.0:
                    update_fear_greed_index()
                    logger.info(f"[HEARTBEAT] System OK [RC v5.2] | F&G: {_fear_greed_score} | VIP: {vip_count}/{MAX_VIP} | ALT: {alt_count}/{MAX_ALT}")
                    _last_heartbeat_time = current_time

                for _ in range(15):
                    if _stop_event.is_set():
                        break
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
