// Browser vertical slice (architecture §82) against a running dev stack.
// Usage: BASE_URL=http://127.0.0.1:5173 PDF=/path/simple_invoice.pdf OUT=/tmp/shots node vertical-slice.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://127.0.0.1:5173";
const PDF = process.env.PDF;
const OUT = process.env.OUT ?? "/tmp/shots";
const EMAIL = "admin@folio.local";
const PASSWORD = "correct horse battery";
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await context.newPage();
const problems = [];
page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));

function step(name) {
  console.log(`• ${name}`);
}

async function shot(name) {
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

step("sign in");
await page.goto(BASE);
await page.waitForSelector("form");
if (await page.getByText("Create the administrator account").isVisible().catch(() => false)) {
  await page.getByLabel("Name").fill("Abdur");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
} else {
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}
await page.getByRole("heading", { name: "Library" }).waitFor();
await shot("01-library");

step("upload invoice");
await page.setInputFiles("input[type=file]", PDF);
await page.waitForURL(/\/d\/[0-9a-f-]{36}/, { timeout: 30_000 });
const documentId = page.url().split("/d/")[1];
const pageEl = page.locator('[data-page-index="0"]');
await pageEl.waitFor();
await page.waitForFunction(() => document.querySelector('[data-page-index="0"] svg') !== null, null, { timeout: 30_000 });
await shot("02-editor-open");

async function pdfText(revision) {
  return page.evaluate(async ([id, rev]) => {
    const scene = await fetch(`/api/v1/documents/${id}`).then((r) => r.json());
    const pageId = scene.pages[0].page_id;
    const data = await fetch(`/api/v1/documents/${id}/pages/${pageId}/scene?revision=${rev}`).then((r) => r.json());
    return data.objects.filter((o) => o.type === "TEXT_NATIVE").map((o) => o.content.text);
  }, [documentId, revision]);
}

step("click the amount on the page and edit in place");
const box = await pageEl.boundingBox();
const scale = box.width / 595;
// "4553.00" occupies x 498.9–535.0, y 613.9–625.0 in PDF space (bottom-left origin).
const target = { x: box.x + 517 * scale, y: box.y + (842 - 619.5) * scale };
await page.mouse.move(target.x, target.y);
await page.waitForTimeout(150);
await shot("03-hover");
await page.mouse.click(target.x, target.y);
const editor = page.getByRole("textbox", { name: "Edit text" });
await editor.waitFor();
await shot("04-editing");
const initial = await editor.textContent();
if (initial !== "4553.00") throw new Error(`editor opened on ${JSON.stringify(initial)}`);
await page.keyboard.press("Control+A");
await page.keyboard.type("4593.00");
await shot("05-typed");
await page.keyboard.press("Enter");
await page.getByText("v2", { exact: true }).waitFor({ timeout: 20_000 });
await page.waitForTimeout(800);
await shot("06-saved");
const afterEdit = await pdfText(2);
if (!afterEdit.includes("4593.00") || afterEdit.includes("4553.00")) throw new Error(`revision 2 text: ${afterEdit}`);

step("undo restores the original");
await page.locator("body").click({ position: { x: 5, y: 300 } });
await page.keyboard.press("Control+z");
await page.getByText("v3", { exact: true }).waitFor({ timeout: 20_000 });
await page.waitForTimeout(800);
const afterUndo = await pdfText(3);
if (!afterUndo.includes("4553.00")) throw new Error(`revision 3 text: ${afterUndo}`);
await shot("07-undone");

step("select tool + properties");
await page.keyboard.press("v");
await page.mouse.click(box.x + 140 * scale, box.y + (842 - 777) * scale); // header line
await page.waitForTimeout(300);
await shot("08-selected");

step("command palette");
await page.keyboard.press("Control+k");
await page.getByPlaceholder("Type a command…").waitFor();
await shot("09-palette");
await page.keyboard.press("Escape");

await browser.close();
const real = problems.filter((p) => !p.includes("favicon"));
if (real.length) {
  console.log("Browser problems:\n" + real.join("\n"));
  process.exitCode = 1;
} else console.log("✓ vertical slice passed in the browser");
