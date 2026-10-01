import json
import math
from datetime import date, timedelta

import psycopg

from search import model
from worker.discover import CACHE_DIR

LOCAL_REGIONS = {"78": "Из Санкт-Петербурга", "47": "Из Ленинградской области"}
REGION_NAMES = {"78": "Санкт-Петербург", "47": "Ленинградская область"}
ROLE_CODES = {"manufacturer": "man", "distributor": "dist", "supplier": "sup"}
NEW_ROLE_SCORES = {"man": 60, "dist": 55, "sup": 50}
PLATFORM_LABELS = {True: "Электронный магазин", False: "АИС ГЗ"}
TOP_BY_WINS = 50
TOP_BY_RECENCY = 50
CONTENDER_SLOTS = 5
HISTORY_ROWS = 5
REASONS_SHOWN = 3
FACTORS_SHOWN = 5
EMPTY = "—"

SIMILAR_LOTS_SQL = """
    CREATE TEMP TABLE similar_lots ON COMMIT DROP AS
    SELECT s.lot_id, count(b.supplier_inn) AS participants
    FROM (SELECT DISTINCT lot_id FROM lots WHERE okpd_code LIKE %(prefix)s) s
    JOIN bids b ON b.lot_id = s.lot_id
    GROUP BY s.lot_id
"""

HISTORY_SQL = """
    SELECT
        b.supplier_inn,
        count(*)                                                        AS part,
        count(*) FILTER (WHERE b.is_winner)                             AS wins,
        count(*) FILTER (WHERE sl.participants >= 2)                    AS comp_part,
        count(*) FILTER (WHERE sl.participants >= 2 AND b.is_winner)    AS comp_wins,
        count(*) FILTER (WHERE sl.participants = 1)                     AS direct_cnt,
        max(a.publish_date)                                             AS last_date,
        count(*) FILTER (WHERE a.is_eshop_or_aisgz)                     AS eshop_bids,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY a.start_price)      AS typical_price,
        count(*) FILTER (WHERE a.customer_inn = %(customer)s)           AS customer_group_bids,
        s.name, s.kpp, s.role, s.role_reason
    FROM bids b
    JOIN similar_lots sl ON sl.lot_id = b.lot_id
    JOIN announcements a ON a.lot_id = b.lot_id
    JOIN suppliers s ON s.inn = b.supplier_inn
    GROUP BY b.supplier_inn, s.name, s.kpp, s.role, s.role_reason
"""

CUSTOMER_BIDS_SQL = """
    SELECT b.supplier_inn, count(*)
    FROM bids b
    JOIN announcements a ON a.lot_id = b.lot_id
    WHERE a.customer_inn = %(customer)s
    GROUP BY b.supplier_inn
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

FACTOR_GROUPS = {
    "experience": ["part", "wins", "win_share", "comp_part", "comp_wins", "comp_win_share"],
    "direct": ["direct_cnt"],
    "profile": ["total_bids", "groups_cnt", "class_bids"],
    "activity": ["days_since_last"],
    "price": ["price_fit"],
    "platform": ["platform_share"],
    "customer": ["customer_bids", "customer_group_bids"],
    "region": ["is_local"],
    "msp": ["is_msp"],
}

GROUP_ICONS = {
    "experience": "★",
    "direct": "🤝",
    "profile": "🧭",
    "activity": "↻",
    "price": "₽",
    "platform": "🏷",
    "customer": "✓",
    "region": "⌖",
    "msp": "◆",
}

MIN_IMPACT = 0.05


def valid_kpp(kpp: str | None) -> str | None:
    if kpp and len(kpp) == 9 and kpp.isdigit() and not kpp.startswith(("00", "99")):
        return kpp
    return None


def region_code(inn: str, kpp: str | None) -> str:
    kpp = valid_kpp(kpp)
    return kpp[:2] if kpp else inn[:2]


def plural(count: int, one: str, few: str, many: str) -> str:
    tail10, tail100 = count % 10, count % 100
    if tail10 == 1 and tail100 != 11:
        return one
    if 2 <= tail10 <= 4 and not 12 <= tail100 <= 14:
        return few
    return many


def bids_word(count: int) -> str:
    return f"{count} {plural(count, 'заявка', 'заявки', 'заявок')}"


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
        "kpp": valid_kpp(kpp) or valid_kpp(record.get("kpp")) or EMPTY,
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


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн ₽".replace(".", ",")
    return f"{round(value / 1000)} тыс. ₽"


def flags_for(inn: str, kpp: str | None, is_msp: bool) -> list[str]:
    flags = []
    if is_msp:
        flags.append("МСП")
    if len(inn) == 12:
        flags.append("ИП")
    if valid_kpp(kpp) and kpp[4:6] == "43":
        flags.append("Филиал")
    return flags


def group_text(group: str, positive: bool, row: dict, lot: dict, values: dict[str, float]) -> str | None:
    platform = PLATFORM_LABELS[lot["eshop"]]
    share = round(100 * values["platform_share"])
    if group == "experience":
        if not row["comp_part"]:
            return f"{bids_word(row['part'])} в категории, конкурентных закупок не было"
        wins = row["comp_wins"]
        share = round(100 * wins / row["comp_part"])
        return f"В конкурентных закупках: {bids_word(row['comp_part'])}, {wins} {plural(wins, 'победа', 'победы', 'побед')} ({share}%)"
    if group == "direct":
        if not positive or not row["direct_cnt"]:
            return None
        return f"Договоры без конкурентов (единственный участник): {row['direct_cnt']}"
    if group == "profile":
        if positive:
            return f"Профильный поставщик: {bids_word(round(values['class_bids']))} в категориях {lot['okpd'][:2]}.*"
        return f"Широкий профиль: работает в {round(values['groups_cnt'])} категориях ОКПД2"
    if group == "activity":
        return f"{'Активен' if positive else 'Давно не участвовал'}: последняя заявка {ago(row['days'])}"
    if group == "price":
        closeness = "близко к вашей НМЦК" if positive else "далеко от вашей НМЦК"
        return f"Обычно участвует в лотах около {money(row['typical_price'])}, {closeness}"
    if group == "platform":
        return f"{'Активен' if positive else 'Редко участвует'} на площадке «{platform}»: {share}% заявок"
    if group == "customer":
        if positive:
            return f"Уже работал с этим заказчиком: {bids_word(round(values['customer_bids']))}, в этой категории {row['customer_group_bids']}"
        return "Ещё не подавал заявки этому заказчику"
    if group == "region":
        return LOCAL_REGIONS.get(row["region"], f"Иногородний, регион {row['region']}")
    if group == "msp":
        return "Субъект МСП" if positive else None
    return None


def grouped_impacts(impacts: dict[str, float], lot: dict) -> list[tuple[str, float]]:
    totals = {
        group: sum(impacts.get(name, 0.0) for name in names)
        for group, names in FACTOR_GROUPS.items()
        if not (group == "customer" and lot["customer"] is None)
    }
    return sorted(totals.items(), key=lambda item: abs(item[1]), reverse=True)


def formula_score(row: dict, lot: dict) -> float:
    eshop_share = row["eshop_bids"] / row["part"]
    platform_share = eshop_share if lot["eshop"] else 1 - eshop_share
    fit = max(0.0, 1 - abs(math.log10(max(lot["nmck"], 1.0) / max(row["typical_price"], 1.0))) / 2)
    return (
        25 * min(1.0, math.log1p(row["part"]) / math.log1p(300))
        + 25 * (row["wins"] + 1) / (row["part"] + 2)
        + 20 * max(0.0, 1 - row["days"] / 730)
        + 10 * row["is_local"]
        + 10 * platform_share
        + 10 * fit
    )


def select_candidates(rows: list[dict]) -> list[dict]:
    by_wins = sorted(rows, key=lambda row: (row["wins"], row["part"]), reverse=True)[:TOP_BY_WINS]
    by_recency = sorted(rows, key=lambda row: row["last_date"], reverse=True)[:TOP_BY_RECENCY]
    with_customer = [row for row in rows if row["customer_group_bids"] > 0]
    selected = {row["inn"]: row for row in by_wins + by_recency + with_customer}
    return list(selected.values())


def explain(row: dict, lot: dict, impacts: dict[str, float] | None) -> tuple[list[list[str]], list[dict]]:
    values = model.feature_values(row, lot)
    contender = is_contender(row)
    why = []
    if contender:
        why.append(["↻", f"В конкурентных закупках: {bids_word(row['comp_part'])}, побед только {row['comp_wins']}: готов конкурировать"])
    if row["days"] > 180:
        why.append(["💤", f"Последняя заявка {ago(row['days'])}, стоит напомнить о закупке"])

    if impacts is None:
        why.append(["★", group_text("experience", True, row, lot, values)])
        return why[:REASONS_SHOWN], []

    factors = []
    for group, impact in grouped_impacts(impacts, lot):
        if abs(impact) < MIN_IMPACT:
            continue
        text = group_text(group, impact > 0, row, lot, values)
        if text is None:
            continue
        factors.append({"text": text, "impact": round(impact, 3)})
        if impact > 0 and len(why) < REASONS_SHOWN and not (group == "experience" and contender):
            why.append([GROUP_ICONS[group], text])
    return why, factors[:FACTORS_SHOWN]


def is_contender(row: dict) -> bool:
    return row["comp_part"] >= 3 and row["comp_wins"] / row["comp_part"] < 0.2


def history_item(row: dict, lot: dict, score: int, impacts: dict[str, float] | None) -> dict:
    why, factors = explain(row, lot, impacts)
    return {
        "id": row["inn"],
        "name": row["name"] or f"Компания ИНН {row['inn']}",
        "inn": row["inn"],
        "flags": flags_for(row["inn"], row["kpp"], row["is_msp"]),
        "novelty": "existing",
        "role": ROLE_CODES.get(row["role"], "sup"),
        "score": score,
        "part": row["comp_part"],
        "wins": row["comp_wins"],
        "direct": row["direct_cnt"],
        "last": ago(row["days"]),
        "why": why,
        "factors": factors,
        "site": "",
        "requisites": requisites_for(row["inn"], row["kpp"]),
        "history": [],
        "isMsp": row["is_msp"],
        "isContender": is_contender(row),
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
        "direct": 0,
        "last": "—",
        "why": why,
        "factors": [],
        "site": site_without_protocol(site),
        "requisites": requisites_for(inn, kpp, json.loads(contacts) if contacts else None),
        "history": [],
        "isMsp": None,
    }


def load_rows(conn: psycopg.Connection, params: dict, lot_date: date) -> list[dict]:
    profiles, _ = model.supplier_profiles()
    customer_bids = dict(conn.execute(CUSTOMER_BIDS_SQL, params)) if params["customer"] else {}
    rows = []
    for (
        inn, part, wins, comp_part, comp_wins, direct_cnt, last_date, eshop_bids, typical_price,
        customer_group_bids, name, kpp, role, role_reason,
    ) in conn.execute(HISTORY_SQL, params):
        rows.append({
            "inn": inn,
            "part": part,
            "wins": wins,
            "comp_part": comp_part,
            "comp_wins": comp_wins,
            "direct_cnt": direct_cnt,
            "last_date": last_date,
            "days": (lot_date - last_date).days,
            "eshop_bids": eshop_bids,
            "typical_price": float(typical_price),
            "customer_group_bids": customer_group_bids,
            "customer_bids": customer_bids.get(inn, 0),
            "name": name,
            "kpp": kpp,
            "role": role,
            "role_reason": role_reason,
            "region": region_code(inn, kpp),
            "is_local": region_code(inn, kpp) in LOCAL_REGIONS,
            "is_msp": profiles.get(inn, (0, 0, False))[2],
        })
    return rows


def scale(scores: list[float]) -> list[int]:
    low, high = min(scores), max(scores)
    if high - low < 1e-9:
        return [100 for _ in scores]
    return [round(100 * (score - low) / (high - low)) for score in scores]


def recommend(
    conn: psycopg.Connection,
    okpd: str,
    nmck: float | None = None,
    eshop: bool = False,
    msp_only: bool = False,
    customer_inn: str | None = None,
    limit: int = 30,
) -> dict:
    params = {"prefix": f"{okpd}%", "okpd": okpd, "customer": customer_inn}
    lot_date = conn.execute("SELECT max(publish_date) FROM announcements").fetchone()[0] + timedelta(days=1)
    lot = {"okpd": okpd, "nmck": float(nmck or 0), "eshop": eshop, "smp": msp_only, "customer": customer_inn}
    conn.execute(SIMILAR_LOTS_SQL, params)

    candidates = select_candidates(load_rows(conn, params, lot_date))
    if msp_only:
        candidates = [row for row in candidates if row["is_msp"]]

    history = []
    if candidates:
        if model.model_available():
            raw_scores, impacts = model.predict(candidates, lot)
            raw_scores = list(raw_scores)
        else:
            raw_scores, impacts = [formula_score(row, lot) for row in candidates], [None] * len(candidates)
        history = [
            history_item(row, lot, score, impact)
            for row, score, impact in zip(candidates, scale(raw_scores), impacts)
        ]

    history = sorted(history, key=lambda item: item["score"], reverse=True)
    top, rest = history[: limit - CONTENDER_SLOTS], history[limit - CONTENDER_SLOTS:]
    contenders = [item for item in rest if item["isContender"]][:CONTENDER_SLOTS]
    fill = [item for item in rest if item not in contenders][: limit - len(top) - len(contenders)]
    history = top + contenders + fill

    by_inn = {item["inn"]: item for item in history}
    for inn, subject, start_price, lot_customer, is_winner in conn.execute(
        LOT_HISTORY_SQL, {"inns": list(by_inn), "rows": HISTORY_ROWS}
    ):
        by_inn[inn]["history"].append({
            "subject": subject,
            "nmck": round(start_price),
            "customer": f"Заказчик ИНН {lot_customer}",
            "won": is_winner,
        })

    new = sorted((new_item(row) for row in conn.execute(NEW_SQL, params)), key=lambda item: item["score"], reverse=True)
    return {"okpd": okpd, "items": history + new, "model": model.model_available()}


def fill_names(conn: psycopg.Connection, items: list[dict]) -> list[dict]:
    missing = [item["inn"] for item in items if item["name"].startswith("Компания ИНН")]
    if missing:
        names = dict(conn.execute("SELECT inn, name FROM suppliers WHERE inn = ANY(%s) AND name IS NOT NULL", [missing]))
        for item in items:
            if item["inn"] in names:
                item["name"] = names[item["inn"]]
                item["requisites"]["ogrn"] = egrul_record(item["inn"]).get("ogrn") or EMPTY
    return items
