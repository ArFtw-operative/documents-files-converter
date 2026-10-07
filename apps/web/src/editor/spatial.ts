/** Per-page R-tree and candidate ranking for click-anywhere hit testing (architecture §11.1). */
import RBush from "rbush";
import type { PageScene, SceneObject } from "@folio/scene-schema";
import { quadContains, type Point } from "@folio/coordinate-engine";
import type { Tool } from "./stores";

interface Entry {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  obj: SceneObject;
}

const INTERACTIVE = new Set(["TEXT_NATIVE", "TEXT_OCR", "TEXT_HANDWRITING", "IMAGE", "INK_ANNOTATION",
  "ANNOTATION_TEXT", "ANNOTATION_HIGHLIGHT", "LINK"]);

export class PageIndex {
  private tree = new RBush<Entry>();

  constructor(public scene: PageScene) {
    this.tree.load(
      scene.objects
        .filter((o) => INTERACTIVE.has(o.type) && !(o.type === "TEXT_NATIVE" && o.style.render_mode === "invisible"))
        .map((obj) => ({ minX: obj.bbox[0], minY: obj.bbox[1], maxX: obj.bbox[2], maxY: obj.bbox[3], obj })),
    );
  }

  /** Ranked candidates under a PDF-space point (§11.1 ranking rules). */
  candidates(point: Point, tool: Tool, tolerance: number): SceneObject[] {
    const [x, y] = point;
    const hits = this.tree.search({ minX: x - tolerance, minY: y - tolerance, maxX: x + tolerance, maxY: y + tolerance });
    const scored = hits.map(({ obj }) => {
      const textTool = tool === "edit";
      const compatible = textTool ? obj.editable && obj.type.startsWith("TEXT") : true;
      const exact = obj.quad ? quadContains(obj.quad, point) : x >= obj.bbox[0] && x <= obj.bbox[2] && y >= obj.bbox[1] && y <= obj.bbox[3];
      const glyph = !!obj.content.glyphs?.some((g) => !g.synthetic && quadContains(g.quad, point));
      const area = (obj.bbox[2] - obj.bbox[0]) * (obj.bbox[3] - obj.bbox[1]);
      return { obj, key: [compatible ? 0 : 1, exact ? 0 : 1, glyph ? 0 : 1, area, -obj.z_index, -obj.confidence,
        obj.source === "PDF_NATIVE" ? 0 : 1] };
    });
    scored.sort((a, b) => {
      for (let i = 0; i < a.key.length; i++) if (a.key[i] !== b.key[i]) return a.key[i] - b.key[i];
      return 0;
    });
    return scored.map((s) => s.obj);
  }
}

const indexes = new WeakMap<PageScene, PageIndex>();

export function pageIndex(scene: PageScene): PageIndex {
  let index = indexes.get(scene);
  if (!index) {
    index = new PageIndex(scene);
    indexes.set(scene, index);
  }
  return index;
}
