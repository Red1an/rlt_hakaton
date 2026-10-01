import type {
    MatchFormValues, ProcurementLot,
} from "./matchService";

/** Сколько символов описания влезает в шапку лота. */
const LOT_TITLE_LIMIT = 60;

/** С какого номера выдаются лоты: Л-2026-0418, Л-2026-0419 и так далее. */
const LOT_NUM_START = 418;

/** Короткий стабильный ключ из строки: djb2 в системе счисления по основанию 36. */
function hash(value: string): string {
    let result = 5381;

    for (let index = 0; index < value.length; index += 1) {
        result = ((( result << 5 ) + result) + value.charCodeAt(index)) >>> 0;
    }

    return result.toString(36);
}

/**
 * Ключ лота из параметров подбора: одинаковые параметры всегда попадают
 * в один лот, поэтому повторный подбор не плодит дубли.
 */
export function lotIdFromValues(values: MatchFormValues): string {
    const signature = [
        values.category?.code ?? "",
        values.nmck.replace(/\s/g, ""),
        values.platform,
        values.mspOnly ? "мсп" : "",
    ].join("|");

    return `lot-${ hash(signature) }`;
}

/** Ключ комментария к записи шорт-листа. */
export function shortListCommentKey(lotId: string, supplierId: string): string {
    return `${ lotId }:${ supplierId }`;
}

function lotTitle(values: MatchFormValues): string {
    const title = values.category?.name ?? "Без категории";

    return title.length > LOT_TITLE_LIMIT ? `${ title.slice(0, LOT_TITLE_LIMIT) }…` : title;
}

/**
 * Создаёт лот под параметры подбора либо обновляет снимок параметров
 * уже существующего. Даты у лота нет — она не показывается в шорт-листе.
 */
export function upsertLot(lots: ProcurementLot[], values: MatchFormValues): ProcurementLot[] {
    const id = lotIdFromValues(values);
    const existing = lots.find((lot) => lot.id === id);

    if (existing !== undefined) {
        return lots.map((lot) => (
            lot.id === id
                ? {
                    ...lot,
                    title: lotTitle(values),
                    nmck: values.nmck,
                    values,
                }
                : lot
        ));
    }

    return [
        ...lots,
        {
            id,
            num: `Л-2026-${ String(LOT_NUM_START + lots.length).padStart(4, "0") }`,
            title: lotTitle(values),
            nmck: values.nmck,
            values,
        },
    ];
}