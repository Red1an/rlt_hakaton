import {
    useEffect, useRef, useState,
} from "react";
import type { FormEvent } from "react";

import {
    batchExportUrl,
    computeLot,
    deleteBatch,
    fetchBatchLots,
    fetchBatchStatus,
    fetchBatches,
    formatDate,
    formatRub,
    jobProgress,
    recomputeBatch,
    uploadBatch,
} from "@/service";
import type {
    Batch, BatchJob, BatchLot,
} from "@/service";
import VariantsWidget from "@/widgets/VariantsWidget/VariantsWidget";

import styles from "./BatchWidget.module.scss";

const POLL_INTERVAL_MS = 2000;

const PLATFORM_LABELS: Record<BatchLot["platform"], string> = {
    ais: "АИС ГЗ",
    em: "ЭМ",
};

interface BatchWidgetProps {
    selectedBatch: string;
    onSelectBatch: (name: string) => void;
    openLotId: number | null;
    onOpenLot: (lotId: number | null) => void;
    shortListIds: string[];
    onToggleShortList: (lot: BatchLot, supplierId: string) => void;
}

type Notice = { tone: "ok" | "bad"; text: string } | null;

function errorText(error: unknown, fallback: string): string {
    return error instanceof Error ? error.message : fallback;
}

export default function BatchWidget({
    selectedBatch, onSelectBatch, openLotId, onOpenLot, shortListIds, onToggleShortList,
}: BatchWidgetProps) {
    const [ batches, setBatches ] = useState<Batch[]>([]);
    const [ lots, setLots ] = useState<BatchLot[]>([]);
    const [ job, setJob ] = useState<BatchJob>({ status: "idle" });
    const [ files, setFiles ] = useState<File[]>([]);
    const [ batchName, setBatchName ] = useState("");
    const [ isUploading, setIsUploading ] = useState(false);
    const [ notice, setNotice ] = useState<Notice>(null);
    const [ computingIds, setComputingIds ] = useState<number[]>([]);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const [ batchesVersion, setBatchesVersion ] = useState(0);
    const [ lotsVersion, setLotsVersion ] = useState(0);
    const [ loadedBatch, setLoadedBatch ] = useState("");

    useEffect(() => {
        let isAlive = true;

        fetchBatches()
            .then((found) => {
                if (!isAlive) {
                    return;
                }

                setBatches(found);

                if (found.length > 0 && !found.some((batch) => batch.name === selectedBatch)) {
                    onSelectBatch(found[0].name);
                }
            })
            .catch((error: unknown) => {
                if (isAlive) {
                    setNotice({
                        tone: "bad",
                        text: errorText(error, "Не удалось получить список пакетов"),
                    });
                }
            });

        return () => {
            isAlive = false;
        };
    }, [ batchesVersion, onSelectBatch, selectedBatch ]);

    useEffect(() => {
        if (selectedBatch === "") {
            return;
        }

        let isAlive = true;

        fetchBatchLots(selectedBatch)
            .then((result) => {
                if (!isAlive) {
                    return;
                }

                setLots(result.lots);
                setJob(result.job);
                setLoadedBatch(selectedBatch);
            })
            .catch((error: unknown) => {
                if (isAlive) {
                    setNotice({
                        tone: "bad",
                        text: errorText(error, "Не удалось загрузить лоты пакета"),
                    });
                }
            });

        return () => {
            isAlive = false;
        };
    }, [ lotsVersion, selectedBatch ]);

    useEffect(() => {
        if (selectedBatch === "" || job.status !== "running") {
            return;
        }

        const timer = setInterval(() => {
            void fetchBatchStatus(selectedBatch)
                .then((result) => {
                    setJob(result.job);

                    if (result.job.status !== "running") {
                        setLotsVersion((value) => value + 1);
                        setBatchesVersion((value) => value + 1);
                    }
                })
                .catch(() => undefined);
        }, POLL_INTERVAL_MS);

        return () => clearInterval(timer);
    }, [ job.status, selectedBatch ]);

    async function handleUpload(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (files.length === 0) {
            setNotice({
                tone: "bad",
                text: "Выберите CSV с извещениями и с товарами (ТРУ)",
            });

            return;
        }

        setIsUploading(true);
        setNotice(null);

        try {
            const started = await uploadBatch(files, batchName);
            const created = started.name;

            setBatchesVersion((value) => value + 1);
            setLotsVersion((value) => value + 1);

            setFiles([]);
            setBatchName("");

            if (fileInputRef.current) {
                fileInputRef.current.value = "";
            }
            onOpenLot(null);
            onSelectBatch(created);
            setJob(started.job);
            setNotice({
                tone: "ok",
                text: `Пакет «${ created }» загружен${ started.lots ? `: ${ started.lots } лотов` : "" }. `
                    + "Подберите поставщиков для нужного лота или обработайте все сразу",
            });
        } catch (error) {
            setNotice({
                tone: "bad",
                text: errorText(error, "Не удалось загрузить файлы"),
            });
        } finally {
            setIsUploading(false);
        }
    }

    async function handleCompute(onlyMissing: boolean) {
        setNotice(null);

        try {
            setJob((await recomputeBatch(selectedBatch, onlyMissing)).job);
        } catch (error) {
            setNotice({
                tone: "bad",
                text: errorText(error, "Не удалось запустить пересчёт"),
            });
        }
    }

    async function handleComputeLot(lotId: number) {
        setComputingIds((ids) => [ ...ids, lotId ]);
        setNotice(null);

        try {
            const computed = await computeLot(lotId);

            setLots((current) => current.map((lot) => (lot.lotId === lotId ? computed : lot)));
            onOpenLot(lotId);
        } catch (error) {
            setNotice({
                tone: "bad",
                text: errorText(error, "Не удалось подобрать поставщиков для лота"),
            });
        } finally {
            setComputingIds((ids) => ids.filter((id) => id !== lotId));
        }
    }

    async function handleDelete() {
        if (!window.confirm(`Удалить пакет «${ selectedBatch }» вместе с рекомендациями?`)) {
            return;
        }

        try {
            await deleteBatch(selectedBatch);
            onOpenLot(null);
            onSelectBatch("");
            setBatchesVersion((value) => value + 1);
            setNotice({
                tone: "ok",
                text: "Пакет удалён",
            });
        } catch (error) {
            setNotice({
                tone: "bad",
                text: errorText(error, "Не удалось удалить пакет"),
            });
        }
    }

    const visibleLots = selectedBatch !== "" && loadedBatch === selectedBatch ? lots : [];
    const isLoadingLots = selectedBatch !== "" && loadedBatch !== selectedBatch;
    const openLot = visibleLots.find((lot) => lot.lotId === openLotId) ?? null;
    const isRunning = job.status === "running";
    const computedCount = visibleLots.filter((lot) => lot.computed).length;
    const missingCount = visibleLots.length - computedCount;

    return (
        <div className={styles.page}>
            <section className={styles.card}>
                <h1 className={styles.title}>Пакетный подбор</h1>

                <p className={styles.lead}>
                    Загрузите закупки в формате исходных данных: CSV с извещениями и с товарами, имена файлов
                    любые. Затем подберите поставщиков для отдельного лота или обработайте весь пакет.
                </p>

                <form className={styles.upload} onSubmit={handleUpload}>
                    <label className={styles.field}>
                        <span className={styles.label}>CSV с извещениями и товарами</span>

                        <input
                            ref={ fileInputRef }
                            className={styles.fileInput}
                            type="file"
                            accept=".csv,text/csv"
                            multiple
                            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
                        />
                    </label>

                    <label className={ `${ styles.field } ${ styles.fieldName }` }>
                        <span className={styles.label}>Название пакета</span>

                        <input
                            className={styles.input}
                            type="text"
                            value={ batchName }
                            placeholder="Например: Закупки на август"
                            onChange={(event) => setBatchName(event.target.value)}
                        />
                    </label>

                    <button className={styles.primary} type="submit" disabled={ isUploading }>
                        { isUploading ? "Загружаем…" : "Загрузить" }
                    </button>
                </form>

                { notice && (
                    <p className={ `${ styles.notice } ${
                        notice.tone === "ok" ? styles.noticeOk : styles.noticeBad
                    }` }
                    >
                        { notice.text }
                    </p>
                ) }
            </section>

            { batches.length > 0 && (
                <section className={styles.card}>
                    <div className={styles.batchHead}>
                        <div className={styles.batchTabs}>
                            { batches.map((batch) => (
                                <button
                                    key={ batch.name }
                                    type="button"
                                    className={ `${ styles.batchTab } ${
                                        batch.name === selectedBatch ? styles.batchTabActive : ""
                                    }` }
                                    onClick={() => {
                                        onOpenLot(null);
                                        onSelectBatch(batch.name);
                                    }}
                                >
                                    <span className={styles.batchName}>{ batch.name }</span>

                                    <span className={styles.batchMeta}>
                                        { batch.lots } лотов
                                        { batch.dateFrom && batch.dateTo
                                            ? ` · ${ formatDate(batch.dateFrom) } – ${ formatDate(batch.dateTo) }`
                                            : "" }
                                    </span>
                                </button>
                            )) }
                        </div>

                        { selectedBatch !== "" && (
                            <div className={styles.actions}>
                                { missingCount > 0 ? (
                                    <button
                                        className={styles.primary}
                                        type="button"
                                        disabled={ isRunning }
                                        onClick={() => void handleCompute(true)}
                                    >
                                        { computedCount > 0 ? `Обработать оставшиеся (${ missingCount })` : "Обработать все" }
                                    </button>
                                ) : (
                                    <button
                                        className={styles.secondary}
                                        type="button"
                                        disabled={ isRunning || visibleLots.length === 0 }
                                        onClick={() => void handleCompute(false)}
                                    >
                                        Пересчитать все
                                    </button>
                                ) }

                                <a
                                    className={ `${ styles.primary } ${ isRunning || computedCount === 0 ? styles.disabled : "" }` }
                                    href={ batchExportUrl(selectedBatch) }
                                    download
                                >
                                    Скачать CSV
                                </a>

                                <button className={styles.danger} type="button" onClick={() => void handleDelete()}>
                                    Удалить
                                </button>
                            </div>
                        ) }
                    </div>

                    { isRunning && (
                        <div className={styles.progress}>
                            <div className={styles.progressText}>
                                Считаем рекомендации: { job.done ?? 0 } из { job.total || visibleLots.length } лотов
                            </div>

                            <div className={styles.progressBar}>
                                <div className={styles.progressFill} style={{ width: `${ jobProgress(job) }%` }} />
                            </div>
                        </div>
                    ) }

                    { job.status === "error" && (
                        <p className={ `${ styles.notice } ${ styles.noticeBad }` }>
                            Расчёт прервался: { job.message }
                        </p>
                    ) }

                    { openLot === null ? (
                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Дата</th>
                                        <th>Закупка</th>
                                        <th>НМЦК</th>
                                        <th>Площадка</th>
                                        <th>Лучшие поставщики</th>
                                        <th aria-label="Действия" />
                                    </tr>
                                </thead>

                                <tbody>
                                    { visibleLots.map((lot) => (
                                        <tr key={ lot.lotId }>
                                            <td className={styles.mono}>{ formatDate(lot.publishDate) }</td>

                                            <td>
                                                <div className={styles.subject}>{ lot.subject }</div>

                                                <div className={styles.lotMeta}>
                                                    <span className={styles.mono}>№ { lot.lotId }</span>
                                                    { lot.categories.map((code) => (
                                                        <span key={ code } className={styles.chip}>{ code }</span>
                                                    )) }
                                                    { lot.mspOnly && <span className={styles.chip}>только МСП</span> }
                                                </div>
                                            </td>

                                            <td className={styles.mono}>{ formatRub(lot.nmck) }</td>

                                            <td>{ PLATFORM_LABELS[lot.platform] }</td>

                                            <td>
                                                { lot.computed ? (
                                                    <ol className={styles.top}>
                                                        { lot.top.map((item) => (
                                                            <li key={ item.inn }>
                                                                <span className={styles.topName}>{ item.name }</span>
                                                                <span className={styles.topScore}>
                                                                    { item.scoreKind === "probability" ? `${ item.score }%` : item.score }
                                                                </span>
                                                            </li>
                                                        )) }
                                                    </ol>
                                                ) : (
                                                    <span className={styles.muted}>
                                                        { isRunning || computingIds.includes(lot.lotId)
                                                            ? "считаем…"
                                                            : "ещё не подобраны" }
                                                    </span>
                                                ) }
                                            </td>

                                            <td>
                                                { lot.computed ? (
                                                    <button
                                                        className={styles.secondary}
                                                        type="button"
                                                        onClick={() => onOpenLot(lot.lotId)}
                                                    >
                                                        Открыть
                                                    </button>
                                                ) : (
                                                    <button
                                                        className={styles.primary}
                                                        type="button"
                                                        disabled={ isRunning || computingIds.includes(lot.lotId) }
                                                        onClick={() => void handleComputeLot(lot.lotId)}
                                                    >
                                                        { computingIds.includes(lot.lotId) ? "Подбираем…" : "Подобрать" }
                                                    </button>
                                                ) }
                                            </td>
                                        </tr>
                                    )) }
                                </tbody>
                            </table>

                            { isLoadingLots && <p className={styles.muted}>Загружаем лоты…</p> }

                            { !isLoadingLots && visibleLots.length === 0 && (
                                <p className={styles.muted}>В пакете нет лотов</p>
                            ) }
                        </div>
                    ) : (
                        <div className={styles.detail}>
                            <button className={styles.back} type="button" onClick={() => onOpenLot(null)}>
                                ← Все лоты пакета
                            </button>

                            <div className={styles.detailHead}>
                                <div className={styles.subject}>{ openLot.subject }</div>

                                <div className={styles.lotMeta}>
                                    <span className={styles.mono}>№ { openLot.lotId }</span>
                                    <span>{ formatDate(openLot.publishDate) }</span>
                                    <span className={styles.mono}>{ formatRub(openLot.nmck) }</span>
                                    <span>{ PLATFORM_LABELS[openLot.platform] }</span>
                                    <span className={styles.mono}>Заказчик ИНН { openLot.customerInn }</span>
                                    { openLot.categories.map((code) => (
                                        <span key={ code } className={styles.chip}>{ code }</span>
                                    )) }
                                    { openLot.mspOnly && <span className={styles.chip}>только МСП</span> }
                                </div>
                            </div>
                        </div>
                    ) }
                </section>
            ) }

            { openLot !== null && (
                <VariantsWidget
                    key={ openLot.lotId }
                    lotId={ openLot.lotId }
                    shortListIds={ shortListIds }
                    onToggleShortList={(supplierId) => onToggleShortList(openLot, supplierId)}
                />
            ) }
        </div>
    );
}
