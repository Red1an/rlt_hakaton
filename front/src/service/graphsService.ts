import * as graphsApi from "../api/graphs";
import type {
    ActivityPointDto,
    OkpdItemDto,
} from "../api/types";

import { plural } from "./format";

/** Сколько категорий ОКПД2 показываем в карточке. */
export const OKPD_TOP = 6;

/** Ширина графика активности в месяцах. */
export const ACTIVITY_MONTHS = 24;

/** Подписи месяцев на оси — коротко, как в макете. */
const MONTH_LABELS = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
];

/** Полные названия месяцев для подсказки над столбцом. */
const MONTH_NAMES = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
];

/** Один месяц графика активности в готовых для разметки значениях. */
export interface ActivityMonth {
    /** Ключ месяца YYYY-MM для react. */
    key: string;
    /** Подпись под столбцом; пустая у месяцев без метки, чтобы не слипались. */
    label: string;
    /** Подсказка над столбцом. */
    title: string;
    engages: number;
    wins: number;
    /** Высота полосы участий в процентах от самой высокой. */
    engagesHeight: string;
    /** Высота полосы побед в тех же процентах. */
    winsHeight: string;
}

/** Данные карточки «Активность». */
export interface ActivityCard {
    months: ActivityMonth[];
    engages: number;
    wins: number;
    /** Есть ли вообще участие в закупках. */
    hasData: boolean;
}

/** Строка карточки «Топ категорий ОКПД2». */
export interface OkpdRow {
    key: string;
    code: string;
    name: string;
    engages: number;
    wins: number;
    /** Доля во всех участиях, например «4,51». */
    percent: string;
    /** Ширина полосы в процентах от самой крупной категории. */
    width: string;
    title: string;
}

/** Данные карточки «Топ категорий ОКПД2». */
export interface OkpdCard {
    items: OkpdRow[];
    hasData: boolean;
}

const activityCache = new Map<string, ActivityCard>();
const okpdCache = new Map<string, OkpdCard>();

/** Русская десятичная дробь: 4.51 → «4,51». */
function formatPercent(value: number): string {
    return value.toFixed(2).replace(".", ",");
}

/** Высота полосы в процентах; нули не рисуем вовсе. */
function toHeight(value: number, max: number): string {
    if (value <= 0 || max <= 0) {
        return "0%";
    }

    return `${ Math.round((value / max) * 1000) / 10 }%`;
}

/** Ключ месяца и его части: 2025-11 → { year: 2025, month: 10 }. */
function splitKey(key: string): { year: number; month: number } {
    const [ year, month ] = key.split("-").map(Number);

    return {
        year,
        month: month - 1,
    };
}

/** Ключ месяца, сдвинутый на offset месяцев назад от года и месяца. */
function shiftMonth(year: number, month: number, offset: number): string {
    const total = year * 12 + month - offset;
    const shiftedYear = Math.floor(total / 12);
    const shiftedMonth = total % 12;

    return `${ shiftedYear }-${ String(shiftedMonth + 1).padStart(2, "0") }`;
}

/**
 * Бэкенд при ошибке отдаёт HTTP 200 с `status: 400`, поэтому 200-ответ
 * ещё приходится проверять глазами.
 */
function unwrap<T extends { status: number; message?: string }>(response: T): T {
    if (response.status !== 200) {
        throw new Error(response.message ?? "Графики недоступны");
    }

    return response;
}

/** Месяцы, в которые не было участий, добиваем нулями, чтобы шкала была ровной. */
function fillMonths(points: ActivityPointDto[]): ActivityMonth[] {
    if (points.length === 0) {
        return [];
    }

    // Окно заканчиваем последним месяцем с данными, а не текущим: выгрузка
    // может отставать, и тогда график не уезжал бы в пустую половину.
    const last = splitKey(points[points.length - 1].month);
    const byKey = new Map(points.map((point) => [ point.month, point ]));

    const months: ActivityMonth[] = [];
    const max = Math.max(...points.map((point) => point.engages));

    for (let offset = ACTIVITY_MONTHS - 1; offset >= 0; offset -= 1) {
        const key = shiftMonth(last.year, last.month, offset);
        const {
            year, month,
        } = splitKey(key);
        const point = byKey.get(key);
        const engages = point?.engages ?? 0;
        const wins = point?.wins ?? 0;
        const name = `${ MONTH_NAMES[month] } ${ year }`;

        months.push({
            key,
            // Подпись ставим на каждый третий месяц — иначе они слипаются.
            label: offset % 3 === 0 ? `${ MONTH_LABELS[month] } ${ String(year).slice(2) }` : "",
            title: `${ name }: ${ engages } ${ plural(engages, "участие", "участия", "участий") }, ${ wins } ${ plural(wins, "победа", "победы", "побед") }`,
            engages,
            wins,
            engagesHeight: toHeight(engages, max),
            winsHeight: toHeight(wins, max),
        });
    }

    return months;
}

function toOkpdRow(item: OkpdItemDto, index: number, maxEngages: number): OkpdRow {
    const name = item.name ?? "Без названия";
    const code = item.code ?? "—";

    return {
        key: `${ code }-${ index }`,
        code,
        name,
        engages: item.engages,
        wins: item.wins,
        percent: formatPercent(item.percent),
        // Масштабируем от самой крупной категории: доли от всех участий у
        // поставщиков с большим числом категорий не набирают и 5% ширины.
        width: toHeight(item.engages, maxEngages),
        title: `${ code } · ${ name }: ${ item.engages } ${ plural(item.engages, "участие", "участия", "участий") }, ${ item.wins } ${ plural(item.wins, "победа", "победы", "побед") }`,
    };
}

/** Карточка «Активность за два года». Результат кешируется по ИНН. */
export async function fetchActivityCard(inn: string): Promise<ActivityCard> {
    const cached = activityCache.get(inn);

    if (cached !== undefined) {
        return cached;
    }

    const response = unwrap(await graphsApi.fetchActivity(inn));
    const card: ActivityCard = {
        months: fillMonths(response.points),
        engages: response.engages,
        wins: response.wins,
        hasData: response.engages > 0,
    };

    activityCache.set(inn, card);

    return card;
}

/** Карточка «Топ категорий ОКПД2». Результат кешируется по ИНН. */
export async function fetchOkpdCard(inn: string): Promise<OkpdCard> {
    const cached = okpdCache.get(inn);

    if (cached !== undefined) {
        return cached;
    }

    const response = unwrap(await graphsApi.fetchOkpd(inn, OKPD_TOP));
    const items = response.items.slice(0, OKPD_TOP);
    const maxEngages = Math.max(...items.map((item) => item.engages), 0);

    const card: OkpdCard = {
        items: items.map((item, index) => toOkpdRow(item, index, maxEngages)),
        hasData: items.length > 0,
    };

    okpdCache.set(inn, card);

    return card;
}