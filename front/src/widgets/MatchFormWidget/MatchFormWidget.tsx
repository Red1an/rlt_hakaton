import {
    useEffect, useRef, useState,
} from "react";
import type { FormEvent } from "react";

import * as matchService from "@/service/matchService";
import type {
    MatchFormValues, MatchPlatform, OkpdCategory,
} from "@/service/matchService";

import styles from "./MatchFormWidget.module.scss";

const INITIAL_VALUES: MatchFormValues = {
    query: "",
    category: null,
    nmck: "",
    platform: "em",
    mspOnly: false,
};

/** Пауза перед автоподбором, чтобы не дёргать api на каждое нажатие клавиши. */
const DETECT_DEBOUNCE_MS = 400;

/** Пауза перед поиском по справочнику категорий. */
const SEARCH_DEBOUNCE_MS = 300;

/** Ниже этой длины описание не даёт оснований для подбора. */
const MIN_DETECT_LENGTH = 3;

const PLATFORM_OPTIONS: Array<{ value: MatchPlatform; label: string }> = [
    {
        value: "ais",
        label: "АИС ГЗ",
    },
    {
        value: "em",
        label: "Электронный магазин",
    },
];

/** Группировка НМЦК: 1240000 → 1 240 000. */
function formatNmck(raw: string): string {
    const digits = raw.replace(/\D/g, "");

    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

export default function MatchFormWidget() {
    const [ values, setValues ] = useState<MatchFormValues>( INITIAL_VALUES );
    const [ categories, setCategories ] = useState<OkpdCategory[]>([]);
    const [ categoryTerm, setCategoryTerm ] = useState("");
    const [ isCategoryOpen, setIsCategoryOpen ] = useState(false);
    const [ isCategoryLoading, setIsCategoryLoading ] = useState(false);
    const [ isAutoDetect, setIsAutoDetect ] = useState(true);
    const [ isDetecting, setIsDetecting ] = useState(false);
    const [ isSubmitting, setIsSubmitting ] = useState(false);
    const [ notice, setNotice ] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

    const categoryRef = useRef<HTMLDivElement>(null);
    const categorySearchRef = useRef<HTMLInputElement>(null);
    /**
     * Счётчик запросов автоподбора: ответ приходит через ~400 мс, как и debounce,
     * поэтому без проверки id поздний ответ по старому тексту перетрёт свежий.
     */
    const detectRequestId = useRef(0);
    /** Счётчик запросов поиска по справочнику — по той же причине. */
    const searchRequestId = useRef(0);

    useEffect(() => {
        if (!isCategoryOpen) {
            return;
        }

        function handlePointerDown(event: MouseEvent) {
            if (!categoryRef.current?.contains(event.target as Node)) {
                setIsCategoryOpen(false);
                setCategoryTerm("");
            }
        }

        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") {
                setIsCategoryOpen(false);
                setCategoryTerm("");
            }
        }

        document.addEventListener("mousedown", handlePointerDown);
        document.addEventListener("keydown", handleKeyDown);

        return () => {
            document.removeEventListener("mousedown", handlePointerDown);
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, [ isCategoryOpen ]);

    // Поиск по справочнику с debounce, чтобы не дёргать api на каждое нажатие.
    useEffect(() => {
        if (!isCategoryOpen) {
            return;
        }

        searchRequestId.current += 1;
        const requestId = searchRequestId.current;

        const timer = setTimeout(() => {
            if (requestId !== searchRequestId.current) {
                return;
            }

            setIsCategoryLoading(true);

            void matchService.searchCategories(categoryTerm)
                .then((found) => {
                    if (requestId !== searchRequestId.current) {
                        return;
                    }

                    setCategories(found);
                })
                .catch(() => {
                    if (requestId !== searchRequestId.current) {
                        return;
                    }

                    setCategories([]);
                })
                .finally(() => {
                    if (requestId === searchRequestId.current) {
                        setIsCategoryLoading(false);
                    }
                });
        }, SEARCH_DEBOUNCE_MS);

        return () => {
            clearTimeout(timer);
        };
    }, [ categoryTerm, isCategoryOpen ]);

    useEffect(() => {
        const query = values.query.trim();

        // Инвалидируем предыдущий подбор при любом изменении текста или режима:
        // иначе ответ по старому запросу перетрёт свежий либо ручной выбор.
        detectRequestId.current += 1;
        const requestId = detectRequestId.current;

        if (!isAutoDetect) {
            return;
        }

        const timer = setTimeout(() => {
            if (requestId !== detectRequestId.current) {
                return;
            }

            if (query.length < MIN_DETECT_LENGTH) {
                setIsDetecting(false);
                setValues((prev) => ({
                    ...prev,
                    category: null,
                }));

                return;
            }

            setIsDetecting(true);

            void matchService.detectCategory(query)
                .then((detected) => {
                    if (requestId !== detectRequestId.current) {
                        return;
                    }

                    setValues((prev) => ({
                        ...prev,
                        category: detected,
                    }));
                })
                .catch(() => {
                    // Молча: во время набора текста ошибка подбора не должна мигать.
                    if (requestId !== detectRequestId.current) {
                        return;
                    }

                    setValues((prev) => ({
                        ...prev,
                        category: null,
                    }));
                })
                .finally(() => {
                    if (requestId === detectRequestId.current) {
                        setIsDetecting(false);
                    }
                });
        }, DETECT_DEBOUNCE_MS);

        return () => {
            clearTimeout(timer);
        };
    }, [ isAutoDetect, values.query ]);

    function setValue<K extends keyof MatchFormValues>(key: K, value: MatchFormValues[K]) {
        setValues((prev) => ({
            ...prev,
            [key]: value,
        }));
        setNotice(null);
    }

    function patchQuery(value: string) {
        setValues((prev) => ({
            ...prev,
            query: value,
            // При ручном режиме выбор пользователя не трогаем — автоподбор выключен.
            category: isAutoDetect ? null : prev.category,
        }));
        setNotice(null);
    }

    /** Снимает автоподбор: ручной выбор не должен перетираться новым подбором. */
    function disableAutoDetect() {
        setIsDetecting(false);
        setIsAutoDetect(false);
        setNotice(null);
    }

    /** Открывает список, ставит фокус в поиск и сразу показывает весь справочник. */
    function openCategoryList() {
        const next = !isCategoryOpen;

        setIsCategoryOpen(next);
        setNotice(null);

        if (!next) {
            setCategoryTerm("");

            return;
        }

        setCategoryTerm("");
        setIsCategoryLoading(true);

        void matchService.fetchCategories()
            .then(setCategories)
            .catch(() => setCategories([]))
            .finally(() => setIsCategoryLoading(false));

        categorySearchRef.current?.focus();
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        setNotice(null);
        setIsSubmitting(true);

        try {
            const result = await matchService.submitSearch(values);

            setNotice({
                tone: "ok",
                text: result.message,
            });
        } catch (error) {
            setNotice({
                tone: "bad",
                text: error instanceof Error ? error.message : "Не удалось выполнить подбор",
            });
        } finally {
            setIsSubmitting(false);
        }
    }

    return (
        <section className={styles.card}>
            <h1 className={styles.title}>Что вы закупаете?</h1>

            <form className={styles.form} onSubmit={handleSubmit}>
                <label className={styles.field}>
                    <span className={styles.label}>Описание закупки</span>

                    <input
                        className={styles.queryInput}
                        type="text"
                        value={ values.query }
                        placeholder="Например: бумага для офисной техники А4, 80 г/м², 600 пачек"
                        onChange={(event) => patchQuery(event.target.value)}
                    />
                </label>

                <div className={styles.field}>
                    <span className={styles.label}>Категория ОКПД2</span>

                    <div className={styles.categoryRow}>
                        <div className={styles.category} ref={ categoryRef }>
                            <button
                                className={styles.categoryChip}
                                type="button"
                                aria-expanded={ isCategoryOpen }
                                aria-haspopup="listbox"
                                onClick={openCategoryList}
                            >
                                { isDetecting
                                    ? "Определяем категорию…"
                                    : values.category === null
                                        ? <span className={styles.categoryEmpty}>
                                            Категория не выбрана
                                        </span>
                                        : (
                                            <>
                                                <span className={styles.categoryCode}>
                                                    { values.category.code }
                                                </span>

                                                <span className={styles.categoryName}>
                                                    { values.category.name }
                                                </span>
                                            </>
                                        ) }

                                <span className={styles.categoryCaret}>▾</span>
                            </button>

                            { isCategoryOpen && (
                                <div className={styles.categoryMenu}>
                                    <input
                                        ref={ categorySearchRef }
                                        className={styles.categorySearch}
                                        type="text"
                                        value={ categoryTerm }
                                        placeholder="Поиск по коду или названию"
                                        onChange={(event) => setCategoryTerm(event.target.value)}
                                        onKeyDown={(event) => {
                                            if (event.key === "Escape") {
                                                setIsCategoryOpen(false);
                                                setCategoryTerm("");
                                            }
                                        }}
                                    />

                                    <div className={styles.categoryList} role="listbox">
                                        { isCategoryLoading
                                            ? <span className={styles.categoryLoading}>
                                                Загрузка…
                                            </span>
                                            : categories.length === 0
                                                ? <span className={styles.categoryLoading}>
                                                    Ничего не найдено
                                                </span>
                                                : categories.map((item) => (
                                                    <button
                                                        key={ item.code }
                                                        className={ `${ styles.categoryOption } ${
                                                            values.category?.code === item.code
                                                                ? styles.categoryOptionSelected
                                                                : ""
                                                        }` }
                                                        type="button"
                                                        role="option"
                                                        aria-selected={ values.category?.code === item.code }
                                                        onClick={() => {
                                                            setValue("category", item);
                                                            setIsCategoryOpen(false);
                                                            setCategoryTerm("");
                                                            // Ручной выбор снимает автоподбор, иначе
                                                            // следующая правка описания его перетрёт.
                                                            disableAutoDetect();
                                                        }}
                                                    >
                                                        <span className={styles.categoryCode}>
                                                            { item.code }
                                                        </span>

                                                        <span className={styles.categoryOptionName}>
                                                            { item.name }
                                                        </span>
                                                    </button>
                                                )) }
                                    </div>
                                </div>
                            ) }
                        </div>

                        <div className={styles.autoRow}>
                            <button
                                className={ `${ styles.switchSmall } ${
                                    isAutoDetect ? styles.switchSmallOn : ""
                                }` }
                                type="button"
                                role="switch"
                                aria-checked={ isAutoDetect }
                                aria-label="Подбирать категорию автоматически"
                                onClick={() => {
                                    // Индикатор гасим здесь, а не в эффекте:
                                    // переключение не должно ждать debounce.
                                    if (isAutoDetect) {
                                        disableAutoDetect();

                                        return;
                                    }

                                    setIsAutoDetect(true);
                                    setNotice(null);
                                }}
                            >
                                <span className={styles.switchSmallKnob} />
                            </button>

                            <span className={styles.autoLabel}>Подбирать автоматически</span>
                        </div>
                    </div>

                    <p className={styles.hint}>
                        { isDetecting
                            ? "Подбирается по описанию…"
                            : isAutoDetect
                                ? "Подбирается по описанию. Можно изменить вручную."
                                : "Автоподбор выключен — выберите категорию вручную." }
                    </p>
                </div>

                <div className={styles.paramsRow}>
                    <label className={styles.field}>
                        <span className={styles.label}>НМЦК, ₽</span>

                        <input
                            className={styles.input}
                            type="text"
                            inputMode="numeric"
                            value={ values.nmck }
                            placeholder="1 240 000"
                            onChange={(event) => setValue("nmck", formatNmck(event.target.value))}
                        />
                    </label>

                    <div className={ `${ styles.field } ${ styles.fieldPlatform }` }>
                        <span className={styles.label}>Площадка</span>

                        <div className={styles.segmented}>
                            { PLATFORM_OPTIONS.map((option) => (
                                <button
                                    key={ option.value }
                                    className={ `${ styles.segment } ${
                                        values.platform === option.value ? styles.segmentActive : ""
                                    }` }
                                    type="button"
                                    onClick={() => setValue("platform", option.value)}
                                >
                                    { option.label }
                                </button>
                            )) }
                        </div>
                    </div>

                    <div className={ `${ styles.field } ${ styles.fieldMsp }` }>
                        <span className={styles.label}>Только МСП</span>

                        <button
                            className={ `${ styles.switch } ${
                                values.mspOnly ? styles.switchOn : ""
                            }` }
                            type="button"
                            role="switch"
                            aria-checked={ values.mspOnly }
                            aria-label="Только МСП"
                            onClick={() => setValue("mspOnly", !values.mspOnly)}
                        >
                            <span className={styles.switchKnob} />
                        </button>
                    </div>
                </div>

                { notice && (
                    <p className={ `${ styles.notice } ${
                        notice.tone === "ok" ? styles.noticeOk : styles.noticeBad
                    }` }
                    >
                        { notice.text }
                    </p>
                ) }

                <div className={styles.actions}>
                    <button className={styles.submit} type="submit" disabled={ isSubmitting }>
                        { isSubmitting ? "Подбираем…" : "Подобрать поставщиков" }
                    </button>
                </div>
            </form>
        </section>
    );
}