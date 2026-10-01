import {
    useEffect, useMemo, useState,
} from "react";

import * as matchService from "@/service/matchService";
import { ROLE_LABELS } from "@/service/matchService";
import type {
    SupplierRole, SupplierVariant,
} from "@/service/matchService";

import styles from "./VariantsWidget.module.scss";

/** Новизна поставщика: показать новых, существующих или всех. */
type NoveltyFilter = "all" | "new" | "existing";

const ROLE_ORDER: SupplierRole[] = [ "man", "dist", "sup" ];

const NOVELTY_OPTIONS: Array<{ value: NoveltyFilter; label: string }> = [
    {
        value: "new",
        label: "Новый",
    },
    {
        value: "existing",
        label: "Существующий",
    },
    {
        value: "all",
        label: "Все",
    },
];

/** Русская форма слова по числу: 1 участие, 2 участия, 5 участий. */
function plural(count: number, one: string, few: string, many: string): string {
    const mod10 = count % 10;
    const mod100 = count % 100;

    if (mod10 === 1 && mod100 !== 11) {
        return one;
    }

    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) {
        return few;
    }

    return many;
}

interface VariantCardProps {
    variant: SupplierVariant;
    inShortList: boolean;
    onToggleShortList: () => void;
}

function VariantCard({
    variant, inShortList, onToggleShortList,
}: VariantCardProps) {
    const {
        part, wins,
    } = variant;

    return (
        <article className={styles.card}>
            <div className={styles.cardMain}>
                <div className={styles.cardHead}>
                    <button className={styles.cardName} type="button">
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

                    <span className={styles.roleBadge}>
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

                <button className={styles.openCard} type="button">Карточка</button>
            </div>
        </article>
    );
}

export default function VariantsWidget() {
    const [ variants, setVariants ] = useState<SupplierVariant[]>([]);
    const [ isLoading, setIsLoading ] = useState(true);
    const [ hasError, setHasError ] = useState(false);
    const [ roles, setRoles ] = useState<SupplierRole[]>([]);
    const [ novelty, setNovelty ] = useState<NoveltyFilter>("all");
    const [ shortList, setShortList ] = useState<string[]>([]);

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

    const noveltyCounts = useMemo(() => {
        const counts: Record<NoveltyFilter, number> = {
            new: 0,
            existing: 0,
            all: variants.length,
        };

        variants.forEach((variant) => {
            counts[variant.isNew ? "new" : "existing"] += 1;
        });

        return counts;
    }, [ variants ]);

    const visibleVariants = useMemo(
        () => variants.filter((variant) => {
            if (roles.length > 0 && !roles.includes(variant.role)) {
                return false;
            }

            if (novelty !== "all") {
                const value: NoveltyFilter = variant.isNew ? "new" : "existing";

                if (value !== novelty) {
                    return false;
                }
            }

            return true;
        }),
        [ variants, roles, novelty ],
    );

    const hasActiveFilters = roles.length > 0 || novelty !== "all";

    function toggleRole(role: SupplierRole) {
        setRoles((prev) => (
            prev.includes(role)
                ? prev.filter((item) => item !== role)
                : [ ...prev, role ]
        ));
    }

    /** Радиокнопка: всегда выбрано ровно одно значение, повторный клик не снимает. */
    function toggleNovelty(value: NoveltyFilter) {
        setNovelty(value);
    }

    function resetFilters() {
        setRoles([]);
        setNovelty("all");
    }

    function toggleShortList(id: string) {
        setShortList((prev) => (
            prev.includes(id)
                ? prev.filter((item) => item !== id)
                : [ ...prev, id ]
        ));
    }

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

                <div className={styles.group} role="radiogroup" aria-label="Новизна">
                    <span className={styles.groupTitle}>Новизна</span>

                    { NOVELTY_OPTIONS.map((option) => {
                        const isOn = novelty === option.value;

                        return (
                            <button
                                key={ option.value }
                                className={styles.checkRow}
                                type="button"
                                role="radio"
                                aria-checked={ isOn }
                                onClick={() => toggleNovelty(option.value)}
                            >
                                <span
                                    className={ `${ styles.radio } ${
                                        isOn ? styles.radioOn : ""
                                    }` }
                                >
                                    { isOn && <span className={styles.radioInner} /> }
                                </span>

                                <span className={styles.checkLabel}>{ option.label }</span>

                                <span className={styles.checkCount}>
                                    { noveltyCounts[option.value] }
                                </span>
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
                                inShortList={ shortList.includes(variant.id) }
                                onToggleShortList={() => toggleShortList(variant.id)}
                            />
                        )) }
                    </div>
                ) }
            </div>
        </div>
    );
}
