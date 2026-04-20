import { MarkdownMessage } from '~/components/chat/MarkdownMessage'
import type { ThreadItem } from '~/lib/chat-types'

type Props = {
  item: ThreadItem & { kind: 'user_message' }
  userInitials: string
  displayName: string
}

export function UserMessageItem({ item, userInitials, displayName }: Props) {
  const attachments = (item.data.attachments ?? []) as {
    id?: number
    original_filename?: string
  }[]
  return (
    <>
      <header className="msg-head">
        <span className="avatar-sm mono">{userInitials}</span>
        <span className="who-name">{displayName}</span>
        <time className="ts mono" dateTime={item.created_at}>
          {formatWhen(item.created_at)}
        </time>
      </header>
      {attachments.length > 0 && (
        <div className="attach-list">
          {attachments.map((a, i) => (
            <span key={a.id ?? i} className="attach-chip">
              {a.original_filename ?? `Attachment ${i + 1}`}
            </span>
          ))}
        </div>
      )}
      <div className="msg-body md">
        <MarkdownMessage content={item.data.text} />
      </div>
    </>
  )
}

function formatWhen(iso: string) {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })
  } catch {
    return iso
  }
}
