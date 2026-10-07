import type { SceneObject } from "@folio/scene-schema";
import { cssMatrix, pdfRectToViewport, textFrameToViewport, type Matrix } from "@folio/coordinate-engine";

/** Geometry + CSS for drawing a text run in its own baseline frame (preview only, §12.1). */
export interface TextFrame {
  transform: string;
  size: number;
  ascent: number;
  descent: number;
  advance: number;
  align: "left" | "right" | "center";
  color: string;
  weight: number;
  italic: boolean;
  letterSpacing: number;
}

export function textFrame(viewport: Matrix, obj: SceneObject): TextFrame {
  const style = obj.style;
  const size = Number(style.size_pt ?? 10);
  const origin = obj.content.baseline_origin ?? [obj.bbox[0], obj.bbox[1]];
  return {
    transform: cssMatrix(textFrameToViewport(viewport, origin, Number(style.rotation_deg ?? 0))),
    size,
    ascent: Number(style.ascender ?? 0.9) * size,
    descent: Number(style.descender ?? -0.2) * size,
    advance: Number(obj.content.advance_pt ?? obj.bbox[2] - obj.bbox[0]),
    align: (style.text_align as TextFrame["align"]) ?? "left",
    color: (style.fill as string) ?? (style.stroke as string) ?? "#000000",
    weight: style.bold ? 700 : 400,
    italic: !!style.italic,
    letterSpacing: Number(style.letter_spacing_pt ?? 0),
  };
}

/**
 * Background colour around a run on the rendered canvas, used to mask the original glyphs during
 * local preview. Samples a ring just outside the run and keeps the most common light colour.
 */
export function sampleBackground(canvas: HTMLCanvasElement | null, viewport: Matrix, obj: SceneObject): string {
  if (!canvas) return "#ffffff";
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return "#ffffff";
  const ratio = canvas.width / (parseFloat(canvas.style.width) || canvas.width);
  const [x0, y0, x1, y1] = pdfRectToViewport(viewport, obj.bbox);
  const pad = 3;
  const points: Array<[number, number]> = [];
  for (let i = 0; i <= 8; i++) {
    const x = x0 + ((x1 - x0) * i) / 8;
    points.push([x, y0 - pad], [x, y1 + pad]);
  }
  points.push([x0 - pad, (y0 + y1) / 2], [x1 + pad, (y0 + y1) / 2]);
  const counts = new Map<string, number>();
  for (const [x, y] of points) {
    const px = Math.round(x * ratio);
    const py = Math.round(y * ratio);
    if (px < 0 || py < 0 || px >= canvas.width || py >= canvas.height) continue;
    const [r, g, b] = context.getImageData(px, py, 1, 1).data;
    const key = `${r & 0xf8},${g & 0xf8},${b & 0xf8}`;
    counts.set(key, (counts.get(key) ?? 0) + 1 + (r + g + b) / 765);
  }
  let best = "248,248,248";
  let score = -1;
  for (const [key, value] of counts) if (value > score) [best, score] = [key, value];
  return `rgb(${best})`;
}

const measurer = typeof document !== "undefined" ? document.createElement("canvas").getContext("2d") : null;

/** Horizontal scale so the preview font reproduces the original run width. */
export function fitRatio(text: string, frame: TextFrame, family: string): number {
  if (!measurer || !text) return 1;
  measurer.font = `${frame.italic ? "italic " : ""}${frame.weight} ${frame.size}px ${family}`;
  const measured = measurer.measureText(text).width + frame.letterSpacing * Math.max(0, text.length - 1);
  if (!measured) return 1;
  return Math.min(1.6, Math.max(0.6, frame.advance / measured));
}
