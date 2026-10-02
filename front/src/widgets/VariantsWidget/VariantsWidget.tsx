import {
    useEffect, useMemo, useState,
} from "react";

import * as matchService from "@/service/matchService";
import { ROLE_LABELS } from "@/service/matchService";
import { plural } from "@/service/format";
import type {
    SupplierRole, SupplierVariant,
} from "@/service/matchService";
import {
    ActivityPanel, OkpdPanel,
} from "@/widgets/SupplierGraphsWidget/SupplierGraphsWidget";

import styles from "./VariantsWidget.module.scss";

const ROLE_ORDER: SupplierRole[] = [ "man", "dist", "sup" ];

type Section = "history" | "new";

const SECTION_LABELS: Record<Section, string> = {
    history: "По истории закупок",
    new: "Новые, без истории",
};

const SECTION_EMPTY: Record<Section, string> = {
    history: "Поставщиков с историей закупок в этой категории не нашлось",
    new: "Новых поставщиков по этой категории пока нет: их можно найти в разделе «Новые поставщики»",
};

const SUITABILITY_HINT = "Релевантность 0–100 — шанс, что компания подаст заявку и выиграет: "
    + "вероятность участия по модели, умноженная на долю побед в конкурентных закупках";

const NEW_HINT = "Нет истории госзакупок. Совпадение с профилем: ОКПД2 и ОКВЭД с категорией, роль, "
    + "статус и возраст компании, филиалы, регион, сайт и контакты";

const PROFILE_LEVELS = [
    {
        min: 78,
        label: "Сильное",
        fill: 100,
    },
    {
        min: 68,
        label: "Среднее",
        fill: 66,
    },
    {
        min: 0,
        label: "Слабое",
        fill: 33,
    },
];

function profileLevel(score: number) {
    return PROFILE_LEVELS.find((level) => score >= level.min) ?? PROFILE_LEVELS[PROFILE_LEVELS.length - 1];
}

function suitabilityHint(lift: number | null, participation: number | null): string {
    const parts = [ SUITABILITY_HINT ];

    if (participation !== null) {
        parts.push(`Вероятность подать заявку: ${ participation }%`);
    }

    if (lift !== null && lift >= 1.05) {
        parts.push(`Шанс победы в ${ lift.toLocaleString("ru-RU") } раза выше среднего кандидата`);
    }

    return parts.join(". ");
}

function ScoreBlock({ variant }: { variant: SupplierVariant }) {
    if (variant.scoreKind === "new") {
        const level = profileLevel(variant.score);

        return (
            <>
                <span className={styles.scoreLabel} title={ NEW_HINT }>Подходимость по профилю</span>

                <div className={styles.scoreValue} title={ NEW_HINT }>
                    <span className={styles.scoreLevel}>{ level.label }</span>
                </div>

                <div className={styles.scoreBar}>
                    <div
                        className={styles.scoreBarFill}
                        style={{ width: `${ level.fill }%` }}
                    />
                </div>
            </>
        );
    }

    const hint = variant.scoreKind === "suitability"
        ? suitabilityHint(variant.lift, variant.participation)
        : undefined;

    return (
        <>
            <span className={styles.scoreLabel} title={ hint }>Релевантность</span>

            <div className={styles.scoreValue} title={ hint }>
                <span className={styles.scoreNumber}>{ variant.score }</span>
                <span className={styles.scoreMax}>/ 100</span>
            </div>

            <div className={styles.scoreBar}>
                <div
                    className={styles.scoreBarFill}
                    style={{ width: `${ variant.score }%` }}
                />
            </div>
        </>
    );
}

function VerificationBadge({ verified }: { verified: SupplierVariant["verified"] }) {
    if (verified?.by === "dadata") {
        const date = verified.at ? new Date(verified.at).toLocaleDateString("ru-RU") : "";

        return (
            <span
                className={ `${ styles.verified } ${ styles.verifiedOk }` }
                title="Статус, ОКВЭД, адрес и регион сверены с ФНС через DaData"
            >
                ✓ Сверено с ЕГРЮЛ{ date && ` · ${ date }` }
            </span>
        );
    }

    if (verified?.by === "egrul") {
        return (
            <span className={styles.verified} title="Название получено из открытых данных ФНС">
                Название из ЕГРЮЛ
            </span>
        );
    }

    return (
        <span className={styles.verified} title="Сведения только из истории закупок, реквизиты не проверялись">
            Данные из закупок
        </span>
    );
}

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

                    <span className={styles.sep}>·</span>

                    <VerificationBadge verified={ variant.verified } />
                </div>

                { !variant.isNew && (
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
                ) }

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
                <ScoreBlock variant={ variant } />

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

                            <VerificationBadge verified={ variant.verified } />

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

                    {/* У новых поставщиков закупочной истории нет — графики покажут пустое состояние. */}
                    <ActivityPanel inn={ variant.isNew ? null : variant.inn } />

                    <OkpdPanel inn={ variant.isNew ? null : variant.inn } />

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
    const [ chosenSection, setChosenSection ] = useState<Section | null>(null);

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

    const sectionVariants = useMemo(() => ({
        history: variants.filter((variant) => !variant.isNew),
        new: variants.filter((variant) => variant.isNew),
    }), [ variants ]);

    const section: Section = chosenSection
        ?? (sectionVariants.history.length === 0 && sectionVariants.new.length > 0 ? "new" : "history");
    const currentVariants = sectionVariants[section];

    /** Счётчики считаем по полному списку раздела, а не по уже отфильтрованному. */
    const roleCounts = useMemo(() => {
        const counts: Record<SupplierRole, number> = {
            man: 0,
            dist: 0,
            sup: 0,
        };

        currentVariants.forEach((variant) => {
            counts[variant.role] += 1;
        });

        return counts;
    }, [ currentVariants ]);

    const visibleVariants = useMemo(
        () => currentVariants.filter((variant) => (
            roles.length === 0 || roles.includes(variant.role)
        )),
        [ currentVariants, roles ],
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

                { !isLoading && !hasError && (
                    <div className={styles.sections} role="tablist">
                        { (Object.keys(SECTION_LABELS) as Section[]).map((key) => (
                            <button
                                key={ key }
                                className={ `${ styles.section } ${ key === section ? styles.sectionActive : "" }` }
                                type="button"
                                role="tab"
                                aria-selected={ key === section }
                                onClick={() => setChosenSection(key)}
                            >
                                { SECTION_LABELS[key] }
                                <span className={styles.sectionCount}>{ sectionVariants[key].length }</span>
                            </button>
                        )) }
                    </div>
                ) }

                { !isLoading && !hasError && currentVariants.length === 0 && (
                    <p className={styles.state}>{ SECTION_EMPTY[section] }</p>
                ) }

                { !isLoading && !hasError && currentVariants.length > 0 && visibleVariants.length === 0 && (
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
                    key={ openCard.id }
                    variant={ openCard }
                    inShortList={ shortListIds.includes(openCard.id) }
                    onToggleShortList={() => onToggleShortList(openCard.id)}
                    onClose={() => setOpenCardId(null)}
                />
            ) }
        </div>
    );
}
