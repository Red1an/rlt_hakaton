import json
import math
from datetime import date, timedelta

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    Table,
    and_,
    any_,
    distinct,
    exists,
    func,
    insert,
    or_,
    select,
)
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from database import AnnouncementModel, BidModel, LotModel, SuppliersModel

from . import model
from worker.dadata import okved_section
from worker.discover import CACHE_DIR

LOCAL_REGIONS = {"78": "Из Санкт-Петербурга", "47": "Из Ленинградской области"}
REGION_NAMES = {"78": "Санкт-Петербург", "47": "Ленинградская область"}
ROLE_CODES = {"manufacturer": "man", "distributor": "dist", "supplier": "sup"}
STATUS_FLAGS = {"LIQUIDATING": "Ликвидируется", "REORGANIZING": "Реорганизация"}
NEW_ROLE_SCORES = {"man": 60, "dist": 55, "sup": 50}
PLATFORM_LABELS = {True: "Электронный магазин", False: "АИС ГЗ"}
TOP_BY_WINS = 50
TOP_BY_RECENCY = 50
CONTENDER_SLOTS = 5
HISTORY_ROWS = 5
REASONS_SHOWN = 3
FACTORS_SHOWN = 5
EMPTY = "—"
CLOSED_STATUSES = ("LIQUIDATED", "BANKRUPT")

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


def similar_lots() -> Table:
    return Table(
        "similar_lots",
        MetaData(),
        Column("lot_id", Integer),
        Column("participants", Integer),
        prefixes=["TEMPORARY"],
        postgresql_on_commit="DROP",
    )


def create_similar_lots(session: Session, prefixes: list[str]) -> Table:
    table = similar_lots()
    category = select(distinct(LotModel.lot_id)).where(LotModel.okpd_code.like(any_(prefixes))).subquery()
    session.execute(CreateTable(table))
    session.execute(
        insert(table).from_select(
            ["lot_id", "participants"],
            select(
                category.c.lot_id,
                func.count(BidModel.supplier_inn).label("participants"),
            )
            .select_from(category)
            .join(BidModel, BidModel.lot_id == category.c.lot_id)
            .group_by(category.c.lot_id),
        )
    )
    return table


def history_stmt(groups: Table, customer: str | None):
    competing = groups.c.participants >= 2
    return (
        select(
            BidModel.supplier_inn,
            func.count().label("part"),
            func.count().filter(BidModel.is_winner).label("wins"),
            func.count().filter(competing).label("comp_part"),
            func.count().filter(and_(competing, BidModel.is_winner)).label("comp_wins"),
            func.count().filter(groups.c.participants == 1).label("direct_cnt"),
            func.max(AnnouncementModel.publish_date).label("last_date"),
            func.count().filter(AnnouncementModel.is_eshop_or_aisgz).label("eshop_bids"),
            func.percentile_cont(0.5).within_group(AnnouncementModel.start_price).label("typical_price"),
            func.count().filter(AnnouncementModel.customer_inn == customer).label("customer_group_bids"),
            SuppliersModel.name,
            SuppliersModel.kpp,
            SuppliersModel.role,
            SuppliersModel.role_reason,
            SuppliersModel.status,
            SuppliersModel.ogrn,
            SuppliersModel.okved_main,
            SuppliersModel.region_code,
            SuppliersModel.reg_date,
        )
        .select_from(BidModel)
        .join(groups, groups.c.lot_id == BidModel.lot_id)
        .join(AnnouncementModel, AnnouncementModel.lot_id == BidModel.lot_id)
        .join(SuppliersModel, SuppliersModel.inn == BidModel.supplier_inn)
        .where(or_(SuppliersModel.status.is_(None), SuppliersModel.status.not_in(CLOSED_STATUSES)))
        .group_by(
            BidModel.supplier_inn,
            SuppliersModel.name,
            SuppliersModel.kpp,
            SuppliersModel.role,
            SuppliersModel.role_reason,
            SuppliersModel.status,
            SuppliersModel.ogrn,
            SuppliersModel.okved_main,
            SuppliersModel.region_code,
            SuppliersModel.reg_date,
        )
    )


def customer_bids_stmt(customer: str | None):
    return (
        select(BidModel.supplier_inn, func.count().label("bids"))
        .select_from(BidModel)
        .join(AnnouncementModel, AnnouncementModel.lot_id == BidModel.lot_id)
        .where(AnnouncementModel.customer_inn == customer)
        .group_by(BidModel.supplier_inn)
    )


def new_stmt(codes: list[str]):
    code = func.unnest(SuppliersModel.okpds).table_valued("code").render_derived()
    wanted = func.unnest(codes).table_valued("wanted").render_derived()
    matching = exists(
        select(1)
        .select_from(code, wanted)
        .where(or_(code.c.code.like(wanted.c.wanted + "%"), wanted.c.wanted.like(code.c.code + "%")))
    )
    return select(
        SuppliersModel.inn,
        SuppliersModel.kpp,
        SuppliersModel.name,
        SuppliersModel.role,
        SuppliersModel.role_reason,
        SuppliersModel.site,
        SuppliersModel.contacts,
        SuppliersModel.status,
        SuppliersModel.ogrn,
        SuppliersModel.okved_main,
        SuppliersModel.region_code,
        SuppliersModel.reg_date,
    ).where(
        SuppliersModel.source == "web",
        or_(SuppliersModel.status.is_(None), SuppliersModel.status.not_in(CLOSED_STATUSES)),
        matching,
    )


def lot_history_stmt(groups: Table, inns: list[str], rows: int):
    ranked = (
        select(
            BidModel.supplier_inn.label("inn"),
            AnnouncementModel.subject,
            AnnouncementModel.start_price,
            AnnouncementModel.customer_inn,
            BidModel.is_winner,
            func.row_number()
            .over(partition_by=BidModel.supplier_inn, order_by=AnnouncementModel.publish_date.desc())
            .label("position"),
        )
        .select_from(BidModel)
        .join(groups, groups.c.lot_id == BidModel.lot_id)
        .join(AnnouncementModel, AnnouncementModel.lot_id == BidModel.lot_id)
        .where(BidModel.supplier_inn.in_(inns))
        .subquery()
    )
    return select(
        ranked.c.inn,
        ranked.c.subject,
        ranked.c.start_price,
        ranked.c.customer_inn,
        ranked.c.is_winner,
    ).where(ranked.c.position <= rows)


def history_end_stmt():
    return select(func.max(AnnouncementModel.publish_date)).where(AnnouncementModel.dataset == "history")


def names_stmt(inns: list[str]):
    return select(SuppliersModel.inn, SuppliersModel.name).where(
        SuppliersModel.inn.in_(inns),
        SuppliersModel.name.is_not(None),
    )


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


def company_age(reg_date: date | None, today: date) -> str | None:
    if reg_date is None:
        return None
    years = (today - reg_date).days // 365
    if years < 1:
        return "Компания зарегистрирована меньше года назад"
    return f"Компании {years} {plural(years, 'год', 'года', 'лет')}"


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
        "flags": flags_for(row, row["is_msp"]),
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
        "requisites": requisites_for(row),
        "roleReason": row["role_reason"],
        "status": row.get("status"),
        "history": [],
        "isMsp": row["is_msp"],
        "isContender": is_contender(row),
    }


def new_item(row: dict) -> dict:
    role_code = ROLE_CODES.get(row["role"], "sup")
    region = row["region_code"] or region_code(row["inn"], row["kpp"])
    why = [["✦", "Нет в истории госзакупок, найден в открытых источниках"]]
    if row["role_reason"]:
        why.append(["⚙", row["role_reason"]])
    age = company_age(row["reg_date"], date.today())
    status_text = "Действующая компания" if row["status"] in (None, "ACTIVE") else STATUS_FLAGS.get(row["status"], row["status"])
    why.append(["✓", f"{status_text}, {REGION_NAMES.get(region, f'регион {region}')}" + (f". {age}" if age else "")])
    contacts = json.loads(row["contacts"]) if row["contacts"] else None
    return {
        "id": row["inn"],
        "name": row["name"] or f"Компания ИНН {row['inn']}",
        "inn": row["inn"],
        "flags": flags_for(row, False),
        "novelty": "new",
        "role": role_code,
        "score": NEW_ROLE_SCORES[role_code],
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
        "history": [],
        "isMsp": None,
    }


def load_rows(session: Session, groups: Table, customer: str | None, lot_date: date) -> list[dict]:
    profiles, _ = model.supplier_profiles()
    customer_bids = dict(session.execute(customer_bids_stmt(customer)).all()) if customer else {}
    rows = []
    for mapping in session.execute(history_stmt(groups, customer)).mappings():
        record = dict(mapping)
        inn = record.pop("supplier_inn")
        region = record["region_code"] or region_code(inn, record["kpp"])
        rows.append({
            **record,
            "inn": inn,
            "days": (lot_date - record["last_date"]).days,
            "typical_price": float(record["typical_price"]),
            "customer_bids": customer_bids.get(inn, 0),
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


def recommend(
    session: Session,
    okpd: str,
    nmck: float | None = None,
    eshop: bool = False,
    msp_only: bool = False,
    customer_inn: str | None = None,
    limit: int = 30,
    extra_codes: list[str] | None = None,
    lot_date: date | None = None,
) -> dict:
    codes = [okpd] + [code for code in extra_codes or [] if code != okpd]
    lot_date = lot_date or session.execute(history_end_stmt()).scalar() + timedelta(days=1)
    lot = {"okpd": okpd, "nmck": float(nmck or 0), "eshop": eshop, "smp": msp_only, "customer": customer_inn}
    groups = create_similar_lots(session, [f"{code}%" for code in codes])

    candidates = select_candidates(load_rows(session, groups, customer_inn, lot_date))
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
    if by_inn:
        for row in session.execute(lot_history_stmt(groups, list(by_inn), HISTORY_ROWS)):
            by_inn[row.inn]["history"].append({
                "subject": row.subject,
                "nmck": round(row.start_price),
                "customer": f"Заказчик ИНН {row.customer_inn}",
                "won": row.is_winner,
            })

    new = sorted(
        (new_item(dict(mapping)) for mapping in session.execute(new_stmt(codes)).mappings()),
        key=lambda item: item["score"],
        reverse=True,
    )
    return {"okpd": okpd, "items": history + new, "model": model.model_available()}


def fill_names(session: Session, items: list[dict]) -> list[dict]:
    missing = [item["inn"] for item in items if item["name"].startswith("Компания ИНН")]
    if missing:
        names = dict(session.execute(names_stmt(missing)).all())
        for item in items:
            if item["inn"] in names:
                item["name"] = names[item["inn"]]
                item["requisites"]["ogrn"] = egrul_record(item["inn"]).get("ogrn") or EMPTY
    return items