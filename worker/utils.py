import hashlib
import re
import time
import json
import httpx
import psycopg
from pathlib import Path
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
CACHE_DIR = BASE_DIR / ".cache"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126 Safari/537.36"
    )
}

EGRUL_URL = "https://egrul.nalog.ru/"
ALLOWED_REGIONS = {"78", "47"}

INN_RE = re.compile(
    r"ИНН(?:\s*/\s*КПП)?[\s:№.]*(\d{10}|\d{12})(?!\d)",
    re.I,
)

EMAIL_RE = re.compile(
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+",
    re.I,
)

PHONE_RE = re.compile(
    r"(?:\+7|8)[\s(-]*[3489]\d{2}"
    r"[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}"
)


def cache_file(kind: str, key: str, suffix: str) -> Path:
    digest = hashlib.md5(key.encode()).hexdigest()
    path = CACHE_DIR / kind / f"{digest}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    return " ".join(soup.stripped_strings)


def valid_inn(inn: str) -> bool:
    digits = [int(x) for x in inn]

    def check(weights: list[int]) -> int:
        return sum(a * b for a, b in zip(weights, digits)) % 11 % 10

    if len(inn) == 10:
        return check([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]

    if len(inn) == 12:
        return (
            check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10]
            and check(
                [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
            ) == digits[11]
        )

    return False


def extract_inn(text: str) -> str | None:
    for inn in INN_RE.findall(text):
        if valid_inn(inn):
            return inn

    return None


def extract_contacts(text: str) -> dict:
    emails = sorted(
        set(EMAIL_RE.findall(text))
    )[:3]

    phones = sorted(
        {
            "7" + re.sub(r"\D", "", value)[-10:]
            for value in PHONE_RE.findall(text)
        }
    )[:3]

    return {
        "emails": emails,
        "phones": phones,
    }


def detect_role(text: str) -> tuple[str, str]:
    text = text.lower()

    for keyword in (
        "собственное производство",
        "собственного производства",
        "наше производство",
        "производим",
    ):
        if keyword in text:
            return "manufacturer", f"найдено: «{keyword}»"

    for keyword in (
        "официальный дистрибьютор",
        "официальный дилер",
        "дистрибьютор",
        "оптовые поставки",
        "собственный склад",
    ):
        if keyword in text:
            return "distributor", f"найдено: «{keyword}»"

    return "supplier", "признаки роли не найдены"

def save(
    conn: psycopg.Connection,
    companies: list[dict],
    okpd: str | None,
) -> None:
    with conn.cursor() as cur:
        for company in companies:
            cur.execute(
                """
                INSERT INTO suppliers (
                    inn, kpp, name, sum_price, is_smp,
                    okpds, source, site, role,
                    role_reason, contacts
                )
                VALUES (
                    %s, %s, %s, 0, false, %s,
                    'web', %s, %s, %s, %s
                )
                ON CONFLICT (inn) DO NOTHING
                """,
                (
                    company["inn"],
                    company["kpp"],
                    company["name"],
                    [okpd] if okpd else [],
                    company["site"],
                    company["role"],
                    company["role_reason"],
                    json.dumps(
                        company["contacts"],
                        ensure_ascii=False,
                    ),
                ),
            )

    conn.commit()


class Fetcher:
    def __init__(
        self,
        client: httpx.Client,
        refresh: bool = False,
    ):
        self.client = client
        self.refresh = refresh

    def get(self, url: str) -> str | None:
        path = cache_file("pages", url, ".html")

        if path.exists() and not self.refresh:
            return path.read_text(encoding="utf-8")

        try:
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        if "html" not in response.headers.get("content-type", ""):
            return None

        path.write_text(response.text, encoding="utf-8")
        time.sleep(0.5)

        return response.text