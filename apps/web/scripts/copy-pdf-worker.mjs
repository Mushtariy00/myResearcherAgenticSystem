/**
 * Copies the PDF.js worker into public/pdfjs/ so the PDF viewer loads it from our own origin
 * (never a CDN). It is the exact pdfjs-dist version react-pdf depends on: the worker and the main
 * library must match. Runs before `next dev` and `next build`; the copy is not committed.
 */
import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
// Resolve pdfjs-dist from react-pdf's own location, so it is the version react-pdf uses.
const fromReactPdf = createRequire(
  createRequire(path.join(webRoot, "package.json")).resolve("react-pdf"),
);
const pdfjsRoot = path.dirname(fromReactPdf.resolve("pdfjs-dist/package.json"));
const { version } = JSON.parse(readFileSync(path.join(pdfjsRoot, "package.json"), "utf8"));

const target = path.join(webRoot, "public", "pdfjs");
mkdirSync(target, { recursive: true });
copyFileSync(
  path.join(pdfjsRoot, "build", "pdf.worker.min.mjs"),
  path.join(target, "pdf.worker.min.mjs"),
);
console.log(`copy-pdf-worker: pdfjs-dist ${version} worker -> public/pdfjs/pdf.worker.min.mjs`);
