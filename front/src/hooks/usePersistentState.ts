import {
    useEffect, useState,
} from "react";
import type {
    Dispatch, SetStateAction,
} from "react";

const STORAGE_PREFIX = "rlt.";

/**
 * Состояние, переживающее переключение экранов и перезагрузку страницы.
 * Значение лежит в localStorage, поэтому его можно восстановить при входе.
 * Панель разработчика может оставить в хранилище мусор — isValid отбрасывает
 * такое значение и возвращает initial.
 */
export default function usePersistentState<T>(
    key: string,
    initial: T,
    isValid?: (value: unknown) => boolean,
): [ T, Dispatch<SetStateAction<T>> ] {
    const storageKey = `${ STORAGE_PREFIX }${ key }`;

    const [ value, setValue ] = useState<T>(() => {
        try {
            const raw = window.localStorage.getItem(storageKey);

            if (raw === null) {
                return initial;
            }

            const parsed: unknown = JSON.parse(raw);

            if (isValid !== undefined && !isValid(parsed)) {
                return initial;
            }

            return parsed as T;
        } catch {
            // Приватный режим и битое значение одинаково опасны: молча берём начальное.
            return initial;
        }
    });

    useEffect(() => {
        try {
            window.localStorage.setItem(storageKey, JSON.stringify(value));
        } catch {
            // Переполненное хранилище не должно ронять подбор.
        }
    }, [ storageKey, value ]);

    return [ value, setValue ];
}