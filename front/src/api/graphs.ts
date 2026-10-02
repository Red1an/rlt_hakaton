import { apiClient } from "./client";

import type {
    ActivityResponseDto,
    OkpdResponseDto,
} from "./types";

/**
 * Графики лежат не в `/match`, а в корне приложения, поэтому в dev и в проде
 * это `/api/graphs/...`: префикс `/api` срезает nginx (см. `nginx/nginx.conf`)
 * и dev-прокси vite (`vite.config.ts`).
 */

/** Ежемесячная активность поставщика за последние два года. */
export async function fetchActivity(inn: string): Promise<ActivityResponseDto> {
    const { data } = await apiClient.get<ActivityResponseDto>("/graphs/activity", {
        params: { inn },
    });

    return data;
}

/** Топ категорий ОКПД2, в которых поставщик участвовал. */
export async function fetchOkpd(inn: string, top?: number): Promise<OkpdResponseDto> {
    const { data } = await apiClient.get<OkpdResponseDto>("/graphs/okpd", {
        params: {
            inn,
            ...( top === undefined ? {} : { top } ),
        },
    });

    return data;
}