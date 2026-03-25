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
  searchParams: Promise<{ templateId?: string; revisionId?: string; created?: string }>
}) {
  const [{ runId }, query] = await Promise.all([params, searchParams])

  return (
    <RunDetailConsole
      runId={Number(runId)}
      returnTemplateId={parseOptionalId(query.templateId)}
      returnRevisionId={parseOptionalId(query.revisionId)}
      showCreatedNotice={query.created === "1"}
    />
  )
}
