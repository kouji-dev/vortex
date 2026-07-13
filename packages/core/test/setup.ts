// Hermetic env for unit tests — set BEFORE any module imports ../src/config/env.ts.
// dotenv does not override pre-set values, so these always win.
process.env.NODE_ENV = "test";
process.env.WEB_ORIGIN ??= "http://127.0.0.1:4200";
process.env.PLATFORM_ORIGIN ??= "http://127.0.0.1:4300";
process.env.DATABASE_URL ??= "postgres://test:test@127.0.0.1:5432/test";
process.env.APP_DATABASE_URL ??= "postgres://test:test@127.0.0.1:5432/test";
process.env.REDIS_URL ??= "redis://127.0.0.1:6379";
process.env.BETTER_AUTH_SECRET ??= "test-secret";
process.env.BETTER_AUTH_URL ??= "http://127.0.0.1:8080";
// 32 bytes, base64
process.env.ENCRYPTION_KEY = Buffer.alloc(32, 7).toString("base64");
process.env.API_KEY_PEPPER ??= "test-pepper";
