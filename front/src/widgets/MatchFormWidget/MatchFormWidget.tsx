import {
    useCallback, useEffect, useRef, useState,
} from "react";
import type {
    Dispatch, FormEvent, SetStateAction,
} from "react";

import * as matchService from "@/service/matchService";
import type {
    MatchFormState, MatchFormValues, MatchPlatform, OkpdCategory,
} from "@/service/matchService";

import styles from "./MatchFormWidget.module.scss";

/** Пауза перед поиском по справочнику категорий. */
const SEARCH_DEBOUNCE_MS = 300;

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

/** Сколько цифр в ИНН заказчика. */
const INN_LENGTH = 10;

/** ИНН принимаем только цифрами фиксированной длины. */
function formatInn(raw: string): string {
    return raw.replace(/\D/g, "").slice(0, INN_LENGTH);
}

interface MatchFormWidgetProps {
    /** Поля, режим автоподбора и свёрнутость хранит родитель — он же переживает экраны. */
    state: MatchFormState;
    onChange: Dispatch<SetStateAction<MatchFormState>>;
    /** Вызывается после успешного подбора — родитель заводит лот и показывает варианты. */
    onSearched?: (values: MatchFormValues, requestId: string) => void;
}

export default function MatchFormWidget({
    state, onChange, onSearched,
}: MatchFormWidgetProps) {
    const {
        values, isCollapsed,
    } = state;
    const [ categories, setCategories ] = useState<OkpdCategory[]>([]);
    const [ categoryTerm, setCategoryTerm ] = useState("");
    const [ isCategoryOpen, setIsCategoryOpen ] = useState(false);
    const [ isCategoryLoading, setIsCategoryLoading ] = useState(false);
    const [ isSubmitting, setIsSubmitting ] = useState(false);
    const [ notice, setNotice ] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

    const setValues = useCallback((update: (prev: MatchFormValues) => MatchFormValues) => {
        onChange((prev) => ({
            ...prev,
            values: update(prev.values),
        }));
    }, [ onChange ]);

    function setIsCollapsed(value: boolean) {
        onChange((prev) => ({
            ...prev,
            isCollapsed: value,
        }));
    }

    const categoryRef = useRef<HTMLDivElement>(null);
    const categorySearchRef = useRef<HTMLInputElement>(null);
    /** Счётчик запросов поиска по справочнику: поздний ответ не должен перетереть свежий. */
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

    function setValue<K extends keyof MatchFormValues>(key: K, value: MatchFormValues[K]) {
        setValues((prev) => ({
            ...prev,
            [key]: value,
        }));
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

        if (values.category === null) {
            setNotice({
                tone: "bad",
                text: "Выберите категорию ОКПД2",
            });

            return;
        }

        if (!matchService.isSelectableCategory(values.category.code)) {
            setNotice({
                tone: "bad",
                text: "Категория слишком общая: выберите группу, например 32.50 или 17.12",
            });

            return;
        }

        if (Number(values.nmck.replace(/\s/g, "")) <= 0) {
            setNotice({
                tone: "bad",
                text: "Укажите НМЦК",
            });

            return;
        }

        const inn = values.customerInn.trim();

        if (inn.length > 0 && inn.length !== INN_LENGTH) {
            setNotice({
                tone: "bad",
                text: `ИНН должен содержать ${ INN_LENGTH } цифр`,
            });

            return;
        }

        setNotice(null);
        setIsSubmitting(true);

        try {
            const result = await matchService.submitSearch(values);

            // Успешный подбор сворачивает форму в сводку, результаты — ниже.
            setNotice(null);
            setIsCollapsed(true);
            onSearched?.(values, result.requestId);
        } catch (error) {
            setNotice({
                tone: "bad",
                text: error instanceof Error ? error.message : "Не удалось выполнить подбор",
            });
        } finally {
            setIsSubmitting(false);
        }
    }

    // После подбора форма схлопывается в строку-сводку с кнопкой «Изменить запрос».
    if (isCollapsed) {
        const platformLabel = PLATFORM_OPTIONS.find(
            (option) => option.value === values.platform,
        )?.label ?? "";

        return (
            <section className={styles.summary}>
                <div className={styles.summaryMain}>
                    <div className={styles.summaryHead}>
                        <span className={styles.summaryLabel}>Вы закупаете</span>

                        { values.category && (
                            <span className={styles.summaryCategory}>
                                <span className={styles.summaryCode}>
                                    { values.category.code }
                                </span>

                                { values.category.name }
                            </span>
                        ) }
                    </div>

                    <div className={styles.summaryMeta}>

                        { values.nmck !== "" && (
                            <span className={styles.summaryItem}>
                                НМЦК
                                <span className={styles.summaryMono}>{ values.nmck }</span>
                                ₽
                            </span>
                        ) }

                        <span className={styles.summaryItem}>{ platformLabel }</span>

                        { values.mspOnly && (
                            <span className={styles.summaryItem}>только МСП</span>
                        ) }

                        { values.customerInn.trim().length > 0 && (
                            <span className={styles.summaryItem}>
                                ИНН
                                <span className={styles.summaryMono}>
                                    { values.customerInn.trim() }
                                </span>
                            </span>
                        ) }
                    </div>
                </div>

                <button
                    className={styles.summaryEdit}
                    type="button"
                    onClick={() => setIsCollapsed(false)}
                >
                    Изменить запрос
                </button>
            </section>
        );
    }

    return (
        <section className={styles.card}>
            <h1 className={styles.title}>Что вы закупаете?</h1>

            <form className={styles.form} onSubmit={handleSubmit}>
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
                                { values.category === null
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
                    </div>

                    <p className={styles.hint}>
                        Выберите группу товаров по коду или названию, например «17.12 Бумага и картон» или «32.50».
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

                    <label className={ `${ styles.field } ${ styles.fieldInn }` }>
                        <span className={styles.label}>ИНН заказчика</span>

                        <input
                            className={styles.input}
                            type="text"
                            inputMode="numeric"
                            maxLength={ INN_LENGTH }
                            value={ values.customerInn }
                            placeholder="7812345678"
                            onChange={(event) => setValue("customerInn", formatInn(event.target.value))}
                        />

                        <span className={styles.hint}>Необязательно: учитываем опыт с этим заказчиком</span>
                    </label>
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

                    { values.category !== null && (
                        <button
                            className={styles.collapseBtn}
                            type="button"
                            onClick={() => setIsCollapsed(true)}
                        >
                            Свернуть
                        </button>
                    ) }
                </div>
            </form>
        </section>
    );
}