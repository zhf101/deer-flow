/**
 * 提取表达式工具：在 ${SOURCE(path)} 形式与可读字段名之间转换。
 *
 * Framework-agnostic helpers extracted from the React
 * `http-output-extraction-editor.tsx` so both the output-extraction editor and
 * the response-mapping editor can share them (the source re-exported these from
 * the component module).
 */

const EXPRESSION_RE = /^\$\{([A-Z_]+)\((.*)\)\}$/

export function extractorExpression(source: string, path: string): string {
  return `\${${source}(${path})}`
}

export function expressionPath(path: string): string {
  return path.replace(/^\$\.?/, '')
}

export function bodyExpression(path: string): string {
  return extractorExpression('RES_BODY', expressionPath(path))
}

export function headerExpression(name: string): string {
  return extractorExpression('RES_HEADER', name)
}

export function cookieExpression(name: string): string {
  return extractorExpression('RES_COOKIE', name)
}

export function parseExtractor(
  value: string,
): { source: string; path: string } | null {
  const match = EXPRESSION_RE.exec(value.trim())
  if (!match) return null
  return { source: match[1] ?? '', path: match[2] ?? '' }
}

export function mappingSource(value: string): 'Body' | 'Headers' | 'Cookies' {
  const parsed = parseExtractor(value)
  if (parsed?.source === 'RES_HEADER') return 'Headers'
  if (parsed?.source === 'RES_COOKIE') return 'Cookies'
  return 'Body'
}

export function mappingDisplayName(value: string): string {
  const parsed = parseExtractor(value)
  if (parsed) return parsed.path.split('.').pop()?.replace('[*]', '') ?? parsed.path
  return value.split('.').pop()?.replace('[*]', '') ?? value
}

export function normalizeMapping(value: string): string {
  const parsed = parseExtractor(value)
  if (parsed) {
    return `${parsed.source}:${parsed.source === 'RES_HEADER' ? parsed.path.toLowerCase() : parsed.path}`
  }
  return `INVALID:${value}`
}

export function isSameMapping(a: string, b: string): boolean {
  return normalizeMapping(a) === normalizeMapping(b)
}
