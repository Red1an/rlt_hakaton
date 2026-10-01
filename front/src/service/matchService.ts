import * as matchApi from "../api/match";
import type { SupplierRole } from "../api/types";

export type { SupplierRole } from "../api/types";

/** Категория ОКПД2 в виде, удобном для отображения. */
export interface OkpdCategory {
    code: string;
    name: string;
    label: string;
}

export type MatchPlatform = "ais" | "em";

/** Значения формы «Что вы закупаете?». */
export interface MatchFormValues {
    query: string;
    category: OkpdCategory | null;
    nmck: string;
    platform: MatchPlatform;
    mspOnly: boolean;
}

/** Результат отправки формы, нормализованный для UI. */
export interface MatchSearchResult {
    requestId: string;
    total: number;
    message: string;
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
    part: number;
    wins: number;
    last: string;
    why: Array<{ icon: string; text: string }>;
}

/** Кеш полного справочника, чтобы не дёргать api при каждом открытии списка. */
let categoriesCache: OkpdCategory[] | null = null;

const PLATFORM_LABELS: Record<MatchPlatform, string> = {
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

/** Автоподбор категории по описанию. Пустая категория — подбор не удался. */
export async function detectCategory(query: string): Promise<OkpdCategory | null> {
    const detected = await matchApi.detectCategory({ query });

    if (detected === null) {
        return null;
    }

    return toCategory(detected);
}

/** Отправка формы. Валидацию полей берёт на себя бэкенд, его сообщения пробрасываются. */
export async function submitSearch(values: MatchFormValues): Promise<MatchSearchResult> {
    const result = await matchApi.searchSuppliers({
        query: values.query.trim(),
        nmck: Number(values.nmck.replace(/\s/g, "")),
        platform: values.platform,
        mspOnly: values.mspOnly,
    });

    return {
        requestId: result.requestId,
        total: result.total,
        message: `Подбор завершён: найдено ${ result.total } поставщиков по площадке «${ PLATFORM_LABELS[values.platform] }»`,
    };
}

/** Список поставщиков-вариантов, нормализованный для UI. */
export async function fetchVariants(): Promise<SupplierVariant[]> {
    const items = await matchApi.fetchVariants();

    return items.map((item) => ({
        id: item.id,
        name: item.name,
        inn: item.inn,
        flags: item.flags,
        isNew: item.novelty === "new",
        role: item.role,
        score: item.score,
        part: item.part,
        wins: item.wins,
        last: item.last,
        why: item.why.map(([ icon, text ]) => ({
            icon,
            text,
        })),
    }));
}