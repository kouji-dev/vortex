import { Paperclip, X } from 'lucide-react'

type AttachmentChipsProps = {
  pendingServerAttachments?: { id: number; name: string }[]
  pendingLocalFileNames?: string[]
  onRemoveServerAttachment?: (id: number) => void
  onRemoveLocalFile?: (index: number) => void
  attachDisabled?: boolean
  streaming: boolean
}

export function AttachmentChips({
  pendingServerAttachments,
  pendingLocalFileNames,
  onRemoveServerAttachment,
  onRemoveLocalFile,
  attachDisabled,
  streaming,
}: AttachmentChipsProps) {
  const disabled = Boolean(attachDisabled) || streaming
  return (
    <>
      {pendingServerAttachments?.map((a) => (
        <span key={`srv-${a.id}`} className="attach-chip" title={a.name}>
          <Paperclip className="size-3" strokeWidth={2} />
          <span className="max-w-[12rem] truncate">{a.name}</span>
          <button
            type="button"
            className="link-btn"
            aria-label={`Remove ${a.name}`}
            disabled={disabled}
            onClick={() => onRemoveServerAttachment?.(a.id)}
          >
            <X className="size-3" strokeWidth={2.5} />
          </button>
        </span>
      ))}
      {pendingLocalFileNames?.map((name, i) => (
        <span key={`loc-${i}-${name}`} className="attach-chip" title={name}>
          <Paperclip className="size-3" strokeWidth={2} />
          <span className="max-w-[12rem] truncate">{name}</span>
          <button
            type="button"
            className="link-btn"
            aria-label={`Remove ${name}`}
            disabled={disabled}
            onClick={() => onRemoveLocalFile?.(i)}
          >
            <X className="size-3" strokeWidth={2.5} />
          </button>
        </span>
      ))}
    </>
  )
}
