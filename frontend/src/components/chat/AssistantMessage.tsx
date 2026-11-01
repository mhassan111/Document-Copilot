import { useState } from 'react'
import type { UIMessage } from 'ai'
import { Check, Copy } from 'lucide-react'

import { AssistantMarkdown } from '@/components/chat/AssistantMarkdown'
import { CitationChip } from '@/components/chat/CitationChip'
import { Button } from '@/components/ui/button'
import {
  citationsFromMessage,
  textFromMessage,
  type CitationPayload,
} from '@/lib/citations'

type AssistantMessageProps = {
  message: UIMessage
  selectedCitationIndex: number | null
  onSelectCitation: (citation: CitationPayload) => void
  isStreaming?: boolean
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className="text-muted-foreground"
      onClick={() => void handleCopy()}
      aria-label="Copy answer"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </Button>
  )
}

export function AssistantMessage({
  message,
  selectedCitationIndex,
  onSelectCitation,
  isStreaming = false,
}: AssistantMessageProps) {
  const text = textFromMessage(message)
  const citations = citationsFromMessage(message)
  const hasNoEvidence = !isStreaming && text.length > 0 && citations.length === 0

  return (
    <div className="min-w-0 space-y-3">
      {text ? (
        <AssistantMarkdown
          text={text}
          citations={citations}
          selectedCitationIndex={selectedCitationIndex}
          onSelectCitation={onSelectCitation}
        />
      ) : null}

      {isStreaming && text ? (
        <span className="inline-block h-4 w-2 translate-y-0.5 animate-pulse rounded-sm bg-foreground" />
      ) : null}

      {hasNoEvidence ? (
        <p className="rounded-lg border border-dashed bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          No filing evidence was found to support this answer.
        </p>
      ) : null}

      {citations.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {citations.map((citation) => (
            <CitationChip
              key={`${citation.chunkId}-${citation.citationIndex}`}
              citation={citation}
              selected={selectedCitationIndex === citation.citationIndex}
              onSelect={onSelectCitation}
            />
          ))}
        </div>
      ) : null}

      {!isStreaming && text ? (
        <div className="flex items-center gap-1 pt-0.5">
          <CopyButton text={text} />
        </div>
      ) : null}
    </div>
  )
}
