import { MockError } from "./types";
import type {
    MockHandler, MockRequest, MockRoute,
} from "./types";
import type {
    CategoryDto,
    SearchSuppliersRequestDto,
    SearchSuppliersResponseDto,
    SupplierRequisitesDto,
    SupplierVariantDto,
    VariantHistoryRowDto,
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

/** Справочник категорий с фильтрацией по query-параметру `q`. */
const handleCategories: MockHandler = (request: MockRequest) => {
    const term = request.query.q ?? "";

    return CATEGORIES.filter((category) => matchesCategory(category, term));
};

const handleSearch: MockHandler = (request: MockRequest): SearchSuppliersResponseDto => {
    const {
        category = "", nmck = 0,
    } = (request.body ?? {}) as SearchSuppliersRequestDto;
    const price = Number(nmck);

    if (!String(category).trim()) {
        throw new MockError(422, "Выберите категорию ОКПД2");
    }

    if (!Number.isFinite(price) || price <= 0) {
        throw new MockError(422, "Укажите НМЦК");
    }

    return {
        requestId: `req-${ Date.now() }`,
        total: 47,
        newFound: 0,
    };
};

/**
 * Варианты поставщиков. Перенесены из макета «Подбор поставщиков (офлайн)»;
 * поля региона, тегов и сегмента в новом экране не используются.
 */
type SupplierVariantBase = Omit<SupplierVariantDto, "site" | "requisites" | "history">;

const VARIANT_BASE: SupplierVariantBase[] = [
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

/** Сайт и реквизиты для карточки — по идентификатору поставщика. */
const VARIANT_DETAILS: Record<string, { site: string; requisites: SupplierRequisitesDto }> = {
    szb: {
        site: "sevzapbum.ru",
        requisites: {
            kpp: "780101001",
            ogrn: "1107847234567",
            okved: "46.49",
            region: "Санкт-Петербург",
            phone: "+7 812 309-60-60",
            email: "opt@sevzapbum.ru",
        },
    },
    okspb: {
        site: "office-komplekt.spb.ru",
        requisites: {
            kpp: "781401001",
            ogrn: "1137847567890",
            okved: "46.66",
            region: "Санкт-Петербург",
            phone: "+7 812 612-44-90",
            email: "sale@office-komplekt.spb.ru",
        },
    },
    nk: {
        site: "nevskiy-kartridge.ru",
        requisites: {
            kpp: "780601001",
            ogrn: "1097847011223",
            okved: "17.12",
            region: "Санкт-Петербург",
            phone: "+7 812 777-12-34",
            email: "sales@nevskiy-kartridge.ru",
        },
    },
    pld: {
        site: "printline-dist.ru",
        requisites: {
            kpp: "784201001",
            ogrn: "1157847233445",
            okved: "46.49",
            region: "Санкт-Петербург",
            phone: "+7 812 425-71-17",
            email: "info@printline-dist.ru",
        },
    },
    smirnov: {
        site: "smirnov-office.ru",
        requisites: {
            kpp: "—",
            ogrn: "317784700012345",
            okved: "46.49",
            region: "Санкт-Петербург",
            phone: "+7 921 555-18-42",
            email: "smirnov@smirnov-office.ru",
        },
    },
    bk: {
        site: "baltkanc.ru",
        requisites: {
            kpp: "781001001",
            ogrn: "1147847567890",
            okved: "46.49",
            region: "Санкт-Петербург",
            phone: "+7 812 309-60-61",
            email: "opt@baltkanc.ru",
        },
    },
    vbd: {
        site: "vologda-paper.ru",
        requisites: {
            kpp: "352501001",
            ogrn: "1113525001234",
            okved: "46.49",
            region: "Вологодская область",
            phone: "+7 817 272-30-30",
            email: "sale@vologda-paper.ru",
        },
    },
    sevbum: {
        site: "severnaya-bumaga.ru",
        requisites: {
            kpp: "780901001",
            ogrn: "1207800123456",
            okved: "17.12",
            region: "Санкт-Петербург",
            phone: "+7 812 244-88-10",
            email: "info@severnaya-bumaga.ru",
        },
    },
    kuznec: {
        site: "kuznecova-ms.ru",
        requisites: {
            kpp: "—",
            ogrn: "320780000012345",
            okved: "46.49",
            region: "Санкт-Петербург",
            phone: "+7 921 300-77-15",
            email: "kuznecova@kuznecova-ms.ru",
        },
    },
};

/** История участия одинакова для компаний из истории; у новых поставщиков пуста. */
const PARTICIPATION_HISTORY: VariantHistoryRowDto[] = [
    {
        subject: "Бумага для офисной техники А4, 400 пачек",
        nmck: 486000,
        customer: "ГБОУ «Школа № 718»",
        won: true,
    },
    {
        subject: "Бумага А4 и А3 для нужд поликлиники",
        nmck: 312500,
        customer: "СПб ГБУЗ «Поликлиника № 61»",
        won: false,
    },
    {
        subject: "Бумага офисная, класс B",
        nmck: 1180000,
        customer: "ГКУ «Жилищное агентство района»",
        won: true,
    },
    {
        subject: "Канцелярские товары и бумага",
        nmck: 264000,
        customer: "ГБДОУ «Детский сад № 45»",
        won: false,
    },
    {
        subject: "Бумага для печати А4, 1 200 пачек",
        nmck: 1940000,
        customer: "СПб ГКУ «Центр информационных технологий»",
        won: true,
    },
    {
        subject: "Бумага для офисной техники",
        nmck: 158700,
        customer: "ГБОУ «Лицей № 590»",
        won: false,
    },
];

const VARIANTS: SupplierVariantDto[] = VARIANT_BASE.map((item) => ({
    ...item,
    site: VARIANT_DETAILS[item.id].site,
    requisites: VARIANT_DETAILS[item.id].requisites,
    history: item.novelty === "new" ? [] : PARTICIPATION_HISTORY,
}));

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
        pattern: /^\/match\/search$/,
        handler: handleSearch,
    },
];
