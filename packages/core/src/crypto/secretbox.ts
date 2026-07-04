import {
  createCipheriv,
  createDecipheriv,
  hkdfSync,
  randomBytes,
} from "node:crypto";
import { env } from "../config/env.js";

// AES-256-GCM authenticated encryption with a per-org derived key.
//
// Packed format (base64): iv(12) || tag(16) || ciphertext(n)
// The org key is derived via HKDF-SHA256 from the deployment ENCRYPTION_KEY
// (input keying material) salted with the orgId, so each org's secrets are
// encrypted under a distinct key without storing per-org key material.

const ALGO = "aes-256-gcm";
const KEY_LEN = 32; // AES-256
const IV_LEN = 12; // GCM standard nonce
const TAG_LEN = 16; // GCM auth tag
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

/** Encrypt `plaintext` for `orgId`; returns base64 pack of iv+tag+ciphertext. */
export function encryptForOrg(orgId: string, plaintext: string): string {
  const key = orgKey(orgId);
  const iv = randomBytes(IV_LEN);
  const cipher = createCipheriv(ALGO, key, iv);
  const ciphertext = Buffer.concat([
    cipher.update(plaintext, "utf8"),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, ciphertext]).toString("base64");
}

/** Decrypt a base64 pack produced by `encryptForOrg` for the same `orgId`. */
export function decryptForOrg(orgId: string, packed: string): string {
  const buf = Buffer.from(packed, "base64");
  if (buf.length < IV_LEN + TAG_LEN) {
    throw new Error("decryptForOrg: ciphertext too short / malformed");
  }
  const iv = buf.subarray(0, IV_LEN);
  const tag = buf.subarray(IV_LEN, IV_LEN + TAG_LEN);
  const ciphertext = buf.subarray(IV_LEN + TAG_LEN);
  const key = orgKey(orgId);
  const decipher = createDecipheriv(ALGO, key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([
    decipher.update(ciphertext),
    decipher.final(),
  ]).toString("utf8");
}
