/**
 * Контракты сетевого слоя. Формат соответствует будущему FastAPI-эндпоинту,
 * доменные типы для UI живут в `src/service/types.ts`.
 */

/** Категория ОКПД2 в том виде, в котором её отдаёт бэкенд. */
export interface CategoryDto {
    code: string;
    name: string;
}

/** Параметры выборки справочника категорий. */
export interface FetchCategoriesParams {
    /** Поисковая строка по коду или названию. */
    q?: string;
}

/** Тело запроса подбора категории по описанию. */
export interface DetectCategoryRequestDto {
    query: string;
}

/** Ответ подбора категории. */
export type DetectCategoryResponseDto = CategoryDto | null;

/** Тело запроса поиска поставщиков. */
export interface SearchSuppliersRequestDto {
    query: string;
    nmck: number;
    platform: "ais" | "em";
    mspOnly: boolean;
}

/** Ответ поиска поставщиков. */
export interface SearchSuppliersResponseDto {
    requestId: string;
    total: number;
}

/** Роль компании на рынке категории. */
export type SupplierRole = "man" | "dist" | "sup";

/** Признак наличия истории закупок у поставщика. */
export type VariantNovelty = "new" | "existing";

/** Реквизиты поставщика для карточки. */
export interface SupplierRequisitesDto {
    kpp: string;
    ogrn: string;
    okved: string;
    region: string;
    phone: string;
    email: string;
}

/** Строка истории участия поставщика (без даты). */
export interface VariantHistoryRowDto {
    /** Предмет лота. */
    subject: string;
    /** НМЦК в рублях. */
    nmck: number;
    customer: string;
    /** Победа или просто участие. */
    won: boolean;
}

/** Поставщик в списке вариантов. */
export interface SupplierVariantDto {
    id: string;
    name: string;
    inn: string;
    /** Плашки компании: МСП, ИП, Филиал. */
    flags: string[];
    novelty: VariantNovelty;
    role: SupplierRole;
    /** Релевантность 0–100. */
    score: number;
    /** Участий в похожих лотах. */
    part: number;
    /** Побед в похожих лотах. */
    wins: number;
    /** Человекочитаемая свежесть последнего участия. */
    last: string;
    /** Аргументы «почему рекомендуем»: [иконка, текст]. */
    why: Array<[string, string]>;
    /** Адрес сайта без протокола. */
    site: string;
    requisites: SupplierRequisitesDto;
    /** История участия без даты; у новых поставщиков пуста. */
    history: VariantHistoryRowDto[];
}

/** Ответ справочника вариантов. */
export interface VariantsResponseDto {
    items: SupplierVariantDto[];
}
