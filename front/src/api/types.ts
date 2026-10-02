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

/** Тело запроса поиска поставщиков. */
export interface SearchSuppliersRequestDto {
    category: string;
    nmck: number;
    platform: "ais" | "em";
    mspOnly: boolean;
    /** ИНН заказчика: пустое поле равносильно его отсутствию. */
    customerInn?: string;
}

/** Ответ поиска поставщиков. */
export interface SearchSuppliersResponseDto {
    requestId: string;
    total: number;
    newFound: number;
}

/** Параметры выборки списка вариантов. */
export interface FetchVariantsParams {
    /** Идентификатор выдачи: без него сервер отдаёт последний поиск. */
    requestId?: string;
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

export type BatchJobStatus = "idle" | "running" | "done" | "error";

export interface BatchJobDto {
    status: BatchJobStatus;
    done?: number;
    total?: number;
    message?: string;
}

export interface BatchDto {
    name: string;
    lots: number;
    computed: number;
    dateFrom: string | null;
    dateTo: string | null;
    computedAt: string | null;
    job: BatchJobDto;
}

export interface BatchLotTopDto {
    inn: string;
    name: string;
    score: number;
    novelty: VariantNovelty;
}

export interface BatchLotDto {
    lotId: number;
    publishDate: string;
    subject: string;
    customerInn: string;
    nmck: number;
    platform: "ais" | "em";
    mspOnly: boolean;
    categories: string[];
    computed: boolean;
    total: number;
    top: BatchLotTopDto[];
}

export interface BatchLotsResponseDto {
    name: string;
    job: BatchJobDto;
    lots: BatchLotDto[];
}

export interface BatchJobResponseDto {
    name: string;
    job: BatchJobDto;
}
