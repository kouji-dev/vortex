import { randomBytes, createHash } from "node:crypto";

const PREFIX = "vtx_";

/** Generate a virtual key. Returns the one-time plaintext + its stored shape. */
export function generateApiKey(): {
  plaintext: string;
  keyHash: string;
  keyPrefix: string;
} {
  const secret = randomBytes(24).toString("base64url");
  const plaintext = `${PREFIX}${secret}`;
  return {
    plaintext,
    keyHash: hashApiKey(plaintext),
    keyPrefix: plaintext.slice(0, 12),
  };
}

export function hashApiKey(plaintext: string): string {
  return createHash("sha256").update(plaintext).digest("hex");
}
