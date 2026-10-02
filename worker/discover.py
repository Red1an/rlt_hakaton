import argparse
import hashlib
import json
import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import psycopg
from bs4 import BeautifulSoup
from ddgs import DDGS

from api.categories import detect_okpd
from api.db import connect

WORKER_DIR = Path(__file__).resolve().parent
CACHE_DIR = WORKER_DIR / ".cache"

QUERY_TEMPLATES = [
    "{query} оптом Санкт-Петербург поставщик",
    "{query} производитель Санкт-Петербург",
    "{query} дистрибьютор Санкт-Петербург",
]

BLOCKED_DOMAINS = {
    "avito.ru", "ozon.ru", "wildberries.ru", "market.yandex.ru", "yandex.ru", "2gis.ru", "zoon.ru",
    "vk.com", "ok.ru", "t.me", "youtube.com", "rutube.ru", "dzen.ru", "wikipedia.org", "pulscen.ru",
    "tiu.ru", "satom.ru", "blizko.ru", "spb.blizko.ru", "flagma.ru", "rusprofile.ru", "list-org.com",
    "checko.ru", "zachestnyibiznes.ru", "sbis.ru", "audit-it.ru", "zakupki.gov.ru", "hh.ru", "otzovik.com",
    "irecommend.ru", "aliexpress.ru", "megamarket.ru", "leroymerlin.ru", "vseinstrumenti.ru", "orgpage.ru",
    "tradedir.ru", "optomtovar.ru", "postavshikov.net", "optlist.ru", "metaprom.ru", "supl.biz",
}

ALLOWED_REGIONS = {"78", "47"}

SUBPAGE_PATTERN = re.compile(r"контакты|реквизиты|о компании|о нас|contacts|about|kontakty|rekvizit|requisit", re.I)
FALLBACK_PATHS = ["contacts/", "kontakty/", "rekvizity/"]
INN_PATTERN = re.compile(r"ИНН(?:\s*/\s*КПП)?[\s:№.]*(\d{12}|\d{10})(?!\d)")
ORG_PATTERN = re.compile(r"\b(ООО|АО|ЗАО|ПАО|ОАО)\s*[«\"“]([^»\"”]{2,80})[»\"”]")
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zа-я]{2,}", re.I)
PHONE_PATTERN = re.compile(r"(?:\+7|8)[\s(-]*[3489]\d{2}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}")

ROLE_KEYWORDS = [
    ("manufacturer", ["собственное производство", "собственного производства", "наше производство", "производим"]),
    ("distributor", ["официальный дистрибьютор", "официальный дилер", "дистрибьютор", "оптовые поставки", "собственный склад"]),
]

EGRUL_URL = "https://egrul.nalog.ru/"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def inn_is_valid(inn: str) -> bool:
    digits = [int(d) for d in inn]

    def checksum(weights: list[int]) -> int:
        return sum(w * d for w, d in zip(weights, digits)) % 11 % 10

    if len(inn) == 10:
        return checksum([2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    if len(inn) == 12:
        return (
            checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[10]
            and checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[11]
        )
    return False


def cache_path(kind: str, key: str, suffix: str) -> Path:
    path = CACHE_DIR / kind / f"{hashlib.md5(key.encode()).hexdigest()}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def search(query: str, max_results: int, refresh: bool = False) -> list[str]:
    path = cache_path("search", f"{query}|{max_results}", ".json")
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        results = DDGS().text(query, region="ru-ru", max_results=max_results)
    except Exception as error:
        print(f"  поиск не удался: {error}")
        return []
    urls = [item["href"] for item in results if item.get("href")]
    path.write_text(json.dumps(urls, ensure_ascii=False), encoding="utf-8")
    time.sleep(2)
    return urls


def fetch(client: httpx.Client, url: str) -> str | None:
    path = cache_path("pages", url, ".html")
    if path.exists():
        return path.read_text(encoding="utf-8")
    try:
        response = client.get(url)
    except (httpx.HTTPError, ValueError):
        return None
    if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
        return None
    path.write_text(response.text, encoding="utf-8")
    time.sleep(0.5)
    return response.text


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_blocked(domain: str) -> bool:
    return domain.endswith(".gov.ru") or any(domain == d or domain.endswith("." + d) for d in BLOCKED_DOMAINS)


def subpage_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_domain = domain_of(base_url)
    links = []
    for anchor in soup.find_all("a", href=True):
        text = f"{anchor.get_text(' ', strip=True)} {anchor['href']}"
        url = urljoin(base_url, anchor["href"]).split("#")[0]
        if SUBPAGE_PATTERN.search(text) and domain_of(url) == base_domain and url not in links:
            links.append(url)
    fallback = [urljoin(base_url, path) for path in FALLBACK_PATHS]
    return links[:3] + [url for url in fallback if url not in links]


def page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" "))


def site_title(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()[:120]
    return None


def org_name_near(text: str, inn: str) -> str | None:
    positions = [m.start() for m in re.finditer(inn, text)]
    best = None
    for org in ORG_PATTERN.finditer(text):
        if "банк" in org.group(2).lower():
            continue
        distance = min(abs(org.start() - p) for p in positions)
        if distance <= 300 and (best is None or distance < best[0]):
            best = (distance, f"{org.group(1)} «{org.group(2).strip()}»")
    return best[1] if best else None


def is_real_email(email: str) -> bool:
    local, _, domain = email.lower().partition("@")
    if domain.endswith((".png", ".jpg", ".svg", ".webp", ".gif")):
        return False
    return not local.isdigit() and not domain.split(".")[0].isdigit()


def detect_role(text: str) -> tuple[str, str]:
    lowered = text.lower()
    for role, keywords in ROLE_KEYWORDS:
        for keyword in keywords:
            if keyword in lowered:
                return role, f"на сайте найдено: «{keyword}»"
    return "supplier", "нет признаков производства или дистрибуции"


def analyze_site(client: httpx.Client, root_url: str) -> dict | None:
    main_html = fetch(client, root_url)
    if not main_html:
        return None
    htmls = [main_html] + [html for url in subpage_links(main_html, root_url) if (html := fetch(client, url))]
    text = " ".join(page_text(html) for html in htmls)

    inns = Counter(inn for inn in INN_PATTERN.findall(text) if inn_is_valid(inn))
    if not inns:
        return None
    inn = inns.most_common(1)[0][0]

    name = org_name_near(text, inn) or site_title(main_html)
    role, role_reason = detect_role(text)
    emails = sorted({e.lower() for e in EMAIL_PATTERN.findall(text) if is_real_email(e)})[:3]
    phones = sorted({"7" + re.sub(r"\D", "", p)[-10:] for p in PHONE_PATTERN.findall(text)})[:3]

    return {
        "inn": inn,
        "kpp": None,
        "name": name,
        "site": root_url,
        "region": inn[:2],
        "role": role,
        "role_reason": role_reason,
        "contacts": {"phones": phones, "emails": emails},
    }


class EgrulUnavailable(Exception):
    pass


def egrul_lookup(client: httpx.Client, inn: str) -> dict | None:
    path = CACHE_DIR / "egrul" / f"{inn}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        payload = client.post(EGRUL_URL, data={"query": inn}, headers={"X-Requested-With": "XMLHttpRequest"}).json()
        if payload.get("captchaRequired") or "t" not in payload:
            raise EgrulUnavailable("сервис просит капчу")
        time.sleep(1)
        rows = client.get(f"{EGRUL_URL}search-result/{payload['t']}").json().get("rows", [])
    except (httpx.HTTPError, ValueError) as error:
        raise EgrulUnavailable(str(error)) from error
    row = next((r for r in rows if r.get("i") == inn), None)
    record = None if row is None else {
        "name": row.get("c") or row.get("n"),
        "full_name": row.get("n"),
        "ogrn": row.get("o"),
        "kpp": row.get("p"),
        "reg_date": row.get("r"),
        "region_name": row.get("rn"),
        "terminated": row.get("e"),
    }
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    time.sleep(1)
    return record


def verify(client: httpx.Client, company: dict) -> str | None:
    try:
        record = egrul_lookup(client, company["inn"])
    except EgrulUnavailable as error:
        return f"не проверен в ЕГРЮЛ: {error}"
    if record is None:
        return "нет в ЕГРЮЛ"
    if record["terminated"]:
        return f"прекратил деятельность {record['terminated']}"
    kpp = record["kpp"]
    company.update(
        name=record["name"],
        kpp=kpp,
        ogrn=record["ogrn"],
        reg_date=record["reg_date"],
        region=kpp[:2] if kpp and not kpp.startswith("99") else company["inn"][:2],
        region_name=record["region_name"],
    )
    if company["region"] not in ALLOWED_REGIONS:
        return f"не СПб и не ЛО ({record['region_name'] or company['region']})"
    return None


def save(conn: psycopg.Connection, companies: list[dict], okpd: str | None) -> None:
    okpds = [okpd] if okpd else []
    with conn.cursor() as cur:
        for company in companies:
            cur.execute(
                """
                INSERT INTO suppliers (inn, kpp, name, sum_price, is_smp, okpds, source, site, role, role_reason, contacts)
                VALUES (%s, %s, %s, 0, false, %s, 'web', %s, %s, %s, %s)
                ON CONFLICT (inn) DO NOTHING
                """,
                (
                    company["inn"], company["kpp"], company["name"], okpds, company["site"],
                    company["role"], company["role_reason"], json.dumps(company["contacts"], ensure_ascii=False),
                ),
            )
    conn.commit()


def discover(
    query: str,
    max_sites: int,
    known_inns: set[str],
    refresh: bool = False,
    progress: Callable[[int, int, int], None] | None = None,
) -> list[dict]:
    roots = []
    for template in QUERY_TEMPLATES:
        search_query = template.format(query=query)
        print(f"Поиск: {search_query}")
        for url in search(search_query, max_results=max_sites, refresh=refresh):
            if not url.startswith("http"):
                continue
            domain = domain_of(url)
            root = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
            if not is_blocked(domain) and all(domain_of(r) != domain for r in roots):
                roots.append(root)

    companies = []
    seen_inns = set()
    with httpx.Client(headers=HEADERS, timeout=10, follow_redirects=True) as client:
        targets = roots[:max_sites]
        for checked, root in enumerate(targets, start=1):
            if progress:
                progress(checked, len(targets), len(companies))
            company = analyze_site(client, root)
            if company is None:
                print(f"  {root}: ИНН не найден")
                continue
            if company["inn"] in known_inns or company["inn"] in seen_inns:
                print(f"  {root}: {company['inn']} уже известен")
                continue
            seen_inns.add(company["inn"])
            rejection = verify(client, company)
            if rejection:
                print(f"  {root}: {company['inn']} отброшен, {rejection}")
                continue
            companies.append(company)
            print(f"  {root}: {company['inn']} {company['name']} [{company['role']}]")
    return companies


def main() -> None:
    parser = argparse.ArgumentParser(description="Поиск новых поставщиков в интернете")
    parser.add_argument("--query", required=True, help="что ищем, например «бумага офисная»")
    parser.add_argument("--okpd", help="код ОКПД2 категории; если не указан, определяется по товарам в базе")
    parser.add_argument("--max-sites", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="не подключаться к базе, только вывести результат")
    parser.add_argument("--refresh", action="store_true", help="искать заново, мимо кеша поисковика")
    args = parser.parse_args()

    if args.dry_run:
        companies = discover(args.query, args.max_sites, set(), args.refresh)
    else:
        with connect() as conn:
            okpd = args.okpd
            if okpd is None:
                candidates = detect_okpd(conn, args.query)
                okpd = candidates[0][0] if candidates else None
                print("Категории по товарам в базе: " + (", ".join(f"{code} ({count})" for code, count in candidates) or "не найдены"))
            print(f"Категория ОКПД2: {okpd or 'не определена'}")
            known_inns = {row[0] for row in conn.execute("SELECT inn FROM suppliers")}
            companies = discover(args.query, args.max_sites, known_inns, args.refresh)
            save(conn, companies, okpd)

    print(f"\nНовых поставщиков: {len(companies)}")
    print(json.dumps(companies, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
