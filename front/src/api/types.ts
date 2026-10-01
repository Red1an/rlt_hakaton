/**
 * Контракты сетевого слоя. Формат соответствует будущему FastAPI-эндпоинту,
 * доменные типы для UI живут в `src/service/types.ts`.
 */

/** Категория ОКПД2 в том виде, в котором её отдаёт бэкенд. */
export interface CategoryDto {
    code: string;
    name: string;
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
    customerInn: string | null;
}

/** Ответ поиска поставщиков. */
export interface SearchSuppliersResponseDto {
    requestId: string;
    total: number;
}
