import { describe, expect, it } from "vitest";
import {
  caretIndex,
  invert,
  multiply,
  pdfPointToViewport,
  pdfRectToViewport,
  quadContains,
  textFrameToViewport,
  viewportPointToPdf,
  apply,
  type Matrix,
} from "./index";

// PDF.js viewport for a 595x842 page at scale 1.5, rotation 0: [s,0,0,-s,0,h*s]
const portrait: Matrix = [1.5, 0, 0, -1.5, 0, 842 * 1.5];
// Same page rotated 90° clockwise: [0, s, s, 0, 0, 0]
const rotated90: Matrix = [0, 1.5, 1.5, 0, 0, 0];

const close = (a: readonly number[], b: readonly number[]) =>
  a.forEach((v, i) => expect(v).toBeCloseTo(b[i], 6));

describe("coordinate engine", () => {
  it("round-trips points through the viewport", () => {
    for (const m of [portrait, rotated90]) {
      const screen = pdfPointToViewport(m, [100, 700]);
      close(viewportPointToPdf(m, screen), [100, 700]);
    }
  });

  it("maps the PDF origin to the bottom-left of an unrotated page", () => {
    close(pdfPointToViewport(portrait, [0, 0]), [0, 1263]);
    close(pdfPointToViewport(portrait, [595, 842]), [892.5, 0]);
  });

  it("produces rotation-safe rect bounds", () => {
    close(pdfRectToViewport(rotated90, [10, 20, 30, 60]), [30, 15, 90, 45]);
  });

  it("inverts and composes matrices", () => {
    close(multiply(portrait, invert(portrait)), [1, 0, 0, 1, 0, 0]);
  });

  it("tests points inside quads", () => {
    const quad = [0, 0, 10, 0, 10, 5, 0, 5];
    expect(quadContains(quad, [5, 2])).toBe(true);
    expect(quadContains(quad, [11, 2])).toBe(false);
  });

  it("builds a text frame whose local y points down from the baseline", () => {
    const frame = textFrameToViewport(portrait, [100, 700], 0);
    close(apply(frame, [0, 0]), pdfPointToViewport(portrait, [100, 700]));
    // 10pt above the baseline (local y = -10) is higher on screen (smaller y).
    expect(apply(frame, [0, -10])[1]).toBeLessThan(apply(frame, [0, 0])[1]);
    // Rotated text (90° CCW) advances upward on screen.
    const up = textFrameToViewport(portrait, [300, 400], 90);
    expect(apply(up, [10, 0])[1]).toBeLessThan(apply(up, [0, 0])[1]);
  });

  it("places the caret at the nearest glyph boundary", () => {
    const glyphs = [0, 1, 2].map((i) => [i * 6, 0, i * 6 + 6, 0, i * 6 + 6, 8, i * 6, 8]);
    expect(caretIndex([1, 3], [0, 0], 0, glyphs)).toBe(0);
    expect(caretIndex([7, 3], [0, 0], 0, glyphs)).toBe(1);
    expect(caretIndex([17, 3], [0, 0], 0, glyphs)).toBe(3);
  });
});
