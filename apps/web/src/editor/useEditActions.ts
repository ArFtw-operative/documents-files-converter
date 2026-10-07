import { useCallback, useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { BatchResult, DocumentDetail, Operation, SceneObject } from "@folio/scene-schema";
import { api, ApiError, newBatchId } from "../api/client";
import { keys } from "../api/queries";
import { forget, pendingFor, remember } from "./recovery";
import { useJobs, useSelection } from "./stores";

export type CommitResult =
  | { status: "committed"; result: BatchResult }
  | { status: "needs_confirmation"; required: number; available: number }
  | { status: "needs_signature_confirmation"; message: string }
  | { status: "conflict"; message: string }
  | { status: "failed"; message: string }
  | { status: "offline" };

export function useEditActions(documentId: string) {
  const client = useQueryClient();

  const refresh = useCallback(async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: keys.document(documentId) }),
      client.invalidateQueries({ queryKey: keys.revisions(documentId) }),
    ]);
  }, [client, documentId]);

  const currentRevision = useCallback(
    () => client.getQueryData<DocumentDetail>(keys.document(documentId))?.current_revision ?? 0,
    [client, documentId],
  );

  const submit = useCallback(
    async (operations: Operation[], pendingObjectId?: string): Promise<CommitResult> => {
      const jobs = useJobs.getState();
      const batch = { base_revision: currentRevision(), client_batch_id: newBatchId(), operations };
      jobs.setSave("saving");
      await remember(documentId, batch);
      try {
        const result = await api<BatchResult>(`/api/v1/documents/${documentId}/operations`, { json: batch });
        await forget(batch.client_batch_id);
        jobs.setResult(result);
        jobs.setSave("saved");
        if (pendingObjectId && result.revision) {
          const pending = useJobs.getState().pending[pendingObjectId];
          if (pending) jobs.putPending({ ...pending, untilRevision: result.revision });
        }
        await refresh();
        return { status: "committed", result };
      } catch (err) {
        const error = err as ApiError;
        if (error.isNetwork) {
          jobs.setSave("offline", error.message);
          return { status: "offline" };
        }
        await forget(batch.client_batch_id);
        if (pendingObjectId) jobs.dropPending(pendingObjectId);
        if (error.code === "needs_confirmation") {
          jobs.setSave("idle");
          return { status: "needs_confirmation", required: Number(error.details.required_pt),
            available: Number(error.details.available_pt) };
        }
        if (error.code === "signed_document") {
          jobs.setSave("idle");
          return { status: "needs_signature_confirmation", message: error.message };
        }
        if (error.status === 409) {
          jobs.setSave("failed", "This text changed in the meantime. The page has been refreshed.");
          await refresh();
          return { status: "conflict", message: error.message };
        }
        jobs.setSave("failed", error.message);
        return { status: "failed", message: error.message };
      }
    },
    [currentRevision, documentId, refresh],
  );

  const replaceText = useCallback(
    (pageId: string, obj: SceneObject, newText: string, extra: Record<string, unknown> = {},
     visual: { family?: string; ratio?: number; background?: string } = {}) => {
      useJobs.getState().putPending({ pageId, objectId: obj.id, text: newText, untilRevision: null, ...visual });
      return submit([{ type: "replace_text", page_id: pageId, target_ids: [obj.id],
        payload: { old_text: obj.content.text, new_text: newText, preserve_style: true, reflow: "preserve_box", ...extra } }],
      obj.id);
    },
    [submit],
  );

  const addText = useCallback(
    (pageId: string, position: [number, number], text: string, style: Record<string, unknown>) =>
      submit([{ type: "add_text", page_id: pageId, payload: { text, position, style } }]),
    [submit],
  );

  const deleteObject = useCallback(
    (pageId: string, obj: SceneObject) => {
      useSelection.getState().select(null);
      return submit([{ type: "delete_object", page_id: pageId, target_ids: [obj.id] }]);
    },
    [submit],
  );

  const pageOperation = useCallback(
    (type: Operation["type"], pageId: string | null, payload: Record<string, unknown> = {}) =>
      submit([{ type, page_id: pageId, payload }]),
    [submit],
  );

  const history = useCallback(
    async (action: "undo" | "redo") => {
      const jobs = useJobs.getState();
      jobs.setSave("saving");
      try {
        await api(`/api/v1/documents/${documentId}/${action}`, { json: { expected_revision: currentRevision() } });
        jobs.setSave("saved");
      } catch (err) {
        const error = err as ApiError;
        jobs.setSave(error.code.startsWith("nothing_to") ? "idle" : "failed", error.message);
      }
      useSelection.getState().stopEditing();
      await refresh();
    },
    [currentRevision, documentId, refresh],
  );

  const restore = useCallback(
    async (revision: number) => {
      await api(`/api/v1/documents/${documentId}/restore/${revision}`, { json: { expected_revision: currentRevision() } });
      await refresh();
    },
    [currentRevision, documentId, refresh],
  );

  const exportPdf = useCallback(
    async (mode: "standard" | "optimized" = "standard") => {
      const jobs = useJobs.getState();
      jobs.setSave("saving", "Preparing download…");
      try {
        const exported = await api<{ id: string; status: string; error: string | null }>(
          `/api/v1/documents/${documentId}/exports`, { json: { mode } });
        if (exported.status !== "ready") throw new Error(exported.error ?? "Export failed.");
        const link = document.createElement("a");
        link.href = `/api/v1/documents/${documentId}/exports/${exported.id}/file`;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
        jobs.setSave("saved");
      } catch (err) {
        jobs.setSave("failed", (err as Error).message);
      }
    },
    [documentId],
  );

  /** Replay batches left in IndexedDB by a crash or lost connection (§69). */
  const replayPending = useCallback(async () => {
    const pending = await pendingFor(documentId);
    if (!pending.length) return 0;
    let replayed = 0;
    for (const item of pending) {
      try {
        await api(`/api/v1/documents/${documentId}/operations`, { json: item.batch });
        replayed++;
      } catch (err) {
        if ((err as ApiError).isNetwork) return replayed;
      }
      await forget(item.batch.client_batch_id);
    }
    await refresh();
    useJobs.getState().setSave("saved", replayed ? `Recovered ${replayed} unsaved change${replayed > 1 ? "s" : ""}` : null);
    return replayed;
  }, [documentId, refresh]);

  return useMemo(
    () => ({ replaceText, addText, deleteObject, pageOperation, undo: () => history("undo"), redo: () => history("redo"),
      restore, exportPdf, replayPending, refresh }),
    [replaceText, addText, deleteObject, pageOperation, history, restore, exportPdf, replayPending, refresh],
  );
}
