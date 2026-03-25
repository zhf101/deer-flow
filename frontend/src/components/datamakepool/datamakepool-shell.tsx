"use client"

import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

interface DatamakepoolShellMetric {
  label: string
  value: string
  hint?: string
}

interface DatamakepoolShellProps {
  eyebrow: string
  title: string
  description: string
  metrics?: DatamakepoolShellMetric[]
  actions?: ReactNode
  children: ReactNode
  className?: string
}

/**
 * datamakepool 后续还会继续落聊天、Run、审计页。
 * 这里先抽一个统一壳子，保证后续工作台页面的视觉层级和节奏一致。
 */
export function DatamakepoolShell({
  eyebrow,
  title,
  description,
  metrics = [],
  actions,
  children,
  className,
}: DatamakepoolShellProps) {
  return (
    <div
      className={cn(
        "relative flex h-full min-h-0 flex-col overflow-hidden bg-background",
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-64 bg-[radial-gradient(circle_at_top_left,hsl(var(--primary)/0.18),transparent_42%),radial-gradient(circle_at_top_right,hsl(var(--accent-foreground)/0.08),transparent_35%)]" />
        <div className="absolute inset-0 opacity-[0.08] [background-image:linear-gradient(to_right,hsl(var(--border))_1px,transparent_1px),linear-gradient(to_bottom,hsl(var(--border))_1px,transparent_1px)] [background-size:32px_32px]" />
      </div>

      <div className="relative border-b border-border/70 px-6 py-6">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="max-w-3xl">
            <div className="text-xs font-semibold uppercase tracking-[0.24em] text-primary/80">
              {eyebrow}
            </div>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight text-foreground">
              {title}
            </h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{description}</p>
          </div>

          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>

        {metrics.length ? (
          <div className="mt-5 grid gap-3 md:grid-cols-3 xl:max-w-4xl">
            {metrics.map((metric) => (
              <div
                key={metric.label}
                className="rounded-2xl border border-border/70 bg-background/70 px-4 py-3 backdrop-blur-sm"
              >
                <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  {metric.label}
                </div>
                <div className="mt-2 text-2xl font-semibold text-foreground">{metric.value}</div>
                {metric.hint ? (
                  <div className="mt-1 text-xs text-muted-foreground">{metric.hint}</div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </div>

      <div className="relative flex-1 min-h-0 overflow-hidden">{children}</div>
    </div>
  )
}
