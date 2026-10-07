/**
 * The single coordinate engine (architecture §8.3).
 *
 * Canonical geometry is PDF user space (points, bottom-left origin, unrotated page). A PDF.js
 * viewport supplies `transform` = [a, b, c, d, e, f], mapping PDF user space to CSS pixels and
 * already accounting for page rotation, crop box and zoom. Every component converts through these
 * functions; nothing else does coordinate math.
 */

export type Matrix = readonly [number, number, number, number, number, number];
export type Point = readonly [number, number];
/** [x0, y0, x1, y1] */
export type Rect = readonly [number, number, number, number];
/** [x0,y0, x1,y1, x2,y2, x3,y3]: baseline-start, baseline-end, end-top, start-top. */
export type Quad = readonly number[];

export function apply(m: Matrix, [x, y]: Point): Point {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

export function invert(m: Matrix): Matrix {
  const det = m[0] * m[3] - m[1] * m[2];
  if (Math.abs(det) < 1e-12) throw new Error("Singular viewport matrix");
  const a = m[3] / det;
  const b = -m[1] / det;
  const c = -m[2] / det;
  const d = m[0] / det;
  return [a, b, c, d, -(a * m[4] + c * m[5]), -(b * m[4] + d * m[5])];
}

/** Matrix product: apply `first`, then `second`. */
export function multiply(first: Matrix, second: Matrix): Matrix {
  return [
    first[0] * second[0] + first[1] * second[2],
    first[0] * second[1] + first[1] * second[3],
    first[2] * second[0] + first[3] * second[2],
    first[2] * second[1] + first[3] * second[3],
    first[4] * second[0] + first[5] * second[2] + second[4],
    first[4] * second[1] + first[5] * second[3] + second[5],
  ];
}

export function pdfPointToViewport(viewport: Matrix, point: Point): Point {
  return apply(viewport, point);
}

export function viewportPointToPdf(viewport: Matrix, point: Point): Point {
  return apply(invert(viewport), point);
}

function bounds(points: Point[]): Rect {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

function corners([x0, y0, x1, y1]: Rect): Point[] {
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
}

/** Axis-aligned bounds of a PDF rect on screen (rotation-safe). */
export function pdfRectToViewport(viewport: Matrix, rect: Rect): Rect {
  return bounds(corners(rect).map((p) => apply(viewport, p)));
}

export function viewportRectToPdf(viewport: Matrix, rect: Rect): Rect {
  const inverse = invert(viewport);
  return bounds(corners(rect).map((p) => apply(inverse, p)));
}

export function quadPoints(quad: Quad): Point[] {
  return [0, 2, 4, 6].map((i) => [quad[i], quad[i + 1]] as Point);
}

export function quadToViewport(viewport: Matrix, quad: Quad): Point[] {
  return quadPoints(quad).map((p) => apply(viewport, p));
}

export function quadBounds(quad: Quad): Rect {
  return bounds(quadPoints(quad));
}

/** Point-in-convex-quad test (PDF space). */
export function quadContains(quad: Quad, [x, y]: Point, tolerance = 0): boolean {
  const pts = quadPoints(quad);
  let sign = 0;
  for (let i = 0; i < 4; i++) {
    const [ax, ay] = pts[i];
    const [bx, by] = pts[(i + 1) % 4];
    const edge = Math.hypot(bx - ax, by - ay) || 1;
    const cross = ((bx - ax) * (y - ay) - (by - ay) * (x - ax)) / edge;
    if (Math.abs(cross) <= tolerance) continue;
    const s = Math.sign(cross);
    if (sign === 0) sign = s;
    else if (s !== sign) return false;
  }
  return true;
}

/**
 * CSS `matrix(...)` that maps a local text frame to the screen: local x runs along the baseline in
 * points, local y points *down* from the baseline (CSS convention), origin at the baseline start.
 * `rotationDeg` is the counter-clockwise text angle in PDF space.
 */
export function textFrameToViewport(viewport: Matrix, origin: Point, rotationDeg: number): Matrix {
  const r = (rotationDeg * Math.PI) / 180;
  const cos = Math.cos(r);
  const sin = Math.sin(r);
  // Local frame -> PDF: x along (cos, sin), CSS-down = -(up) = (sin, -cos).
  const local: Matrix = [cos, sin, sin, -cos, origin[0], origin[1]];
  return multiply(local, viewport);
}

export function cssMatrix(m: Matrix): string {
  return `matrix(${m.map((v) => +v.toFixed(6)).join(",")})`;
}

/** Distance along a baseline direction, for caret placement. */
export function projectOnBaseline(point: Point, origin: Point, rotationDeg: number): number {
  const r = (rotationDeg * Math.PI) / 180;
  return (point[0] - origin[0]) * Math.cos(r) + (point[1] - origin[1]) * Math.sin(r);
}

/**
 * Caret index for a click (§11.2): project the PDF point onto the run's baseline and pick the
 * nearest glyph boundary. `glyphQuads` are the run's glyph quads in reading order.
 */
export function caretIndex(point: Point, origin: Point, rotationDeg: number, glyphQuads: Quad[]): number {
  if (glyphQuads.length === 0) return 0;
  const t = projectOnBaseline(point, origin, rotationDeg);
  let best = 0;
  let bestDistance = Infinity;
  for (let i = 0; i <= glyphQuads.length; i++) {
    const boundary =
      i < glyphQuads.length
        ? projectOnBaseline([glyphQuads[i][0], glyphQuads[i][1]], origin, rotationDeg)
        : projectOnBaseline([glyphQuads[i - 1][2], glyphQuads[i - 1][3]], origin, rotationDeg);
    const distance = Math.abs(boundary - t);
    if (distance < bestDistance) {
      best = i;
      bestDistance = distance;
    }
  }
  return best;
}
