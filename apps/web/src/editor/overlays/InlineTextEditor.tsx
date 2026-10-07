import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import type { SceneObject } from "@folio/scene-schema";
import type { TextFrame } from "./textLayout";

function anchorStyle(frame: TextFrame, ratio: number): CSSProperties {
  const origin = frame.align === "right" ? "right" : frame.align === "center" ? "center" : "left";
  const left = frame.align === "right" ? frame.advance : frame.align === "center" ? frame.advance / 2 : 0;
  const shift = frame.align === "right" ? "translateX(-100%) " : frame.align === "center" ? "translateX(-50%) " : "";
  return {
    position: "absolute",
    left,
    top: -frame.ascent,
    height: frame.ascent - frame.descent,
    lineHeight: `${frame.ascent - frame.descent}px`,
    transform: `${shift}scaleX(${ratio})`,
    transformOrigin: `${origin} center`,
  };
}

export function textStyle(frame: TextFrame, family: string, ratio: number): CSSProperties {
  return {
    ...anchorStyle(frame, ratio),
    fontFamily: family,
    fontSize: `${frame.size}px`,
    fontWeight: frame.weight,
    fontStyle: frame.italic ? "italic" : "normal",
    letterSpacing: `${frame.letterSpacing}px`,
    color: frame.color,
    whiteSpace: "pre",
  };
}

/** Covers the original glyphs while the browser preview shows the edited text (§12.1 step 1). */
export function Mask({ frame, background }: { frame: TextFrame; background: string }) {
  return (
    <div aria-hidden style={{ position: "absolute", left: -0.8, top: -frame.ascent - 0.6,
      width: frame.advance + 1.6, height: frame.ascent - frame.descent + 1.2, background }} />
  );
}

/** Read-only optimistic text shown after commit until the canonical revision renders (§12.2). */
export function TextPreview({ frame, family, ratio, background, text }: {
  frame: TextFrame; family: string; ratio: number; background: string; text: string;
}) {
  return (
    <div style={{ position: "absolute", left: 0, top: 0, transform: frame.transform, transformOrigin: "0 0", pointerEvents: "none" }}>
      <Mask frame={frame} background={background} />
      <div style={textStyle(frame, family, ratio)}>{text}</div>
    </div>
  );
}

interface Props {
  obj: SceneObject;
  frame: TextFrame;
  family: string;
  ratio: number;
  background: string;
  caret: number;
  busy: boolean;
  onCommit: (text: string) => void;
  onCancel: () => void;
  onTab?: (backwards: boolean, text: string) => void;
}

/** The focused DOM editor placed exactly over the run, in the run's own transform (§12.1). */
export function InlineTextEditor({ obj, frame, family, ratio, background, caret, busy, onCommit, onCancel, onTab }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const done = useRef(false);
  const [initial] = useState(obj.content.text ?? "");

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = initial;
    el.focus({ preventScroll: true });
    const node = el.firstChild;
    if (node) {
      const range = document.createRange();
      const offset = Math.min(caret, node.textContent?.length ?? 0);
      range.setStart(node, offset);
      range.collapse(true);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
  }, [caret, initial]);

  useEffect(() => {
    // Re-armed on every mount (StrictMode mounts, unmounts and remounts in development).
    done.current = false;
    return () => {
      done.current = true;
    };
  }, []);

  function finish(commit: boolean) {
    if (done.current) return;
    const text = (ref.current?.textContent ?? "").replace(/ /g, " ");
    if (!commit || text === initial) {
      done.current = true;
      onCancel();
      return;
    }
    done.current = true;
    onCommit(text);
  }

  function onKeyDown(event: KeyboardEvent) {
    event.stopPropagation();
    if (event.key === "Enter") {
      event.preventDefault();
      finish(true);
    } else if (event.key === "Escape") {
      event.preventDefault();
      finish(false);
    } else if (event.key === "Tab" && onTab) {
      event.preventDefault();
      done.current = true;
      onTab(event.shiftKey, (ref.current?.textContent ?? "").replace(/ /g, " "));
    } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
      event.preventDefault();
      const selection = window.getSelection();
      if (ref.current && selection) selection.selectAllChildren(ref.current);
    }
  }

  return (
    <div style={{ position: "absolute", left: 0, top: 0, transform: frame.transform, transformOrigin: "0 0", zIndex: 4 }}>
      <Mask frame={frame} background={background} />
      <div
        ref={ref}
        role="textbox"
        aria-label="Edit text"
        aria-busy={busy}
        contentEditable={!busy}
        suppressContentEditableWarning
        spellCheck={false}
        className="inline-editor"
        style={{ ...textStyle(frame, family, ratio), minWidth: 2,
          boxShadow: "0 0 0 1px rgb(37 99 235 / 0.9)", borderRadius: 1, background }}
        onKeyDown={onKeyDown}
        onBlur={() => finish(true)}
        onPaste={(event) => {
          event.preventDefault();
          const text = event.clipboardData.getData("text/plain").replace(/[\r\n]+/g, " ");
          document.execCommand("insertText", false, text);
        }}
        onDrop={(event) => event.preventDefault()}
      />
    </div>
  );
}
