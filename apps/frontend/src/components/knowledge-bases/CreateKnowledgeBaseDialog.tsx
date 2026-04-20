import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { ChevronLeft } from 'lucide-react'
import * as React from 'react'

import { Dialog, DialogBody } from '~/components/ui/Dialog'
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

  const title = (
    <span className="flex flex-col leading-tight">
      <span className="mono text-[10px] font-medium uppercase tracking-wide" style={{ color: 'var(--ink-3)' }}>
        Step {step} of 2
      </span>
      <span>{step === 1 ? 'Knowledge base details' : 'Source & configuration'}</span>
    </span>
  )

  const footer =
    step === 1 ? (
      <>
        <button type="button" className="btn btn-sm" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={!canGoNext}
          onClick={() => canGoNext && setStep(2)}
        >
          Next
        </button>
      </>
    ) : (
      <>
        <button
          type="button"
          className="btn btn-sm"
          onClick={() => setStep(1)}
          disabled={createMut.isPending}
          style={{ marginRight: 'auto' }}
        >
          <ChevronLeft className="size-3" strokeWidth={2} aria-hidden />
          Back
        </button>
        <button
          type="button"
          className="btn btn-sm"
          onClick={onClose}
          disabled={createMut.isPending}
        >
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={!canCreate}
          onClick={() => {
            if (!canCreate) return
            createMut.mutate({
              name: name.trim(),
              description: description.trim(),
              connectorKind,
              connectorForm,
              initialFile,
            })
          }}
        >
          {createMut.isPending ? 'Creating…' : 'Create'}
        </button>
      </>
    )

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      labelledBy="create-kb-title"
      size="lg"
      footer={footer}
    >
      <DialogBody>
        <p className="mb-4 text-xs" style={{ color: 'var(--ink-3)' }}>
          {step === 1
            ? 'Choose a name and optional description for this corpus.'
            : 'Pick how content will be connected. Some source types are preview-only until the integration ships.'}
        </p>

        {step === 1 ? (
          <form onSubmit={goNext} className="flex flex-col gap-4">
            <div className="form-row !mb-0">
              <label>Name</label>
              <input
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={255}
                required
                autoFocus
              />
            </div>
            <div className="form-row !mb-0">
              <label>Description (optional)</label>
              <textarea
                className="textarea"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={10_000}
              />
            </div>
          </form>
        ) : (
          <form onSubmit={finish} className="flex flex-col gap-4">
            <fieldset className="form-row !mb-0">
              <legend className="mb-1.5 text-xs font-medium" style={{ color: 'var(--ink)' }}>
                Source type
              </legend>
              <div className="space-y-2">
                {CONNECTOR_KINDS.map((k) => {
                  const implemented = isConnectorKindImplemented(k)
                  const active = connectorKind === k
                  return (
                    <label
                      key={k}
                      className="flex cursor-pointer gap-3 rounded px-3 py-2.5 text-sm transition-colors"
                      style={{
                        border: `1px solid ${active ? 'var(--ink)' : 'var(--line)'}`,
                        background: active ? 'var(--hl)' : 'var(--panel)',
                      }}
                    >
                      <input
                        type="radio"
                        name="kb-connector-type"
                        className="mt-0.5"
                        checked={active}
                        onChange={() => setConnectorKind(k)}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="font-medium" style={{ color: 'var(--ink)' }}>
                          {CONNECTOR_KIND_LABELS[k]}
                        </span>
                        {!implemented && (
                          <span
                            className="ml-2 text-xs font-normal"
                            style={{ color: 'var(--warn)' }}
                          >
                            Coming soon
                          </span>
                        )}
                      </span>
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <div
              className="rounded px-3 py-3"
              style={{ border: '1px solid var(--line)', background: 'var(--bg-2)' }}
            >
              <p
                className="mb-2 mono text-[10px] font-semibold uppercase tracking-wide"
                style={{ color: 'var(--ink-3)' }}
              >
                Configuration
              </p>

              {connectorKind === 'files' && (
                <div className="flex flex-col gap-3">
                  <div className="form-row !mb-0">
                    <label>Connector label</label>
                    <input
                      className="input"
                      value={connectorForm.filesLabel}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, filesLabel: e.target.value }))
                      }
                      maxLength={255}
                      placeholder="File uploads"
                    />
                  </div>
                  <div>
                    <span className="text-xs font-medium" style={{ color: 'var(--ink)' }}>
                      Initial document (optional)
                    </span>
                    <p className="mt-0.5 text-[11px]" style={{ color: 'var(--ink-3)' }}>
                      .txt, .md, or .pdf — the file uploads in the background after creation.
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      data-testid="kb-create-initial-file"
                      accept=".txt,.md,.pdf,text/plain,text/markdown,application/pdf"
                      className="mt-2 block w-full text-xs file:mr-3 file:rounded-sm file:border-0 file:px-3 file:py-1.5 file:text-xs"
                      style={{ color: 'var(--ink-2)' }}
                      disabled={createMut.isPending}
                      onChange={(e) => {
                        const f = e.target.files?.[0] ?? null
                        setInitialFile(f)
                      }}
                    />
                    {initialFile && (
                      <div
                        className="mt-2 flex items-center justify-between gap-2 rounded px-2 py-1.5 text-xs"
                        style={{
                          border: '1px solid var(--line)',
                          background: 'var(--panel)',
                          color: 'var(--ink-2)',
                        }}
                      >
                        <span className="min-w-0 truncate">{initialFile.name}</span>
                        <button
                          type="button"
                          className="link-btn shrink-0"
                          style={{ color: 'var(--err)' }}
                          onClick={() => {
                            setInitialFile(null)
                            if (fileInputRef.current) fileInputRef.current.value = ''
                          }}
                        >
                          Remove
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {connectorKind === 'github' && (
                <div className="flex flex-col gap-3">
                  <div className="form-row !mb-0">
                    <label>Repository</label>
                    <input
                      className="input input-mono"
                      value={connectorForm.githubRepo}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, githubRepo: e.target.value }))
                      }
                      placeholder="org/repository"
                      autoComplete="off"
                    />
                  </div>
                  <div className="form-row !mb-0">
                    <label>Branch</label>
                    <input
                      className="input"
                      value={connectorForm.githubBranch}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, githubBranch: e.target.value }))
                      }
                      placeholder="main"
                    />
                  </div>
                </div>
              )}

              {connectorKind === 'gitlab' && (
                <div className="flex flex-col gap-3">
                  <div className="form-row !mb-0">
                    <label>Project ID or path</label>
                    <input
                      className="input input-mono"
                      value={connectorForm.gitlabProject}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, gitlabProject: e.target.value }))
                      }
                      placeholder="12345 or group/project"
                    />
                  </div>
                  <div className="form-row !mb-0">
                    <label>Ref / branch</label>
                    <input
                      className="input"
                      value={connectorForm.gitlabRef}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, gitlabRef: e.target.value }))
                      }
                      placeholder="main"
                    />
                  </div>
                </div>
              )}

              {connectorKind === 'confluence' && (
                <div className="flex flex-col gap-3">
                  <div className="form-row !mb-0">
                    <label>Space key</label>
                    <input
                      className="input"
                      value={connectorForm.confluenceSpace}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, confluenceSpace: e.target.value }))
                      }
                      placeholder="ENG"
                    />
                  </div>
                  <div className="form-row !mb-0">
                    <label>Root page ID (optional)</label>
                    <input
                      className="input"
                      value={connectorForm.confluenceRoot}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, confluenceRoot: e.target.value }))
                      }
                      placeholder="123456"
                    />
                  </div>
                </div>
              )}

              {connectorKind === 's3' && (
                <div className="flex flex-col gap-3">
                  <div className="form-row !mb-0">
                    <label>Bucket</label>
                    <input
                      className="input"
                      value={connectorForm.s3Bucket}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, s3Bucket: e.target.value }))
                      }
                      placeholder="my-doc-bucket"
                    />
                  </div>
                  <div className="form-row !mb-0">
                    <label>Key prefix (optional)</label>
                    <input
                      className="input input-mono"
                      value={connectorForm.s3Prefix}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, s3Prefix: e.target.value }))
                      }
                      placeholder="docs/rag/"
                    />
                  </div>
                  <div className="form-row !mb-0">
                    <label>Region (optional)</label>
                    <input
                      className="input"
                      value={connectorForm.s3Region}
                      onChange={(e) =>
                        setConnectorForm((s) => ({ ...s, s3Region: e.target.value }))
                      }
                      placeholder="us-east-1"
                    />
                  </div>
                </div>
              )}
            </div>

            {!kindImplemented && (
              <p
                className="rounded px-3 py-2 text-xs"
                style={{
                  border: '1px solid color-mix(in oklch, var(--warn) 40%, var(--line))',
                  background: 'color-mix(in oklch, var(--warn) 10%, var(--panel))',
                  color: 'var(--ink-2)',
                }}
                role="status"
              >
                This source type is not available yet. Choose <strong>Files</strong> to create a
                knowledge base now, or swap the source later from the base page once the integration
                ships.
              </p>
            )}

            {createMut.isError && (
              <p className="text-xs" style={{ color: 'var(--err)' }} role="alert">
                {(createMut.error as Error).message}
              </p>
            )}
          </form>
        )}
      </DialogBody>
    </Dialog>
  )
}
