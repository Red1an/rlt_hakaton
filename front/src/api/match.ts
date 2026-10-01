import { apiClient } from "./client";
import type {
    CategoryDto,
    DetectCategoryRequestDto,
    DetectCategoryResponseDto,
    FetchCategoriesParams,
    SearchSuppliersRequestDto,
    SearchSuppliersResponseDto,
} from "./types";

/**
 * Справочник категорий ОКПД2 для выпадающего списка.
 * Пустой `params.q` возвращает полный справочник, иначе — отфильтрованный.
 */
export async function fetchCategories(params: FetchCategoriesParams = {}): Promise<CategoryDto[]> {
    const term = params.q?.trim() ?? "";
    const { data } = await apiClient.get<CategoryDto[]>("/match/categories", {
        params: term.length > 0 ? { q: term } : undefined,
    });

    return data;
}

/** Автоподбор категории ОКПД2 по тексту описания. */
export async function detectCategory(
    query: DetectCategoryRequestDto,
): Promise<DetectCategoryResponseDto> {
    const { data } = await apiClient.post<DetectCategoryResponseDto>(
        "/match/detect-category",
        query,
    );

    return data;
}

/** Отправка формы подбора поставщиков. */
export async function searchSuppliers(
    payload: SearchSuppliersRequestDto,
): Promise<SearchSuppliersResponseDto> {
    const { data } = await apiClient.post<SearchSuppliersResponseDto>(
        "/match/search",
        payload,
    );

    return data;
}