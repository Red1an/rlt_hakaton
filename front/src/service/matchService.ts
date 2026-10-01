import * as matchApi from "../api/match";

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

/** Кеш полного справочника, чтобы не дёргать api при каждом открытии списка. */
let categoriesCache: OkpdCategory[] | null = null;

const PLATFORM_LABELS: Record<MatchPlatform, string> = {
    ais: "АИС ГЗ",
    em: "Электронный магазин",
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