import type { ChatStatus, UIMessage } from 'ai'

import { MessageBubble } from '@/components/chat/MessageBubble'
import { PipelineStatus } from '@/components/chat/PipelineStatus'
import {
  ChatContainerContent,
  ChatContainerRoot,
} from '@/components/ui/chat-container'
import { PromptSuggestion } from '@/components/ui/prompt-suggestion'
import { ScrollButton } from '@/components/ui/scroll-button'
import {
  textFromMessage,
  type CitationPayload,
  type PipelineStatus as PipelineStatusState,
} from '@/lib/citations'
import { EXAMPLE_QUESTIONS } from '@/lib/suggestions'

type MessageListProps = {
  messages: UIMessage[]
  status: ChatStatus
  pipelineStatus: PipelineStatusState | null
  selectedCitationIndex: number | null
  onSelectCitation: (citation: CitationPayload) => void
  onSendSuggestion: (text: string) => void
}

export function MessageList({
  messages,
  status,
  pipelineStatus,
  selectedCitationIndex,
  onSelectCitation,
  onSendSuggestion,
}: MessageListProps) {
  const isBusy = status === 'submitted' || status === 'streaming'
  const lastMessage = messages[messages.length - 1]
  const lastIsStreamingAssistant =
    status === 'streaming' &&
    lastMessage?.role === 'assistant' &&
    textFromMessage(lastMessage).length > 0

  // Show the pipeline block while the model is working but before answer text arrives.
  const showPipeline = isBusy && !lastIsStreamingAssistant

  return (
    <ChatContainerRoot className="relative flex-1">
      <ChatContainerContent className="mx-auto w-full max-w-3xl gap-6 px-4 py-6">
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 py-12 text-center">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold text-foreground">
                Ask about SEC filings
              </h2>
              <p className="text-sm text-muted-foreground">
                Every answer is grounded in source documents with citations.
              </p>
            </div>
            <div className="flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((question) => (
                <PromptSuggestion
                  key={question}
                  size="sm"
                  className="text-xs"
                  onClick={() => onSendSuggestion(question)}
                >
                  {question}
                </PromptSuggestion>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            selectedCitationIndex={selectedCitationIndex}
            onSelectCitation={onSelectCitation}
            isStreaming={message === lastMessage && lastIsStreamingAssistant}
          />
        ))}

        {showPipeline ? (
          <PipelineStatus
            isSubmitted={status === 'submitted'}
            pipelineStatus={pipelineStatus}
          />
        ) : null}
      </ChatContainerContent>

      <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center">
        <div className="pointer-events-auto">
          <ScrollButton />
        </div>
      </div>
    </ChatContainerRoot>
  )
}
