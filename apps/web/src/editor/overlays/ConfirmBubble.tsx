import { useEffect, useRef } from "react";

export interface BubbleAction {
  label: string;
  primary?: boolean;
  run: () => void;
}

/** Small anchored prompt for recoverable edit outcomes (§68 failure handling). */
export function ConfirmBubble({ x, y, message, actions, onDismiss }: {
  x: number; y: number; message: string; actions: BubbleAction[]; onDismiss: () => void;
}) {
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => first.current?.focus(), []);
  return (
    <div role="alertdialog" aria-label="Edit needs attention" className="chrome border rounded-lg shadow-xl p-3 text-xs space-y-2"
      style={{ position: "absolute", left: Math.max(4, x), top: y, zIndex: 6, maxWidth: 340 }}
      onClick={(e) => e.stopPropagation()} onDoubleClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => { e.stopPropagation(); if (e.key === "Escape") onDismiss(); }}>
      <p>{message}</p>
      <div className="flex gap-2 justify-end">
        {actions.map((action, i) => (
          <button key={action.label} ref={i === 0 ? first : undefined} className={`btn !h-7 ${action.primary ? "btn-primary" : ""}`}
            onClick={action.run}>{action.label}</button>
        ))}
      </div>
    </div>
  );
}
