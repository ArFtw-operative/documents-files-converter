"use client";
import { useEffect, useState } from "react";
import { SELECTION_META } from "./registry";
import type { StudioApi } from "./useStudio";
import type { PdfSceneFormField } from "../types";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="sd-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function StyleControls({ s }: { s: StudioApi }) {
  return (
    <div className="sd-grid2">
      <Field label="Color">
        <input type="color" value={s.color} onChange={(e) => s.setColor(e.target.value)} />
      </Field>
      <Field label="Fill">
        <input type="color" value={s.fill} onChange={(e) => s.setFill(e.target.value)} />
      </Field>
      <label className="sd-field sd-span2">
        <span>Opacity · {Math.round(s.opacity * 100)}%</span>
        <input type="range" min={0} max={1} step={0.05} value={s.opacity} onChange={(e) => s.setOpacity(Number(e.target.value))} />
      </label>
    </div>
  );
}

function TextTypography({ s }: { s: StudioApi }) {
  const fontOption = s.capability("pdf.edit")?.options.fonts as { values?: unknown[] } | undefined;
  const fonts = Array.isArray(fontOption?.values)
    ? fontOption.values.filter((item): item is string => typeof item === "string")
    : ["Helvetica", "Times", "Courier"];
  return (
    <div className="sd-grid2">
      <Field label="Font">
        <>
          <input list="sd-font-families" value={s.font} onChange={(e) => s.setFont(e.target.value)} />
          <datalist id="sd-font-families">
            {fonts.map((family) => <option key={family} value={family} />)}
          </datalist>
        </>
      </Field>
      <Field label="Size">
        <input type="number" min={1} max={500} value={s.fontSize} onChange={(e) => s.setFontSize(Number(e.target.value))} />
      </Field>
    </div>
  );
}

/* ---------------- Selection property panels ---------------- */

function TextProps({ s }: { s: StudioApi }) {
  if (s.selection?.kind !== "text" && s.selection?.kind !== "paragraph") return null;
  const object = s.selection.object;
  const paragraph = s.selection.kind === "paragraph";
  const editable = object.editability !== "Protected" && !object.lock_state;
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{object.style.font || "Unknown font"}</span>
        <span>{Math.round(object.style.font_size || 0)} pt</span>
        <span className="sd-editability">{object.editability}</span>
      </div>
      <p className="sd-current-text">“{object.text}”</p>
      {editable ? (
        <>
          <button className="sd-primary" onClick={() => s.beginInlineEdit(object)}>
            {paragraph ? "Edit paragraph" : "Edit in place"}
          </button>
          <Field label="Replace with">
            {paragraph ? (
              <textarea value={s.replacement} onChange={(e) => s.setReplacement(e.target.value)} placeholder="New paragraph text" />
            ) : (
              <input value={s.replacement} onChange={(e) => s.setReplacement(e.target.value)} placeholder="New wording" />
            )}
          </Field>
          <button
            className="sd-secondary"
            disabled={s.busy || !s.replacement}
            onClick={() => s.replaceTextObject(object, s.replacement)}
          >
            Replace text
          </button>
          <p className="sd-hint">
            {paragraph
              ? "Paragraph lines are reflowed inside the original text box, reducing the font only when needed."
              : "Baseline, size, colour, and font are preserved where the PDF permits. Subset fonts are rebuilt on export."}
          </p>
        </>
      ) : (
        <p className="sd-warn">
          This text is {object.editability.toLowerCase()} — likely a scanned image
          or outlined glyphs. Use OCR mode to recognise it, or add a new text box.
        </p>
      )}
    </div>
  );
}

function LinkProps({ s }: { s: StudioApi }) {
  const selected = s.selection?.kind === "link" ? s.selection.object : null;
  const [uri, setUri] = useState(selected?.properties.uri || "");
  useEffect(() => setUri(selected?.properties.uri || ""), [selected?.id]);
  if (!selected) return null;
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{selected.properties.uri ? "Web link" : `Page ${(selected.properties.page ?? 0) + 1}`}</span>
        <span>{Math.round(selected.bounds[2] - selected.bounds[0])} × {Math.round(selected.bounds[3] - selected.bounds[1])} pt</span>
      </div>
      <Field label="Web address">
        <input value={uri} onChange={(event) => setUri(event.target.value)} placeholder="https://example.com" />
      </Field>
      <button className="sd-primary" disabled={s.busy || !uri} onClick={() => s.editExistingLink(selected, "update", uri)}>Update destination</button>
      <button className="sd-secondary" disabled={s.busy} onClick={() => s.editExistingLink(selected, "delete")}>Delete link</button>
    </div>
  );
}

function ImageProps({ s }: { s: StudioApi }) {
  if (s.selection?.kind !== "image") return null;
  const object = s.selection.object;
  const locked = object.lock_state;
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>
          {Math.round(object.bounds[2] - object.bounds[0])} ×{" "}
          {Math.round(object.bounds[3] - object.bounds[1])} pt
        </span>
        <span className="sd-editability">{object.editability}</span>
      </div>
      <div className="sd-btn-row">
        <button disabled={s.busy || locked} onClick={() => s.editExistingImage(object, "move")}>Move</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingImage(object, "resize")}>Resize</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingImage(object, "rotate")}>Rotate 15°</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingImage(object, "crop")}>Crop 10%</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingImage(object, "delete")}>Delete</button>
      </div>
      <Field label="Replace with asset">
        <select value={s.imageId} onChange={(e) => s.setImageId(e.target.value)}>
          <option value="">Choose an image</option>
          {s.imageAssets.map((asset) => (
            <option key={asset.id} value={asset.id}>{asset.display_name}</option>
          ))}
        </select>
      </Field>
      <button className="sd-secondary" disabled={s.busy || locked || !s.imageId} onClick={() => s.editExistingImage(object, "replace")}>
        Replace image
      </button>
      {locked && <p className="sd-warn">This image is protected and cannot be edited directly.</p>}
    </div>
  );
}

function VectorProps({ s }: { s: StudioApi }) {
  if (s.selection?.kind !== "vector") return null;
  const object = s.selection.object;
  const locked = object.lock_state;
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{object.properties.type || "path"}</span>
        <span className="sd-editability">{object.editability}</span>
      </div>
      <div className="sd-btn-row">
        <button disabled={s.busy || locked} onClick={() => s.editExistingVector(object, "move")}>Move</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingVector(object, "resize")}>Resize</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingVector(object, "rotate")}>Rotate 15°</button>
        <button disabled={s.busy || locked} onClick={() => s.editExistingVector(object, "delete")}>Delete</button>
      </div>
      <StyleControls s={s} />
      <button className="sd-secondary" disabled={s.busy || locked} onClick={() => s.editExistingVector(object, "restyle")}>
        Apply style
      </button>
    </div>
  );
}

function AnnotationProps({ s }: { s: StudioApi }) {
  const annotation = s.selectedAnnotation;
  if (!annotation) return null;
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{annotation.type}</span>
        <span>Page {annotation.page}</span>
        <span className="sd-editability">{annotation.status}</span>
      </div>
      <Field label="Author">
        <input value={s.annotationAuthor} onChange={(e) => s.setAnnotationAuthor(e.target.value)} />
      </Field>
      <Field label="Comment">
        <textarea value={s.text} onChange={(e) => s.setText(e.target.value)} />
      </Field>
      <div className="sd-grid2">
        <Field label="Status">
          <select value={s.annotationStatus} onChange={(e) => s.setAnnotationStatus(e.target.value)}>
            <option value="none">No status</option>
            <option value="open">Open</option>
            <option value="accepted">Accepted</option>
            <option value="rejected">Rejected</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </Field>
        <Field label="Color">
          <input type="color" value={s.color} onChange={(e) => s.setColor(e.target.value)} />
        </Field>
      </div>
      <div className="sd-btn-row">
        <button
          className="sd-secondary"
          disabled={s.busy}
          onClick={() =>
            s.updateAnnotation(annotation, {
              text: s.text,
              author: s.annotationAuthor,
              annotation_status: s.annotationStatus,
              color: s.color,
            })
          }
        >
          Apply
        </button>
        <button disabled={s.busy} onClick={() => s.updateAnnotation(annotation, { annotation_status: "completed" })}>Resolve</button>
        <button disabled={s.busy} onClick={() => s.deleteAnnotation(annotation)}>Delete</button>
      </div>
      <Field label="Reply">
        <textarea value={s.replyText} onChange={(e) => s.setReplyText(e.target.value)} placeholder="Write a reply" />
      </Field>
      <button className="sd-secondary" disabled={s.busy || !s.replyText.trim()} onClick={() => s.replyToAnnotation(annotation)}>
        Add reply
      </button>
    </div>
  );
}

function FormFieldProps({ s, object }: { s: StudioApi; object: PdfSceneFormField }) {
  const flags = Number(object.properties.flags || 0);
  const [value, setValue] = useState(String(object.properties.value ?? ""));
  const [required, setRequired] = useState(Boolean(flags & 2));
  const [readonly, setReadonly] = useState(Boolean(flags & 1));
  useEffect(() => {
    const nextFlags = Number(object.properties.flags || 0);
    setValue(String(object.properties.value ?? ""));
    setRequired(Boolean(nextFlags & 2));
    setReadonly(Boolean(nextFlags & 1));
  }, [object.id, object.properties.value, object.properties.flags]);
  const signature = object.properties.type === "Signature";
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{object.properties.type || "Form field"}</span>
        <span>Page {object.page}</span>
      </div>
      <Field label="Field name"><input value={object.properties.name} readOnly /></Field>
      <Field label="Value">
        <input value={value} disabled={signature} onChange={(event) => setValue(event.target.value)} />
      </Field>
      <label className="sd-check"><input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} /> Required</label>
      <label className="sd-check"><input type="checkbox" checked={readonly} onChange={(event) => setReadonly(event.target.checked)} /> Read only</label>
      <button
        className="sd-primary"
        disabled={s.busy}
        onClick={() => s.editExistingFormField(object, "update", { field_value: value, required, readonly })}
      >
        Apply field changes
      </button>
      <button
        className="sd-secondary"
        disabled={s.busy}
        onClick={() => {
          if (window.confirm(`Delete form field ${object.properties.name}?`))
            void s.editExistingFormField(object, "delete");
        }}
      >
        Delete field
      </button>
    </div>
  );
}

/* ---------------- Mode task panels ---------------- */

function EditPanel({ s }: { s: StudioApi }) {
  if (["watermark", "header_footer", "metadata"].includes(s.tool)) {
    return (
      <div className="sd-section">
        <Field label={s.tool === "metadata" ? "Document title" : "Text ({page} for numbers)"}>
          <input value={s.text} onChange={(e) => s.setText(e.target.value)} />
        </Field>
        {s.tool !== "metadata" && <StyleControls s={s} />}
        <button
          className="sd-primary"
          disabled={s.busy}
          onClick={() =>
            s.addDocumentOperation(
              s.tool === "metadata"
                ? "metadata.set"
                : s.tool === "watermark"
                  ? "watermark.text"
                  : "header_footer",
            )
          }
        >
          Queue for every page
        </button>
        <p className="sd-hint">Applied on Save/Export. Non-destructive until then.</p>
      </div>
    );
  }
  return (
    <div className="sd-section">
      {["text", "link"].includes(s.tool) && (
        <Field label={s.tool === "link" ? "Web address" : "Text"}>
          <input value={s.text} onChange={(e) => s.setText(e.target.value)} />
        </Field>
      )}
      {s.tool === "shape" && (
        <Field label="Shape">
          <select value={s.shapeKind} onChange={(e) => s.setShapeKind(e.target.value)}>
            <option value="rectangle">Rectangle</option>
            <option value="ellipse">Ellipse</option>
            <option value="line">Line</option>
          </select>
        </Field>
      )}
      {["image", "signature"].includes(s.tool) && (
        <Field label="Image asset">
          <select value={s.imageId} onChange={(e) => s.setImageId(e.target.value)}>
            <option value="">Choose an image</option>
            {s.imageAssets.map((asset) => (
              <option key={asset.id} value={asset.id}>{asset.display_name}</option>
            ))}
          </select>
        </Field>
      )}
      {s.tool === "text" && <TextTypography s={s} />}
      {s.tool !== "select" && s.tool !== "edit_text" && <StyleControls s={s} />}
      <p className="sd-hint">
        {s.tool === "select"
          ? "Pick a tool, then click the page to place it. Double-click existing text to edit it in place."
          : s.tool === "edit_text"
            ? "Double-click any highlighted text to edit it directly on the page."
            : "Click on the page to place this element."}
      </p>
    </div>
  );
}

function CommentPanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <div className="sd-grid2">
        <Field label="Author"><input value={s.annotationAuthor} onChange={(e) => s.setAnnotationAuthor(e.target.value)} /></Field>
        <Field label="Subject"><input value={s.annotationSubject} onChange={(e) => s.setAnnotationSubject(e.target.value)} /></Field>
      </div>
      {["comment", "free_text"].includes(s.tool) || s.annotationKind.includes("comment") || s.annotationKind.includes("free_text") ? (
        <Field label="Note text"><textarea value={s.text} onChange={(e) => s.setText(e.target.value)} /></Field>
      ) : null}
      {s.tool === "annotation" && s.annotationKind === "annotate.attachment" && (
        <Field label="Attach vault file">
          <select value={s.attachmentId} onChange={(e) => s.setAttachmentId(e.target.value)}>
            <option value="">Choose a file</option>
            {s.files.map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
          </select>
        </Field>
      )}
      <div className="sd-grid2">
        <Field label="Color"><input type="color" value={s.color} onChange={(e) => s.setColor(e.target.value)} /></Field>
        <Field label="Width"><input type="number" min={0.5} max={20} step={0.5} value={s.annotationWidth} onChange={(e) => s.setAnnotationWidth(Number(e.target.value))} /></Field>
      </div>
      <p className="sd-hint">Click the page to place this comment. It's added to the recoverable history immediately.</p>
    </div>
  );
}

function FormsPanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <Field label="Field name">
        <input value={s.text} onChange={(e) => s.setText(e.target.value)} placeholder="e.g. full_name" />
      </Field>
      <Field label="Default value / choices">
        <input value={s.replacement} onChange={(e) => s.setReplacement(e.target.value)} placeholder={["form.radio", "form.combo", "form.listbox"].includes(s.formKind) ? "Option 1, Option 2" : "Current value"} />
      </Field>
      <TextTypography s={s} />
      <p className="sd-hint">Pick a field type in the toolbar, then click the page to place it.</p>
    </div>
  );
}

function ProtectPanel({ s }: { s: StudioApi }) {
  const [password, setPassword] = useState("");
  const confirmRun = (message: string, op: string, options: Record<string, unknown> = {}) => {
    if (window.confirm(message)) s.runJob(op, "pdf", options);
  };
  return (
    <div className="sd-section">
      <p className="sd-hint">These run on your original source PDF and create a new library file — pending editor changes aren't included.</p>
      <Field label="Password">
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="For encrypt / decrypt" autoComplete="new-password" />
      </Field>
      <div className="sd-btn-col">
        <button className="sd-secondary" disabled={s.busy || !password} onClick={() => s.runJob("pdf.encrypt", "pdf", { password })}>Encrypt (AES-256)</button>
        <button className="sd-secondary" disabled={s.busy || !password} onClick={() => s.runJob("pdf.decrypt", "pdf", { password })}>Decrypt</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => confirmRun("Remove all metadata and XMP from a new copy? This can't be undone on the output.", "pdf.remove_metadata")}>Remove metadata</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => confirmRun("Flatten annotations and form fields into page content? Fields become non-editable in the output.", "pdf.flatten")}>Flatten</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => confirmRun("Sanitise removes JavaScript, embedded files, and hidden active content from a new copy. Continue?", "pdf.sanitize")}>Sanitise</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => confirmRun("Repair rebuilds and cleans the PDF object structure in a new copy. Continue?", "pdf.repair")}>Repair structure</button>
      </div>
      <div className="sd-obj-facts">
        <span>{s.documentInfo?.has_signatures ? "Signed document" : "No signatures"}</span>
        <span>{Object.keys(s.documentInfo?.metadata ?? {}).length} metadata keys</span>
      </div>
    </div>
  );
}

function RedactPanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <ol className="sd-steps">
        <li>Mark areas with the toolbar tool, or find patterns below</li>
        <li>Review marks on the page</li>
        <li>Apply — underlying text and pixels are removed</li>
        <li>Export validates nothing sensitive remains</li>
      </ol>
      <Field label="Find pattern">
        <select value={s.redactionPattern} onChange={(e) => s.setRedactionPattern(e.target.value)}>
          <option value="keyword">Keyword list</option>
          <option value="name">Person names</option>
          <option value="email">Email addresses</option>
          <option value="phone">Phone numbers</option>
          <option value="account">Account numbers</option>
          <option value="credit_card">Credit-card patterns</option>
          <option value="national_id">National identifiers</option>
          <option value="ip">IP addresses</option>
          <option value="date">Dates</option>
          <option value="custom_regex">Custom regular expression</option>
        </select>
      </Field>
      <Field label="Keywords (comma or line separated)">
        <textarea value={s.redactionTerms} onChange={(e) => s.setRedactionTerms(e.target.value)} />
      </Field>
      {s.redactionPattern === "custom_regex" && (
        <Field label="Regular expression">
          <input value={s.replacement} onChange={(e) => s.setReplacement(e.target.value)} />
        </Field>
      )}
      <label className="sd-check"><input type="checkbox" checked={s.redactionMetadata} onChange={(e) => s.setRedactionMetadata(e.target.checked)} /> Remove metadata & XMP</label>
      <label className="sd-check"><input type="checkbox" checked={s.redactionComments} onChange={(e) => s.setRedactionComments(e.target.checked)} /> Remove comments & replies</label>
      <label className="sd-check"><input type="checkbox" checked={s.redactionAttachments} onChange={(e) => s.setRedactionAttachments(e.target.checked)} /> Remove embedded attachments</label>
      <label className="sd-check"><input type="checkbox" checked={s.redactionForms} onChange={(e) => s.setRedactionForms(e.target.checked)} /> Clear form values</label>
      <button className="sd-primary" disabled={s.busy} onClick={() => { if (window.confirm("Apply redaction? Matched content is permanently removed from the exported copy — this can't be undone once exported.")) s.applySearchRedaction(); }}>
        Review & apply redaction
      </button>
    </div>
  );
}

function ComparePanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <Field label="Compare with">
        <select value={s.compareFileId} onChange={(e) => s.setCompareFileId(e.target.value)}>
          <option value="">Choose another PDF</option>
          {s.pdfs.filter((f) => f.id !== s.project?.source_file_id).map((f) => (
            <option key={f.id} value={f.id}>{f.display_name}</option>
          ))}
        </select>
      </Field>
      <button className="sd-primary" disabled={s.busy || !s.compareFileId} onClick={s.compareDocuments}>Run comparison</button>
      {s.comparison && (
        <>
          <div className="sd-grid2">
            <Field label="View">
              <select value={s.comparisonMode} onChange={(e) => s.setComparisonMode(e.target.value)}>
                <option value="side-by-side">Side by side</option>
                <option value="overlay">Difference overlay</option>
              </select>
            </Field>
            <Field label="Type">
              <select value={s.comparisonFilter} onChange={(e) => s.setComparisonFilter(e.target.value)}>
                <option value="">All differences</option>
                {Object.keys(s.comparison.summary.by_type).sort().map((k) => <option key={k}>{k}</option>)}
              </select>
            </Field>
          </div>
          <div className="sd-diff-list">
            {s.comparison.differences.filter((d) => !s.comparisonFilter || d.type === s.comparisonFilter).map((d) => (
              <button key={d.id} className={d.reviewed ? "reviewed" : ""} onClick={() => {
                s.setComparison(s.comparison ? { ...s.comparison, differences: s.comparison.differences.map((x) => x.id === d.id ? { ...x, reviewed: !x.reviewed } : x) } : s.comparison);
                void s.loadComparisonImages(s.comparison!.after_file_id, d.after_page || d.before_page || 1);
              }}>
                <b>{d.type.replaceAll("_", " ")}</b>
                <small>Before {d.before_page || "—"} · After {d.after_page || "—"}</small>
              </button>
            ))}
          </div>
          <button className="sd-secondary" onClick={s.exportComparisonReport}>Export report (JSON)</button>
        </>
      )}
    </div>
  );
}

function ConvertPanel({ s }: { s: StudioApi }) {
  const [pages, setPages] = useState("1-1");
  const [mergeId, setMergeId] = useState("");
  return (
    <div className="sd-section">
      <p className="sd-hint">Jobs run on your original source PDF and appear in your library and Jobs.</p>
      <div className="sd-btn-col">
        <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.compress", "pdf", { preset: "balanced", remove_metadata: true })}>Compress</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.split", "zip", { pages: "every" })}>Split every page</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.render_all", "zip", { format: "png", dpi: 150 })}>Render all to images</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.extract_images", "zip", {})}>Extract images</button>
        <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.extract_text", "txt", {})}>Extract text</button>
      </div>
      <Field label="Extract pages (e.g. 1-3,5)">
        <input value={pages} onChange={(e) => setPages(e.target.value)} />
      </Field>
      <button className="sd-secondary" disabled={s.busy} onClick={() => s.runJob("pdf.extract_pages", "pdf", { pages })}>Extract pages</button>
      <Field label="Merge with">
        <select value={mergeId} onChange={(e) => setMergeId(e.target.value)}>
          <option value="">Choose another PDF</option>
          {s.pdfs.filter((f) => f.id !== s.project?.source_file_id).map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
        </select>
      </Field>
      <button className="sd-secondary" disabled={s.busy || !mergeId} onClick={() => s.runJob("pdf.merge", "pdf", {}, [mergeId])}>Merge</button>
    </div>
  );
}

function OcrPanel({ s }: { s: StudioApi }) {
  const option = s.capability("pdf.ocr")?.options.language as
    | { enum?: unknown[]; default?: unknown }
    | undefined;
  const languages = Array.isArray(option?.enum)
    ? option.enum.filter((item): item is string => typeof item === "string")
    : ["eng"];
  const [language, setLanguage] = useState(
    typeof option?.default === "string" ? option.default : languages[0] || "eng",
  );
  const labels: Record<string, string> = {
    eng: "English", fra: "French", deu: "German", spa: "Spanish", ara: "Arabic",
    osd: "Orientation detection",
  };
  return (
    <div className="sd-section">
      <p className="sd-hint">Makes scanned pages searchable with the OCR engine installed on this server. Existing searchable pages are preserved.</p>
      <Field label="Language">
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          {languages.map((code) => <option key={code} value={code}>{labels[code] || code}</option>)}
        </select>
      </Field>
      <button className="sd-primary" disabled={s.busy} onClick={() => s.runJob("pdf.ocr", "pdf", { language, deskew: true, rotate_pages: true })}>Make searchable</button>
    </div>
  );
}

function SignPanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <p className="sd-warn">Places a <b>visual</b> signature image. Certificate/PKI digital signing isn't available in this build.</p>
      <Field label="Signature image asset">
        <select value={s.imageId} onChange={(e) => s.setImageId(e.target.value)}>
          <option value="">Choose an image</option>
          {s.imageAssets.map((asset) => <option key={asset.id} value={asset.id}>{asset.display_name}</option>)}
        </select>
      </Field>
      <p className="sd-hint">Select the Place Signature tool, then click where it should appear.</p>
    </div>
  );
}

function ViewPanel({ s }: { s: StudioApi }) {
  return (
    <div className="sd-section">
      <div className="sd-obj-facts">
        <span>{s.pageInfo?.fonts.length || 0} fonts</span>
        <span>{s.pageInfo?.images || 0} images</span>
        <span>{s.pageInfo?.links || 0} links</span>
        <span>{s.pageInfo?.annotations || 0} annotations</span>
      </div>
      {!!s.pageInfo?.subset_fonts.length && (
        <p className="sd-hint">Subset fonts on this page: {s.pageInfo.subset_fonts.join(", ")}</p>
      )}
      <p className="sd-hint">Use Edit or Comment mode to change the page. Double-click any text to edit it in place.</p>
      {!!s.pendingOperations.length && (
        <div className="sd-section">
          <h4>Pending edits</h4>
          <p className="sd-hint">These edits are saved only after the PDF engine proves they can be applied.</p>
          {s.pendingOperations.map(({ operation, index }) => (
            <div className="sd-list-row-flat" key={`${operation.kind}-${index}`}>
              <span>{operation.kind.replaceAll(".", " ")}</span>
              <button
                className="sd-del"
                title="Remove pending edit"
                onClick={() => s.removePendingOperation(index)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Inspector({ s }: { s: StudioApi }) {
  const sel = s.selection;
  let title = "Properties";
  let body: React.ReactNode;

  if (sel?.kind === "text") { title = SELECTION_META.text.label; body = <TextProps s={s} />; }
  else if (sel?.kind === "paragraph") { title = SELECTION_META.paragraph.label; body = <TextProps s={s} />; }
  else if (sel?.kind === "link") { title = SELECTION_META.link.label; body = <LinkProps s={s} />; }
  else if (sel?.kind === "image") { title = SELECTION_META.image.label; body = <ImageProps s={s} />; }
  else if (sel?.kind === "vector") { title = SELECTION_META.vector.label; body = <VectorProps s={s} />; }
  else if (sel?.kind === "form_field") { title = SELECTION_META.form_field.label; body = <FormFieldProps s={s} object={sel.object} />; }
  else if (sel?.kind === "annotation") { title = "Annotation"; body = <AnnotationProps s={s} />; }
  else {
    switch (s.workMode) {
      case "edit": title = "Edit"; body = <EditPanel s={s} />; break;
      case "comment": title = "Comment"; body = <CommentPanel s={s} />; break;
      case "forms": title = "Form field"; body = <FormsPanel s={s} />; break;
      case "protect": title = "Protect"; body = <ProtectPanel s={s} />; break;
      case "redact": title = "Redact"; body = <RedactPanel s={s} />; break;
      case "compare": title = "Compare"; body = <ComparePanel s={s} />; break;
      case "convert": title = "Convert"; body = <ConvertPanel s={s} />; break;
      case "ocr": title = "OCR"; body = <OcrPanel s={s} />; break;
      case "sign": title = "Sign"; body = <SignPanel s={s} />; break;
      default: title = "View"; body = <ViewPanel s={s} />;
    }
  }

  return (
    <aside className="sd-inspector">
      <header className="sd-inspector-head">
        <span>{title}</span>
        {sel && (
          <button className="sd-icon" title="Clear selection" onClick={() => s.setSelection(null)}>×</button>
        )}
      </header>
      <div className="sd-inspector-body">{body}</div>
    </aside>
  );
}
