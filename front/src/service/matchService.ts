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
    customerInn: string;
}

/** Результат отправки формы, нормализованный для UI. */
export interface MatchSearchResult {
    requestId: string;
    total: number;
    message: string;
}

/** Ошибка валидации формы — показывается рядом с полем. */
export class ValidationError extends Error {
    readonly field: keyof MatchFormValues;

    constructor(field: keyof MatchFormValues, message: string) {
        super(message);
        this.name = "ValidationError";
        this.field = field;
    }
}

const INN_LENGTH = 10;

/** Кеш справочника, чтобы не дёргать api при каждом открытии списка. */
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

/** Справочник категорий для выпадающего списка «Сменить». */
export async function fetchCategories(): Promise<OkpdCategory[]> {
    if (categoriesCache !== null) {
        return categoriesCache;
    }

    const categories = (await matchApi.fetchCategories()).map(toCategory);

    categoriesCache = categories;

    return categories;
}

/** Автоподбор категории по описанию. Пустая категория — подбор не удался. */
export async function detectCategory(query: string): Promise<OkpdCategory | null> {
    const detected = await matchApi.detectCategory({ query });

    if (detected === null) {
        return null;
    }

    return toCategory(detected);
}

/**
 * Отправка формы. Валидация ИНН — пусто либо строго 10 цифр;
 * остальные поля проверяет бэкенд, его сообщение пробрасывается как есть.
 */
export async function submitSearch(values: MatchFormValues): Promise<MatchSearchResult> {
    const inn = values.customerInn.trim();

    if (inn.length > 0 && !new RegExp(`^\\d{${ INN_LENGTH }}$`).test(inn)) {
        throw new ValidationError("customerInn", "ИНН должен состоять из 10 цифр");
    }

    const result = await matchApi.searchSuppliers({
        query: values.query.trim(),
        nmck: Number(values.nmck.replace(/\s/g, "")),
        platform: values.platform,
        mspOnly: values.mspOnly,
        customerInn: inn.length > 0 ? inn : null,
    });

    return {
        requestId: result.requestId,
        total: result.total,
        message: `Подбор завершён: найдено ${ result.total } поставщиков по площадке «${ PLATFORM_LABELS[values.platform] }»`,
    };
}