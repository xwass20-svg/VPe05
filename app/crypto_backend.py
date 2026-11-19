"""
Эмулятор бэкенда криптобиржи: постоянно генерирует «живые» логи
и отправляет их в Loki (для дашборда Grafana).
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

LOKI_URL = "http://localhost:3100/loki/api/v1/push"
APP_LABEL = "crypto_exchange"

PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "TON/USDT"]
SIDES = ["buy", "sell"]
ORDER_TYPES = ["market", "limit"]
USERS = [f"user_{i:04d}" for i in range(1001, 1041)]
WALLETS = ["spot", "futures", "earn"]
LEVELS = ["debug", "info", "warning", "error"]
# веса: чаще info, реже error — как у реального сервиса
LEVEL_WEIGHTS = [0.15, 0.55, 0.22, 0.08]


def _ns_now() -> str:
    return str(time.time_ns())


def _price(pair: str) -> float:
    base = {
        "BTC/USDT": 95_000,
        "ETH/USDT": 3_400,
        "SOL/USDT": 180,
        "XRP/USDT": 0.62,
        "DOGE/USDT": 0.18,
        "TON/USDT": 5.4,
    }[pair]
    jitter = random.uniform(-0.012, 0.012)
    return round(base * (1 + jitter), 4 if base < 10 else 2)


def _amount() -> float:
    return round(random.uniform(0.001, 2.5), 6)


def emulate_crypto_backend_event() -> tuple[str, str]:
    """
    Одна «реальная» операция бэкенда криптоприложения.
    Возвращает (level, message).
    """
    level = random.choices(LEVELS, weights=LEVEL_WEIGHTS, k=1)[0]
    pair = random.choice(PAIRS)
    user = random.choice(USERS)
    side = random.choice(SIDES)
    order_type = random.choice(ORDER_TYPES)
    price = _price(pair)
    amount = _amount()
    wallet = random.choice(WALLETS)
    order_id = f"ord_{random.randint(10_000_000, 99_999_999)}"
    trade_id = f"trd_{random.randint(10_000_000, 99_999_999)}"
    latency_ms = random.randint(8, 420)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    scenarios = [
        (
            "info",
            f"{ts} order_accepted order_id={order_id} user={user} pair={pair} "
            f"side={side} type={order_type} price={price} amount={amount} "
            f"wallet={wallet} latency_ms={latency_ms}",
        ),
        (
            "info",
            f"{ts} trade_executed trade_id={trade_id} order_id={order_id} "
            f"user={user} pair={pair} side={side} price={price} amount={amount} "
            f"fee_usdt={round(price * amount * 0.001, 6)}",
        ),
        (
            "info",
            f"{ts} balance_updated user={user} wallet={wallet} asset={pair.split('/')[0]} "
            f"delta={amount if side == 'buy' else -amount} "
            f"available={round(random.uniform(0.01, 12.0), 6)}",
        ),
        (
            "debug",
            f"{ts} orderbook_snapshot pair={pair} best_bid={round(price * 0.9997, 4)} "
            f"best_ask={round(price * 1.0003, 4)} depth_bids={random.randint(20, 80)} "
            f"depth_asks={random.randint(20, 80)}",
        ),
        (
            "debug",
            f"{ts} ws_tick pair={pair} last={price} volume_24h={round(random.uniform(1e6, 9e8), 2)} "
            f"clients={random.randint(120, 2500)}",
        ),
        (
            "warning",
            f"{ts} rate_limit_soft user={user} endpoint=/api/v1/orders "
            f"remaining={random.randint(1, 8)} reset_in_sec={random.randint(1, 30)}",
        ),
        (
            "warning",
            f"{ts} high_slippage order_id={order_id} pair={pair} "
            f"expected={price} filled={round(price * random.uniform(0.992, 1.008), 4)} "
            f"slippage_bps={random.randint(15, 95)}",
        ),
        (
            "error",
            f"{ts} order_rejected order_id={order_id} user={user} pair={pair} "
            f"reason={random.choice(['insufficient_balance', 'min_notional', 'market_closed', 'risk_check'])} "
            f"requested={amount}",
        ),
        (
            "error",
            f"{ts} matching_engine_timeout order_id={order_id} pair={pair} "
            f"latency_ms={latency_ms} retry={random.randint(1, 3)}",
        ),
        (
            "info",
            f"{ts} deposit_detected user={user} asset={pair.split('/')[0]} "
            f"amount={round(random.uniform(0.01, 5.0), 6)} "
            f"txid=0x{random.getrandbits(64):016x} confirmations={random.randint(1, 12)}",
        ),
        (
            "info",
            f"{ts} withdrawal_queued user={user} asset={pair.split('/')[1]} "
            f"amount={round(random.uniform(10, 2500), 2)} "
            f"address=T{random.getrandbits(40):010x} status=pending_review",
        ),
        (
            "warning",
            f"{ts} risk_flag user={user} rule=velocity_check trades_1m={random.randint(12, 40)} "
            f"threshold=10 action=throttle",
        ),
    ]

    # подбираем сценарий, близкий к выбранному уровню
    same_level = [s for s in scenarios if s[0] == level]
    if not same_level:
        same_level = scenarios
    chosen_level, message = random.choice(same_level)
    return chosen_level, message


def send_log_to_loki(
    message: str,
    *,
    level: str = "info",
    app: str = APP_LABEL,
    extra_labels: dict[str, str] | None = None,
) -> bool:
    """
    Отправляет одно лог-сообщение в Loki через POST /loki/api/v1/push.
    Возвращает True при успехе, False при ошибке сети/ответа.
    """
    labels = {
        "app": app,
        "level": level,
        "service": "crypto-backend",
        "job": "exchange-api",
    }
    if extra_labels:
        labels.update(extra_labels)

    payload = {
        "streams": [
            {
                "stream": labels,
                "values": [[_ns_now(), message]],
            }
        ]
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LOKI_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status not in (200, 204):
                print(f"[SEND FAIL] Loki HTTP {resp.status}")
                return False
        return True
    except urllib.error.URLError as exc:
        print(f"[SEND FAIL] {exc}")
        return False


def run_forever(min_delay: float = 0.4, max_delay: float = 1.8) -> None:
    print(f"Crypto backend emulator started → {LOKI_URL}")
    print(f"Labels: app={APP_LABEL}, level=debug|info|warning|error")
    print("Press Ctrl+C to stop.\n")

    while True:
        level, message = emulate_crypto_backend_event()
        ok = send_log_to_loki(message, level=level)
        if ok:
            print(f"[{level.upper():7}] {message}")
        time.sleep(random.uniform(min_delay, max_delay))



if __name__ == "__main__":
    run_forever()
