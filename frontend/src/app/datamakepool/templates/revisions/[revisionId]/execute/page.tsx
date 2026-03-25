import { TemplateExecutionConsole } from "@/components/datamakepool/templates/template-execution-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolTemplateExecutePage({
  params,
  searchParams,
}: {
  params: Promise<{ revisionId: string }>
  searchParams: Promise<{ templateId?: string }>
}) {
  const [{ revisionId }, query] = await Promise.all([params, searchParams])

  return (
    <TemplateExecutionConsole
      revisionId={Number(revisionId)}
      templateId={parseOptionalId(query.templateId)}
    />
  )
}
