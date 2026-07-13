import {
  createCipheriv,
  createDecipheriv,
  hkdfSync,
  randomBytes,
} from "node:crypto";
import { env } from "../config/env.js";

// AES-256-GCM authenticated encryption with a per-org derived key.
//
// Versioned packed format (base64): 0x01 || iv(12) || tag(16) || ciphertext(n)
// Legacy (pre-version) format:              iv(12) || tag(16) || ciphertext(n)
// Encrypt always emits v1; decrypt tries v1 first and falls back to the legacy
// layout when the GCM auth check fails (so pre-existing blobs keep working).
//
// The org key is derived via HKDF-SHA256 from the deployment ENCRYPTION_KEY
// (input keying material) salted with the orgId, so each org's secrets are
// encrypted under a distinct key without storing per-org key material.

// HKDF scope for platform-owned (managed pool) secrets — not tied to any org.
export const PLATFORM_SCOPE = "__platform__";

const ALGO = "aes-256-gcm";
const KEY_LEN = 32; // AES-256
const IV_LEN = 12; // GCM standard nonce
const TAG_LEN = 16; // GCM auth tag
const VERSION_1 = 0x01;
const HKDF_INFO = Buffer.from("vortex:provider-credentials:v1", "utf8");

// Root key material. Accept base64; fall back to raw utf8 bytes.
const ROOT_IKM = (() => {
  const raw = env.ENCRYPTION_KEY;
  const b64 = Buffer.from(raw, "base64");
  return b64.length > 0 ? b64 : Buffer.from(raw, "utf8");
})();

function orgKey(orgId: string): Buffer {
  const salt = Buffer.from(orgId, "utf8");
  const derived = hkdfSync("sha256", ROOT_IKM, salt, HKDF_INFO, KEY_LEN);
  return Buffer.from(derived);
}

/** Encrypt `plaintext` for `orgId`; returns base64 pack of 0x01+iv+tag+ciphertext. */
export function encryptForOrg(orgId: string, plaintext: string): string {
  const key = orgKey(orgId);
  const iv = randomBytes(IV_LEN);
  const cipher = createCipheriv(ALGO, key, iv);
  const ciphertext = Buffer.concat([
    cipher.update(plaintext, "utf8"),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([
    Buffer.from([VERSION_1]),
    iv,
    tag,
    ciphertext,
  ]).toString("base64");
}

/** AES-GCM decrypt of iv||tag||ct starting at `offset` in `buf`. */
function gcmOpen(key: Buffer, buf: Buffer, offset: number): string {
  const iv = buf.subarray(offset, offset + IV_LEN);
  const tag = buf.subarray(offset + IV_LEN, offset + IV_LEN + TAG_LEN);
  const ciphertext = buf.subarray(offset + IV_LEN + TAG_LEN);
  const decipher = createDecipheriv(ALGO, key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([
    decipher.update(ciphertext),
    decipher.final(),
  ]).toString("utf8");
}

/** Decrypt a base64 pack produced by `encryptForOrg` for the same `orgId`. */
export function decryptForOrg(orgId: string, packed: string): string {
  const buf = Buffer.from(packed, "base64");
  if (buf.length < IV_LEN + TAG_LEN) {
    throw new Error("decryptForOrg: ciphertext too short / malformed");
  }
  const key = orgKey(orgId);
  // v1: leading version byte. A legacy blob may start with 0x01 by chance, so
  // on GCM auth failure fall back to the legacy (unversioned) layout.
  if (buf[0] === VERSION_1 && buf.length >= 1 + IV_LEN + TAG_LEN) {
    try {
      return gcmOpen(key, buf, 1);
    } catch {
      /* fall through to legacy parse */
    }
  }
  return gcmOpen(key, buf, 0);
}
