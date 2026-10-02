import { apiClient } from "./client";
import type { EnrichmentStateDto } from "./types";

export async function fetchEnrichment(): Promise<EnrichmentStateDto> {
    const { data } = await apiClient.get<EnrichmentStateDto>("/match/enrichment");

    return data;
}

export async function startEnrichment(okpd: string | null, limit: number): Promise<EnrichmentStateDto> {
    const { data } = await apiClient.post<EnrichmentStateDto>("/match/enrichment", {
        okpd: okpd ?? "",
        limit,
    });

    return data;
}
