import {
    useEffect, useMemo, useState,
} from "react";

import * as matchService from "@/service/matchService";
import { ROLE_LABELS } from "@/service/matchService";
import type {
    ProcurementLot, ShortListEntry, SupplierVariant,
} from "@/service/matchService";
import { shortListCommentKey } from "@/service/lots";
import { plural } from "@/service/format";

import styles from "./ShortListWidget.module.scss";

interface ShortListWidgetProps {
    lots: ProcurementLot[];
    entries: ShortListEntry[];
    /** Комментарии к записям: «lotId:supplierId» → текст. */
    comments: Record<string, string>;
    onRemove: (lotId: string, supplierId: string) => void;
    onClear: () => void;
    onComment: (lotId: string, supplierId: string, text: string) => void;
    onOpenLot: (lot: ProcurementLot) => void;
    /** Обычный переход на «Подбор», когда лотов ещё нет. */
    onBackToMatch: () => void;
}

interface LotRow {
    variant: SupplierVariant;
    comment: string;
}

/**
 * Шорт-лист, собранный по лотам. Даты, сегменты, экспорт и копирование
 * в разметке не показываем — только заголовок, таблица и возврат в подбор.
 */
export default function ShortListWidget({
    lots, entries, comments, onRemove, onClear, onComment, onOpenLot, onBackToMatch,
}: ShortListWidgetProps) {
    const [ variants, setVariants ] = useState<SupplierVariant[]>([]);
    const [ isLoading, setIsLoading ] = useState(true);
    const [ hasError, setHasError ] = useState(false);

    useEffect(() => {
        let isAlive = true;

        matchService.fetchVariants()
            .then((items) => {
                if (!isAlive) {
                    return;
                }

                setVariants(items);
                setHasError(false);
            })
            .catch(() => {
                if (isAlive) {
                    setHasError(true);
                }
            })
            .finally(() => {
                if (isAlive) {
                    setIsLoading(false);
                }
            });

        return () => {
            isAlive = false;
        };
    }, []);

    const byId = useMemo(
        () => new Map(variants.map((variant) => [ variant.id, variant ])),
        [ variants ],
    );

    /** Записи лота в том порядке, в котором их добавляли. */
    function rowsOfLot(lot: ProcurementLot): LotRow[] {
        return entries
            .filter((entry) => entry.lotId === lot.id)
            .map((entry) => {
                const variant = byId.get(entry.supplierId);

                if (variant === undefined) {
                    return null;
                }

                return {
                    variant,
                    comment: comments[
                        shortListCommentKey(entry.lotId, entry.supplierId)
                    ] ?? "",
                };
            })
            .filter((row): row is LotRow => row !== null);
    }

    const hasAnyEntries = entries.length > 0;

    function handleClear() {
        const count = `${ entries.length } ${ plural(entries.length, "поставщика", "поставщиков", "поставщиков") }`;

        if (window.confirm(`Убрать из шорт-листа ${ count } вместе с комментариями?`)) {
            onClear();
        }
    }

    return (
        <div className={styles.screen}>
            <div className={styles.head}>
                <h1 className={styles.title}>Шорт-лист</h1>

                { hasAnyEntries && (
                    <button className={styles.clearBtn} type="button" onClick={ handleClear }>
                        Очистить шорт-лист
                    </button>
                ) }
            </div>

            { isLoading && <p className={styles.state}>Загружаем шорт-лист…</p> }

            { !isLoading && hasError && (
                <p className={styles.state}>
                    Не удалось загрузить поставщиков. Попробуйте ещё раз.
                </p>
            ) }

            { !isLoading && !hasError && lots.length === 0 && (
                <div className={styles.empty}>
                    <span className={styles.emptyTitle}>Лотов пока нет</span>
                    <span>Сделайте подбор — и отобранные поставщики соберутся здесь по лотам.</span>

                    <button
                        className={styles.backBtn}
                        type="button"
                        onClick={ onBackToMatch }
                    >
                        Подобрать поставщиков
                    </button>
                </div>
            ) }

            { !isLoading
                && !hasError
                && lots.map((lot) => {
                    const rows = rowsOfLot(lot);
                    const isEmpty = rows.length === 0;

                    return (
                        <section key={ lot.id } className={styles.lot}>
                            <div className={styles.lotHead}>
                                <span className={styles.lotTitle}>{ lot.title }</span>

                                <span className={styles.lotNum}>{ lot.num }</span>

                                { lot.nmck !== "" && (
                                    <span className={styles.lotNmck}>
                                        НМЦК
                                        <span className={styles.lotNmckValue}>{ lot.nmck }</span>
                                        ₽
                                    </span>
                                ) }

                                <span className={styles.lotSpacer} />

                                <span className={styles.lotCount}>
                                    { rows.length }
                                    { " " }
                                    { plural(rows.length, "поставщик", "поставщика", "поставщиков") }
                                </span>

                                <button
                                    className={styles.lotBack}
                                    type="button"
                                    onClick={() => onOpenLot(lot)}
                                >
                                    { isEmpty ? "Подобрать поставщиков" : "Вернуться в подбор" }
                                </button>
                            </div>

                            { isEmpty ? (
                                <p className={styles.lotEmpty}>Пока пусто.</p>
                            ) : (
                                <table className={styles.table}>
                                    <thead>
                                        <tr>
                                            <th className={styles.th}>Компания</th>

                                            <th className={styles.th}>ИНН</th>

                                            <th className={styles.th}>Роль</th>

                                            <th className={styles.th}>Контакты</th>

                                            <th className={ `${ styles.th } ${ styles.thComment }` }>
                                                Комментарий
                                            </th>

                                            <th className={styles.thAction}>
                                                <span className={styles.srOnly}>Действия</span>
                                            </th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        { rows.map(({
                                            variant, comment,
                                        }) => (
                                            <tr key={ variant.id } className={styles.row}>
                                                <td className={styles.tdName}>
                                                    <span className={styles.name}>{ variant.name }</span>

                                                    { variant.flags.map((flag) => (
                                                        <span key={ flag } className={styles.flag}>
                                                            { flag }
                                                        </span>
                                                    )) }

                                                    { variant.isNew && (
                                                        <span className={styles.flagNew}>Новый</span>
                                                    ) }
                                                </td>

                                                <td className={styles.tdMono}>{ variant.inn }</td>

                                                <td className={styles.tdRole}>
                                                    <span
                                                        className={ `${ styles.roleDot } ${
                                                            styles[`roleDot_${ variant.role }`]
                                                        }` }
                                                    />

                                                    { ROLE_LABELS[variant.role] }
                                                </td>

                                                <td className={styles.tdContacts}>
                                                    <span className={styles.phone}>{ variant.phone }</span>

                                                    <span className={styles.email}>{ variant.email }</span>
                                                </td>

                                                <td className={styles.tdComment}>
                                                    <input
                                                        className={styles.commentInput}
                                                        type="text"
                                                        value={ comment }
                                                        placeholder="Добавить комментарий"
                                                        onChange={(event) => onComment(
                                                            lot.id,
                                                            variant.id,
                                                            event.target.value,
                                                        )}
                                                    />
                                                </td>

                                                <td className={styles.tdAction}>
                                                    <button
                                                        className={styles.remove}
                                                        type="button"
                                                        title="Убрать"
                                                        aria-label={ `Убрать ${ variant.name } из шорт-листа` }
                                                        onClick={() => onRemove(lot.id, variant.id)}
                                                    >
                                                        ×
                                                    </button>
                                                </td>
                                            </tr>
                                        )) }
                                    </tbody>
                                </table>
                            ) }
                        </section>
                    );
                }) }

            { !isLoading && !hasError && lots.length > 0 && !hasAnyEntries && (
                <p className={styles.hint}>
                    Ни один поставщик пока не отобран — жмите «В шорт-лист» в подборе.
                </p>
            ) }
        </div>
    );
}