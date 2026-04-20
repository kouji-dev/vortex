import { MarkdownMessage } from '~/components/chat/MarkdownMessage'
import type { ThreadItem } from '~/lib/chat-types'

type Props = {
  item: ThreadItem & { kind: 'assistant_text' }
  streaming?: boolean
}

export function AssistantTextItem({ item, streaming }: Props) {
  return (
    <div className="msg-body md">
      <MarkdownMessage content={item.data.text} streaming={streaming} />
    </div>
  )
}
