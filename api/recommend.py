import json
import math
from datetime import date, timedelta

import psycopg
from psycopg.rows import dict_row

from . import model
from worker.dadata import okved_section
from worker.discover import CACHE_DIR

LOCAL_REGIONS = {"78": "Из Санкт-Петербурга", "47": "Из Ленинградской области"}
REGION_NAMES = {"78": "Санкт-Петербург", "47": "Ленинградская область"}
ROLE_CODES = {"manufacturer": "man", "distributor": "dist", "supplier": "sup"}
STATUS_FLAGS = {"LIQUIDATING": "Ликвидируется", "REORGANIZING": "Реорганизация"}
NEW_ROLE_REASONS = {
    "man": ["🏭", "Производитель: можно закупать напрямую, без посредников"],
    "dist": ["📦", "Оптовая торговля: поставка со склада"],
}
NEW_ROLE_POINTS = {"man": 15, "dist": 10, "sup": 5}
NEW_STATUS_POINTS = {"ACTIVE": 10, None: 5}
NEW_CODE_POINTS = 20
NEW_OKVED_POINTS = {4: 15, 2: 7}
NEW_REGION_POINTS = 10
NEW_SITE_POINTS = 5
NEW_CONTACTS_POINTS = 5
NEW_AGE_POINTS = 10
NEW_MATURE_YEARS = 25
NEW_BRANCH_POINTS = 5
NEW_STAFF_POINTS = 10
NEW_STAFF_LARGE = 100
WIN_PRIOR_WINS = 1
WIN_PRIOR_BIDS = 5
WIN_FLOOR = 0.001
PLATFORM_LABELS = {True: "Электронный магазин", False: "АИС ГЗ"}
TOP_BY_WINS = 50
TOP_BY_RECENCY = 50
CONTENDER_SLOTS = 5
CONTENDER_MIN_PARTICIPATION = 10
SUITABILITY_FLOOR = 0.005
HISTORY_ROWS = 5
REASONS_SHOWN = 3
FACTORS_SHOWN = 5
EMPTY = "—"

SIMILAR_LOTS_SQL = """
    CREATE TEMP TABLE similar_lots ON COMMIT DROP AS
    SELECT s.lot_id, count(b.supplier_inn) AS participants
    FROM (
        SELECT DISTINCT lot_id FROM lots
        WHERE left(okpd_code, 5) = ANY(%(groups)s) AND okpd_code LIKE ANY(%(prefixes)s)
    ) s
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
        array_agg(b.lot_id)                                             AS lot_ids,
        s.name, s.kpp, s.role, s.role_reason, s.status, s.ogrn, s.okved_main, s.region_code, s.reg_date, s.enriched_at
    FROM bids b
    JOIN similar_lots sl ON sl.lot_id = b.lot_id
    JOIN announcements a ON a.lot_id = b.lot_id
    JOIN suppliers s ON s.inn = b.supplier_inn
    WHERE (s.status IS NULL OR s.status NOT IN ('LIQUIDATED', 'BANKRUPT'))
    GROUP BY b.supplier_inn, s.name, s.kpp, s.role, s.role_reason, s.status, s.ogrn, s.okved_main, s.region_code, s.reg_date, s.enriched_at
"""

CUSTOMER_BIDS_SQL = """
    SELECT b.supplier_inn, count(*)
    FROM bids b
    JOIN announcements a ON a.lot_id = b.lot_id
    WHERE a.customer_inn = %(customer)s
    GROUP BY b.supplier_inn
"""

NEW_SQL = """
    SELECT inn, kpp, name, role, role_reason, site, contacts, status, ogrn, okved_main, region_code, reg_date, enriched_at, source, okpds, employees,
        coalesce((dadata->'data'->>'branch_count')::int, (dadata->>'branch_count')::int, 0) AS branches,
        (SELECT o.name FROM okpd o WHERE o.code = s.okved_main) AS okved_name
    FROM suppliers s
    WHERE source IN ('web', 'dadata')
      AND (s.status IS NULL OR s.status NOT IN ('LIQUIDATED', 'BANKRUPT'))
      AND EXISTS (
          SELECT 1 FROM unnest(okpds) code, unnest(%(codes)s::text[]) wanted
          WHERE code LIKE wanted || '%%' OR wanted LIKE code || '%%'
      )
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
    "experience": ["comp_part", "comp_wins", "comp_win_share"],
    "volume": ["part", "wins", "win_share"],
    "direct": ["direct_cnt", "direct_share"],
    "profile": ["total_bids", "groups_cnt", "class_bids", "spec_share"],
    "typicality": ["typicality"],
    "activity": ["days_since_last"],
    "price": ["price_fit"],
    "platform": ["platform_share"],
    "customer": ["customer_bids", "customer_group_bids"],
    "region": ["is_local"],
    "msp": ["is_msp"],
}

GROUP_ICONS = {
    "typicality": "🎯",
    "volume": "📊",
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


def okved_text(okved: str | None) -> str:
    if not okved:
        return EMPTY
    section = okved_section(okved)
    return f"{okved} — {section}" if section else okved


def requisites_for(row: dict, contacts: dict | None = None) -> dict:
    record = egrul_record(row["inn"])
    region = row.get("region_code") or region_code(row["inn"], row["kpp"])
    contacts = contacts or {}
    return {
        "kpp": valid_kpp(row["kpp"]) or valid_kpp(record.get("kpp")) or EMPTY,
        "ogrn": row.get("ogrn") or record.get("ogrn") or EMPTY,
        "okved": okved_text(row.get("okved_main")),
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


def flags_for(row: dict, is_msp: bool) -> list[str]:
    flags = []
    if is_msp:
        flags.append("МСП")
    if len(row["inn"]) == 12:
        flags.append("ИП")
    if valid_kpp(row["kpp"]) and row["kpp"][4:6] == "43":
        flags.append("Филиал")
    if row.get("status") in STATUS_FLAGS:
        flags.append(STATUS_FLAGS[row["status"]])
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
    if group == "volume":
        if positive:
            return f"Всего в категории: {bids_word(row['part'])}, из них без конкурентов {row['direct_cnt']}"
        return f"Мало заявок в категории: {bids_word(row['part'])}"
    if group == "typicality":
        if row["typicality"] != row["typicality"]:
            return None
        if positive:
            return "Профиль закупок совпадает с категорией: предметы его лотов типичны для неё"
        return "Предметы его лотов нетипичны для категории: часто другие работы и товары"
    if group == "direct":
        if not row["direct_cnt"]:
            return None
        share = round(100 * row["direct_cnt"] / row["part"])
        if positive:
            return f"Договоры без конкурентов (единственный участник): {row['direct_cnt']}"
        return f"Часто работает без конкуренции: {share}% заявок — единственный участник"
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
        why.append(["↻", f"Часто участвует, но редко выигрывает: {bids_word(row['comp_part'])}, побед {row['comp_wins']}. Добавит конкуренции"])
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


def verification(row: dict) -> dict | None:
    if row.get("enriched_at") and row.get("status") != "NOT_FOUND":
        return {"by": "dadata", "at": row["enriched_at"].date().isoformat()}
    if row.get("name"):
        return {"by": "egrul", "at": None}
    return None


def needs_check(item: dict) -> bool:
    return item["name"].startswith("Компания ИНН")


def suitability(probability: float, ceiling: float, floor: float = SUITABILITY_FLOOR) -> int:
    share = math.log(max(probability, floor) / floor) / math.log(ceiling / floor)
    return round(100 * min(max(share, 0.0), 1.0))


def win_rate(row: dict) -> float:
    return (row["comp_wins"] + WIN_PRIOR_WINS) / (row["comp_part"] + WIN_PRIOR_BIDS)


def win_prior() -> float:
    return WIN_PRIOR_WINS / WIN_PRIOR_BIDS


def history_item(
    row: dict,
    lot: dict,
    score: int,
    impacts: dict[str, float] | None,
    score_kind: str,
    lift: float | None,
    participation: int | None,
) -> dict:
    why, factors = explain(row, lot, impacts)
    return {
        "id": row["inn"],
        "name": row["name"] or f"Компания ИНН {row['inn']}",
        "inn": row["inn"],
        "flags": flags_for(row, row["is_msp"]),
        "novelty": "existing",
        "role": ROLE_CODES.get(row["role"], "sup"),
        "score": score,
        "scoreKind": score_kind,
        "lift": lift,
        "participation": participation,
        "part": row["comp_part"],
        "wins": row["comp_wins"],
        "direct": row["direct_cnt"],
        "last": ago(row["days"]),
        "why": why,
        "factors": factors,
        "site": "",
        "requisites": requisites_for(row),
        "roleReason": row["role_reason"],
        "status": row.get("status"),
        "verified": verification(row),
        "history": [],
        "isMsp": row["is_msp"],
        "isContender": is_contender(row),
    }


def code_match(supplier_codes: list[str], wanted_codes: list[str]) -> float:
    best = 0.0
    for code in supplier_codes or []:
        for wanted in wanted_codes:
            if code.startswith(wanted):
                return 1.0
            if wanted.startswith(code):
                best = max(best, len(code.replace(".", "")) / len(wanted.replace(".", "")))
    return best


def has_contacts(contacts: str | None) -> bool:
    if not contacts:
        return False
    try:
        return bool(json.loads(contacts))
    except ValueError:
        return False


def okved_points(okved: str | None, codes: list[str]) -> int:
    digits = (okved or "").replace(".", "")
    for length, points in NEW_OKVED_POINTS.items():
        if len(digits) >= length and any(code.replace(".", "")[:length] == digits[:length] for code in codes):
            return points
    return 0


def new_score(row: dict, codes: list[str], region: str) -> int:
    role_code = ROLE_CODES.get(row["role"], "sup")
    years = (date.today() - row["reg_date"]).days / 365 if row["reg_date"] else None
    staff = row["employees"] or 0
    score = (
        NEW_CODE_POINTS * code_match(row["okpds"], codes)
        + okved_points(row["okved_main"], codes)
        + NEW_STAFF_POINTS * min(math.log1p(staff) / math.log1p(NEW_STAFF_LARGE), 1.0)
        + NEW_ROLE_POINTS[role_code]
        + NEW_STATUS_POINTS.get(row["status"], 0)
        + (NEW_AGE_POINTS * min(math.log1p(years) / math.log1p(NEW_MATURE_YEARS), 1.0) if years is not None else NEW_AGE_POINTS / 2)
        + (NEW_BRANCH_POINTS if row["branches"] else 0)
        + (NEW_REGION_POINTS if region in LOCAL_REGIONS else 0)
        + (NEW_SITE_POINTS if row["site"] else 0)
        + (NEW_CONTACTS_POINTS if has_contacts(row["contacts"]) else 0)
    )
    return round(min(score, 100))


def profile_text(row: dict, codes: list[str]) -> list[str] | None:
    okved = row["okved_main"]
    if not okved:
        return None
    activity = f"ОКВЭД {okved}" + (f" — {row['okved_name'].lower()}" if row["okved_name"] else "")
    points = okved_points(okved, codes)
    if points == max(NEW_OKVED_POINTS.values()):
        return ["🎯", f"Основной вид деятельности совпадает с закупкой: {activity}"]
    if points:
        return ["🎯", f"Смежный профиль: {activity}"]
    return ["🧭", f"Основной профиль другой ({activity}), категория среди дополнительных"]


def reliability_text(row: dict) -> list[str]:
    if row["status"] not in (None, "ACTIVE"):
        return ["⚠", f"{STATUS_FLAGS.get(row['status'], row['status'])}: уточните, может ли компания заключить договор"]
    if row["reg_date"] is None:
        return ["✓", "Действующая компания"]
    years = (date.today() - row["reg_date"]).days // 365
    if years < 1:
        return ["⚠", "Зарегистрирована меньше года назад: проверьте надёжность"]
    branches = ", есть филиалы" if row["branches"] else ""
    return ["✓", f"{years} {plural(years, 'год', 'года', 'лет')} на рынке, компания действующая{branches}"]


def new_item(row: dict, codes: list[str]) -> dict:
    role_code = ROLE_CODES.get(row["role"], "sup")
    region = row["region_code"] or region_code(row["inn"], row["kpp"])
    why = [line for line in [profile_text(row, codes), NEW_ROLE_REASONS.get(role_code)] if line]
    why.append(reliability_text(row))
    contacts = json.loads(row["contacts"]) if row["contacts"] else None
    return {
        "id": row["inn"],
        "name": row["name"] or f"Компания ИНН {row['inn']}",
        "inn": row["inn"],
        "flags": flags_for(row, False),
        "novelty": "new",
        "role": role_code,
        "score": new_score(row, codes, region),
        "scoreKind": "new",
        "part": 0,
        "wins": 0,
        "direct": 0,
        "last": "—",
        "why": why,
        "factors": [],
        "site": site_without_protocol(row["site"]),
        "requisites": requisites_for(row, contacts),
        "roleReason": row["role_reason"],
        "status": row["status"],
        "verified": verification(row),
        "history": [],
        "isMsp": None,
    }


def load_rows(conn: psycopg.Connection, params: dict, lot_date: date) -> list[dict]:
    profiles, _ = model.supplier_profiles()
    customer_bids = dict(conn.execute(CUSTOMER_BIDS_SQL, params)) if params["customer"] else {}
    rows = []
    with conn.cursor(row_factory=dict_row) as cur:
        for record in cur.execute(HISTORY_SQL, params):
            inn = record.pop("supplier_inn")
            region = record["region_code"] or region_code(inn, record["kpp"])
            rows.append({
                **record,
                "inn": inn,
                "days": (lot_date - record["last_date"]).days,
                "typical_price": float(record["typical_price"]),
                "customer_bids": customer_bids.get(inn, 0),
                "typicality": model.lots_typicality(record.pop("lot_ids")),
                "region": region,
                "is_local": region in LOCAL_REGIONS,
                "is_msp": profiles.get(inn, (0, 0, False))[2],
            })
    return rows


def scale(scores: list[float]) -> list[int]:
    low, high = min(scores), max(scores)
    if high - low < 1e-9:
        return [100 for _ in scores]
    return [round(100 * (score - low) / (high - low)) for score in scores]


HISTORY_END_SQL = "SELECT max(publish_date) FROM announcements WHERE dataset = 'history'"


def recommend(
    conn: psycopg.Connection,
    okpd: str,
    nmck: float | None = None,
    eshop: bool | None = False,
    msp_only: bool = False,
    customer_inn: str | None = None,
    limit: int = 30,
    extra_codes: list[str] | None = None,
    lot_date: date | None = None,
) -> dict:
    codes = [okpd] + [code for code in extra_codes or [] if code != okpd]
    params = {
        "prefixes": [f"{code}%" for code in codes],
        "groups": sorted({code[:5] for code in codes}),
        "codes": codes,
        "customer": customer_inn,
    }
    lot_date = lot_date or conn.execute(HISTORY_END_SQL).fetchone()[0] + timedelta(days=1)
    lot = {"okpd": okpd, "nmck": float(nmck or 0), "eshop": eshop, "smp": msp_only, "customer": customer_inn}
    conn.execute(SIMILAR_LOTS_SQL, params)

    candidates = select_candidates(load_rows(conn, params, lot_date))
    if msp_only:
        candidates = [row for row in candidates if row["is_msp"]]

    history = []
    if candidates:
        variants = [{**lot, "eshop": value} for value in ((True, False) if eshop is None else (eshop,))]
        if model.model_available():
            per_variant = [
                (list(scores), impacts)
                for scores, impacts in (model.predict(candidates, variant) for variant in variants)
            ]
        else:
            per_variant = [
                ([formula_score(row, variant) for row in candidates], [None] * len(candidates))
                for variant in variants
            ]
        best = [
            max(range(len(variants)), key=lambda index: per_variant[index][0][position])
            for position in range(len(candidates))
        ]
        raw_scores = [per_variant[index][0][position] for position, index in enumerate(best)]
        impacts = [per_variant[index][1][position] for position, index in enumerate(best)]
        row_lots = [variants[index] for index in best]

        probabilities = model.participation(raw_scores) if model.model_available() else None
        if probabilities is None:
            scores, lifts, score_kind = scale(raw_scores), [None] * len(candidates), "relative"
            participations = [None] * len(candidates)
            order = raw_scores
        else:
            base_rate, ceiling = model.calibration_scale()
            expected = [probability * win_rate(row) for probability, row in zip(probabilities, candidates)]
            scores = [suitability(value, ceiling * win_prior() * 2, WIN_FLOOR) for value in expected]
            lifts = [round(value / (base_rate * win_prior()), 1) if base_rate else None for value in expected]
            participations = [round(100 * probability) for probability in probabilities]
            score_kind = "suitability"
            order = expected
        history = [
            history_item(row, row_lot, score, impact, score_kind, lift, participation)
            for row, row_lot, score, impact, lift, participation, _ in sorted(
                zip(candidates, row_lots, scores, impacts, lifts, participations, order),
                key=lambda entry: entry[6],
                reverse=True,
            )
        ]

    top, rest = history[: limit - CONTENDER_SLOTS], history[limit - CONTENDER_SLOTS:]
    contenders = [
        item for item in rest
        if item["isContender"] and (item["participation"] or item["score"]) >= CONTENDER_MIN_PARTICIPATION
    ][:CONTENDER_SLOTS]
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

    with conn.cursor(row_factory=dict_row) as cur:
        new = sorted(
            (new_item(row, codes) for row in cur.execute(NEW_SQL, params)),
            key=lambda item: item["score"],
            reverse=True,
        )
    return {"okpd": okpd, "items": history + new, "model": model.model_available()}


def fill_names(conn: psycopg.Connection, items: list[dict]) -> list[dict]:
    if not items:
        return items
    rows = conn.execute(
        "SELECT inn, name, status, enriched_at, ogrn FROM suppliers WHERE inn = ANY(%s)",
        [[item["inn"] for item in items]],
    )
    known = {row[0]: dict(zip(("inn", "name", "status", "enriched_at", "ogrn"), row)) for row in rows}
    for item in items:
        row = known.get(item["inn"])
        if row is None:
            continue
        item["verified"] = verification(row)
        if row["name"] and item["name"].startswith("Компания ИНН"):
            item["name"] = row["name"]
            item["requisites"]["ogrn"] = row["ogrn"] or egrul_record(item["inn"]).get("ogrn") or EMPTY
    return items
