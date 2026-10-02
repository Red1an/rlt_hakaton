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
    /** При scoreKind = suitability — подходимость 0–100 по общей шкале, иначе относительная оценка в выдаче. */
    score: number;
    scoreKind?: ScoreKind;
    /** Во сколько раз чаще среднего кандидата такие компании подают заявки. */
    lift?: number | null;
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
    roleReason?: string | null;
    verified?: SupplierVerificationDto | null;
}

export interface SupplierVerificationDto {
    by: "dadata" | "egrul";
    at: string | null;
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

export type ScoreKind = "suitability" | "probability" | "relative" | "new";

export interface BatchLotTopDto {
    inn: string;
    name: string;
    score: number;
    scoreKind?: ScoreKind;
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
    lots?: number;
    name: string;
    job: BatchJobDto;
}

/** Месяц активности поставщика в формате YYYY-MM. */
export interface ActivityPointDto {
    month: string;
    wins: number;
    engages: number;
}

/**
 * График активности. Бэкенд при ошибке отдаёт HTTP 200 с `status: 400`,
 * поэтому поле приходится проверять на клиенте.
 */
export interface ActivityResponseDto {
    status: number;
    message?: string;
    inn: string;
    points: ActivityPointDto[];
    wins: number;
    engages: number;
}

/** Доля участий поставщика в одной категории ОКПД2. */
export interface OkpdItemDto {
    /** Код ОКПД2; может отсутствовать, если категория не распознана. */
    code: string | null;
    /** Название категории; `null`, если кода нет в справочнике. */
    name: string | null;
    wins: number;
    engages: number;
    /** Доля категории во всех участиях поставщика, %. */
    percent: number;
    /** Доля побед категории во всех победах поставщика, %. */
    win_percent: number;
}

export interface OkpdResponseDto {
    status: number;
    message?: string;
    inn: string;
    items: OkpdItemDto[];
    wins: number;
    engages: number;
}

export interface EnrichmentResultDto {
    inn: string;
    name: string | null;
    role: "manufacturer" | "distributor" | "supplier" | null;
    roleReason: string | null;
    okved: string | null;
    regionCode: string | null;
    regDate: string | null;
    address: string | null;
}

export interface EnrichmentJobDto {
    status: "idle" | "running" | "done" | "stopped" | "error";
    okpd?: string | null;
    limit?: number;
    requests?: number;
    found?: number;
    categories?: number;
    categoriesDone?: number;
    current?: string;
    message?: string;
    results?: EnrichmentResultDto[];
}

export interface EnrichmentStateDto {
    job: EnrichmentJobDto;
    maxLimit: number;
    perCategory: number;
    suppliers: { total: number; found: number; web: number };
}
