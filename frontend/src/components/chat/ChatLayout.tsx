import { Outlet, useParams } from 'react-router-dom'

import { ThreadSidebar } from '@/components/chat/ThreadSidebar'
import { ThreadsProvider } from '@/components/chat/ThreadsProvider'
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { useThreads } from '@/hooks/useThreads'

function ChatHeader() {
  const { threadId } = useParams()
  const { threads } = useThreads()
  const activeThread = threads.find((thread) => thread.id === threadId)

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b bg-background/80 px-3 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <SidebarTrigger className="text-muted-foreground" />
      <span className="truncate text-sm font-medium text-foreground">
        {activeThread?.title ?? 'Document Copilot'}
      </span>
    </header>
  )
}

export function ChatLayout() {
  return (
    <ThreadsProvider>
      <SidebarProvider>
        <ThreadSidebar />
        <SidebarInset className="flex h-svh min-h-0 flex-col">
          <ChatHeader />
          <div className="flex min-h-0 flex-1 flex-col">
            <Outlet />
          </div>
        </SidebarInset>
      </SidebarProvider>
    </ThreadsProvider>
  )
}
