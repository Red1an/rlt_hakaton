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

const STATUS_LABELS: Record<string, string> = {
    ACTIVE: "Действует",
    LIQUIDATING: "Ликвидируется",
    REORGANIZING: "Реорганизация",
    LIQUIDATED: "Ликвидирована",
    BANKRUPT: "Банкрот",
    NOT_FOUND: "Не найдена",
    ERROR: "Ошибка запроса",
};

const BAD_STATUSES = new Set([ "LIQUIDATED", "BANKRUPT", "NOT_FOUND", "ERROR" ]);
const WARN_STATUSES = new Set([ "LIQUIDATING", "REORGANIZING" ]);

const ROLE_NAMES: Record<string, string> = {
    manufacturer: "Производитель",
    distributor: "Дистрибьютор",
    supplier: "Поставщик",
};

const REGION_NAMES: Record<string, string> = {
    "78": "Санкт-Петербург",
    "47": "Ленинградская обл.",
};

function statusClass(status: string | null): string {
    if (status && BAD_STATUSES.has(status)) {
        return styles.statusBad;
    }

    return status && WARN_STATUSES.has(status) ? styles.statusWarn : styles.statusOk;
}

function regionName(code?: string | null): string {
    if (!code) {
        return "—";
    }

    return REGION_NAMES[code] ?? `регион ${ code }`;
}

const SEARCH_DEBOUNCE_MS = 300;

type Scope = "all" | "category";

function percent(part: number, total: number): number {
    return total > 0 ? Math.round(100 * part / total) : 0;
}

function jobSummary(job: EnrichmentJob): string | null {
    const scope = job.okpd ? `категория ${ job.okpd }` : "все категории";

    if (job.status === "done") {
        return `Готово (${ scope }): проверено ${ job.done ?? 0 }, закрытых компаний ${ job.closed ?? 0 }, не найдено ${ job.notFound ?? 0 }`;
    }

    if (job.status === "stopped" || job.status === "error") {
        return `Остановлено: ${ job.message ?? "неизвестная ошибка" }. Проверено ${ job.done ?? 0 }`;
    }

    return null;
}

export default function EnrichmentWidget() {
    const [ state, setState ] = useState<EnrichmentState | null>(null);
    const [ scope, setScope ] = useState<Scope>("all");
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
        if (scope !== "category") {
            return;
        }

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
    }, [ categoryTerm, scope ]);

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError(null);

        const okpd = scope === "category" ? categoryTerm.trim().split(" ")[0] : "";

        if (scope === "category" && okpd === "") {
            setError("Выберите категорию ОКПД2");

            return;
        }

        const count = Math.min(Math.max(Number(limit) || DEFAULT_LIMIT, 1), maxLimit);

        try {
            setState(await startEnrichment(okpd === "" ? null : okpd, count));
        } catch (reason) {
            setError(reason instanceof Error ? reason.message : "Не удалось запустить обогащение");
        }
    }

    const job = state?.job;
    const maxLimit = state?.maxLimit ?? MAX_LIMIT;
    const suppliers = state?.suppliers;
    const summary = job ? jobSummary(job) : null;
    const results: EnrichmentResult[] = job?.results ?? [];

    return (
        <div className={styles.page}>
            <section className={styles.card}>
                <h1 className={styles.title}>Обогащение данных о компаниях</h1>

                <p className={styles.lead}>
                    Сверяем поставщиков с ЕГРЮЛ через DaData: название, статус, ОКВЭД, адрес и дату регистрации.
                    Ликвидированные компании и банкроты убираются из рекомендаций, роль определяется по ОКВЭД.
                    Сначала проверяются поставщики из рекомендаций и лучшие в категории.
                </p>

                { suppliers && (
                    <div className={styles.stats}>
                        <div className={styles.stat}>
                            <span className={styles.statValue}>
                                { suppliers.enriched.toLocaleString("ru-RU") }
                            </span>
                            <span className={styles.statLabel}>
                                проверено из { suppliers.total.toLocaleString("ru-RU") } ({ percent(suppliers.enriched, suppliers.total) }%)
                            </span>
                        </div>

                        <div className={styles.stat}>
                            <span className={styles.statValue}>{ suppliers.closed }</span>
                            <span className={styles.statLabel}>ликвидированы или банкроты — скрыты</span>
                        </div>

                        <div className={styles.stat}>
                            <span className={styles.statValue}>{ suppliers.warning }</span>
                            <span className={styles.statLabel}>ликвидируются или реорганизуются</span>
                        </div>

                    </div>
                ) }

                <form className={styles.form} onSubmit={handleSubmit}>
                    <div className={styles.field}>
                        <span className={styles.label}>Что проверять</span>

                        <div className={styles.segmented}>
                            <button
                                type="button"
                                className={ `${ styles.segment } ${ scope === "all" ? styles.segmentActive : "" }` }
                                onClick={() => setScope("all")}
                            >
                                Все категории
                            </button>

                            <button
                                type="button"
                                className={ `${ styles.segment } ${ scope === "category" ? styles.segmentActive : "" }` }
                                onClick={() => setScope("category")}
                            >
                                Одна категория
                            </button>
                        </div>
                    </div>

                    { scope === "category" && (
                        <label className={ `${ styles.field } ${ styles.fieldWide }` }>
                            <span className={styles.label}>Категория ОКПД2</span>

                            <input
                                className={styles.input}
                                type="text"
                                list="enrichment-categories"
                                value={ categoryTerm }
                                placeholder="Код или название, например 17.12"
                                onChange={(event) => setCategoryTerm(event.target.value)}
                            />

                            <datalist id="enrichment-categories">
                                { categories.map((category) => (
                                    <option key={ category.code } value={ `${ category.code } ${ category.name }` } />
                                )) }
                            </datalist>
                        </label>
                    ) }

                    <label className={styles.field}>
                        <span className={styles.label}>Сколько компаний за раз (до { maxLimit })</span>

                        <input
                            className={ `${ styles.input } ${ styles.inputShort }` }
                            type="number"
                            min={ 1 }
                            max={ maxLimit }
                            value={ limit }
                            onChange={(event) => setLimit(event.target.value)}
                        />
                    </label>

                    <button className={styles.primary} type="submit" disabled={ isRunning }>
                        { isRunning ? "Проверяем…" : "Обогатить" }
                    </button>
                </form>

                { isRunning && job && (
                    <div className={styles.progress}>
                        <div className={styles.progressText}>
                            { job.total
                                ? `Проверено ${ job.done ?? 0 } из ${ job.total }${ job.closed ? ` · закрытых найдено: ${ job.closed }` : "" }`
                                : "Отбираем компании для проверки…" }
                        </div>

                        <div className={styles.progressBar}>
                            <div
                                className={styles.progressFill}
                                style={{ width: `${ percent(job.done ?? 0, job.total ?? 0) }%` }}
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
                            { isRunning ? "Проверяем" : "Проверены в последнем запуске" } · { results.length }
                        </h2>

                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Компания</th>
                                        <th>ИНН</th>
                                        <th>Статус</th>
                                        <th>Роль</th>
                                        <th>ОКВЭД</th>
                                        <th>Регион</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    { results.map((item) => (
                                        <tr key={ item.inn }>
                                            <td>{ item.name ?? "—" }</td>
                                            <td className={styles.mono}>{ item.inn }</td>
                                            <td>
                                                <span className={ `${ styles.status } ${ statusClass(item.status) }` }>
                                                    { STATUS_LABELS[item.status ?? ""] ?? item.status ?? "—" }
                                                </span>
                                            </td>
                                            <td title={ item.roleReason ?? undefined }>
                                                { item.role ? ROLE_NAMES[item.role] : "—" }
                                            </td>
                                            <td className={styles.mono}>{ item.okved ?? "—" }</td>
                                            <td>{ regionName(item.regionCode) }</td>
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
