"use client";
import { useEffect, useState } from "react";
import type { MouseEvent } from "react";
import { API, request } from "../lib";
import type {
  Bookmark,
  Capability,
  EmbeddedAttachment,
  PdfAnnotation,
  PdfComparison,
  PdfDocumentInfo,
  PdfOperation,
  PdfProject,
  PdfRevision,
  PdfSceneImage,
  PdfSceneFormField,
  PdfSceneLink,
  PdfSceneParagraph,
  PdfSceneObject,
  PdfSceneText,
  PdfSceneVector,
  PdfWorkspaceDocument,
  PdfWorkspaceSession,
  Selection,
  VaultFile,
} from "../types";

export type WorkMode =
  | "view"
  | "edit"
  | "comment"
  | "organize"
  | "forms"
  | "protect"
  | "redact"
  | "compare"
  | "convert"
  | "ocr"
  | "sign";

export type LeftTab =
  | "pages"
  | "bookmarks"
  | "comments"
  | "attachments"
  | "fields"
  | "search";

export type InlineEdit = {
  object: PdfSceneText | PdfSceneParagraph;
  value: string;
  caret: number | null;
} | null;

/** Reads a persisted UI preference (safe on the server). */
function persisted<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : (JSON.parse(raw) as T);
  } catch {
    return fallback;
  }
}

function operationMatches(serverValue: unknown, localValue: unknown): boolean {
  if (Array.isArray(localValue)) {
    return (
      Array.isArray(serverValue) &&
      localValue.length === serverValue.length &&
      localValue.every((item, index) =>
        operationMatches(serverValue[index], item),
      )
    );
  }
  if (localValue && typeof localValue === "object") {
    if (!serverValue || typeof serverValue !== "object") return false;
    return Object.entries(localValue).every(([key, value]) =>
      operationMatches(
        (serverValue as Record<string, unknown>)[key],
        value,
      ),
    );
  }
  return Object.is(serverValue, localValue);
}

function commonOperationPrefix(
  server: PdfOperation[],
  local: PdfOperation[],
): number {
  let common = 0;
  while (
    common < server.length &&
    common < local.length &&
    operationMatches(server[common], local[common])
  )
    common += 1;
  return common;
}

export function useStudio(
  files: VaultFile[],
  capabilities: Capability[],
  onJobsChanged: () => Promise<void>,
) {
  const pdfs = files.filter((file) => file.extension === "pdf");
  const imageAssets = files.filter((file) => file.category === "image");
  const hasCapability = (operation: string) =>
    capabilities.some((capability) => capability.operation === operation);
  const capability = (operation: string) =>
    capabilities.find((item) => item.operation === operation);

  // ---- Project + document state (behaviour preserved from the original) ----
  const [projects, setProjects] = useState<PdfProject[]>([]);
  const [project, setProject] = useState<PdfProject | null>(null);
  const [workspaceSession, setWorkspaceSession] =
    useState<PdfWorkspaceSession | null>(null);
  const [sceneText, setSceneText] = useState<PdfSceneText[]>([]);
  const [sceneParagraphs, setSceneParagraphs] = useState<PdfSceneParagraph[]>([]);
  const [sceneImages, setSceneImages] = useState<PdfSceneImage[]>([]);
  const [sceneVectors, setSceneVectors] = useState<PdfSceneVector[]>([]);
  const [sceneFields, setSceneFields] = useState<PdfSceneFormField[]>([]);
  const [sceneLinks, setSceneLinks] = useState<PdfSceneLink[]>([]);
  const [annotations, setAnnotations] = useState<PdfAnnotation[]>([]);
  const [pageBoxes, setPageBoxes] = useState<Record<string, number[]>>({});
  const [documentInfo, setDocumentInfo] = useState<PdfDocumentInfo | null>(null);
  const [revisions, setRevisions] = useState<PdfRevision[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [page, setPage] = useState(1);
  const [pageImage, setPageImage] = useState("");
  const [operations, setOperations] = useState<PdfOperation[]>([]);
  const [tool, setToolState] = useState("select");
  const [text, setText] = useState("Text");
  const [replacement, setReplacement] = useState("");
  const [font, setFont] = useState("Helvetica");
  const [fontSize, setFontSize] = useState(12);
  const [color, setColor] = useState("#14211b");
  const [fill, setFill] = useState("#dff4e9");
  const [opacity, setOpacity] = useState(1);
  const [annotationKind, setAnnotationKind] = useState("annotate.highlight");
  const [annotationAuthor, setAnnotationAuthor] = useState("");
  const [annotationSubject, setAnnotationSubject] = useState("Review");
  const [annotationStatus, setAnnotationStatus] = useState("none");
  const [annotationBorder, setAnnotationBorder] = useState("solid");
  const [annotationWidth, setAnnotationWidth] = useState(2);
  const [annotationSearch, setAnnotationSearch] = useState("");
  const [annotationTypeFilter, setAnnotationTypeFilter] = useState("");
  const [annotationStatusFilter, setAnnotationStatusFilter] = useState("");
  const [annotationPageFilter, setAnnotationPageFilter] = useState("all");
  const [annotationSort, setAnnotationSort] = useState("page");
  const [hideResolved, setHideResolved] = useState(false);
  const [selectedAnnotationId, setSelectedAnnotationId] = useState("");
  const [replyText, setReplyText] = useState("");
  const [attachmentId, setAttachmentId] = useState("");
  const [audioAnnotationsSupported, setAudioAnnotationsSupported] =
    useState(false);
  const [redactionPattern, setRedactionPattern] = useState("keyword");
  const [redactionTerms, setRedactionTerms] = useState("");
  const [redactionMetadata, setRedactionMetadata] = useState(false);
  const [redactionComments, setRedactionComments] = useState(false);
  const [redactionAttachments, setRedactionAttachments] = useState(false);
  const [redactionForms, setRedactionForms] = useState(false);
  const [compareFileId, setCompareFileId] = useState("");
  const [comparison, setComparison] = useState<PdfComparison | null>(null);
  const [comparisonMode, setComparisonMode] = useState("side-by-side");
  const [comparisonFilter, setComparisonFilter] = useState("");
  const [comparisonImages, setComparisonImages] = useState<
    Record<string, string>
  >({});
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [embeddedAttachments, setEmbeddedAttachments] = useState<
    EmbeddedAttachment[]
  >([]);
  const [bookmarkTitle, setBookmarkTitle] = useState("");
  const [attachmentAssetId, setAttachmentAssetId] = useState("");
  const [attachmentName, setAttachmentName] = useState("");
  const [imageId, setImageId] = useState("");
  const [pageSourceId, setPageSourceId] = useState("");
  const [pageSourceNumber, setPageSourceNumber] = useState(1);
  const [pageWidthValue, setPageWidthValue] = useState(595);
  const [pageHeightValue, setPageHeightValue] = useState(842);
  const [resizeMode, setResizeMode] = useState("fit");
  const [shapeKind, setShapeKind] = useState("rectangle");
  const [formKind, setFormKind] = useState("form.text");
  const [notice, setNoticeState] = useState("");
  const [noticeTone, setNoticeTone] = useState<"info" | "error">("info");
  const [busy, setBusy] = useState(false);

  // ---- New workspace UI state ----
  const [workMode, setWorkMode] = useState<WorkMode>("view");
  const [selection, setSelection] = useState<Selection>(null);
  const [inlineEdit, setInlineEdit] = useState<InlineEdit>(null);
  const [zoom, setZoom] = useState(1);
  const [fitRequest, setFitRequest] = useState(0);
  const [leftTab, setLeftTab] = useState<LeftTab>("pages");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [toolLock, setToolLock] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [theme, setThemeState] = useState<"light" | "dark">(() =>
    persisted("studio.theme", "light"),
  );
  const [density, setDensityState] = useState<"comfortable" | "compact">(() =>
    persisted("studio.density", "comfortable"),
  );

  function setNotice(message: string, tone: "info" | "error" = "info") {
    setNoticeState(message);
    setNoticeTone(tone);
  }
  function fail(error: unknown, fallback: string) {
    setNotice(error instanceof Error ? error.message : fallback, "error");
  }
  function setTheme(next: "light" | "dark") {
    setThemeState(next);
    try {
      localStorage.setItem("studio.theme", JSON.stringify(next));
    } catch {}
  }
  function setDensity(next: "comfortable" | "compact") {
    setDensityState(next);
    try {
      localStorage.setItem("studio.density", JSON.stringify(next));
    } catch {}
  }
  function fitWidth() {
    setFitRequest((current) => current + 1);
  }
  /** Set the active tool; clears any live selection so context is unambiguous. */
  function setTool(next: string) {
    setToolState(next);
    if (next !== "select") setSelection(null);
  }

  const loadProjects = async () => {
    const response = await request<{ items: PdfProject[] }>(
      "/api/v1/pdf/projects",
    );
    setProjects(response.items);
    return response.items;
  };
  useEffect(() => {
    loadProjects().catch((error) => fail(error, "Projects could not be loaded"));
  }, []);

  useEffect(() => {
    if (!project) return;
    setWorkspaceSession(null);
    setSceneText([]);
    setSceneParagraphs([]);
    setSceneImages([]);
    setSceneVectors([]);
    setSceneFields([]);
    setSceneLinks([]);
    setPageBoxes({});
    setSelection(null);
    setInlineEdit(null);
    setOperations(project.operations);
    setPage(1);
    Promise.all([
      request<PdfDocumentInfo>(`/api/v1/pdf/projects/${project.id}/document`),
      request<{ items: PdfRevision[] }>(
        `/api/v1/pdf/projects/${project.id}/revisions`,
      ),
    ])
      .then(([info, history]) => {
        setDocumentInfo(info);
        setRevisions(history.items);
      })
      .catch((error) => fail(error, "The project could not be opened"));
    (async () => {
      const documents = await request<{ items: PdfWorkspaceDocument[] }>(
        "/api/v1/pdf/documents",
      );
      let document = documents.items.find(
        (item) => item.source_file_id === project.source_file_id,
      );
      if (!document) {
        document = await request<PdfWorkspaceDocument>("/api/v1/pdf/documents", {
          method: "POST",
          body: JSON.stringify({
            file_id: project.source_file_id,
            name: project.name,
          }),
        });
      }
      const sessions = await request<{ items: PdfWorkspaceSession[] }>(
        `/api/v1/pdf/documents/${document.id}/sessions`,
      );
      let session = sessions.items.find(
        (item) =>
          item.status === "active" &&
          item.operations.length === project.operations.length &&
          commonOperationPrefix(item.operations, project.operations) === project.operations.length,
      );
      if (!session) {
        session = await request<PdfWorkspaceSession>(
          `/api/v1/pdf/documents/${document.id}/sessions`,
          {
            method: "POST",
            body: JSON.stringify({ operations: project.operations }),
          },
        );
      }
      setWorkspaceSession(session);
      setOperations(session.operations);
    })().catch((error) =>
      fail(error, "The command workspace could not be opened"),
    );
  }, [project?.id]);

  useEffect(() => {
    if (!workspaceSession) return;
    request<{ objects: PdfSceneObject[]; boxes: Record<string, number[]> }>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/scene?page=${page}`,
    )
      .then((scene) => {
        setSceneText(
          scene.objects.filter(
            (item): item is PdfSceneText => item.type === "text_run",
          ),
        );
        setSceneParagraphs(
          scene.objects.filter(
            (item): item is PdfSceneParagraph => item.type === "text_block",
          ),
        );
        setSceneImages(
          scene.objects.filter(
            (item): item is PdfSceneImage => item.type === "image",
          ),
        );
        setSceneVectors(
          scene.objects.filter(
            (item): item is PdfSceneVector => item.type === "vector_path",
          ),
        );
        setSceneFields(
          scene.objects.filter(
            (item): item is PdfSceneFormField => item.type === "form_field",
          ),
        );
        setSceneLinks(
          scene.objects.filter(
            (item): item is PdfSceneLink => item.type === "link",
          ),
        );
        setPageBoxes(scene.boxes);
        const media = scene.boxes.media;
        if (media) {
          setPageWidthValue(Math.round((media[2] - media[0]) * 100) / 100);
          setPageHeightValue(Math.round((media[3] - media[1]) * 100) / 100);
        }
      })
      .catch((error) => fail(error, "The page could not be inspected"));
  }, [workspaceSession?.id, workspaceSession?.revision, page]);

  useEffect(() => {
    if (!workspaceSession) return;
    request<PdfDocumentInfo>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/document`,
    )
      .then((info) => {
        setDocumentInfo(info);
        setPage((current) => Math.min(current, info.page_count));
      })
      .catch((error) => fail(error, "The document could not be inspected"));
  }, [workspaceSession?.id, workspaceSession?.revision]);

  useEffect(() => {
    if (!workspaceSession) return;
    const params = new URLSearchParams();
    if (annotationSearch) params.set("search", annotationSearch);
    if (annotationTypeFilter) params.set("type", annotationTypeFilter);
    if (annotationStatusFilter) params.set("status", annotationStatusFilter);
    if (annotationPageFilter === "current") params.set("page", String(page));
    if (hideResolved) params.set("hide_resolved", "true");
    params.set("sort", annotationSort);
    request<{ items: PdfAnnotation[]; audio_supported: boolean }>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/annotations?${params}`,
    )
      .then((response) => {
        setAnnotations(response.items);
        setAudioAnnotationsSupported(response.audio_supported);
      })
      .catch((error) => fail(error, "Comments could not be loaded"));
  }, [
    workspaceSession?.id,
    workspaceSession?.revision,
    annotationSearch,
    annotationTypeFilter,
    annotationStatusFilter,
    annotationPageFilter,
    annotationSort,
    hideResolved,
    page,
  ]);

  useEffect(() => {
    if (!workspaceSession) return;
    request<{ bookmarks: Bookmark[]; attachments: EmbeddedAttachment[] }>(
      `/api/v1/pdf/sessions/${workspaceSession.id}/navigation`,
    )
      .then((response) => {
        setBookmarks(response.bookmarks);
        setEmbeddedAttachments(response.attachments);
      })
      .catch((error) => fail(error, "Navigation could not be loaded"));
  }, [workspaceSession?.id, workspaceSession?.revision]);

  useEffect(() => {
    if (!project) return;
    let active = true;
    const token = localStorage.getItem("access_token");
    const previewPath = workspaceSession
      ? `/api/v1/pdf/sessions/${workspaceSession.id}/pages/${page}/render?dpi=150`
      : `/api/v1/pdf/projects/${project.id}/pages/${page}/render?dpi=150`;
    fetch(`${API}${previewPath}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((response) => {
        if (!response.ok) throw new Error("Page preview could not be rendered");
        return response.blob();
      })
      .then((blob) => {
        if (!active) return;
        const url = URL.createObjectURL(blob);
        setPageImage((old) => {
          if (old) URL.revokeObjectURL(old);
          return url;
        });
      })
      .catch((error) => fail(error, "The page preview could not be rendered"));
    return () => {
      active = false;
    };
  }, [project?.id, workspaceSession?.id, workspaceSession?.revision, page]);

  // Clear any live selection when the page changes.
  useEffect(() => {
    setSelection(null);
    setInlineEdit(null);
  }, [page]);

  async function createProject(fromId?: string) {
    const useId = fromId ?? sourceId;
    if (!useId) return;
    setBusy(true);
    try {
      const source = pdfs.find((file) => file.id === useId);
      const created = await request<PdfProject>("/api/v1/pdf/projects", {
        method: "POST",
        body: JSON.stringify({
          file_id: useId,
          name: source ? `${source.display_name} studio project` : undefined,
        }),
      });
      await loadProjects();
      setProject(created);
      setWorkMode("view");
      setNotice("Editing project created. Your original file stays untouched.");
    } catch (error) {
      fail(error, "The project could not be created");
    } finally {
      setBusy(false);
    }
  }

  async function syncCommandSession() {
    if (!workspaceSession) return null;
    let current = workspaceSession;
    const rejected: Array<{ operation: PdfOperation; message: string }> = [];
    const common = commonOperationPrefix(current.operations, operations);
    for (let index = current.operations.length; index > common; index -= 1) {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${current.id}/undo`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: current.revision,
            idempotency_key: `ui-undo-${crypto.randomUUID()}`,
          }),
        },
      );
      current = result.session;
    }
    for (const operation of operations.slice(common)) {
      try {
        const result = await request<{ session: PdfWorkspaceSession }>(
          `/api/v1/pdf/sessions/${current.id}/commands`,
          {
            method: "POST",
            body: JSON.stringify({
              expected_revision: current.revision,
              idempotency_key: `ui-command-${crypto.randomUUID()}`,
              operation,
              object_id: operation.object_id,
            }),
          },
        );
        current = result.session;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "The edit was rejected";
        if (message.includes("changed in another client")) throw error;
        rejected.push({ operation, message });
      }
    }
    setWorkspaceSession(current);
    setOperations(current.operations);
    return { session: current, rejected };
  }

  async function saveProject() {
    if (!project) return null;
    setBusy(true);
    try {
      const syncResult = await syncCommandSession();
      const commandSession = syncResult?.session ?? null;
      const savedOperations = commandSession?.operations ?? operations;
      const saved = await request<PdfProject>(
        `/api/v1/pdf/projects/${project.id}`,
        {
          method: "PUT",
          body: JSON.stringify({
            expected_revision: project.revision,
            operations: savedOperations,
          }),
        },
      );
      setProject(saved);
      await loadProjects();
      const history = await request<{ items: PdfRevision[] }>(
        `/api/v1/pdf/projects/${saved.id}/revisions`,
      );
      setRevisions(history.items);
      if (syncResult?.rejected.length) {
        const details = syncResult.rejected
          .map(
            ({ operation, message }) =>
              `${operation.kind.replaceAll(".", " ")}: ${message}`,
          )
          .join("; ");
        setNotice(
          `Saved revision ${saved.revision}, but ${syncResult.rejected.length} invalid edit${syncResult.rejected.length === 1 ? " was" : "s were"} removed: ${details}`,
          "error",
        );
      } else {
        setNotice(
          `Saved as revision ${saved.revision} (${commandSession?.cursor ?? savedOperations.length} recoverable commands).`,
        );
      }
      return { project: saved, session: commandSession };
    } catch (error) {
      fail(error, "Your edits could not be saved");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    const saved = await saveProject();
    if (!saved) return;
    setBusy(true);
    try {
      if (saved.session) {
        await request(`/api/v1/pdf/sessions/${saved.session.id}/exports`, {
          method: "POST",
          body: JSON.stringify({
            expected_revision: saved.session.revision,
            idempotency_key: `ui-export-${crypto.randomUUID()}`,
          }),
        });
        setWorkspaceSession({
          ...saved.session,
          revision: saved.session.revision + 1,
          status: "exporting",
        });
      } else {
        await request(`/api/v1/pdf/projects/${saved.project.id}/publish`, {
          method: "POST",
        });
      }
      setProject({ ...saved.project, status: "queued" });
      setNotice(
        "Export queued. The finished PDF will appear in your library and Jobs.",
      );
      await onJobsChanged();
    } catch (error) {
      fail(error, "The PDF could not be exported");
    } finally {
      setBusy(false);
    }
  }

  async function historyAction(action: "undo" | "redo") {
    if (!workspaceSession) {
      if (action === "undo") setOperations((current) => current.slice(0, -1));
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/${action}`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-${action}-${crypto.randomUUID()}`,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(`${action === "undo" ? "Undid" : "Redid"} the last command.`);
    } catch (error) {
      fail(error, `Could not ${action}`);
    } finally {
      setBusy(false);
    }
  }

  async function createAnnotationOperation(operation: PdfOperation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-${crypto.randomUUID()}`,
            operation,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Comment added to the recoverable history.");
    } catch (error) {
      fail(error, "The comment could not be added");
    } finally {
      setBusy(false);
    }
  }

  async function updateAnnotation(
    annotation: PdfAnnotation,
    changes: Record<string, unknown>,
  ) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-update-${crypto.randomUUID()}`,
            ...changes,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Comment updated.");
    } catch (error) {
      fail(error, "The comment could not be updated");
    } finally {
      setBusy(false);
    }
  }

  async function replyToAnnotation(annotation: PdfAnnotation) {
    if (!workspaceSession || !replyText.trim()) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}/replies`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-reply-${crypto.randomUUID()}`,
            text: replyText.trim(),
            author: annotationAuthor || undefined,
            subject: "Reply",
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setReplyText("");
      setNotice("Reply added to the thread.");
    } catch (error) {
      fail(error, "The reply could not be added");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAnnotation(annotation: PdfAnnotation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/annotations/${encodeURIComponent(annotation.id)}`,
        {
          method: "DELETE",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-annotation-delete-${crypto.randomUUID()}`,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setSelectedAnnotationId("");
      setSelection(null);
      setNotice("Comment deleted. Undo can restore it.");
    } catch (error) {
      fail(error, "The comment could not be deleted");
    } finally {
      setBusy(false);
    }
  }

  async function applySearchRedaction() {
    if (!workspaceSession) return;
    const terms = redactionTerms
      .split(/[\n,]/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (redactionPattern === "keyword" && !terms.length) {
      setNotice("Enter at least one keyword to redact.", "error");
      return;
    }
    setBusy(true);
    try {
      const operation: PdfOperation = {
        kind: "redact.search",
        pages: documentInfo?.pages.map((item) => item.page),
        search_terms: terms,
        pattern_type: redactionPattern,
        custom_regex:
          redactionPattern === "custom_regex" ? replacement : undefined,
        fill: "#000000",
        color: "#ffffff",
        remove_metadata: redactionMetadata,
        remove_comments: redactionComments,
        remove_attachments: redactionAttachments,
        remove_hidden_text: true,
        remove_form_values: redactionForms,
      };
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-search-redaction-${crypto.randomUUID()}`,
            operation,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        "Redaction queued. Export validation confirms no matches remain, and underlying text is removed — not just hidden.",
      );
    } catch (error) {
      fail(error, "The redaction could not be applied");
    } finally {
      setBusy(false);
    }
  }

  async function loadComparisonImages(afterFileId: string, comparisonPage = 1) {
    if (!project) return;
    const token = localStorage.getItem("access_token");
    const entries = await Promise.all(
      ["before", "after", "overlay"].map(async (side) => {
        const params = new URLSearchParams({
          before_file_id: project.source_file_id,
          after_file_id: afterFileId,
          side,
          page: String(comparisonPage),
          dpi: "96",
        });
        const response = await fetch(
          `${API}/api/v1/pdf/compare/render?${params}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : {} },
        );
        if (!response.ok)
          throw new Error("Comparison preview could not be rendered");
        return [side, URL.createObjectURL(await response.blob())] as const;
      }),
    );
    setComparisonImages((current) => {
      Object.values(current).forEach((url) => URL.revokeObjectURL(url));
      return Object.fromEntries(entries);
    });
  }

  async function compareDocuments() {
    if (!project || !compareFileId) return;
    setBusy(true);
    try {
      const report = await request<PdfComparison>("/api/v1/pdf/compare", {
        method: "POST",
        body: JSON.stringify({
          before_file_id: project.source_file_id,
          after_file_id: compareFileId,
          ignore_headers_footers: false,
          ignore_formatting: false,
          ignore_whitespace: true,
        }),
      });
      setComparison(report);
      const firstPage = report.differences.find(
        (item) => item.after_page || item.before_page,
      );
      await loadComparisonImages(
        compareFileId,
        firstPage?.after_page || firstPage?.before_page || 1,
      );
      setNotice(
        `Comparison found ${report.summary.total} text, object, page, metadata, and visual differences.`,
      );
    } catch (error) {
      fail(error, "The PDFs could not be compared");
    } finally {
      setBusy(false);
    }
  }

  function exportComparisonReport() {
    if (!comparison) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(comparison, null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pdf-comparison-report.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function applyNavigationOperation(operation: PdfOperation) {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-navigation-${crypto.randomUUID()}`,
            operation,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice("Navigation command added to recoverable history.");
    } catch (error) {
      fail(error, "The navigation command failed");
    } finally {
      setBusy(false);
    }
  }

  async function downloadEmbeddedAttachment(name: string) {
    if (!workspaceSession) return;
    const token = localStorage.getItem("access_token");
    const response = await fetch(
      `${API}/api/v1/pdf/sessions/${workspaceSession.id}/attachments/download?name=${encodeURIComponent(name)}`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} },
    );
    if (!response.ok) {
      setNotice("The embedded attachment could not be downloaded", "error");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  function addOperation(event: MouseEvent<HTMLDivElement>) {
    if (!documentInfo || tool === "select") return;
    const pageInfo = documentInfo.pages[page - 1];
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * pageInfo.width;
    const y = ((event.clientY - bounds.top) / bounds.height) * pageInfo.height;
    const rectWidth = tool === "text" ? 240 : tool === "shape" ? 120 : tool === "comment" ? 25 : 180;
    const rectHeight = tool === "text" ? Math.max(60, fontSize * 4) : tool === "shape" ? 120 : tool === "comment" ? 25 : 45;
    const rect = [
      Math.max(0, x - 5),
      Math.max(0, y - 5),
      Math.min(pageInfo.width, x + rectWidth),
      Math.min(pageInfo.height, y + rectHeight),
    ];
    const base = { page, rect, color, fill, opacity, font, font_size: fontSize };
    let operation: PdfOperation | null = null;
    if (tool === "text") operation = { kind: "content.add_text", ...base, text };
    if (tool === "shape")
      operation = { kind: "content.add_shape", ...base, text: shapeKind };
    if (tool === "highlight") operation = { kind: "annotate.highlight", ...base };
    if (tool === "underline") operation = { kind: "annotate.underline", ...base };
    if (tool === "strikeout") operation = { kind: "annotate.strikeout", ...base };
    if (tool === "comment")
      operation = { kind: "annotate.comment", ...base, text };
    if (tool === "free_text")
      operation = { kind: "annotate.free_text", ...base, text };
    if (tool === "annotation") {
      operation = {
        kind: annotationKind,
        ...base,
        text: [
          "annotate.comment",
          "annotate.free_text",
          "annotate.callout",
          "annotate.replace_text",
          "annotate.redaction_mark",
        ].includes(annotationKind)
          ? text
          : undefined,
        author: annotationAuthor || undefined,
        subject: annotationSubject || undefined,
        annotation_status: annotationStatus,
        border_style: annotationBorder,
        width: annotationWidth,
        printable: true,
        visible: true,
        locked: false,
        attachment_file_id:
          annotationKind === "annotate.attachment" ? attachmentId : undefined,
        stamp_type: annotationKind === "annotate.stamp" ? "approved" : undefined,
        measurement_scale:
          annotationKind === "annotate.measurement" ? 1 : undefined,
        measurement_unit:
          annotationKind === "annotate.measurement" ? "pt" : undefined,
      };
      if (
        ["annotate.line", "annotate.arrow", "annotate.measurement"].includes(
          annotationKind,
        )
      )
        operation.points = [
          [rect[0], rect[1]],
          [rect[2], rect[3]],
        ];
      if (annotationKind === "annotate.ink")
        operation.points = [
          [x - 30, y + 10],
          [x, y - 10],
          [x + 30, y + 10],
        ];
      if (["annotate.polygon", "annotate.polyline"].includes(annotationKind))
        operation.points = [
          [x - 40, y + 20],
          [x, y - 25],
          [x + 40, y + 20],
        ];
      if (annotationKind === "annotate.callout")
        operation.points = [
          [x - 25, y + 20],
          [x, y],
        ];
    }
    if (tool === "redact") operation = { kind: "redact", ...base };
    if (tool === "crop") operation = { kind: "page.crop", ...base };
    if (tool === "link") operation = { kind: "link.add", ...base, uri: text };
    if (tool === "form")
      operation = {
        kind: formKind,
        ...base,
        field_name: text || `field_${operations.length + 1}`,
        field_label: text || `Field ${operations.length + 1}`,
        field_value: replacement,
        choice_values: ["form.radio", "form.combo", "form.listbox"].includes(
          formKind,
        )
          ? (replacement || "Option 1, Option 2")
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean)
          : undefined,
        multiline: formKind === "form.multiline",
        format_type:
          formKind === "form.date"
            ? "date"
            : formKind === "form.numeric"
              ? "number"
              : "none",
      };
    if (tool === "draw")
      operation = {
        kind: "content.draw",
        page,
        points: [
          [x - 20, y],
          [x, y - 15],
          [x + 20, y],
        ],
        color,
        width: 2,
        opacity,
      };
    if (["image", "signature"].includes(tool) && imageId)
      operation = {
        kind: tool === "image" ? "content.add_image" : "signature.add",
        ...base,
        image_file_id: imageId,
      };
    if (operation) {
      if (operation.kind.startsWith("annotate.") && workspaceSession) {
        if (operation.kind === "annotate.attachment" && !attachmentId) {
          setNotice("Choose a vault file to attach first.", "error");
          return;
        }
        void createAnnotationOperation(operation);
      } else {
        setOperations((current) => [...current, operation as PdfOperation]);
        setNotice(`${tool} added to page ${page}. Save to create a revision.`);
      }
      if (!toolLock) setTool("select");
    } else if (["image", "signature"].includes(tool)) {
      setNotice("Choose an image asset first.", "error");
    }
  }

  function pageAction(kind: "rotate" | "delete" | "duplicate" | "blank", targetPage = page) {
    if (!documentInfo) return;
    if (kind === "rotate")
      setOperations((current) => [
        ...current,
        { kind: "page.rotate", page: targetPage, rotation: 90 },
      ]);
    if (kind === "delete" && documentInfo.page_count > 1)
      setOperations((current) => [
        ...current,
        { kind: "page.delete", pages: [targetPage] },
      ]);
    if (kind === "duplicate")
      setOperations((current) => [
        ...current,
        { kind: "page.duplicate", page: targetPage },
      ]);
    if (kind === "blank")
      setOperations((current) => [
        ...current,
        { kind: "page.insert_blank", page: targetPage + 1 },
      ]);
  }

  function currentPageOrder(): number[] {
    if (!documentInfo) return [];
    const lastOrder = [...operations]
      .reverse()
      .find((operation) => operation.kind === "page.reorder")?.order;
    return lastOrder
      ? [...lastOrder]
      : Array.from({ length: documentInfo.page_count }, (_, i) => i + 1);
  }

  function movePage(direction: -1 | 1, targetPage = page) {
    if (!documentInfo) return;
    const order = currentPageOrder();
    const index = order.indexOf(targetPage);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= order.length) return;
    [order[index], order[target]] = [order[target], order[index]];
    setOperations((current) => [...current, { kind: "page.reorder", order }]);
  }

  /** Drag-reorder in Organize mode: move a page to a new index. */
  function reorderPage(fromPage: number, toIndex: number) {
    if (!documentInfo) return;
    const order = currentPageOrder();
    const from = order.indexOf(fromPage);
    if (from < 0) return;
    const clamped = Math.max(0, Math.min(order.length - 1, toIndex));
    order.splice(from, 1);
    order.splice(clamped, 0, fromPage);
    setOperations((current) => [...current, { kind: "page.reorder", order }]);
    setNotice("Page order updated. Save to create a revision.");
  }

  async function restoreRevision(revision: number) {
    if (!project) return;
    try {
      const restored = await request<PdfProject>(
        `/api/v1/pdf/projects/${project.id}/restore/${revision}`,
        { method: "POST" },
      );
      setProject(restored);
      setOperations(restored.operations);
      setNotice(`Revision ${revision} restored as revision ${restored.revision}.`);
    } catch (error) {
      fail(error, "The revision could not be restored");
    }
  }

  function addDocumentOperation(
    kind: "watermark.text" | "header_footer" | "metadata.set",
    value = text,
  ) {
    if (kind === "metadata.set") {
      setOperations((current) => [
        ...current,
        { kind, metadata: { title: value } },
      ]);
      setNotice("Document title metadata queued.");
      return;
    }
    setOperations((current) => [
      ...current,
      {
        kind,
        text: value,
        font_size: kind === "watermark.text" ? fontSize : Math.min(fontSize, 24),
        color,
        opacity,
      },
    ]);
    setNotice(
      kind === "watermark.text"
        ? "Watermark queued for every page."
        : "Footer queued for every page. Use {page} for page numbers.",
    );
  }

  async function replaceTextObject(textObject: PdfSceneText | PdfSceneParagraph, newText: string) {
    if (!workspaceSession) {
      setNotice("The editing session is still opening. Try again shortly.", "error");
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/${textObject.type === "text_block" ? "paragraphs" : "text"}/${textObject.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-native-text-${crypto.randomUUID()}`,
            operation: "replace_range",
            range: { start: 0, end: textObject.text.length },
            text: newText,
            reflow_policy: textObject.type === "text_block" ? "reduce_font" : "preserve_line_positions",
            font_policy: "preserve_or_prompt",
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setInlineEdit(null);
      setNotice(
        textObject.type === "text_block"
          ? "Paragraph edited and reflowed inside its original text box."
          : "Text edited in place. Font, size, colour, and baseline are preserved where the PDF permits.",
      );
    } catch (error) {
      fail(
        error,
        `Text could not be edited on page ${page}. The embedded font may not include a needed glyph — try a compatible font or add a new text box.`,
      );
    } finally {
      setBusy(false);
    }
  }

  // Backwards-compatible wrapper used by list-based flows.
  async function replaceExistingText(textObject: PdfSceneText) {
    await replaceTextObject(textObject, replacement);
  }

  async function editExistingImage(
    image: PdfSceneImage,
    action: "move" | "resize" | "rotate" | "crop" | "replace" | "delete",
  ) {
    if (!workspaceSession) return;
    const [x0, y0, x1, y1] = image.bounds;
    if (action === "replace" && !imageId) {
      setNotice("Choose a replacement image asset first.", "error");
      return;
    }
    const payload: Record<string, unknown> = {
      expected_revision: workspaceSession.revision,
      idempotency_key: `ui-image-${crypto.randomUUID()}`,
      action:
        action === "delete"
          ? "delete"
          : action === "replace"
            ? "replace"
            : "transform",
      rect:
        action === "move"
          ? [x0 + 18, y0 + 18, x1 + 18, y1 + 18]
          : action === "resize"
            ? [x0, y0, x1 + (x1 - x0) * 0.2, y1 + (y1 - y0) * 0.2]
            : image.bounds,
      rotation: action === "rotate" ? 15 : 0,
      crop: action === "crop" ? [0.1, 0.1, 0.9, 0.9] : undefined,
      image_file_id: action === "replace" ? imageId : undefined,
    };
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/images/${image.id}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(`Image ${action} applied and added to recoverable history.`);
    } catch (error) {
      fail(error, "The image could not be edited");
    } finally {
      setBusy(false);
    }
  }

  async function editExistingVector(
    vector: PdfSceneVector,
    action: "move" | "resize" | "rotate" | "restyle" | "delete",
  ) {
    if (!workspaceSession) return;
    const [x0, y0, x1, y1] = vector.bounds;
    const payload = {
      expected_revision: workspaceSession.revision,
      idempotency_key: `ui-vector-${crypto.randomUUID()}`,
      action: action === "delete" ? "delete" : "transform",
      rect:
        action === "move"
          ? [x0 + 18, y0 + 18, x1 + 18, y1 + 18]
          : action === "resize"
            ? [x0, y0, x1 + (x1 - x0) * 0.2, y1 + (y1 - y0) * 0.2]
            : vector.bounds,
      rotation: action === "rotate" ? 15 : 0,
      color: action === "restyle" ? color : undefined,
      fill: action === "restyle" ? fill : undefined,
      width: action === "restyle" ? 3 : undefined,
      opacity: action === "restyle" ? opacity : undefined,
    };
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/vectors/${vector.id}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(`Vector ${action} applied and added to recoverable history.`);
    } catch (error) {
      fail(error, "The vector could not be edited");
    } finally {
      setBusy(false);
    }
  }

  async function editExistingFormField(
    field: PdfSceneFormField,
    action: "update" | "delete",
    changes: Record<string, unknown> = {},
  ) {
    if (!workspaceSession) return;
    const operation: PdfOperation = {
      kind: action === "delete" ? "form.delete" : "form.update",
      page: field.page,
      field_name: field.properties.name,
      ...changes,
    };
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-form-field-${crypto.randomUUID()}`,
            operation,
            object_id: field.id,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setSelection(null);
      setNotice(
        action === "delete"
          ? `Form field ${field.properties.name} deleted.`
          : `Form field ${field.properties.name} updated.`,
      );
    } catch (error) {
      fail(error, "The form field could not be updated");
    } finally {
      setBusy(false);
    }
  }

  async function editExistingLink(
    link: PdfSceneLink,
    action: "update" | "delete",
    uri?: string,
  ) {
    if (!workspaceSession || !link.source.xref) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/commands`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-link-${crypto.randomUUID()}`,
            object_id: link.id,
            operation: {
              kind: action === "delete" ? "link.delete" : "link.update",
              page: link.page,
              source_xref: link.source.xref,
              uri: action === "update" ? uri : undefined,
            },
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setSelection(null);
      setNotice(action === "delete" ? "Link deleted." : "Link destination updated.");
    } catch (error) {
      fail(error, "The link could not be edited");
    } finally {
      setBusy(false);
    }
  }

  async function importExistingPage(action: "insert" | "replace") {
    if (!workspaceSession || !pageSourceId) {
      setNotice("Choose a source PDF before importing a page.", "error");
      return;
    }
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/pages/import`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-page-import-${crypto.randomUUID()}`,
            action,
            page: action === "insert" ? page + 1 : page,
            source_file_id: pageSourceId,
            source_page: pageSourceNumber,
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        action === "insert"
          ? `Imported page inserted after page ${page}.`
          : `Page ${page} replaced from the source PDF.`,
      );
    } catch (error) {
      fail(error, "The page could not be imported");
    } finally {
      setBusy(false);
    }
  }

  async function updatePageGeometry(action: "resize" | "set_boxes") {
    if (!workspaceSession) return;
    setBusy(true);
    try {
      const result = await request<{ session: PdfWorkspaceSession }>(
        `/api/v1/pdf/sessions/${workspaceSession.id}/pages/${page}/geometry`,
        {
          method: "PATCH",
          body: JSON.stringify({
            expected_revision: workspaceSession.revision,
            idempotency_key: `ui-page-geometry-${crypto.randomUUID()}`,
            action,
            width: action === "resize" ? pageWidthValue : undefined,
            height: action === "resize" ? pageHeightValue : undefined,
            resize_mode: resizeMode,
            boxes: action === "set_boxes" ? pageBoxes : {},
          }),
        },
      );
      setWorkspaceSession(result.session);
      setOperations(result.session.operations);
      setNotice(
        action === "resize"
          ? "Page and content resized."
          : "Page boxes applied.",
      );
    } catch (error) {
      fail(error, "The page geometry could not be updated");
    } finally {
      setBusy(false);
    }
  }

  function updateBox(name: string, value: string) {
    const coordinates = value
      .split(",")
      .map((item) => Number(item.trim()))
      .filter((item) => Number.isFinite(item));
    setPageBoxes((current) => ({ ...current, [name]: coordinates }));
  }

  /** Queue a one-shot job (Convert/Protect/OCR) against the original source PDF. */
  async function runJob(
    operation: string,
    targetFormat: string,
    options: Record<string, unknown> = {},
    extraInputs: string[] = [],
  ) {
    if (!project) return;
    if (!hasCapability(operation)) {
      setNotice(
        `${operation.replaceAll(".", " ")} is not available on the running PDF worker. Install or enable its engine first.`,
        "error",
      );
      return;
    }
    setBusy(true);
    try {
      await request("/api/v1/jobs", {
        method: "POST",
        body: JSON.stringify({
          input_file_id: project.source_file_id,
          input_file_ids: extraInputs,
          operation,
          target_format: targetFormat,
          options,
        }),
      });
      setNotice(
        `${operation.replaceAll(".", " ")} queued. It runs on your original file and appears in your library and Jobs.`,
      );
      await onJobsChanged();
    } catch (error) {
      fail(error, "The job could not be started");
    } finally {
      setBusy(false);
    }
  }

  /** Select a canvas object and route the inspector/tool to match. */
  function selectObject(next: Selection) {
    setSelection(next);
    if (next?.kind === "annotation") setSelectedAnnotationId(next.id);
  }

  function beginInlineEdit(object: PdfSceneText | PdfSceneParagraph, caret: number | null = null) {
    if (object.editability === "Protected" || object.lock_state) {
      setNotice(
        `This text is ${object.editability.toLowerCase()} and can't be edited directly. It may be a scanned image or outlined glyphs — use OCR or add a new text box.`,
        "error",
      );
      return;
    }
    setSelection(object.type === "text_block" ? { kind: "paragraph", object } : { kind: "text", object });
    setInlineEdit({ object, value: object.text, caret });
  }

  const pageInfo = documentInfo?.pages[page - 1];
  const selectedAnnotation = annotations.find(
    (annotation) => annotation.id === selectedAnnotationId,
  );
  const pendingStart = workspaceSession
    ? commonOperationPrefix(workspaceSession.operations, operations)
    : 0;
  const pendingOperations = operations
    .slice(pendingStart)
    .map((operation, offset) => ({ operation, index: pendingStart + offset }));
  const pageOps = pendingOperations
    .filter(({ operation }) => operation.page === page && operation.rect);

  function removePendingOperation(index: number) {
    if (index < pendingStart) return;
    setOperations((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setNotice("Pending edit removed.");
  }

  function updatePendingOperation(index: number, patch: Partial<PdfOperation>) {
    if (index < pendingStart) return;
    setOperations((current) => current.map((operation, itemIndex) =>
      itemIndex === index ? { ...operation, ...patch } : operation,
    ));
  }

  return {
    // files / derived
    files,
    pdfs,
    imageAssets,
    hasCapability,
    capability,
    // project state
    projects,
    project,
    setProject,
    workspaceSession,
    sceneText,
    sceneParagraphs,
    sceneImages,
    sceneVectors,
    sceneFields,
    sceneLinks,
    annotations,
    pageBoxes,
    documentInfo,
    revisions,
    sourceId,
    setSourceId,
    page,
    setPage,
    pageImage,
    operations,
    setOperations,
    tool,
    setTool,
    text,
    setText,
    replacement,
    setReplacement,
    font,
    setFont,
    fontSize,
    setFontSize,
    color,
    setColor,
    fill,
    setFill,
    opacity,
    setOpacity,
    annotationKind,
    setAnnotationKind,
    annotationAuthor,
    setAnnotationAuthor,
    annotationSubject,
    setAnnotationSubject,
    annotationStatus,
    setAnnotationStatus,
    annotationBorder,
    setAnnotationBorder,
    annotationWidth,
    setAnnotationWidth,
    annotationSearch,
    setAnnotationSearch,
    annotationTypeFilter,
    setAnnotationTypeFilter,
    annotationStatusFilter,
    setAnnotationStatusFilter,
    annotationPageFilter,
    setAnnotationPageFilter,
    annotationSort,
    setAnnotationSort,
    hideResolved,
    setHideResolved,
    selectedAnnotationId,
    setSelectedAnnotationId,
    replyText,
    setReplyText,
    attachmentId,
    setAttachmentId,
    audioAnnotationsSupported,
    redactionPattern,
    setRedactionPattern,
    redactionTerms,
    setRedactionTerms,
    redactionMetadata,
    setRedactionMetadata,
    redactionComments,
    setRedactionComments,
    redactionAttachments,
    setRedactionAttachments,
    redactionForms,
    setRedactionForms,
    compareFileId,
    setCompareFileId,
    comparison,
    setComparison,
    comparisonMode,
    setComparisonMode,
    comparisonFilter,
    setComparisonFilter,
    comparisonImages,
    bookmarks,
    embeddedAttachments,
    bookmarkTitle,
    setBookmarkTitle,
    attachmentAssetId,
    setAttachmentAssetId,
    attachmentName,
    setAttachmentName,
    imageId,
    setImageId,
    pageSourceId,
    setPageSourceId,
    pageSourceNumber,
    setPageSourceNumber,
    pageWidthValue,
    setPageWidthValue,
    pageHeightValue,
    setPageHeightValue,
    resizeMode,
    setResizeMode,
    shapeKind,
    setShapeKind,
    formKind,
    setFormKind,
    notice,
    noticeTone,
    setNotice,
    busy,
    // new UI state
    workMode,
    setWorkMode,
    selection,
    selectObject,
    setSelection,
    inlineEdit,
    setInlineEdit,
    zoom,
    setZoom,
    fitRequest,
    fitWidth,
    leftTab,
    setLeftTab,
    leftCollapsed,
    setLeftCollapsed,
    rightCollapsed,
    setRightCollapsed,
    paletteOpen,
    setPaletteOpen,
    toolLock,
    setToolLock,
    searchQuery,
    setSearchQuery,
    theme,
    setTheme,
    density,
    setDensity,
    // derived
    pageInfo,
    pageOps,
    selectedAnnotation,
    pendingOperations,
    // handlers
    createProject,
    saveProject,
    publish,
    historyAction,
    createAnnotationOperation,
    updateAnnotation,
    replyToAnnotation,
    deleteAnnotation,
    applySearchRedaction,
    loadComparisonImages,
    compareDocuments,
    exportComparisonReport,
    applyNavigationOperation,
    downloadEmbeddedAttachment,
    addOperation,
    pageAction,
    movePage,
    reorderPage,
    restoreRevision,
    addDocumentOperation,
    replaceExistingText,
    replaceTextObject,
    beginInlineEdit,
    editExistingImage,
    editExistingVector,
    editExistingFormField,
    editExistingLink,
    importExistingPage,
    updatePageGeometry,
    updateBox,
    removePendingOperation,
    updatePendingOperation,
    runJob,
  };
}

export type StudioApi = ReturnType<typeof useStudio>;
