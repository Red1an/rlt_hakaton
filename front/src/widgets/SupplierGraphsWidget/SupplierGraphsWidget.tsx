import {
    useEffect, useState,
} from "react";

import * as graphsService from "@/service/graphsService";
import type {
    ActivityCard, OkpdCard,
} from "@/service/graphsService";

import styles from "./SupplierGraphsWidget.module.scss";

const NO_DATA_ACTIVITY = "Компания не участвовала в закупках за последние два года.";
const NO_DATA_OKPD = "Компания не участвовала ни в одной категории ОКПД2.";

/**
 * Загрузка одной карточки графиков. У каждой панели своё состояние, чтобы
 * падение одного графика не убирало второй, и свой кеш в сервисном слое,
 * чтобы возвращение в ту же карточку не ходило в сеть.
 *
 * Компонент пересоздаётся при смене поставщика (на нём стоит `key`), поэтому
 * состояние сбрасывать не нужно, а `isLoading` выводится из наличия данных,
 * а не хранится.
 */
function useGraph<T>(inn: string | null, load: (inn: string) => Promise<T>) {
    const [ data, setData ] = useState<T | null>(null);
    const [ hasError, setHasError ] = useState(false);

    useEffect(() => {
        // У новых поставщиков закупочной истории нет — ходить за ней незачем.
        if (inn === null) {
            return;
        }

        let isAlive = true;

        load(inn)
            .then((result) => {
                if (isAlive) {
                    setData(result);
                    setHasError(false);
                }
            })
            .catch(() => {
                if (isAlive) {
                    setHasError(true);
                }
            });

        return () => {
            isAlive = false;
        };
    }, [ inn, load ]);

    const isLoading = inn !== null && !hasError && data === null;

    return {
        data,
        isLoading,
        hasError,
    };
}

interface ActivityPanelProps {
    /** ИНН поставщика; `null` — компании нет в истории закупок. */
    inn: string | null;
}

/** Столбцы участия и побед по месяцам за последние два года. */
export function ActivityPanel({ inn }: ActivityPanelProps) {
    const {
        data, isLoading, hasError,
    } = useGraph<ActivityCard>(inn, graphsService.fetchActivityCard);

    return (
        <div className={styles.panel}>
            <div className={styles.panelHead}>
                <span className={styles.panelTitle}>Активность за 2 года</span>

                { data?.hasData === true && (
                    <>
                        <span className={styles.legend}>
                            <span className={ `${ styles.swatch } ${ styles.swatchPart }` } />
                            Участия
                            <b className={styles.legendValue}>{ data.engages }</b>
                        </span>

                        <span className={styles.legend}>
                            <span className={ `${ styles.swatch } ${ styles.swatchWin }` } />
                            Победы
                            <b className={styles.legendValue}>{ data.wins }</b>
                        </span>
                    </>
                ) }
            </div>

            { isLoading && <p className={styles.hint}>Считаем активность…</p> }

            { !isLoading && hasError && (
                <p className={styles.hint}>Не удалось загрузить график активности.</p>
            ) }

            { !isLoading && !hasError && data?.hasData !== true && (
                <p className={styles.chartEmpty}>{ NO_DATA_ACTIVITY }</p>
            ) }

            { !isLoading && !hasError && data?.hasData === true && (
                <div className={styles.chart}>
                    <div className={styles.plot}>
                        { data.months.map((month) => (
                            <div key={ month.key } className={styles.column} title={ month.title }>
                                <div
                                    className={styles.barPart}
                                    style={{ height: month.engagesHeight }}
                                />
                                <div
                                    className={styles.barWin}
                                    style={{ height: month.winsHeight }}
                                />
                            </div>
                        )) }
                    </div>

                    <div className={styles.axis}>
                        { data.months.map((month) => (
                            <span key={ month.key } className={styles.axisLabel}>
                                { month.label }
                            </span>
                        )) }
                    </div>
                </div>
            ) }
        </div>
    );
}

interface OkpdPanelProps {
    inn: string | null;
}

/** Полосы долей по категориям ОКПД2, в которых поставщик участвовал. */
export function OkpdPanel({ inn }: OkpdPanelProps) {
    const {
        data, isLoading, hasError,
    } = useGraph<OkpdCard>(inn, graphsService.fetchOkpdCard);

    return (
        <div className={styles.panel}>
            <span className={styles.panelTitle}>Топ категорий ОКПД2</span>

            { isLoading && <p className={styles.hint}>Считаем категории…</p> }

            { !isLoading && hasError && (
                <p className={styles.hint}>Не удалось загрузить категории.</p>
            ) }

            { !isLoading && !hasError && data?.hasData !== true && (
                <p className={styles.chartEmpty}>{ NO_DATA_OKPD }</p>
            ) }

            { !isLoading && !hasError && data?.hasData === true && (
                <div className={styles.rows}>
                    { data.items.map((item) => (
                        <div key={ item.key } className={styles.row} title={ item.title }>
                            <div className={styles.rowHead}>
                                <span className={styles.rowCode}>{ item.code }</span>
                                <span className={styles.rowName}>{ item.name }</span>
                                <span className={styles.rowPercent}>{ item.percent }%</span>
                            </div>

                            <div className={styles.track}>
                                <div className={styles.fill} style={{ width: item.width }} />
                            </div>
                        </div>
                    )) }
                </div>
            ) }
        </div>
    );
}