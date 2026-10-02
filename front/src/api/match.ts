import { apiClient } from "./client";

const SEARCH_TIMEOUT_MS = 60_000;
import type {
    CategoryDto,
    FetchCategoriesParams,
    FetchVariantsParams,
    SearchSuppliersRequestDto,
    SearchSuppliersResponseDto,
    SupplierVariantDto,
    VariantsResponseDto,
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

/** Отправка формы подбора поставщиков. */
export async function searchSuppliers(
    payload: SearchSuppliersRequestDto,
): Promise<SearchSuppliersResponseDto> {
    const { data } = await apiClient.post<SearchSuppliersResponseDto>(
        "/match/search",
        payload,
        { timeout: SEARCH_TIMEOUT_MS },
    );

    return data;
}

/** Список поставщиков-вариантов для экрана подбора. */
export async function fetchVariants(params: FetchVariantsParams = {}): Promise<SupplierVariantDto[]> {
    const { data } = await apiClient.get<VariantsResponseDto>("/match/variants", {
        params: params.requestId === undefined ? undefined : { requestId: params.requestId },
    });

    return data.items;
}