import { MockError } from "./types";
import type {
    MockHandler, MockRequest, MockRoute,
} from "./types";
import type {
    CategoryDto,
    DetectCategoryRequestDto,
    DetectCategoryResponseDto,
    SearchSuppliersRequestDto,
    SearchSuppliersResponseDto,
} from "../types";

/**
 * Справочник ОКПД2 — взят из макета «Подбор поставщиков (офлайн)».
 * Группы приведены к плоскому виду: клиенту удобнее искать по коду и названию.
 */
const CATEGORIES: CategoryDto[] = [
    {
        code: "17.12.14",
        name: "Бумага для печати",
    },
    {
        code: "17.23.13",
        name: "Тетради, журналы, блокноты",
    },
    {
        code: "28.23.25",
        name: "Картриджи и части офисных машин",
    },
    {
        code: "31.01.12",
        name: "Мебель офисная деревянная",
    },
    {
        code: "31.01.11",
        name: "Мебель офисная металлическая",
    },
    {
        code: "22.19.60",
        name: "Перчатки медицинские",
    },
    {
        code: "10.51.11",
        name: "Молоко питьевое для школ",
    },
    {
        code: "10.71.11",
        name: "Хлеб и хлебобулочные изделия",
    },
];

/** Поиск по коду и названию, без учёта регистра и лишних пробелов. */
function matchesCategory(category: CategoryDto, term: string): boolean {
    const needle = term.trim().toLowerCase();

    if (needle.length === 0) {
        return true;
    }

    return category.code.toLowerCase().includes(needle)
        || category.name.toLowerCase().includes(needle);
}

const CATEGORY_NAMES = new Map(CATEGORIES.map((item) => [ item.code, item.name ]));

/** Категория по умолчанию — бумага для печати, как в макете. */
const DEFAULT_CATEGORY = CATEGORIES[0];

/**
 * Правила подбора категории по ключевым словам описания.
 * Перенесены из метода okpdCode() исходного макета.
 */
const KEYWORD_RULES: Array<{ code: string; words: string[] }> = [
    {
        code: "28.23.25",
        words: [ "картридж" ],
    },
    {
        code: "31.01.12",
        words: [ "мебел", "стол", "стул" ],
    },
    {
        code: "22.19.60",
        words: [ "перчат" ],
    },
    {
        code: "10.51.11",
        words: [ "молок", "питан", "продукт" ],
    },
    {
        code: "10.71.11",
        words: [ "хлеб" ],
    },
];

/** Ниже этой длины описание не даёт оснований для подбора. */
const MIN_QUERY_LENGTH = 3;

/** Справочник категорий с фильтрацией по query-параметру `q`. */
const handleCategories: MockHandler = (request: MockRequest) => {
    const term = request.query.q ?? "";

    return CATEGORIES.filter((category) => matchesCategory(category, term));
};

const handleDetectCategory: MockHandler = (request: MockRequest): DetectCategoryResponseDto => {
    const { query = "" } = (request.body ?? {}) as DetectCategoryRequestDto;
    const normalized = String(query).trim().toLowerCase();

    if (normalized.length < MIN_QUERY_LENGTH) {
        throw new MockError(422, "Слишком короткое описание закупки");
    }

    const matched = KEYWORD_RULES.find((rule) =>
        rule.words.some((word) => normalized.includes(word)),
    );

    const code = matched?.code ?? DEFAULT_CATEGORY.code;

    return {
        code,
        name: CATEGORY_NAME_OF(code),
    };
};

const handleSearch: MockHandler = (request: MockRequest): SearchSuppliersResponseDto => {
    const {
        query = "", nmck = 0,
    } = (request.body ?? {}) as SearchSuppliersRequestDto;
    const trimmed = String(query).trim();
    const price = Number(nmck);

    if (!trimmed) {
        throw new MockError(422, "Укажите, что вы закупаете");
    }

    if (!Number.isFinite(price) || price <= 0) {
        throw new MockError(422, "Укажите НМЦК");
    }

    return {
        requestId: `req-${ Date.now() }`,
        total: 47,
    };
};

function CATEGORY_NAME_OF(code: string): string {
    return CATEGORY_NAMES.get(code) ?? DEFAULT_CATEGORY.name;
}

export const mockRoutes: MockRoute[] = [
    {
        method: "get",
        pattern: /^\/match\/categories$/,
        handler: handleCategories,
    },
    {
        method: "post",
        pattern: /^\/match\/detect-category$/,
        handler: handleDetectCategory,
    },
    {
        method: "post",
        pattern: /^\/match\/search$/,
        handler: handleSearch,
    },
];
