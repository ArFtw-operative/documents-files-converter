import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { DocumentEvent } from "@folio/scene-schema";
import { keys } from "../api/queries";
import { useJobs } from "./stores";

/** Realtime channel (architecture §29) with reconnect backoff. Events only trigger refetches;
 * the database stays the source of truth. */
export function useDocumentEvents(documentId: string, onReconnect: () => void) {
  const client = useQueryClient();
  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let attempt = 0;
    let timer: number | undefined;
    let ping: number | undefined;

    const connect = () => {
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/documents/${documentId}/events`);
      socket.onopen = () => {
        if (attempt > 0) onReconnect();
        attempt = 0;
        ping = window.setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 25_000);
      };
      socket.onmessage = (message) => {
        let event: DocumentEvent;
        try {
          event = JSON.parse(message.data);
        } catch {
          return;
        }
        switch (event.event) {
          case "revision.created":
          case "operation.committed":
          case "document.analysis.completed":
            client.invalidateQueries({ queryKey: keys.document(documentId) });
            client.invalidateQueries({ queryKey: keys.revisions(documentId) });
            break;
          case "page.scene.updated":
            client.invalidateQueries({ queryKey: keys.document(documentId) });
            break;
          case "document.analysis.started":
            useJobs.getState().setAnalysis("running");
            break;
        }
        if (event.event === "document.analysis.completed") useJobs.getState().setAnalysis("idle");
      };
      socket.onclose = () => {
        window.clearInterval(ping);
        if (closed) return;
        attempt++;
        timer = window.setTimeout(connect, Math.min(15_000, 500 * 2 ** attempt));
      };
    };
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      socket?.close();
    };
  }, [client, documentId, onReconnect]);
}
