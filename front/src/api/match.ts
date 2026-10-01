import { apiClient } from "./client";
import type {
    CategoryDto,
    DetectCategoryRequestDto,
    DetectCategoryResponseDto,
    SearchSuppliersRequestDto,
    SearchSuppliersResponseDto,
} from "./types";

/** Справочник категорий ОКПД2 для выпадающего списка. */
export async function fetchCategories(): Promise<CategoryDto[]> {
    const { data } = await apiClient.get<CategoryDto[]>("/match/categories");

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