import { DatamakepoolChatConsole } from "@/components/datamakepool/chat/datamakepool-chat-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolChatPage({
  searchParams,
}: {
  searchParams: Promise<{ conversationId?: string; flowdraftId?: string }>
}) {
  const params = await searchParams

  return (
    <DatamakepoolChatConsole
      initialConversationId={parseOptionalId(params.conversationId)}
      initialFlowdraftId={parseOptionalId(params.flowdraftId)}
    />
  )
}
