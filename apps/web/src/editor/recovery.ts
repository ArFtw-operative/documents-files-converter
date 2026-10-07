/** Crash recovery (architecture §69): unsent operation batches persist in IndexedDB until the
 * server acknowledges them; on reload they are replayed (the server deduplicates by batch id). */
import { createStore, del, entries, set } from "idb-keyval";
import type { OperationBatch } from "@folio/scene-schema";

let store: ReturnType<typeof createStore> | null = null;

function db() {
  if (!store) store = createStore("verso-folio", "pending-operations");
  return store;
}

export interface PendingBatch {
  documentId: string;
  batch: OperationBatch;
  savedAt: number;
}

export async function remember(documentId: string, batch: OperationBatch): Promise<void> {
  try {
    await set(batch.client_batch_id, { documentId, batch, savedAt: Date.now() } satisfies PendingBatch, db());
  } catch {
    /* storage unavailable (private mode): editing still works, only crash recovery is lost */
  }
}

export async function forget(batchId: string): Promise<void> {
  try {
    await del(batchId, db());
  } catch {
    /* ignore */
  }
}

export async function pendingFor(documentId: string): Promise<PendingBatch[]> {
  try {
    const all = await entries<string, PendingBatch>(db());
    return all.map(([, value]) => value).filter((p) => p.documentId === documentId).sort((a, b) => a.savedAt - b.savedAt);
  } catch {
    return [];
  }
}
