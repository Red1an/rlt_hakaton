import { mockAdapter } from "./adapter";

/** Мок-слой включён по умолчанию; отключается через VITE_USE_MOCK=false. */
export const isMockEnabled = import.meta.env.VITE_USE_MOCK !== "false";

export { MockError } from "./types";
export type {
    HttpMethod, MockHandler, MockRequest, MockRoute,
} from "./types";
export { mockRoutes } from "./handlers";
export { mockAdapter };
