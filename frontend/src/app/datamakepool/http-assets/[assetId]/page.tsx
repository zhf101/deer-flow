import { HttpAssetDetailConsole } from "@/components/datamakepool/assets/http-asset-detail-console"

function parseOptionalId(value?: string): number | null {
  if (!value) {
    return null
  }

  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export default async function DatamakepoolHttpAssetDetailPage({
  params,
  searchParams,
}: {
  params: Promise<{ assetId: string }>
  searchParams: Promise<{ templateId?: string; revisionId?: string }>
}) {
  const [{ assetId }, query] = await Promise.all([params, searchParams])

  return (
    <HttpAssetDetailConsole
      assetId={Number(assetId)}
      returnTemplateId={parseOptionalId(query.templateId)}
      returnRevisionId={parseOptionalId(query.revisionId)}
    />
  )
}
