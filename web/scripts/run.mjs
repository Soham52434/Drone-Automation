import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL("..", import.meta.url));
const task = process.argv[2];
const tasks = {
  dev: [["vite"]],
  build: [
    ["tsc", "--noEmit"],
    ["vite", "build"],
  ],
  test: [["vitest", "run"]],
  typecheck: [["tsc", "--noEmit"]],
};

if (!task || !(task in tasks)) {
  console.error("Usage: node scripts/run.mjs <dev|build|test|typecheck>");
  process.exit(1);
}

if (!nodeSupportsBuild(process.versions.node)) {
  const bin = installedNodeBin();
  if (!bin || process.env.DRONE_NODE_REEXEC === "1") {
    console.error(`Node ${process.version} cannot build this UI. Install Node 22.12 or newer (nvm install 22).`);
    process.exit(1);
  }
  const result = spawnSync(join(bin, "npm"), ["run", task], {
    cwd: webRoot,
    stdio: "inherit",
    env: {
      ...process.env,
      PATH: `${bin}${delimiter}${process.env.PATH ?? ""}`,
      DRONE_NODE_REEXEC: "1",
    },
  });
  process.exit(result.status ?? 1);
}

for (const [command, ...args] of tasks[task]) {
  const result = spawnSync(process.execPath, [join(webRoot, "node_modules", ".bin", command), ...args], {
    cwd: webRoot,
    stdio: "inherit",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

function nodeSupportsBuild(version) {
  const [major, minor] = version.split(".").map(Number);
  return major > 22 || (major === 22 && minor >= 12) || (major === 20 && minor >= 19);
}

function installedNodeBin() {
  const root = join(homedir(), ".nvm", "versions", "node");
  if (!existsSync(root)) return null;
  const match = readdirSync(root)
    .map((name) => ({ name, version: name.replace(/^v/, "") }))
    .filter((item) => nodeSupportsBuild(item.version))
    .sort((a, b) => a.version.localeCompare(b.version, undefined, { numeric: true }))
    .at(-1);
  return match ? join(root, match.name, "bin") : null;
}
