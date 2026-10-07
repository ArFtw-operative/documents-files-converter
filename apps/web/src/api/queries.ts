import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import type { DocumentDetail, PageScene } from "@folio/scene-schema";
import { api } from "./client";

export interface SessionUser {
  id: string;
  email: string;
  display_name: string;
  role: "admin" | "user";
  mfa_enabled: boolean;
  must_change_password: boolean;
  quota_bytes: number;
  preferences: Record<string, unknown>;
}

export interface AuthState {
  setup_required: boolean;
  registration_open: boolean;
  user: SessionUser | null;
  app_name: string;
}

export interface DocumentSummary {
  id: string;
  name: string;
  status: string;
  error: string | null;
  page_count: number;
  current_revision: number;
  size: number;
  updated_at: string;
  created_at: string;
}

export interface Revision {
  revision: number;
  parent_revision: number | null;
  kind: "original" | "edit" | "undo" | "redo" | "restore";
  size: number;
  sha256: string;
  page_count: number;
  created_at: string;
  current: boolean;
}

export const keys = {
  auth: ["auth"] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["document", id] as const,
  revisions: (id: string) => ["revisions", id] as const,
  scene: (id: string, pageId: string, version: number, diagnostics = false) =>
    ["scene", id, pageId, version, diagnostics] as const,
};

export function useAuthState() {
  return useQuery({ queryKey: keys.auth, queryFn: () => api<AuthState>("/api/v1/auth/state"), staleTime: 60_000 });
}

export function useDocuments() {
  return useQuery({
    queryKey: keys.documents,
    queryFn: () =>
      api<{ documents: DocumentSummary[]; usage_bytes: number; quota_bytes: number }>("/api/v1/documents"),
  });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: keys.document(id),
    queryFn: () => api<DocumentDetail>(`/api/v1/documents/${id}`),
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 1000 : false),
  });
}

export function useRevisions(id: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.revisions(id),
    queryFn: () => api<Revision[]>(`/api/v1/documents/${id}/revisions`),
    enabled,
  });
}

/** Scenes are keyed by page *version*, which is immutable, so they never go stale. */
export function useScene(documentId: string, pageId: string | undefined, version: number | undefined,
                         enabled: boolean, diagnostics = false) {
  return useQuery({
    queryKey: keys.scene(documentId, pageId ?? "", version ?? 0, diagnostics),
    queryFn: () =>
      api<PageScene>(`/api/v1/documents/${documentId}/pages/${pageId}/scene?version=${version}${diagnostics ? "&diagnostics=true" : ""}`),
    enabled: enabled && !!pageId && !!version,
    staleTime: Infinity,
    gcTime: 10 * 60_000,
    retry: 1,
    // A page keeps its previous version's geometry visible while the edited version is analysed.
    placeholderData: keepPreviousData,
  });
}

export function useInvalidateDocument(id: string) {
  const client = useQueryClient();
  return () => {
    client.invalidateQueries({ queryKey: keys.document(id) });
    client.invalidateQueries({ queryKey: keys.revisions(id) });
    client.invalidateQueries({ queryKey: keys.documents });
  };
}
