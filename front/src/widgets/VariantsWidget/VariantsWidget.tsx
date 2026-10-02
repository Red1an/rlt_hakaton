import {
    useEffect, useMemo, useState,
} from "react";

import * as matchService from "@/service/matchService";
import { ROLE_LABELS } from "@/service/matchService";
import { plural } from "@/service/format";
import type {
    SupplierRole, SupplierVariant,
} from "@/service/matchService";

import styles from "./VariantsWidget.module.scss";

const ROLE_ORDER: SupplierRole[] = [ "man", "dist", "sup" ];

interface VariantCardProps {
    variant: SupplierVariant;
    inShortList: boolean;
    onToggleShortList: () => void;
    onOpenCard: () => void;
}

function VariantCard({
    variant, inShortList, onToggleShortList, onOpenCard,
}: VariantCardProps) {
    const {
        part, wins,
    } = variant;

    return (
        <article className={styles.card}>
            <div className={styles.cardMain}>
                <div className={styles.cardHead}>
                    <button className={styles.cardName} type="button" onClick={ onOpenCard }>
                        { variant.name }
                    </button>

                    { variant.flags.map((flag) => (
                        <span key={ flag } className={styles.flag}>{ flag }</span>
                    )) }

                    { variant.isNew && <span className={styles.flagNew}>Новый</span> }
                </div>

                <div className={styles.cardMeta}>
                    <span className={styles.inn}>ИНН { variant.inn }</span>

                    <span className={styles.sep}>·</span>

                    <span className={styles.roleBadge} title={ variant.roleReason || undefined }>
                        <span
                            className={ `${ styles.roleDot } ${ styles[`roleDot_${ variant.role }`] }` }
                        />
                        { ROLE_LABELS[variant.role] }
                    </span>
                </div>

                <div className={styles.cardStats}>
                    <span>
                        <b>{ part }</b>
                        { " " }
                        { plural(part, "участие", "участия", "участий") }
                        { " / " }
                        <b>{ wins }</b>
                        { " " }
                        { plural(wins, "победа", "победы", "побед") }
                        { " в похожих лотах" }
                    </span>
                </div>

                <div className={styles.why}>
                    <span className={styles.whyTitle}>Почему рекомендуем</span>

                    <div className={styles.whyList}>
                        { variant.why.map(({
                            icon, text,
                        }) => (
                            <span key={ `${ icon }-${ text }` } className={styles.whyItem}>
                                <span className={styles.whyIcon}>{ icon }</span>
                                { text }
                            </span>
                        )) }
                    </div>
                </div>
            </div>

            <div className={styles.cardSide}>
                <span className={styles.scoreLabel}>Релевантность</span>

                <div className={styles.scoreValue}>
                    <span className={styles.scoreNumber}>{ variant.score }</span>
                    <span className={styles.scoreMax}>/ 100</span>
                </div>

                <div className={styles.scoreBar}>
                    <div
                        className={styles.scoreBarFill}
                        style={{ width: `${ variant.score }%` }}
                    />
                </div>

                <div className={styles.sideSpacer} />

                <button
                    className={ `${ styles.shortList } ${
                        inShortList ? styles.shortListOn : ""
                    }` }
                    type="button"
                    onClick={ onToggleShortList }
                >
                    { inShortList ? "✓ В шорт-листе" : "В шорт-лист" }
                </button>

                <button className={styles.openCard} type="button" onClick={ onOpenCard }>
                    Карточка
                </button>
            </div>
        </article>
    );
}

interface VariantDrawerProps {
    variant: SupplierVariant;
    inShortList: boolean;
    onToggleShortList: () => void;
    onClose: () => void;
}

/** Выезжающая карточка: шапка, реквизиты и история участия без даты. */
function VariantDrawer({
    variant, inShortList, onToggleShortList, onClose,
}: VariantDrawerProps) {
    useEffect(() => {
        function handleKeyDown(event: KeyboardEvent) {
            if (event.key === "Escape") {
                onClose();
            }
        }

        document.addEventListener("keydown", handleKeyDown);

        return () => {
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, [ onClose ]);

    return (
        <>
            <div className={styles.overlay} onClick={ onClose } />

            <div
                className={styles.drawer}
                role="dialog"
                aria-modal="true"
                aria-label={ variant.name }
            >
                <div className={styles.drawerHead}>
                    <div className={styles.drawerIdentity}>
                        <div className={styles.drawerNameRow}>
                            <span className={styles.drawerName}>{ variant.name }</span>

                            { variant.flags.map((flag) => (
                                <span key={ flag } className={styles.flag}>{ flag }</span>
                            )) }

                            { variant.isNew && <span className={styles.flagNew}>Новый</span> }
                        </div>

                        <div className={styles.drawerMeta}>
                            <span className={styles.roleBadge} title={ variant.roleReason || undefined }>
                                <span
                                    className={ `${ styles.roleDot } ${
                                        styles[`roleDot_${ variant.role }`]
                                    }` }
                                />
                                { ROLE_LABELS[variant.role] }
                            </span>

                            <a
                                className={styles.drawerSite}
                                href={ `https://${ variant.site }` }
                                target="_blank"
                                rel="noreferrer"
                            >
                                { variant.site }
                            </a>
                        </div>
                    </div>

                    <div className={styles.drawerActions}>
                        <button
                            className={ `${ styles.shortList } ${
                                inShortList ? styles.shortListOn : ""
                            }` }
                            type="button"
                            onClick={ onToggleShortList }
                        >
                            { inShortList ? "✓ В шорт-листе" : "В шорт-лист" }
                        </button>

                        <button
                            className={styles.close}
                            type="button"
                            aria-label="Закрыть"
                            onClick={ onClose }
                        >
                            ×
                        </button>
                    </div>
                </div>

                <div className={styles.drawerBody}>
                    <div className={styles.panel}>
                        <span className={styles.panelTitle}>Реквизиты</span>

                        <div className={styles.reqGrid}>
                            { variant.requisites.map((field) => (
                                <div key={ field.label } className={styles.reqRow}>
                                    <span className={styles.reqLabel}>{ field.label }</span>

                                    <span
                                        className={ `${ styles.reqValue } ${
                                            field.mono ? styles.reqMono : ""
                                        }` }
                                    >
                                        { field.value }
                                    </span>
                                </div>
                            )) }
                        </div>
                    </div>

                    <div className={styles.panel}>
                        <span className={styles.panelTitle}>История участия</span>

                        { variant.history.length === 0 ? (
                            <p className={styles.histEmpty}>Нет записей в истории закупок.</p>
                        ) : (
                            <table className={styles.histTable}>
                                <thead>
                                    <tr>
                                        <th className={styles.histTh}>Предмет лота</th>

                                        <th className={ `${ styles.histTh } ${ styles.histThNum }` }>
                                            НМЦК, ₽
                                        </th>

                                        <th className={styles.histTh}>Заказчик</th>

                                        <th className={styles.histTh}>Результат</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    { variant.history.map((row) => (
                                        <tr
                                            key={ `${ row.subject }-${ row.customer }` }
                                            className={styles.histRow}
                                        >
                                            <td className={styles.histTd}>{ row.subject }</td>

                                            <td className={ `${ styles.histTd } ${ styles.histNum }` }>
                                                { row.nmck }
                                            </td>

                                            <td className={ `${ styles.histTd } ${ styles.histCustomer }` }>
                                                { row.customer }
                                            </td>

                                            <td className={styles.histTd}>
                                                <span
                                                    className={ `${ styles.histResult } ${
                                                        row.won ? styles.histWin : styles.histLose
                                                    }` }
                                                >
                                                    { row.won ? "Победа" : "Участие" }
                                                </span>
                                            </td>
                                        </tr>
                                    )) }
                                </tbody>
                            </table>
                        ) }
                    </div>
                </div>
            </div>
        </>
    );
}

interface VariantsWidgetProps {
    /** Идентификатор выдачи активного лота: без него сервер отдаёт последний поиск. */
    requestId?: string;
    lotId?: number;
    /** Список id поставщиков, которые уже в шорт-листе активного лота. */
    shortListIds: string[];
    onToggleShortList: (id: string) => void;
}

export default function VariantsWidget({
    requestId, lotId, shortListIds, onToggleShortList,
}: VariantsWidgetProps) {
    const [ variants, setVariants ] = useState<SupplierVariant[]>([]);
    const [ isLoading, setIsLoading ] = useState(true);
    const [ hasError, setHasError ] = useState(false);
    const [ roles, setRoles ] = useState<SupplierRole[]>([]);
    const [ openCardId, setOpenCardId ] = useState<string | null>(null);

    useEffect(() => {
        let isAlive = true;

        const request = lotId === undefined
            ? matchService.fetchVariants(requestId)
            : matchService.fetchLotVariants(lotId);

        request
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
    }, [ requestId, lotId ]);

    /** Счётчики считаем по полному списку, а не по уже отфильтрованному. */
    const roleCounts = useMemo(() => {
        const counts: Record<SupplierRole, number> = {
            man: 0,
            dist: 0,
            sup: 0,
        };

        variants.forEach((variant) => {
            counts[variant.role] += 1;
        });

        return counts;
    }, [ variants ]);

    const visibleVariants = useMemo(
        () => variants.filter((variant) => (
            roles.length === 0 || roles.includes(variant.role)
        )),
        [ variants, roles ],
    );

    const hasActiveFilters = roles.length > 0;

    function toggleRole(role: SupplierRole) {
        setRoles((prev) => (
            prev.includes(role)
                ? prev.filter((item) => item !== role)
                : [ ...prev, role ]
        ));
    }

    function resetFilters() {
        setRoles([]);
    }

    const openCard = variants.find((variant) => variant.id === openCardId) ?? null;

    return (
        <div className={styles.layout}>
            <aside className={styles.filters}>
                <div className={styles.filtersHead}>
                    <span className={styles.filtersTitle}>Фильтры</span>

                    { hasActiveFilters && (
                        <button className={styles.reset} type="button" onClick={ resetFilters }>
                            Сбросить
                        </button>
                    ) }
                </div>

                <div className={styles.group}>
                    <span className={styles.groupTitle}>Роль</span>

                    { ROLE_ORDER.map((role) => {
                        const isOn = roles.includes(role);

                        return (
                            <button
                                key={ role }
                                className={styles.checkRow}
                                type="button"
                                role="checkbox"
                                aria-checked={ isOn }
                                onClick={() => toggleRole(role)}
                            >
                                <span
                                    className={ `${ styles.checkBox } ${
                                        isOn ? styles.checkBoxOn : ""
                                    }` }
                                >
                                    { isOn ? "✓" : "" }
                                </span>

                                <span
                                    className={ `${ styles.roleDot } ${
                                        styles[`roleDot_${ role }`]
                                    }` }
                                />

                                <span className={styles.checkLabel}>{ ROLE_LABELS[role] }</span>

                                <span className={styles.checkCount}>{ roleCounts[role] }</span>
                            </button>
                        );
                    }) }
                </div>
            </aside>

            <div className={styles.results}>
                { isLoading && <p className={styles.state}>Загружаем варианты…</p> }

                { !isLoading && hasError && (
                    <p className={styles.state}>Не удалось загрузить варианты. Попробуйте ещё раз.</p>
                ) }

                { !isLoading && !hasError && visibleVariants.length === 0 && (
                    <div className={styles.empty}>
                        <span className={styles.emptyTitle}>Под эти фильтры никто не подходит</span>
                        <span>Снимите часть фильтров.</span>

                        <button className={styles.emptyReset} type="button" onClick={ resetFilters }>
                            Сбросить фильтры
                        </button>
                    </div>
                ) }

                { !isLoading && !hasError && visibleVariants.length > 0 && (
                    <div className={styles.cards}>
                        { visibleVariants.map((variant) => (
                            <VariantCard
                                key={ variant.id }
                                variant={ variant }
                                inShortList={ shortListIds.includes(variant.id) }
                                onToggleShortList={() => onToggleShortList(variant.id)}
                                onOpenCard={() => setOpenCardId(variant.id)}
                            />
                        )) }
                    </div>
                ) }
            </div>

            { openCard && (
                <VariantDrawer
                    variant={ openCard }
                    inShortList={ shortListIds.includes(openCard.id) }
                    onToggleShortList={() => onToggleShortList(openCard.id)}
                    onClose={() => setOpenCardId(null)}
                />
            ) }
        </div>
    );
}
