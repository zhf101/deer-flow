import { SqlAuditConsole } from "@/components/datamakepool/audits/sql-audit-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolAuditsPage({
  searchParams,
}: {
  searchParams: Promise<{ auditId?: string }>
}) {
  const params = await searchParams

  return <SqlAuditConsole initialAuditId={parseOptionalId(params.auditId)} />
}
