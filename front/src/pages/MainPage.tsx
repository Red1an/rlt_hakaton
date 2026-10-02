import { useState } from "react";

import usePersistentState from "@/hooks/usePersistentState";
import {
    INITIAL_MATCH_STATE, lotIdFromValues, normalizeMatchValues,
    shortListCommentKey, upsertLot,
} from "@/service";
import type {
    MatchFormState, MatchFormValues, ProcurementLot, ShortListEntry,
} from "@/service";
import MatchFormWidget from "@/widgets/MatchFormWidget/MatchFormWidget";
import ShortListWidget from "@/widgets/ShortListWidget/ShortListWidget";
import SidebarWidget from "@/widgets/SidebarWidget/SidebarWidget";
import type { SidebarScreen } from "@/widgets/SidebarWidget/SidebarWidget";
import VariantsWidget from "@/widgets/VariantsWidget/VariantsWidget";

import styles from "./MainPage.module.scss";

/** Комментарии к записям шорт-листа: «lotId:supplierId» → текст. */
type Comments = Record<string, string>;

function isArray(value: unknown): boolean {
    return Array.isArray(value);
}

function isPlainObject(value: unknown): boolean {
    return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Убирает комментарий записи, чтобы он не оставался после удаления поставщика. */
function omitComment(comments: Comments, lotId: string, supplierId: string): Comments {
    const key = shortListCommentKey(lotId, supplierId);
    const {
        [key]: _removed, ...rest
    } = comments;

    return rest;
}

/** Сохранённая форма: значения дополняем дефолтами новых полей, не сбрасывая ввод. */
function normalizeMatch(saved: MatchFormState): MatchFormState {
    return {
        ...INITIAL_MATCH_STATE,
        ...saved,
        values: normalizeMatchValues(saved?.values),
    };
}

/** Сохранённые лоты: то же для снимка параметров внутри лота. */
function normalizeLots(saved: ProcurementLot[]): ProcurementLot[] {
    return saved.map((lot) => ({
        ...lot,
        values: normalizeMatchValues(lot.values),
    }));
}

export default function MainPage() {
    const [ screen, setScreen ] = useState<SidebarScreen>( "match" );
    const [ match, setMatch ] = usePersistentState<MatchFormState>(
        "match", INITIAL_MATCH_STATE, undefined, normalizeMatch,
    );
    const [ hasSearched, setHasSearched ] = usePersistentState("searched", false);
    const [ lots, setLots ] = usePersistentState<ProcurementLot[]>(
        "lots", [], isArray, normalizeLots,
    );
    const [ activeLotId, setActiveLotId ] = usePersistentState("activeLot", "");
    const [ entries, setEntries ] = usePersistentState<ShortListEntry[]>("shortlist", [], isArray);
    const [ comments, setComments ] = usePersistentState<Comments>("comments", {}, isPlainObject);

    function handleNavigate(next: SidebarScreen) {
        // Выдачу не прячем: кнопка возврата из шорт-листа должна вернуть к тому же подбору.
        setScreen(next);
    }

    /** Переход на «Подбор» без параметров — на случай, пока лотов нет. */
    function handleBackToMatch() {
        setScreen("match");
    }

    /** Подбор заводит лот либо переиспользует существующий с теми же параметрами. */
    function handleSearched(values: MatchFormValues, requestId: string) {
        setLots((prev) => upsertLot(prev, values, requestId));
        setActiveLotId(lotIdFromValues(values));
        setHasSearched(true);
    }

    /** Возврат из шорт-листа в подбор с параметрами лота. */
    function handleOpenLot(lot: ProcurementLot) {
        setMatch((prev) => ({
            ...prev,
            values: lot.values,
            isCollapsed: false,
        }));
        setActiveLotId(lot.id);
        setHasSearched(true);
        setScreen("match");
    }

    function isInShortList(supplierId: string): boolean {
        return entries.some((entry) => (
            entry.lotId === activeLotId && entry.supplierId === supplierId
        ));
    }

    function removeFromShortList(lotId: string, supplierId: string) {
        setEntries((prev) => prev.filter((entry) => (
            entry.lotId !== lotId || entry.supplierId !== supplierId
        )));
        setComments((prev) => omitComment(prev, lotId, supplierId));
    }

    function toggleShortList(supplierId: string) {
        if (isInShortList(supplierId)) {
            removeFromShortList(activeLotId, supplierId);

            return;
        }

        setEntries((prev) => [
            ...prev,
            {
                lotId: activeLotId,
                supplierId,
            },
        ]);
    }

    function setComment(lotId: string, supplierId: string, text: string) {
        setComments((prev) => ({
            ...prev,
            [shortListCommentKey(lotId, supplierId)]: text,
        }));
    }

    /** Поставщики активного лота: их кнопки «В шорт-лист» уже нажаты. */
    const activeShortListIds = entries
        .filter((entry) => entry.lotId === activeLotId)
        .map((entry) => entry.supplierId);

    /** Выдача активного лота: по requestId бэкенд отдаёт именно его подбор. */
    const activeLot = lots.find((lot) => lot.id === activeLotId);

    return (
        <div className={styles.page}>
            <SidebarWidget
                activeScreen={ screen }
                onNavigate={ handleNavigate }
                shortListCount={ entries.length }
            />

            <main className={styles.content}>
                { screen === "match" ? (
                    <>
                        <MatchFormWidget
                            state={ match }
                            onChange={ setMatch }
                            onSearched={ handleSearched }
                        />

                        { hasSearched && (
                            <VariantsWidget
                                key={ activeLotId }
                                requestId={ activeLot?.requestId }
                                shortListIds={ activeShortListIds }
                                onToggleShortList={ toggleShortList }
                            />
                        ) }
                    </>
                ) : screen === "short" ? (
                    <ShortListWidget
                        lots={ lots }
                        entries={ entries }
                        comments={ comments }
                        onRemove={ removeFromShortList }
                        onComment={ setComment }
                        onOpenLot={ handleOpenLot }
                        onBackToMatch={ handleBackToMatch }
                    />
                ) : null }
            </main>
        </div>
    );
}