import * as batchApi from "../api/batches";
import type {
    BatchDto, BatchJobDto, BatchLotDto,
} from "../api/types";

export type { BatchJobStatus } from "../api/types";

export type BatchJob = BatchJobDto;
export type Batch = BatchDto;
export type BatchLot = BatchLotDto;

export const BATCH_EXPORT_TOP = 10;

export const fetchBatches = batchApi.fetchBatches;
export const recomputeBatch = batchApi.recomputeBatch;
export const fetchBatchStatus = batchApi.fetchBatchStatus;
export const deleteBatch = batchApi.deleteBatch;

export async function uploadBatch(files: File[], name: string): Promise<{ name: string; job: BatchJob }> {
    return batchApi.uploadBatch(files, name.trim());
}

export async function fetchBatchLots(name: string): Promise<{ job: BatchJob; lots: BatchLot[] }> {
    const {
        job, lots,
    } = await batchApi.fetchBatchLots(name);

    return {
        job,
        lots,
    };
}

export function batchExportUrl(name: string): string {
    return batchApi.batchExportUrl(name, BATCH_EXPORT_TOP);
}

export function formatRub(value: number): string {
    return `${ Math.round(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") } ₽`;
}

export function formatDate(iso: string): string {
    const [ year, month, day ] = iso.split("-");

    return `${ day }.${ month }.${ year }`;
}

export function jobProgress(job: BatchJob): number {
    if (!job.total) {
        return 0;
    }

    return Math.round(100 * (job.done ?? 0) / job.total);
}
