// ASCII header shown on `vortex` / `vortex --help` (TTY only — see bin/vortex.mjs).
import pc from "picocolors";

export function bannerText(version) {
  return (
    pc.cyan(`
 ╦  ╦╔═╗╦═╗╔╦╗╔═╗═╗ ╦
 ╚╗╔╝║ ║╠╦╝ ║ ║╣ ╔╩╦╝
  ╚╝ ╚═╝╩╚═ ╩ ╚═╝╩ ╚═`) + pc.dim(`  Enterprise LLM Gateway  v${version}\n`)
  );
}
