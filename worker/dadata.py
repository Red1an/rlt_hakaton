import json
import os
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from .utils import CACHE_DIR

DADATA_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
SUGGEST_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"
SUGGEST_COUNT = 20
DAILY_LIMIT = int(os.getenv("DADATA_DAILY_LIMIT", "9500"))
CACHE_TTL = timedelta(days=7)
REQUEST_PAUSE = 0.05

QUOTA_PATH = CACHE_DIR / "dadata_quota.json"

MANUFACTURING = range(10, 34)

OKVED_SECTIONS = [
    (range(1, 4), "сельское и лесное хозяйство"),
    (range(5, 10), "добыча полезных ископаемых"),
    (range(10, 34), "производство"),
    (range(35, 40), "энергетика и водоснабжение"),
    (range(41, 44), "строительство"),
    (range(45, 46), "торговля и ремонт автотранспорта"),
    (range(46, 47), "оптовая торговля"),
    (range(47, 48), "розничная торговля"),
    (range(49, 54), "транспорт и хранение"),
    (range(55, 57), "гостиницы и общепит"),
    (range(58, 64), "информация и связь"),
    (range(64, 67), "финансы и страхование"),
    (range(68, 69), "недвижимость"),
    (range(69, 76), "профессиональные и научные услуги"),
    (range(77, 83), "административные услуги"),
    (range(85, 86), "образование"),
    (range(86, 89), "здравоохранение"),
    (range(90, 94), "культура и спорт"),
    (range(94, 97), "прочие услуги"),
]


class DadataQuotaExceeded(Exception):
    pass


class DadataUnavailable(Exception):
    pass


def api_key() -> str:
    key = os.getenv("DADATA_API_KEY", "").strip()
    if not key:
        raise DadataUnavailable("не задан DADATA_API_KEY")
    return key


def used_today() -> int:
    if not QUOTA_PATH.exists():
        return 0
    quota = json.loads(QUOTA_PATH.read_text(encoding="utf-8"))
    return quota["count"] if quota.get("date") == date.today().isoformat() else 0


def count_request() -> None:
    QUOTA_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUOTA_PATH.write_text(json.dumps({"date": date.today().isoformat(), "count": used_today() + 1}), encoding="utf-8")


def cached(inn: str) -> dict | None:
    path = CACHE_DIR / "dadata" / f"{inn}.json"
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    fetched = datetime.fromisoformat(record["fetched_at"])
    return record if datetime.now(timezone.utc) - fetched < CACHE_TTL else None


def fetch_party(client: httpx.Client, inn: str) -> dict | None:
    record = cached(inn)
    if record is not None:
        return record["data"]
    if used_today() >= DAILY_LIMIT:
        raise DadataQuotaExceeded(f"дневной лимит DaData исчерпан ({DAILY_LIMIT} запросов)")

    try:
        response = client.post(
            DADATA_URL,
            json={"query": inn, "branch_type": "MAIN"},
            headers={"Authorization": f"Token {api_key()}", "Accept": "application/json"},
        )
        count_request()
        if response.status_code in (401, 403):
            raise DadataUnavailable("ключ DaData не принят")
        if response.status_code == 429:
            raise DadataQuotaExceeded("DaData ограничила частоту запросов")
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise DadataUnavailable(str(error)) from error

    suggestions = response.json().get("suggestions", [])
    data = suggestions[0]["data"] if suggestions else None
    path = CACHE_DIR / "dadata" / f"{inn}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "data": data}, ensure_ascii=False),
        encoding="utf-8",
    )
    time.sleep(REQUEST_PAUSE)
    return data


def suggest_parties(client: httpx.Client, query: str, okveds: list[str], regions: list[str]) -> list[dict]:
    if used_today() >= DAILY_LIMIT:
        raise DadataQuotaExceeded(f"дневной лимит DaData исчерпан ({DAILY_LIMIT} запросов)")
    try:
        response = client.post(
            SUGGEST_URL,
            json={
                "query": query,
                "count": SUGGEST_COUNT,
                "status": ["ACTIVE"],
                "okved": okveds,
                "branch_type": ["MAIN"],
                "locations": [{"kladr_id": region} for region in regions],
            },
            headers={"Authorization": f"Token {api_key()}", "Accept": "application/json"},
        )
        count_request()
        if response.status_code in (401, 403):
            raise DadataUnavailable("ключ DaData не принят")
        if response.status_code == 429:
            raise DadataQuotaExceeded("DaData ограничила частоту запросов")
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise DadataUnavailable(str(error)) from error
    time.sleep(REQUEST_PAUSE)
    return [item["data"] for item in response.json().get("suggestions", []) if item.get("data")]


def from_millis(value: int | None) -> date | None:
    if not value:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date()


def okved_division(okved: str | None) -> int | None:
    if not okved or not okved[:2].isdigit():
        return None
    return int(okved[:2])


def okved_section(okved: str | None) -> str | None:
    division = okved_division(okved)
    if division is None:
        return None
    return next((name for numbers, name in OKVED_SECTIONS if division in numbers), None)


def role_from_okved(okved: str | None) -> tuple[str, str] | None:
    division = okved_division(okved)
    if division is None:
        return None
    reason = f"основной ОКВЭД {okved} — {okved_section(okved) or 'прочая деятельность'}"
    if division in MANUFACTURING:
        return "manufacturer", reason
    if division == 46:
        return "distributor", reason
    return "supplier", reason


def region_from_address(address: dict | None) -> str | None:
    details = (address or {}).get("data") or {}
    kladr = details.get("region_kladr_id") or details.get("kladr_id") or ""
    return kladr[:2] if len(kladr) >= 2 and kladr[:2].isdigit() else None


def parse_party(data: dict) -> dict:
    state = data.get("state") or {}
    name = data.get("name") or {}
    opf = data.get("opf") or {}
    address = data.get("address") or {}
    okved = data.get("okved")
    role = role_from_okved(okved)
    return {
        "name": name.get("short_with_opf") or name.get("full_with_opf"),
        "kpp": data.get("kpp"),
        "ogrn": data.get("ogrn"),
        "status": state.get("status"),
        "status_date": from_millis(state.get("liquidation_date")),
        "reg_date": from_millis(state.get("registration_date")),
        "okved_main": okved,
        "address": address.get("unrestricted_value") or address.get("value"),
        "region_code": region_from_address(address),
        "opf": opf.get("short"),
        "is_individual": data.get("type") == "INDIVIDUAL",
        "employees": data.get("employee_count"),
        "role": role[0] if role else None,
        "role_reason": role[1] if role else None,
    }
