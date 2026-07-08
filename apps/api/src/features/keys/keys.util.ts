import { randomBytes, createHmac } from "node:crypto";
import { env } from "@vortex/core";

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

// HMAC-SHA256 with a server-side pepper (env, never in the DB): a keyHash leak
// alone can't be used to verify guesses offline. High-entropy keys → fast hash
// is correct here (no bcrypt/argon2).
export function hashApiKey(plaintext: string): string {
  return createHmac("sha256", env.API_KEY_PEPPER).update(plaintext).digest("hex");
}
