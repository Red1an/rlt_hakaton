import axios from "axios";
import type { AxiosError } from "axios";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

export const apiClient = axios.create({
    baseURL: API_BASE_URL,
    timeout: 15000,
    headers: {
        "Content-Type": "application/json",
    },
});

export class ApiError extends Error {
    readonly status: number;

    constructor(message: string, status: number) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

apiClient.interceptors.response.use(
    (response) => response,
    (error: AxiosError<{ message?: string }>) => {
        if (error.response) {
            return Promise.reject(new ApiError(
                error.response.data?.message ?? "Ошибка запроса",
                error.response.status,
            ));
        }

        if (error.code === "ECONNABORTED") {
            return Promise.reject(new ApiError("Превышено время ожидания", 408));
        }

        return Promise.reject(new ApiError("Сервис недоступен", 0));
    },
);
