import asyncio
import json
import websockets
import requests
from collections import deque
from datetime import datetime

BOT_TOKEN = "8809735238:AAHgovPDWMTqGA4dSpHsIlECOtSgAnRDs54"
CHAT_ID = "7811742140"
DERIV_APP_ID = "1089"
WS_URL = f"wss://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}"

MARKETS = {
    "R_10": "Volatility 10",
    "R_25": "Volatility 25",
    "R_50": "Volatility 50",
    "R_75": "Volatility 75",
    "R_100": "Volatility 100",
}

MAX_TICKS = 500
COOLDOWN_SECONDS = 60

RULES = [
    {"digit": 0, "min": 8.5, "max": 9.6},
    {"digit": 1, "min": 8.5, "max": 9.6},
    {"digit": 2, "min": 10.0, "max": 11.0},
]


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Telegram error] {e}")


def check_signal(counts: dict, total: int):
    if total < 50:
        return False, []
    results = []
    for rule in RULES:
        d = rule["digit"]
        p = (counts.get(d, 0) / total) * 100
        passed = rule["min"] <= p <= rule["max"]
        results.append({"digit": d, "pct": p, "pass": passed, "min": rule["min"], "max": rule["max"]})
    all_pass = all(r["pass"] for r in results)
    return all_pass, results


async def watch_market(symbol: str, market_name: str):
    counts = {i: 0 for i in range(10)}
    tick_window = deque(maxlen=MAX_TICKS)
    last_alert = 0
    was_active = False

    print(f"[{market_name}] Connecting...")

    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=30) as ws:
                await ws.send(json.dumps({"ticks": symbol, "subscribe": 1}))
                print(f"[{market_name}] Connected and subscribed.")

                async for raw in ws:
                    msg = json.loads(raw)
                    if "tick" not in msg:
                        continue

                    quote = str(msg["tick"]["quote"])
                    digit = int(quote[-1])

                    if len(tick_window) == MAX_TICKS:
                        old = tick_window[0]
                        counts[old] -= 1

                    tick_window.append(digit)
                    counts[digit] += 1
                    total = len(tick_window)

                    signal, results = check_signal(counts, total)
                    now = datetime.now().timestamp()

                    if signal and not was_active and (now - last_alert) > COOLDOWN_SECONDS:
                        last_alert = now
                        was_active = True

                        time_str = datetime.now().strftime("%H:%M:%S")
                        lines = [
                            f"<b>OVER 2 SIGNAL DETECTED</b>",
                            f"Market: <b>{market_name}</b>",
                            f"Time: {time_str}",
                            f"Sample: {total} ticks",
                            "",
                        ]
                        for r in results:
                            icon = "✅" if r["pass"] else "❌"
                            lines.append(f"{icon} Digit {r['digit']}: {r['pct']:.1f}% (need {r['min']}–{r['max']}%)")

                        lines += ["", "<b>Trade Over 2 with confidence!</b>"]
                        send_telegram("\n".join(lines))
                        print(f"[{market_name}] Signal fired at {time_str}")

                    elif not signal:
                        was_active = False

        except Exception as e:
            print(f"[{market_name}] Error: {e} — reconnecting in 5s...")
            await asyncio.sleep(5)


async def main():
    send_telegram(
        "<b>Deriv Over 2 Bot started!</b>\n"
        "Watching: Volatility 10, 25, 50, 75, 100\n"
        "You will be notified when the Over 2 signal fires."
    )
    print("Bot started. Watching all markets...")
    await asyncio.gather(*[
        watch_market(sym, name) for sym, name in MARKETS.items()
    ])


if __name__ == "__main__":
    asyncio.run(main())
