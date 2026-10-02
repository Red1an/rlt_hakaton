import {
    API_BASE_URL, apiClient,
} from "./client";
import type {
    BatchDto,
    BatchJobResponseDto,
    BatchLotsResponseDto,
    SupplierVariantDto,
    VariantsResponseDto,
} from "./types";

const UPLOAD_TIMEOUT_MS = 120_000;

export async function fetchBatches(): Promise<BatchDto[]> {
    const { data } = await apiClient.get<BatchDto[]>("/match/batches");

    return data;
}

export async function uploadBatch(files: File[], name: string): Promise<BatchJobResponseDto> {
    const form = new FormData();

    files.forEach((file) => form.append("files", file));
    form.append("name", name);

    const { data } = await apiClient.post<BatchJobResponseDto>("/match/batches", form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: UPLOAD_TIMEOUT_MS,
    });

    return data;
}

export async function recomputeBatch(name: string): Promise<BatchJobResponseDto> {
    const { data } = await apiClient.post<BatchJobResponseDto>("/match/batches/recompute", null, {
        params: { name },
    });

    return data;
}

export async function fetchBatchStatus(name: string): Promise<BatchJobResponseDto> {
    const { data } = await apiClient.get<BatchJobResponseDto>("/match/batches/status", {
        params: { name },
    });

    return data;
}

export async function fetchBatchLots(name: string): Promise<BatchLotsResponseDto> {
    const { data } = await apiClient.get<BatchLotsResponseDto>("/match/batches/lots", {
        params: { name },
    });

    return data;
}

export async function deleteBatch(name: string): Promise<void> {
    await apiClient.delete("/match/batches", { params: { name } });
}

export function batchExportUrl(name: string, top: number): string {
    const query = new URLSearchParams({
        name,
        top: String(top),
    });

    return `${ API_BASE_URL }/match/batches/export?${ query.toString() }`;
}

export async function fetchLotVariants(lotId: number): Promise<SupplierVariantDto[]> {
    const { data } = await apiClient.get<VariantsResponseDto>(`/match/lots/${ lotId }/variants`);

    return data.items;
}
