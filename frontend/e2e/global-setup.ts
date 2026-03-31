export default async function globalSetup() {
  const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
  const url = `${base.replace(/\/$/, '')}/health`
  const deadline = Date.now() + 60_000
  let lastErr: unknown
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url)
      if (res.ok) return
      lastErr = new Error(`health not ok: ${res.status}`)
    } catch (e) {
      lastErr = e
    }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr))
}
