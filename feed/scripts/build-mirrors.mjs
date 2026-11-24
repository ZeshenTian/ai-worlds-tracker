import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  readFile,
  writeFile,
  mkdir,
  rename,
  rm,
  access,
} from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import {
  feed,
  state,
  snapshot,
  publicDir,
  readJSON,
  saveJSON,
} from "./paths.mjs";

const configs = await readJSON(join(feed, "scripts/mirrors.config.json"));
const worlds = new Map((await readJSON(snapshot)).map((w) => [w.world_id, w]));
const manifest = {};
const refresh = process.argv.includes("--refresh");
const origins = new Set([
  "MIT",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "ISC",
]);
function child(base, path) {
  if (
    !path ||
    path.split("/").some((x) => !x || x === "." || x === "..") ||
    /[:\\?#]/.test(path)
  )
    throw Error("Invalid mirror file path");
  return join(base, path);
}
async function verifiedFile(config, file) {
  const cached = child(join(feed, "vendor", config.world_id), file.output);
  const repo = file.repo || config.repo,
    commit = file.commit || config.commit;
  if (!/^[\w.-]+\/[\w.-]+$/.test(repo) || !/^[a-f0-9]{40}$/.test(commit))
    throw Error("Expected a repository pinned by full commit");
  child("/source", file.path);
  let data;
  if (!refresh) {
    try {
      data = await readFile(cached);
    } catch (err) {
      if (err.code !== "ENOENT") throw err;
    }
  }
  if (!data) {
    const url =
      "https://raw.githubusercontent.com/" +
      repo +
      "/" +
      commit +
      "/" +
      file.path.split("/").map(encodeURIComponent).join("/");
    data = execFileSync(
      "curl",
      [
        "-fsSL",
        "--retry",
        "2",
        "--max-time",
        "55",
        "--proto",
        "=https",
        "--proto-redir",
        "=https",
        url,
      ],
      { maxBuffer: 12 * 1024 * 1024 },
    );
  }
  if (createHash("sha256").update(data).digest("hex") !== file.sha256)
    throw Error("Pinned file hash mismatch: " + file.path);
  await mkdir(dirname(cached), { recursive: true });
  if (refresh) await writeFile(cached, data);
  else {
    try {
      await access(cached);
    } catch {
      await writeFile(cached, data);
    }
  }
  return data;
}
for (const config of configs) {
  const { world_id: id, repo, commit, license } = config;
  const world = worlds.get(id);
  if (
    !world ||
    !/^[\w-]+$/.test(id) ||
    !origins.has(license) ||
    new URL(world.repo_url).pathname
      .replace(/(?:\.git)?\/?$/, "")
      .toLowerCase() !==
      "/" + repo.toLowerCase()
  )
    throw Error("Invalid mirror registration: " + id);
  const files = new Map();
  for (const source of config.files)
    files.set(source.output, await verifiedFile(config, source));
  const legal = files.get("LICENSE")?.toString() || "";
  const signatures = {
    MIT: /Permission is hereby granted, free of charge,[\s\S]+THE SOFTWARE IS PROVIDED "AS IS"/i,
    "Apache-2.0": /Apache License\s+Version 2\.0/,
    ISC: /Permission to use, copy, modify, and\/or distribute/i,
    "BSD-2-Clause": /Redistribution and use in source and binary forms/i,
    "BSD-3-Clause": /Redistribution and use in source and binary forms/i,
  };
  if (!signatures[license].test(legal) || !files.has("index.html"))
    throw Error("Missing entry or invalid license for " + id);
  if (config.removeGoogleFonts)
    files.set(
      "index.html",
      files
        .get("index.html")
        .toString()
        .replace(
          /<link\b[^>]*href="https:\/\/fonts\.(?:googleapis|gstatic)\.com[^"]*"[^>]*>/gi,
          "",
        ),
    );
  const staged = join(publicDir, "mirrors", "." + id + "-" + process.pid);
  await mkdir(staged, { recursive: true });
  for (const [name, data] of files) {
    const dest = child(staged, name);
    await mkdir(dirname(dest), { recursive: true });
    await writeFile(dest, data);
  }
  const target = resolve(publicDir, "mirrors", id);
  const backup = target + ".old-" + process.pid;
  let previous = false;
  try {
    await rename(target, backup);
    previous = true;
  } catch (err) {
    if (err.code !== "ENOENT") throw err;
  }
  try {
    await rename(staged, target);
  } catch (err) {
    if (previous) await rename(backup, target);
    throw err;
  }
  if (previous) await rm(backup, { recursive: true });
  manifest[id] = {
    repo: "https://github.com/" + repo,
    commit,
    license,
    license_url: "https://github.com/" + repo + "/blob/" + commit + "/LICENSE",
    ...(config.cover ? { cover: config.cover } : {}),
    license_sha256: config.files.find((x) => x.output === "LICENSE").sha256,
    entry: "/mirrors/" + id + "/index.html",
  };
}
await saveJSON(join(state, "mirrors.json"), manifest);
console.log(
  "Verified and built",
  Object.keys(manifest).length,
  "licensed static mirrors.",
);
