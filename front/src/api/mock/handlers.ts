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
    SupplierVariantDto,
    VariantsResponseDto,
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

/**
 * Варианты поставщиков. Перенесены из макета «Подбор поставщиков (офлайн)»;
 * поля региона, тегов и сегмента в новом экране не используются.
 */
const VARIANTS: SupplierVariantDto[] = [
    {
        id: "szb",
        name: "ООО «СевЗапБумага»",
        inn: "7801234567",
        flags: [ "МСП" ],
        novelty: "existing",
        role: "dist",
        score: 94,
        part: 22,
        wins: 11,
        last: "1 нед. назад",
        why: [
            [ "✓", "Уже работал с этим заказчиком — 3 контракта" ],
            [ "★", "Победил в 11 из 22 похожих лотов" ],
            [ "₽", "Снижает цену в среднем на 6,4% от НМЦК" ],
        ],
    },
    {
        id: "okspb",
        name: "ООО «Офис-Комплект СПб»",
        inn: "7814567890",
        flags: [ "МСП" ],
        novelty: "existing",
        role: "sup",
        score: 88,
        part: 18,
        wins: 7,
        last: "2 нед. назад",
        why: [
            [ "★", "Победил в 7 из 18 похожих лотов" ],
            [ "⌖", "Поставлял в 9 школ вашего района" ],
            [ "↻", "Активен: 4 заявки за последний месяц" ],
        ],
    },
    {
        id: "nk",
        name: "АО «Невский картридж»",
        inn: "7806543210",
        flags: [],
        novelty: "existing",
        role: "man",
        score: 81,
        part: 14,
        wins: 1,
        last: "3 нед. назад",
        why: [
            [ "↻", "Подал 14 заявок, проигрывал по цене в среднем на 1,9%" ],
            [ "⚙", "Производитель — может дать цену ниже дистрибьюторов" ],
            [ "✓", "Заявки ни разу не отклоняли" ],
        ],
    },
    {
        id: "pld",
        name: "ООО «ПринтЛайн Дистрибуция»",
        inn: "7842135790",
        flags: [ "МСП", "Филиал" ],
        novelty: "existing",
        role: "dist",
        score: 76,
        part: 11,
        wins: 2,
        last: "1 мес. назад",
        why: [
            [ "↻", "11 участий, 2 победы — готов конкурировать" ],
            [ "⌖", "Склад во Всеволожске, 25 км до заказчика" ],
            [ "₽", "Дважды предлагал цену на 3% ниже победителя" ],
        ],
    },
    {
        id: "smirnov",
        name: "ИП Смирнов А.В.",
        inn: "781234567812",
        flags: [ "МСП", "ИП" ],
        novelty: "existing",
        role: "sup",
        score: 69,
        part: 9,
        wins: 4,
        last: "8 мес. назад",
        why: [
            [ "✓", "Работал с этим заказчиком в 2025 году" ],
            [ "★", "Победил в 4 из 9 лотов" ],
            [ "💤", "Давно не участвовал — стоит напомнить о закупке" ],
        ],
    },
    {
        id: "bk",
        name: "ООО «Балт-Канц»",
        inn: "7810987654",
        flags: [ "МСП" ],
        novelty: "existing",
        role: "sup",
        score: 64,
        part: 6,
        wins: 1,
        last: "2 нед. назад",
        why: [
            [ "🧭", "38 лотов в соседних категориях: канцтовары" ],
            [ "⌖", "Работает со школами района" ],
            [ "✓", "Бумага А4 есть в каталоге на сайте" ],
        ],
    },
    {
        id: "vbd",
        name: "ООО «Вологодский бумажный двор»",
        inn: "3525412398",
        flags: [ "МСП" ],
        novelty: "existing",
        role: "dist",
        score: 58,
        part: 7,
        wins: 0,
        last: "5 нед. назад",
        why: [
            [ "↻", "7 заявок без побед — проигрывал 1–2%" ],
            [ "₽", "Цена с доставкой сопоставима с местными" ],
            [ "⌖", "Возит в СПб раз в неделю" ],
        ],
    },
    {
        id: "sevbum",
        name: "ООО «Северная Бумага»",
        inn: "7809876543",
        flags: [ "МСП" ],
        novelty: "new",
        role: "man",
        score: 61,
        part: 0,
        wins: 0,
        last: "—",
        why: [
            [ "✦", "Нет в истории закупок заказчика" ],
            [ "⚙", "Производитель бумаги — возможна цена ниже рынка" ],
            [ "⌖", "Готов работать по СПб и ЛО" ],
        ],
    },
    {
        id: "kuznec",
        name: "ИП Кузнецова М.С.",
        inn: "781876543210",
        flags: [ "МСП", "ИП" ],
        novelty: "new",
        role: "sup",
        score: 57,
        part: 0,
        wins: 0,
        last: "—",
        why: [
            [ "✦", "Нет в истории закупок заказчика" ],
            [ "⌖", "Малые партии с доставкой по СПб" ],
            [ "↻", "Подаёт заявки в соседних категориях" ],
        ],
    },
];

const handleVariants: MockHandler = (): VariantsResponseDto => ({ items: VARIANTS });

export const mockRoutes: MockRoute[] = [
    {
        method: "get",
        pattern: /^\/match\/categories$/,
        handler: handleCategories,
    },
    {
        method: "get",
        pattern: /^\/match\/variants$/,
        handler: handleVariants,
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
