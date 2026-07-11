// Terminal output helpers. picocolors for human-facing color; pretty for data.
import pc from "picocolors";

export { pc };

export function die(m) {
  console.error(pc.red(`✗ ${m}`));
  process.exit(1);
}

export function pretty(x) {
  console.log(typeof x === "string" ? x : JSON.stringify(x, null, 2));
}
