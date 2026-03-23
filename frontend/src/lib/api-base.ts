export function getApiBase(): string {
  return (
    typeof import.meta.env.VITE_API_URL === 'string' &&
    import.meta.env.VITE_API_URL.length > 0
      ? import.meta.env.VITE_API_URL
      : 'http://127.0.0.1:8000'
  ).replace(/\/$/, '')
}
