import { TemplateManagementConsole } from "@/components/datamakepool/templates/template-management-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolTemplatesPage({
  searchParams,
}: {
  searchParams: Promise<{ templateId?: string; revisionId?: string }>
}) {
  const params = await searchParams

  return (
    <TemplateManagementConsole
      initialTemplateId={parseOptionalId(params.templateId)}
      initialRevisionId={parseOptionalId(params.revisionId)}
    />
  )
}
