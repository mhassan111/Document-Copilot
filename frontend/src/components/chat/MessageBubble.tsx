import type { UIMessage } from 'ai'

import { AssistantMessage } from '@/components/chat/AssistantMessage'
import { textFromMessage, type CitationPayload } from '@/lib/citations'

type MessageBubbleProps = {
  message: UIMessage
  selectedCitationIndex: number | null
  onSelectCitation: (citation: CitationPayload) => void
  isStreaming?: boolean
}

export function MessageBubble({
  message,
  selectedCitationIndex,
  onSelectCitation,
  isStreaming,
}: MessageBubbleProps) {
  if (message.role === 'assistant') {
    return (
      <AssistantMessage
        message={message}
        selectedCitationIndex={selectedCitationIndex}
        onSelectCitation={onSelectCitation}
        isStreaming={isStreaming}
      />
    )
  }

  const text = textFromMessage(message)

  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-secondary-foreground">
        {text}
      </div>
    </div>
  )
}
