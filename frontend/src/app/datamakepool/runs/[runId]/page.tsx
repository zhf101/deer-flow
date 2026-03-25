import { RunDetailConsole } from "@/components/datamakepool/runs/run-detail-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolRunDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ runId: string }>
  searchParams: Promise<{
    templateId?: string
    revisionId?: string
    created?: string
    returnTo?: string
    conversationId?: string
    flowdraftId?: string
  }>
}) {
  const [{ runId }, query] = await Promise.all([params, searchParams])
  const conversationId = parseOptionalId(query.conversationId)
  const flowdraftId = parseOptionalId(query.flowdraftId)
  let returnHref: string | undefined
  let returnLabel: string | undefined

  if (query.returnTo === "chat") {
    const nextQuery = new URLSearchParams()
    if (conversationId) {
      nextQuery.set("conversationId", String(conversationId))
    }
    if (flowdraftId) {
      nextQuery.set("flowdraftId", String(flowdraftId))
    }
    returnHref = nextQuery.toString()
      ? `/datamakepool/chat?${nextQuery.toString()}`
      : "/datamakepool/chat"
    returnLabel = "返回探索"
  }

  return (
    <RunDetailConsole
      runId={Number(runId)}
      returnTemplateId={parseOptionalId(query.templateId)}
      returnRevisionId={parseOptionalId(query.revisionId)}
      returnHref={returnHref}
      returnLabel={returnLabel}
      showCreatedNotice={query.created === "1"}
    />
  )
}
