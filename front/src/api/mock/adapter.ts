import {
    AxiosError, AxiosHeaders,
} from "axios";
import type {
    AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig,
} from "axios";

import { MockError } from "./types";
import type {
    HttpMethod, MockRequest,
} from "./types";
import { mockRoutes } from "./handlers";

/** Задержка мок-ответа, чтобы UI успевал отрисовать состояние загрузки. */
const MOCK_DELAY_MS = 400;

function delay(ms: number) {
    return new Promise<void>((resolve) => {
        setTimeout(resolve, ms);
    });
}

function buildResponse(request: MockRequest, config: InternalAxiosRequestConfig): AxiosResponse {
    const route = mockRoutes.find((item) =>
        item.method === request.method && item.pattern.test(request.path),
    );

    if (!route) {
        throw new MockError(404, `Мок не найден: ${ request.method.toUpperCase() } ${ request.path }`);
    }

    return {
        data: route.handler(request),
        status: 200,
        statusText: "OK",
        headers: new AxiosHeaders(),
        config,
    };
}

function buildErrorResponse(
    error: unknown,
    config: InternalAxiosRequestConfig,
): AxiosResponse {
    const status = error instanceof MockError ? error.status : 500;
    const message = error instanceof Error ? error.message : "Неизвестная ошибка мока";

    return {
        data: { message },
        status,
        statusText: message,
        headers: new AxiosHeaders(),
        config,
    };
}

/**
 * Кастомный адаптер не проходит через settle() из axios, поэтому проверку
 * validateStatus выполняем сами: иначе ответы 4xx/5xx разрешались бы успешно.
 */
function settle(
    response: AxiosResponse,
    config: InternalAxiosRequestConfig,
): AxiosResponse {
    const validate = config.validateStatus ?? ((status: number) => status >= 200 && status < 300);

    if (validate(response.status)) {
        return response;
    }

    throw new AxiosError(
        `Request failed with status code ${ response.status }`,
        AxiosError.ERR_BAD_REQUEST,
        config,
        null,
        response,
    );
}

/**
 * Адаптер axios, отвечающий локально: подменяет сетевой слой целиком,
 * поэтому response-интерцепторы и transformResponse продолжают работать.
 */
export const mockAdapter: AxiosAdapter = async(config) => {
    await delay(MOCK_DELAY_MS);

    let body: unknown = config.data;

    if (typeof config.data === "string" && config.data.length > 0) {
        try {
            body = JSON.parse(config.data);
        } catch {
            body = config.data;
        }
    }

    let response: AxiosResponse;

    try {
        response = buildResponse({
            method: (config.method ?? "get") as HttpMethod,
            path: config.url ?? "",
            body,
        }, config);
    } catch (error) {
        response = buildErrorResponse(error, config);
    }

    return settle(response, config);
};
