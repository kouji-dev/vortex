import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ChevronLeft, X } from 'lucide-react'
import * as React from 'react'

import { getApiBase } from '~/lib/api-base'
import { getAuthHeaders } from '~/lib/authorizedFetch'
import {
  CONNECTOR_KINDS,
  CONNECTOR_KIND_LABELS,
  type ConnectorKind,
  type KnowledgeBaseSummary,
  isConnectorKindImplemented,
  isFastApiGenericNotFoundResponse,
} from '~/lib/knowledge-base-types'
import { queryKeys } from '~/lib/queryKeys'

type CreateKnowledgeBaseDialogProps = {
  open: boolean
  onClose: () => void
  onCreated?: (kb: KnowledgeBaseSummary, meta?: { ingestWarning?: string }) => void
}

type ConnectorFormState = {
  filesLabel: string
  githubRepo: string
  githubBranch: string
  gitlabProject: string
  gitlabRef: string
  confluenceSpace: string
  confluenceRoot: string
  s3Bucket: string
  s3Prefix: string
  s3Region: string
}

function defaultConnectorForm(): ConnectorFormState {
  return {
    filesLabel: 'File uploads',
    githubRepo: '',
    githubBranch: 'main',
    gitlabProject: '',
    gitlabRef: 'main',
    confluenceSpace: '',
    confluenceRoot: '',
    s3Bucket: '',
    s3Prefix: '',
    s3Region: '',
  }
}

function httpStepError(step: string, method: string, url: string, res: Response, body: string): Error {
  const snippet = body.trim().slice(0, 500)
  return new Error(
    `${step}: ${method} ${url} → HTTP ${res.status}${snippet ? `\n${snippet}` : ''}`,
  )
}

function buildConnectorBody(
  kind: ConnectorKind,
  f: ConnectorFormState,
): { kind: ConnectorKind; label: string; settings: Record<string, string> } {
  switch (kind) {
    case 'files':
      return {
        kind,
        label: f.filesLabel.trim() || 'File uploads',
        settings: {},
      }
    case 'github': {
      const repo = f.githubRepo.trim()
      return {
        kind,
        label: repo ? `GitHub · ${repo}` : 'GitHub',
        settings: {
          repo,
          branch: f.githubBranch.trim() || 'main',
        },
      }
    }
    case 'gitlab':
      return {
        kind,
        label: f.gitlabProject.trim() || 'GitLab',
        settings: {
          project: f.gitlabProject.trim(),
          ref: f.gitlabRef.trim() || 'main',
        },
      }
    case 'confluence':
      return {
        kind,
        label: f.confluenceSpace.trim() || 'Confluence',
        settings: {
          space_key: f.confluenceSpace.trim(),
          root_page_id: f.confluenceRoot.trim(),
        },
      }
    case 's3':
      return {
        kind,
        label: f.s3Bucket.trim() || 'S3',
        settings: {
          bucket: f.s3Bucket.trim(),
          prefix: f.s3Prefix.trim(),
          region: f.s3Region.trim(),
        },
      }
  }
}

export function CreateKnowledgeBaseDialog({
  open,
  onClose,
  onCreated,
}: CreateKnowledgeBaseDialogProps) {
  const apiBase = getApiBase()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [step, setStep] = React.useState<1 | 2>(1)
  const [name, setName] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [connectorKind, setConnectorKind] = React.useState<ConnectorKind>('files')
  const [connectorForm, setConnectorForm] = React.useState<ConnectorFormState>(defaultConnectorForm)
  const [initialFile, setInitialFile] = React.useState<File | null>(null)
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    if (!open) return
    setStep(1)
    setName('')
    setDescription('')
    setConnectorKind('files')
    setConnectorForm(defaultConnectorForm())
    setInitialFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [open])

  React.useEffect(() => {
    if (connectorKind !== 'files') {
      setInitialFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [connectorKind])

  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const createMut = useMutation({
    mutationFn: async (args: {
      name: string
      description: string
      connectorKind: ConnectorKind
      connectorForm: ConnectorFormState
      initialFile: File | null
    }) => {
      const kbCreateUrl = `${apiBase}/api/knowledge-bases`
      const kbRes = await fetch(kbCreateUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify({
          name: args.name,
          description: args.description,
        }),
      })
      const kbText = await kbRes.text()
      if (!kbRes.ok) {
        const err = httpStepError('Create knowledge base', 'POST', kbCreateUrl, kbRes, kbText)
        if (isFastApiGenericNotFoundResponse(kbRes, kbText)) {
          err.message +=
            '\n\nIf the UI and API run on different ports: remove or comment out VITE_API_URL in frontend/.env so dev uses the Vite proxy to FastAPI, or set VITE_API_URL to your real API origin (see comments in frontend/.env or frontend/.env.example).' +
            `\n\nThis 404 means nothing on that origin handled POST /api/knowledge-bases. Check GET ${apiBase}/health — this API should include "api":{"post_knowledge_bases":true}. If it is missing or false, restart the backend from this repo on that host/port.`
        }
        throw err
      }
      const kb = JSON.parse(kbText) as KnowledgeBaseSummary

      const connector = buildConnectorBody(args.connectorKind, args.connectorForm)
      const connectorUrl = `${apiBase}/api/knowledge-bases/${kb.id}/connectors`
      const cRes = await fetch(connectorUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(await getAuthHeaders()),
        },
        body: JSON.stringify(connector),
      })
      const cText = await cRes.text()
      if (!cRes.ok) {
        if (isFastApiGenericNotFoundResponse(cRes, cText)) {
          // Older API without connector routes, or wrong doubled `/api` path — KB still exists.
        } else {
          throw httpStepError('Create connector', 'POST', connectorUrl, cRes, cText)
        }
      }

      const deferredFile =
        args.connectorKind === 'files' && args.initialFile ? args.initialFile : null

      return { kb, deferredFile }
    },
    onSuccess: (data) => {
      const { kb, deferredFile } = data
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBases() })
      void qc.invalidateQueries({ queryKey: queryKeys.knowledgeBase(kb.id) })
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseConnectors(kb.id),
      })
      void qc.invalidateQueries({
        queryKey: queryKeys.knowledgeBaseDocuments(kb.id),
      })
      onClose()
      onCreated?.(kb)

      if (deferredFile) {
        void (async () => {
          const uploadUrl = `${apiBase}/api/knowledge-bases/${kb.id}/documents`
          try {
            const fd = new FormData()
            fd.append('file', deferredFile)
            const uRes = await fetch(uploadUrl, {
              method: 'POST',
              headers: await getAuthHeaders(),
              body: fd,
            })
            const uText = await uRes.text()
            let ingestWarning: string | undefined
            if (uRes.ok) {
              try {
                const uJson = JSON.parse(uText) as {
                  results?: Array<{ ingest_error?: string }>
                  ingest_error?: string
                }
                const first = uJson.results?.[0]
                const err =
                  (typeof first?.ingest_error === 'string' && first.ingest_error.trim()) ||
                  (typeof uJson.ingest_error === 'string' && uJson.ingest_error.trim())
                if (err) {
                  ingestWarning = err
                }
              } catch {
                /* non-JSON success body — ignore */
              }
            } else if (!isFastApiGenericNotFoundResponse(uRes, uText)) {
              ingestWarning =
                uText.trim().slice(0, 500) || `Initial file upload failed (HTTP ${uRes.status}).`
            }
            await qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kb.id) })
            await qc.invalidateQueries({ queryKey: queryKeys.knowledgeBase(kb.id) })
            await qc.invalidateQueries({ queryKey: queryKeys.knowledgeBases() })

            const onKbDetail =
              typeof window !== 'undefined' &&
              window.location.pathname.replace(/\/$/, '') === `/knowledge-bases/${kb.id}`
            if (ingestWarning && onKbDetail) {
              void navigate({
                to: '/knowledge-bases/$id',
                params: { id: String(kb.id) },
                replace: true,
                state: { kbIngestWarning: ingestWarning },
              })
            }
          } catch (e) {
            await qc.invalidateQueries({ queryKey: queryKeys.knowledgeBaseDocuments(kb.id) })
            const onKbDetail =
              typeof window !== 'undefined' &&
              window.location.pathname.replace(/\/$/, '') === `/knowledge-bases/${kb.id}`
            const msg = e instanceof Error ? e.message : 'Initial file upload failed.'
            if (onKbDetail) {
              void navigate({
                to: '/knowledge-bases/$id',
                params: { id: String(kb.id) },
                replace: true,
                state: { kbIngestWarning: msg },
              })
            }
          }
        })()
      }
    },
  })

  if (!open) return null

  const canGoNext = Boolean(name.trim())
  const kindImplemented = isConnectorKindImplemented(connectorKind)
  const canCreate =
    kindImplemented &&
    !createMut.isPending &&
    Boolean(name.trim()) &&
    step === 2

  const goNext = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canGoNext) return
    setStep(2)
  }

  const finish = (e: React.FormEvent) => {
    e.preventDefault()
    if (!canCreate) return
    createMut.mutate({
      name: name.trim(),
      description: description.trim(),
      connectorKind,
      connectorForm,
      initialFile,
    })
  }

  return (
    <div
      className="fixed inset-0 z-60 flex items-end justify-center bg-black/45 md:items-center md:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-kb-title"
      onClick={(ev) => ev.target === ev.currentTarget && onClose()}
    >
      <div
        className="max-h-[90vh] w-full overflow-y-auto rounded-t-2xl border border-neutral-200 bg-white p-4 shadow-xl dark:border-neutral-700 dark:bg-neutral-950 md:max-w-lg md:rounded-xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-neutral-300 dark:bg-neutral-700 md:hidden" />
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-neutral-500">
              Step {step} of 2
            </p>
            <h2
              id="create-kb-title"
              className="mt-0.5 text-base font-semibold text-neutral-900 dark:text-neutral-100"
            >
              {step === 1 ? 'Knowledge base details' : 'Source & configuration'}
            </h2>
          </div>
          <button
            type="button"
            className="rounded p-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-900"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-400">
          {step === 1
            ? 'Choose a name and optional description for this corpus.'
            : 'Pick how content will be connected. Only some types can be created today; others show a preview of the settings we will use when the integration is ready.'}
        </p>

        {step === 1 ? (
          <form className="mt-4 flex flex-col gap-4" onSubmit={goNext}>
            <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              Name
              <input
                className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={255}
                required
                autoFocus
              />
            </label>
            <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
              Description (optional)
              <textarea
                className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={10_000}
              />
            </label>
            <div className="flex justify-end gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
              <button
                type="button"
                className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
                onClick={onClose}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!canGoNext}
                className="rounded-lg bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
              >
                Next
              </button>
            </div>
          </form>
        ) : (
          <form className="mt-4 flex flex-col gap-4" onSubmit={finish}>
            <fieldset>
              <legend className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                Source type
              </legend>
              <div className="mt-2 space-y-2">
                {CONNECTOR_KINDS.map((k) => {
                  const implemented = isConnectorKindImplemented(k)
                  return (
                    <label
                      key={k}
                      className={
                        'flex cursor-pointer gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors ' +
                        (connectorKind === k
                          ? 'border-neutral-900 bg-neutral-50 dark:border-neutral-100 dark:bg-neutral-900/80'
                          : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-700 dark:hover:border-neutral-600')
                      }
                    >
                      <input
                        type="radio"
                        name="kb-connector-type"
                        className="mt-0.5 border-neutral-400"
                        checked={connectorKind === k}
                        onChange={() => setConnectorKind(k)}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium text-neutral-900 dark:text-neutral-100">
                          {CONNECTOR_KIND_LABELS[k]}
                        </span>
                        {!implemented ? (
                          <span className="ml-2 text-xs font-normal text-amber-700 dark:text-amber-400">
                            Coming soon
                          </span>
                        ) : null}
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <div className="rounded-lg border border-neutral-200 bg-neutral-50/80 px-3 py-3 dark:border-neutral-700 dark:bg-neutral-900/40">
              <p className="text-xs font-medium text-neutral-700 dark:text-neutral-300">
                Configuration
              </p>
              <div className="mt-3">
                {connectorKind === 'files' ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Connector label
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.filesLabel}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, filesLabel: e.target.value }))
                        }
                        maxLength={255}
                        placeholder="File uploads"
                      />
                    </label>
                    <div>
                      <span className="text-xs font-medium text-neutral-600 dark:text-neutral-400">
                        Initial document (optional)
                      </span>
                      <p className="mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                        .txt, .md, or .pdf — after you create the base you&apos;ll go to the detail
                        page right away; the file uploads in the background and indexing progress
                        appears there.
                      </p>
                      <input
                        ref={fileInputRef}
                        type="file"
                        data-testid="kb-create-initial-file"
                        accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
                        className="mt-2 block w-full text-sm text-neutral-600 file:mr-3 file:rounded-md file:border-0 file:bg-neutral-200 file:px-3 file:py-1.5 file:text-sm dark:text-neutral-400 dark:file:bg-neutral-800"
                        disabled={createMut.isPending}
                        onChange={(e) => {
                          const f = e.target.files?.[0] ?? null
                          setInitialFile(f)
                        }}
                      />
                      {initialFile ? (
                        <div className="mt-2 flex items-center justify-between gap-2 rounded-md border border-neutral-200 bg-white px-2 py-1.5 text-xs dark:border-neutral-700 dark:bg-neutral-950">
                          <span className="min-w-0 truncate text-neutral-800 dark:text-neutral-200">
                            {initialFile.name}
                          </span>
                          <button
                            type="button"
                            className="shrink-0 text-neutral-500 underline hover:text-red-600 dark:hover:text-red-400"
                            onClick={() => {
                              setInitialFile(null)
                              if (fileInputRef.current) fileInputRef.current.value = ''
                            }}
                          >
                            Remove
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}

                {connectorKind === 'github' ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Repository
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.githubRepo}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, githubRepo: e.target.value }))
                        }
                        placeholder="org/repository"
                        autoComplete="off"
                      />
                    </label>
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Branch
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.githubBranch}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, githubBranch: e.target.value }))
                        }
                        placeholder="main"
                      />
                    </label>
                  </div>
                ) : null}

                {connectorKind === 'gitlab' ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Project ID or path
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.gitlabProject}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, gitlabProject: e.target.value }))
                        }
                        placeholder="12345 or group/project"
                      />
                    </label>
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Ref / branch
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.gitlabRef}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, gitlabRef: e.target.value }))
                        }
                        placeholder="main"
                      />
                    </label>
                  </div>
                ) : null}

                {connectorKind === 'confluence' ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Space key
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.confluenceSpace}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, confluenceSpace: e.target.value }))
                        }
                        placeholder="ENG"
                      />
                    </label>
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Root page ID (optional)
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.confluenceRoot}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, confluenceRoot: e.target.value }))
                        }
                        placeholder="123456"
                      />
                    </label>
                  </div>
                ) : null}

                {connectorKind === 's3' ? (
                  <div className="space-y-3">
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Bucket
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.s3Bucket}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, s3Bucket: e.target.value }))
                        }
                        placeholder="my-doc-bucket"
                      />
                    </label>
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Key prefix (optional)
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 font-mono text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.s3Prefix}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, s3Prefix: e.target.value }))
                        }
                        placeholder="docs/rag/"
                      />
                    </label>
                    <label className="block text-xs font-medium text-neutral-600 dark:text-neutral-400">
                      Region (optional)
                      <input
                        className="mt-1 w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm dark:border-neutral-600 dark:bg-neutral-950 dark:text-neutral-100"
                        value={connectorForm.s3Region}
                        onChange={(e) =>
                          setConnectorForm((s) => ({ ...s, s3Region: e.target.value }))
                        }
                        placeholder="us-east-1"
                      />
                    </label>
                  </div>
                ) : null}
              </div>
            </div>

            {!kindImplemented ? (
              <p
                className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
                role="status"
              >
                This source type is not available yet. Choose <strong>Files</strong> to create a
                knowledge base now, or go back and change your selection later from the base page
                once integrations ship.
              </p>
            ) : null}

            {createMut.isError ? (
              <p className="text-sm text-red-600" role="alert">
                {(createMut.error as Error).message}
              </p>
            ) : null}

            <div className="flex flex-wrap justify-between gap-2 border-t border-neutral-200 pt-3 dark:border-neutral-800">
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
                onClick={() => setStep(1)}
                disabled={createMut.isPending}
              >
                <ChevronLeft className="size-4" aria-hidden />
                Back
              </button>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="rounded-lg border border-neutral-300 px-3 py-1.5 text-sm dark:border-neutral-600"
                  onClick={onClose}
                  disabled={createMut.isPending}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!canCreate}
                  className="rounded-lg bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50 dark:bg-neutral-100 dark:text-neutral-900"
                >
                  {createMut.isPending ? 'Creating…' : 'Create'}
                </button>
              </div>
            </div>
          </form>
        )}
        <div className="md:hidden" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }} />
      </div>
    </div>
  )
}
