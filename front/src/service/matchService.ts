import * as batchApi from "../api/batches";
import * as matchApi from "../api/match";
import type {
    ScoreKind, SupplierRole, SupplierVariantDto, SupplierVerificationDto,
} from "../api/types";

export type { SupplierRole } from "../api/types";

/** Категория ОКПД2 в виде, удобном для отображения. */
export interface OkpdCategory {
    code: string;
    name: string;
    label: string;
}

export type MatchPlatform = "all" | "ais" | "em";

/** Значения формы «Что вы закупаете?». */
export interface MatchFormValues {
    category: OkpdCategory | null;
    nmck: string;
    platform: MatchPlatform;
    mspOnly: boolean;
    /** ИНН заказчика: пустая строка — работаем со всеми заказчиками. */
    customerInn: string;
}

/**
 * Состояние формы, которым владеет страница: оно переживает переключение
 * экранов и хранится в localStorage.
 */
export interface MatchFormState {
    values: MatchFormValues;
    /** Форма свёрнута в строку-сводку. */
    isCollapsed: boolean;
}

/** Лот закупки — это подбор с зафиксированными параметрами. */
export interface ProcurementLot {
    id: string;
    /** Номер для шапки таблицы: Л-2026-0418. */
    num: string;
    /** Название категории, обрезанное для шапки. */
    title: string;
    /** НМЦК в виде, в котором его вводят в форме. */
    nmck: string;
    /** Снимок параметров: им форма восстанавливается кнопкой возврата. */
    values: MatchFormValues;
    /** Идентификатор выдачи бэкенда: по нему грузится список вариантов. */
    requestId?: string;
    batchName?: string;
    batchLotId?: number;
}

/** Запись шорт-листа: поставщик, отобранный в конкретном лоте. */
export interface ShortListEntry {
    lotId: string;
    supplierId: string;
}

export const INITIAL_MATCH_VALUES: MatchFormValues = {
    category: null,
    nmck: "",
    platform: "all",
    mspOnly: false,
    customerInn: "",
};

export const INITIAL_MATCH_STATE: MatchFormState = {
    values: INITIAL_MATCH_VALUES,
    isCollapsed: false,
};

/**
 * Дополняет сохранённые значения формы текущими дефолтами. Нужна после
 * появления новых полей: в хранилище лежит объект без них.
 */
export function isSelectableCategory(code: string): boolean {
    return /^\d{2}\.\d{2}/.test(code);
}

export function normalizeMatchValues(values?: Partial<MatchFormValues> | null): MatchFormValues {
    const merged = {
        ...INITIAL_MATCH_VALUES,
        ...values,
    };

    return {
        ...merged,
        category: merged.category && isSelectableCategory(merged.category.code) ? merged.category : null,
    };
}

/** Результат отправки формы, нормализованный для UI. */
export interface MatchSearchResult {
    requestId: string;
    total: number;
    message: string;
}

/** Поле реквизитов поставщика для карточки. */
export interface SupplierRequisite {
    label: string;
    value: string;
    /** Значение выводится моно-шрифтом (числа, коды). */
    mono: boolean;
}

/** Строка истории участия в карточке поставщика (без даты). */
export interface SupplierHistoryRow {
    subject: string;
    nmck: string;
    customer: string;
    won: boolean;
}

/** Поставщик-вариант в удобном для UI виде. */
export interface SupplierVariant {
    id: string;
    name: string;
    inn: string;
    flags: string[];
    /** Поставщика нет в истории закупок заказчика. */
    isNew: boolean;
    role: SupplierRole;
    score: number;
    scoreKind: ScoreKind;
    lift: number | null;
    participation: number | null;
    part: number;
    wins: number;
    last: string;
    why: Array<{ icon: string; text: string }>;
    /** Сайт без протокола. */
    site: string;
    phone: string;
    email: string;
    requisites: SupplierRequisite[];
    history: SupplierHistoryRow[];
    roleReason: string;
    verified: SupplierVerificationDto | null;
}

/** Кеш полного справочника, чтобы не дёргать api при каждом открытии списка. */
let categoriesCache: OkpdCategory[] | null = null;

const PLATFORM_LABELS: Record<MatchPlatform, string> = {
    all: "все площадки",
    ais: "АИС ГЗ",
    em: "Электронный магазин",
};

/** Подписи ролей компаний для фильтра и карточек. */
export const ROLE_LABELS: Record<SupplierRole, string> = {
    man: "Производитель",
    dist: "Дистрибьютор",
    sup: "Поставщик",
};

function toCategory(dto: { code: string; name: string }): OkpdCategory {
    return {
        code: dto.code,
        name: dto.name,
        label: `${ dto.code } · ${ dto.name }`,
    };
}

/** Полный справочник категорий для первого открытия списка. */
export async function fetchCategories(): Promise<OkpdCategory[]> {
    if (categoriesCache !== null) {
        return categoriesCache;
    }

    const categories = (await matchApi.fetchCategories()).map(toCategory);

    categoriesCache = categories;

    return categories;
}

/**
 * Поиск категории по коду или названию. Пустая строка отдаёт полный справочник
 * из кеша без обращения к api.
 */
export async function searchCategories(term: string): Promise<OkpdCategory[]> {
    const trimmed = term.trim();

    if (trimmed.length === 0) {
        return fetchCategories();
    }

    return (await matchApi.fetchCategories({ q: trimmed })).map(toCategory);
}

/** Отправка формы. Валидацию полей берёт на себя бэкенд, его сообщения пробрасываются. */
export async function submitSearch(values: MatchFormValues): Promise<MatchSearchResult> {
    const customerInn = values.customerInn.trim();
    const result = await matchApi.searchSuppliers({
        category: values.category?.code ?? "",
        nmck: Number(values.nmck.replace(/\s/g, "")),
        platform: values.platform,
        mspOnly: values.mspOnly,
        ...( customerInn.length > 0 ? { customerInn } : {} ),
    });

    return {
        requestId: result.requestId,
        total: result.total,
        message: `Подбор завершён: найдено ${ result.total } поставщиков ${
            values.platform === "all" ? "по всем площадкам" : `по площадке «${ PLATFORM_LABELS[values.platform] }»`
        }`,
    };
}

/** Группировка денег: 486000 → 486 000. */
function formatMoney(value: number): string {
    return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function toVariant(item: SupplierVariantDto): SupplierVariant {
    return {
        id: item.id,
        name: item.name,
        inn: item.inn,
        flags: item.flags,
        isNew: item.novelty === "new",
        role: item.role,
        score: item.score,
        scoreKind: item.scoreKind ?? (item.novelty === "new" ? "new" : "relative"),
        lift: item.lift ?? null,
        participation: item.participation ?? null,
        part: item.part,
        wins: item.wins,
        last: item.last,
        why: item.why.map(([ icon, text ]) => ({
            icon,
            text,
        })),
        site: item.site,
        phone: item.requisites.phone,
        email: item.requisites.email,
        requisites: [
            {
                label: "ИНН",
                value: item.inn,
                mono: true,
            },
            {
                label: "КПП",
                value: item.requisites.kpp,
                mono: true,
            },
            {
                label: "ОГРН",
                value: item.requisites.ogrn,
                mono: true,
            },
            {
                label: "ОКВЭД",
                value: item.requisites.okved,
                mono: true,
            },
            {
                label: "Регион",
                value: item.requisites.region,
                mono: false,
            },
            {
                label: "Телефон",
                value: item.requisites.phone,
                mono: true,
            },
            {
                label: "Email",
                value: item.requisites.email,
                mono: true,
            },
        ],
        roleReason: item.roleReason ?? "",
        verified: item.verified ?? null,
        history: item.history.map((row) => ({
            subject: row.subject,
            nmck: formatMoney(row.nmck),
            customer: row.customer,
            won: row.won,
        })),
    };
}

/** Список поставщиков-вариантов, нормализованный для UI. */
export async function fetchVariants(requestId?: string): Promise<SupplierVariant[]> {
    const items = await matchApi.fetchVariants(
        requestId === undefined || requestId.length === 0 ? {} : { requestId },
    );

    return items.map(toVariant);
}

export async function fetchLotVariants(lotId: number): Promise<SupplierVariant[]> {
    return (await batchApi.fetchLotVariants(lotId)).map(toVariant);
}
