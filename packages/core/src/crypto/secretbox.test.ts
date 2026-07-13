import { describe, it, expect } from "vitest";
import { encryptForOrg, decryptForOrg, PLATFORM_SCOPE } from "./secretbox.js";

const ORG = "org_test_123";

describe("secretbox", () => {
  it("round-trips the v1 (versioned) format", () => {
    const packed = encryptForOrg(ORG, "sk-super-secret");
    const buf = Buffer.from(packed, "base64");
    expect(buf[0]).toBe(0x01); // version byte
    expect(decryptForOrg(ORG, packed)).toBe("sk-super-secret");
  });

  it("round-trips the legacy (unversioned) format", () => {
    // legacy layout = v1 without the leading version byte
    const v1 = Buffer.from(encryptForOrg(ORG, "legacy-secret"), "base64");
    const legacy = v1.subarray(1).toString("base64");
    expect(decryptForOrg(ORG, legacy)).toBe("legacy-secret");
  });

  it("decrypts a legacy blob whose first byte happens to be 0x01", () => {
    // craft a legacy blob starting with 0x01 (iv[0] === 0x01) so the v1 parse
    // is attempted first, fails GCM auth, and falls back to the legacy layout
    let legacy: Buffer | null = null;
    for (let i = 0; i < 20_000; i++) {
      const v1 = Buffer.from(encryptForOrg(ORG, "tricky"), "base64");
      const candidate = v1.subarray(1);
      if (candidate[0] === 0x01) {
        legacy = Buffer.from(candidate);
        break;
      }
    }
    expect(legacy).not.toBeNull();
    expect(decryptForOrg(ORG, legacy!.toString("base64"))).toBe("tricky");
  });

  it("scopes ciphertext to the org (wrong org fails)", () => {
    const packed = encryptForOrg(ORG, "scoped");
    expect(() => decryptForOrg("other_org", packed)).toThrow();
    expect(() => decryptForOrg(PLATFORM_SCOPE, packed)).toThrow();
  });

  it("rejects malformed/short input", () => {
    expect(() => decryptForOrg(ORG, Buffer.alloc(10).toString("base64"))).toThrow(
      /too short|malformed/,
    );
  });
});
