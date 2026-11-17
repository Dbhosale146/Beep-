// Copy the pipeline's published output into public/ so the static build can
// serve it. Vite only serves files inside its own root, so this copies rather
// than reaching outside.
//
// This is what makes the GitHub Pages deploy work with no server: the bundle
// ships the dataset, and lib/search.js searches it in the browser. When the
// real API is configured through VITE_API_BASE the file is simply never
// fetched, so carrying it costs nothing at runtime.
import { copyFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";

const FILES = ["jobs.json", "run_meta.json"];
const FROM = new URL("../../backend/data/", import.meta.url);
const TO = new URL("../public/data/", import.meta.url);

await mkdir(TO, { recursive: true });

let missing = 0;
for (const name of FILES) {
  const from = new URL(name, FROM);
  if (!existsSync(from)) {
    console.error(`  missing backend/data/${name}`);
    missing += 1;
    continue;
  }
  await copyFile(from, new URL(name, TO));
  console.log(`  copied ${name}`);
}

if (missing) {
  console.error('\nRun the pipeline first:  cd backend && python -m pipeline.run');
  process.exit(1);
}
