import { useState } from 'react'
import type { ChatStatus } from 'ai'
import { ArrowUp, Square } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from '@/components/ui/prompt-input'

type ChatInputProps = {
  status: ChatStatus
  onSend: (text: string) => void
  onStop: () => void
}

export function ChatInput({ status, onSend, onStop }: ChatInputProps) {
  const [input, setInput] = useState('')
  const isBusy = status === 'submitted' || status === 'streaming'

  function submit() {
    const text = input.trim()
    if (!text || isBusy) return
    onSend(text)
    setInput('')
  }

  return (
    <div className="bg-background px-4 pb-4">
      <div className="mx-auto w-full max-w-3xl">
        <PromptInput
          value={input}
          onValueChange={setInput}
          isLoading={isBusy}
          onSubmit={submit}
          className="rounded-2xl"
        >
          <PromptInputTextarea placeholder="Ask about SEC filings…" />
          <PromptInputActions className="justify-end pt-1">
            {isBusy ? (
              <PromptInputAction tooltip="Stop">
                <Button type="button" size="icon" className="rounded-full" onClick={onStop}>
                  <Square className="size-4 fill-current" />
                </Button>
              </PromptInputAction>
            ) : (
              <PromptInputAction tooltip="Send">
                <Button
                  type="button"
                  size="icon"
                  className="rounded-full"
                  onClick={submit}
                  disabled={input.trim() === ''}
                  aria-label="Send message"
                >
                  <ArrowUp className="size-4" />
                </Button>
              </PromptInputAction>
            )}
          </PromptInputActions>
        </PromptInput>
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Answers are grounded in SEC filings. Verify citations before relying on them.
        </p>
      </div>
    </div>
  )
}
