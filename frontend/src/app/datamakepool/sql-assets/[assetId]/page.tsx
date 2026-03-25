import { SqlAssetDetailConsole } from "@/components/datamakepool/assets/sql-asset-detail-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolSqlAssetDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ assetId: string }>
  searchParams: Promise<{ templateId?: string; revisionId?: string }>
}) {
  const [{ assetId }, query] = await Promise.all([params, searchParams])

  return (
    <SqlAssetDetailConsole
      assetId={Number(assetId)}
      returnTemplateId={parseOptionalId(query.templateId)}
      returnRevisionId={parseOptionalId(query.revisionId)}
    />
  )
}
