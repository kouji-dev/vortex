/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  /** `dev` (default): send VITE_DEV_BEARER_TOKEN to API. `entra`: MSAL + VITE_ENTRA_* */
  readonly VITE_AUTH_MODE?: string
  readonly VITE_DEV_BEARER_TOKEN?: string
  /** @deprecated Use VITE_DEV_BEARER_TOKEN */
  readonly VITE_DEV_TOKEN?: string
  readonly VITE_ENTRA_SPA_CLIENT_ID?: string
  readonly VITE_ENTRA_TENANT_ID?: string
  readonly VITE_ENTRA_API_SCOPE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/** Allow `navigate({ state: { pendingStream } })` for first-message bootstrap. */
declare module '@tanstack/history' {
  interface HistoryState {
    pendingStream?: {
      bootstrapId: string
      content: string
      use_rag: boolean
      model?: string
    }
    /** Shown once on KB detail after create flow upload ingest did not complete (e.g. missing embed key). */
    kbIngestWarning?: string
  }
}
