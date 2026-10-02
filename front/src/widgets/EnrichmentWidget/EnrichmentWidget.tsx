import {
    useEffect, useState,
} from "react";
import type { FormEvent } from "react";

import {
    fetchEnrichment, searchCategories, startEnrichment,
} from "@/service";
import type {
    EnrichmentJob, EnrichmentResult, EnrichmentState, OkpdCategory,
} from "@/service";

import styles from "./EnrichmentWidget.module.scss";

const POLL_INTERVAL_MS = 1500;
const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 50;
const SEARCH_DEBOUNCE_MS = 300;
const SELECTABLE_CODE = /^\d{2}\.\d{2}/;
const PER_CATEGORY = 20;

type Scope = "category" | "all";

const ROLE_NAMES: Record<string, string> = {
    manufacturer: "Производитель",
    distributor: "Дистрибьютор",
    supplier: "Поставщик",
};

const REGION_NAMES: Record<string, string> = {
    "78": "Санкт-Петербург",
    "47": "Ленинградская обл.",
};

function regionName(code: string | null): string {
    if (!code) {
        return "—";
    }

    return REGION_NAMES[code] ?? `регион ${ code }`;
}

function formatDate(value: string | null): string {
    return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}

function jobSummary(job: EnrichmentJob): string | null {
    const found = job.found ?? job.results?.length ?? 0;

    if (job.status === "done" && !job.okpd) {
        return `Готово: пройдено категорий ${ job.categoriesDone ?? 0 }, новых компаний добавлено ${ found }`;
    }

    if (job.status === "done") {
        return found > 0
            ? `Готово: категория ${ job.okpd }, новых компаний добавлено ${ found }`
            : `Новых компаний в категории ${ job.okpd } не нашлось: все подходящие уже есть в базе`;
    }

    if (job.status === "stopped" || job.status === "error") {
        return `Остановлено: ${ job.message ?? "неизвестная ошибка" }. Добавлено ${ found }`;
    }

    return null;
}

function progressPercent(job: EnrichmentJob, found: number): number {
    if (job.okpd) {
        return job.limit ? Math.round(100 * found / job.limit) : 0;
    }

    return job.categories ? Math.round(100 * (job.categoriesDone ?? 0) / job.categories) : 0;
}

export default function EnrichmentWidget() {
    const [ state, setState ] = useState<EnrichmentState | null>(null);
    const [ scope, setScope ] = useState<Scope>("category");
    const [ categoryTerm, setCategoryTerm ] = useState("");
    const [ categories, setCategories ] = useState<OkpdCategory[]>([]);
    const [ limit, setLimit ] = useState(String(DEFAULT_LIMIT));
    const [ error, setError ] = useState<string | null>(null);
    const [ version, setVersion ] = useState(0);

    useEffect(() => {
        let isAlive = true;

        fetchEnrichment()
            .then((result) => {
                if (isAlive) {
                    setState(result);
                }
            })
            .catch((reason: unknown) => {
                if (isAlive) {
                    setError(reason instanceof Error ? reason.message : "Не удалось получить состояние");
                }
            });

        return () => {
            isAlive = false;
        };
    }, [ version ]);

    const isRunning = state?.job.status === "running";

    useEffect(() => {
        if (!isRunning) {
            return;
        }

        const timer = setInterval(() => setVersion((value) => value + 1), POLL_INTERVAL_MS);

        return () => clearInterval(timer);
    }, [ isRunning ]);

    useEffect(() => {
        let isAlive = true;
        const timer = setTimeout(() => {
            searchCategories(categoryTerm)
                .then((found) => {
                    if (isAlive) {
                        setCategories(found.slice(0, 30));
                    }
                })
                .catch(() => undefined);
        }, SEARCH_DEBOUNCE_MS);

        return () => {
            isAlive = false;
            clearTimeout(timer);
        };
    }, [ categoryTerm ]);

    const job = state?.job;
    const maxLimit = state?.maxLimit ?? MAX_LIMIT;
    const perCategory = state?.perCategory ?? PER_CATEGORY;
    const found = job?.found ?? 0;
    const suppliers = state?.suppliers;
    const summary = job ? jobSummary(job) : null;
    const results: EnrichmentResult[] = job?.results ?? [];

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);

        if (scope === "all") {
            try {
                setState(await startEnrichment(null, perCategory));
            } catch (reason) {
                setError(reason instanceof Error ? reason.message : "Не удалось запустить поиск");
            }

            return;
        }

        const okpd = categoryTerm.trim().split(" ")[0];

        if (!SELECTABLE_CODE.test(okpd)) {
            setError("Выберите конкретную категорию ОКПД2 вида XX.XX, например 45.20");

            return;
        }

        const count = Math.min(Math.max(Number(limit) || DEFAULT_LIMIT, 1), maxLimit);

        try {
            setState(await startEnrichment(okpd, count));
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Не удалось запустить поиск");
        }
    }

    return (
        <div className={styles.page}>
            <section className={styles.card}>
                <h1 className={styles.title}>Поиск новых поставщиков</h1>

                <p className={styles.lead}>
                    Ищем в ЕГРЮЛ через DaData действующие компании Санкт-Петербурга и Ленинградской области,
                    у которых основной ОКВЭД совпадает с выбранной категорией. В базу добавляются только те,
                    кого в ней ещё нет, существующие записи не меняются. Роль определяется по ОКВЭД.
                </p>

                { suppliers && (
                    <div className={styles.stats}>
                        <div className={styles.stat}>
                            <span className={styles.statValue}>{ suppliers.found.toLocaleString("ru-RU") }</span>
                            <span className={styles.statLabel}>новых найдено в ЕГРЮЛ</span>
                        </div>

                        <div className={styles.stat}>
                            <span className={styles.statValue}>{ suppliers.web.toLocaleString("ru-RU") }</span>
                            <span className={styles.statLabel}>найдено ранее в открытых источниках</span>
                        </div>

                        <div className={styles.stat}>
                            <span className={styles.statValue}>{ suppliers.total.toLocaleString("ru-RU") }</span>
                            <span className={styles.statLabel}>всего компаний в базе</span>
                        </div>
                    </div>
                ) }

                <form className={styles.form} onSubmit={handleSubmit}>
                    <div className={styles.field}>
                        <span className={styles.label}>Где искать</span>

                        <div className={styles.segmented}>
                            <button
                                type="button"
                                className={ `${ styles.segment } ${ scope === "category" ? styles.segmentActive : "" }` }
                                onClick={() => setScope("category")}
                            >
                                Одна категория
                            </button>

                            <button
                                type="button"
                                className={ `${ styles.segment } ${ scope === "all" ? styles.segmentActive : "" }` }
                                onClick={() => setScope("all")}
                            >
                                Все категории
                            </button>
                        </div>
                    </div>

                    { scope === "all" && (
                        <p className={styles.hint}>
                            Пройдём по всем категориям из истории закупок, в каждой добавим не больше { perCategory } новых.
                            Категории, где уже найдено { perCategory }, пропускаются.
                        </p>
                    ) }

                    { scope === "category" && (
                        <label className={ `${ styles.field } ${ styles.fieldWide }` }>
                            <span className={styles.label}>Категория ОКПД2</span>

                            <input
                                className={styles.input}
                                type="text"
                                list="enrichment-categories"
                                value={ categoryTerm }
                                placeholder="Код или название, например 45.20"
                                onChange={(event) => setCategoryTerm(event.target.value)}
                            />

                            <datalist id="enrichment-categories">
                                { categories.map((category) => (
                                    <option key={ category.code } value={ `${ category.code } ${ category.name }` } />
                                )) }
                            </datalist>
                        </label>
                    ) }

                    { scope === "category" && (
                        <label className={styles.field}>
                            <span className={styles.label}>Сколько новых добавить (до { maxLimit })</span>

                            <input
                                className={ `${ styles.input } ${ styles.inputShort }` }
                                type="number"
                                min={ 1 }
                                max={ maxLimit }
                                value={ limit }
                                onChange={(event) => setLimit(event.target.value)}
                            />
                        </label>
                    ) }

                    <button className={styles.primary} type="submit" disabled={ isRunning }>
                        { isRunning ? "Ищем…" : "Найти новых" }
                    </button>
                </form>

                { isRunning && job && (
                    <div className={styles.progress}>
                        <div className={styles.progressText}>
                            { job.okpd
                                ? `Категория ${ job.okpd }: найдено новых ${ found } из ${ job.limit ?? 0 }`
                                : `Категорий пройдено ${ job.categoriesDone ?? 0 } из ${ job.categories ?? "…" }${
                                    job.current ? ` · сейчас ${ job.current }` : "" } · новых найдено ${ found }` }
                        </div>

                        <div className={styles.progressBar}>
                            <div
                                className={styles.progressFill}
                                style={{ width: `${ progressPercent(job, found) }%` }}
                            />
                        </div>
                    </div>
                ) }

                { summary && !isRunning && (
                    <p className={ `${ styles.notice } ${ job?.status === "done" ? styles.noticeOk : styles.noticeBad }` }>
                        { summary }
                    </p>
                ) }

                { error && <p className={ `${ styles.notice } ${ styles.noticeBad }` }>{ error }</p> }

                { results.length > 0 && (
                    <div className={styles.results}>
                        <h2 className={styles.subtitle}>
                            { isRunning ? "Найдены" : "Добавлены в последнем запуске" } · { found }
                            { found > results.length && ` (показаны последние ${ results.length })` }
                        </h2>

                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Компания</th>
                                        <th>ИНН</th>
                                        <th>Роль</th>
                                        <th>ОКВЭД</th>
                                        <th>Регион</th>
                                        <th>Регистрация</th>
                                        <th>Адрес</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    { results.map((item) => (
                                        <tr key={ item.inn }>
                                            <td>{ item.name ?? "—" }</td>
                                            <td className={styles.mono}>{ item.inn }</td>
                                            <td title={ item.roleReason ?? undefined }>
                                                { item.role ? ROLE_NAMES[item.role] : "—" }
                                            </td>
                                            <td className={styles.mono}>{ item.okved ?? "—" }</td>
                                            <td>{ regionName(item.regionCode) }</td>
                                            <td className={styles.mono}>{ formatDate(item.regDate) }</td>
                                            <td>{ item.address ?? "—" }</td>
                                        </tr>
                                    )) }
                                </tbody>
                            </table>
                        </div>
                    </div>
                ) }
            </section>
        </div>
    );
}
