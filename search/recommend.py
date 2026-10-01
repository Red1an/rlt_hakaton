import json
import math
from datetime import date

import psycopg

from search.categories import detect_okpd
from worker.discover import CACHE_DIR

LOCAL_REGIONS = {"78": "Из Санкт-Петербурга", "47": "Из Ленинградской области"}
REGION_NAMES = {"78": "Санкт-Петербург", "47": "Ленинградская область"}
ROLE_CODES = {"manufacturer": "man", "distributor": "dist", "supplier": "sup"}
NEW_ROLE_SCORES = {"man": 60, "dist": 55, "sup": 50}
PLATFORM_LABELS = {True: "Электронный магазин", False: "АИС ГЗ"}
CONTENDER_SLOTS = 5
HISTORY_ROWS = 5
EMPTY = "—"

SIMILAR_LOTS_SQL = """
    CREATE TEMP TABLE similar_lots ON COMMIT DROP AS
    SELECT DISTINCT lot_id FROM lots WHERE okpd_code LIKE %(prefix)s
"""

HISTORY_SQL = """
    WITH stats AS (
        SELECT
            b.supplier_inn,
            count(*)                                                    AS part,
            count(*) FILTER (WHERE b.is_winner)                         AS wins,
            max(a.publish_date)                                         AS last_date,
            count(*) FILTER (WHERE a.is_eshop_or_aisgz = %(eshop)s)     AS same_platform
        FROM bids b
        JOIN similar_lots s ON s.lot_id = b.lot_id
        JOIN announcements a ON a.lot_id = b.lot_id
        GROUP BY b.supplier_inn
        ORDER BY wins DESC, part DESC
        LIMIT %(candidates)s
    )
    SELECT
        st.supplier_inn, st.part, st.wins, st.last_date, st.same_platform,
        s.name, s.kpp, s.role, s.role_reason,
        EXISTS (
            SELECT 1 FROM bids b2 JOIN announcements a2 ON a2.lot_id = b2.lot_id
            WHERE b2.supplier_inn = st.supplier_inn AND a2.is_smp
        ) AS is_msp
    FROM stats st
    JOIN suppliers s ON s.inn = st.supplier_inn
"""

NEW_SQL = """
    SELECT inn, kpp, name, role, role_reason, site, contacts
    FROM suppliers
    WHERE source = 'web'
      AND EXISTS (SELECT 1 FROM unnest(okpds) code WHERE code LIKE %(prefix)s OR %(okpd)s LIKE code || '%%')
"""


LOT_HISTORY_SQL = """
    SELECT inn, subject, start_price, customer_inn, is_winner
    FROM (
        SELECT
            b.supplier_inn AS inn, a.subject, a.start_price, a.customer_inn, b.is_winner,
            row_number() OVER (PARTITION BY b.supplier_inn ORDER BY a.publish_date DESC) AS position
        FROM bids b
        JOIN similar_lots s ON s.lot_id = b.lot_id
        JOIN announcements a ON a.lot_id = b.lot_id
        WHERE b.supplier_inn = ANY(%(inns)s)
    ) ranked
    WHERE position <= %(rows)s
"""


def region_code(inn: str, kpp: str | None) -> str:
    return kpp[:2] if kpp and not kpp.startswith("99") else inn[:2]


def ago(days: int) -> str:
    if days < 7:
        return "на этой неделе"
    if days < 30:
        return f"{days // 7} нед. назад"
    if days < 365:
        return f"{days // 30} мес. назад"
    return f"{days // 365} г. назад"


def egrul_record(inn: str) -> dict:
    path = CACHE_DIR / "egrul" / f"{inn}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")) or {}


def requisites_for(inn: str, kpp: str | None, contacts: dict | None = None) -> dict:
    record = egrul_record(inn)
    region = region_code(inn, kpp)
    contacts = contacts or {}
    return {
        "kpp": kpp or record.get("kpp") or EMPTY,
        "ogrn": record.get("ogrn") or EMPTY,
        "okved": EMPTY,
        "region": REGION_NAMES.get(region) or record.get("region_name") or f"Регион {region}",
        "phone": ", ".join(contacts.get("phones", [])) or EMPTY,
        "email": ", ".join(contacts.get("emails", [])) or EMPTY,
    }


def site_without_protocol(site: str | None) -> str:
    if not site:
        return ""
    return site.split("://", 1)[-1].rstrip("/")


def flags_for(inn: str, kpp: str | None, is_msp: bool) -> list[str]:
    flags = []
    if is_msp:
        flags.append("МСП")
    if len(inn) == 12:
        flags.append("ИП")
    if kpp and kpp[4:6] == "43":
        flags.append("Филиал")
    return flags


def history_item(row: tuple, reference: date, eshop: bool) -> dict:
    inn, part, wins, last_date, same_platform, name, kpp, role, role_reason, is_msp = row
    days = (reference - last_date).days
    win_share = wins / part
    region = region_code(inn, kpp)

    score = round(
        30 * min(1.0, math.log1p(part) / math.log1p(300))
        + 30 * (wins + 1) / (part + 2)
        + 20 * max(0.0, 1 - days / 730)
        + 10 * (region in LOCAL_REGIONS)
        + 10 * same_platform / part
    )

    why = []
    if days > 180:
        why.append(["💤", f"Последняя заявка {ago(days)}, стоит напомнить о закупке"])
    if wins >= 3 and win_share >= 0.3:
        why.append(["★", f"Победил в {wins} из {part} похожих лотов"])
    elif part >= 3 and win_share < 0.2:
        why.append(["↻", f"Подал {part} заявок, побед: {wins}, готов конкурировать"])
    else:
        why.append(["★", f"Участвовал в {part} похожих лотах, побед: {wins}"])
    if days <= 30:
        why.append(["↻", "Активен в последний месяц"])
    why.append(["⌖", LOCAL_REGIONS.get(region, f"Иногородний, регион {region}")])
    if same_platform:
        why.append(["🏷", f"{same_platform} заявок на площадке «{PLATFORM_LABELS[eshop]}»"])
    if role_reason:
        why.append(["⚙", role_reason])

    return {
        "id": inn,
        "name": name or f"Компания ИНН {inn}",
        "inn": inn,
        "flags": flags_for(inn, kpp, is_msp),
        "novelty": "existing",
        "role": ROLE_CODES.get(role, "sup"),
        "score": score,
        "part": part,
        "wins": wins,
        "last": ago(days),
        "why": why[:3],
        "site": "",
        "requisites": requisites_for(inn, kpp),
        "history": [],
        "isMsp": is_msp,
        "isContender": part >= 3 and win_share < 0.2,
    }


def new_item(row: tuple) -> dict:
    inn, kpp, name, role, role_reason, site, contacts = row
    role_code = ROLE_CODES.get(role, "sup")
    region = region_code(inn, kpp)
    why = [["✦", "Нет в истории госзакупок, найден в открытых источниках"]]
    if role_reason:
        why.append(["⚙", role_reason])
    why.append(["✓", f"Действующая компания по ЕГРЮЛ, {REGION_NAMES.get(region, f'регион {region}')}"])
    return {
        "id": inn,
        "name": name or f"Компания ИНН {inn}",
        "inn": inn,
        "flags": flags_for(inn, kpp, False),
        "novelty": "new",
        "role": role_code,
        "score": NEW_ROLE_SCORES[role_code],
        "part": 0,
        "wins": 0,
        "last": "—",
        "why": why,
        "site": site_without_protocol(site),
        "requisites": requisites_for(inn, kpp, json.loads(contacts) if contacts else None),
        "history": [],
        "isMsp": None,
    }


def recommend(
    conn: psycopg.Connection,
    query: str,
    okpd: str | None = None,
    eshop: bool = False,
    msp_only: bool = False,
    limit: int = 30,
) -> dict:
    if okpd is None:
        candidates = detect_okpd(conn, query)
        okpd = candidates[0][0] if candidates else None
    if okpd is None:
        return {"okpd": None, "items": []}

    params = {"prefix": f"{okpd}%", "okpd": okpd, "eshop": eshop, "candidates": limit * 5}
    reference = conn.execute("SELECT max(publish_date) FROM announcements").fetchone()[0]
    conn.execute(SIMILAR_LOTS_SQL, params)

    history = [history_item(row, reference, eshop) for row in conn.execute(HISTORY_SQL, params)]
    if msp_only:
        history = [item for item in history if item["isMsp"]]
    history = sorted(history, key=lambda item: item["score"], reverse=True)
    top, rest = history[: limit - CONTENDER_SLOTS], history[limit - CONTENDER_SLOTS:]
    contenders = [item for item in rest if item["isContender"]][:CONTENDER_SLOTS]
    fill = [item for item in rest if item not in contenders][: limit - len(top) - len(contenders)]
    history = top + contenders + fill

    by_inn = {item["inn"]: item for item in history}
    for inn, subject, start_price, customer_inn, is_winner in conn.execute(
        LOT_HISTORY_SQL, {"inns": list(by_inn), "rows": HISTORY_ROWS}
    ):
        by_inn[inn]["history"].append({
            "subject": subject,
            "nmck": round(start_price),
            "customer": f"Заказчик ИНН {customer_inn}",
            "won": is_winner,
        })

    new = sorted((new_item(row) for row in conn.execute(NEW_SQL, params)), key=lambda item: item["score"], reverse=True)

    return {"okpd": okpd, "items": history + new}


def fill_names(conn: psycopg.Connection, items: list[dict]) -> list[dict]:
    missing = [item["inn"] for item in items if item["name"].startswith("Компания ИНН")]
    if missing:
        names = dict(conn.execute("SELECT inn, name FROM suppliers WHERE inn = ANY(%s) AND name IS NOT NULL", [missing]))
        for item in items:
            if item["inn"] in names:
                item["name"] = names[item["inn"]]
                item["requisites"]["ogrn"] = egrul_record(item["inn"]).get("ogrn") or EMPTY
    return items
