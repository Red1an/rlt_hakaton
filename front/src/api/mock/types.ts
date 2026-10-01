/** Тип ключа запроса — для маппинга URL на мок-обработчик. */
export type HttpMethod = "get" | "post";

/** Параметры запроса после разбора axios-конфига. */
export interface MockRequest {
    method: HttpMethod;
    /** Путь без query-строки, например "/api/match/search". */
    path: string;
    /** Тело запроса, разобранное из JSON. */
    body: unknown;
}

/** Обработчик мок-маршрута. */
export type MockHandler = (request: MockRequest) => unknown;

/**
 * Маршрут мока. `pattern` — регулярка, по которой ищется путь.
 * Возвращается тело ответа; чтобы отдать ошибку, бросьте MockError.
 */
export interface MockRoute {
    method: HttpMethod;
    pattern: RegExp;
    handler: MockHandler;
}

/** Ошибка, которую мок возвращает как ответ с неуспешным статусом. */
export class MockError extends Error {
    readonly status: number;

    constructor(status: number, message: string) {
        super(message);
        this.name = "MockError";
        this.status = status;
    }
}
