"use client";

import {
  ChevronDownIcon,
  ChevronRightIcon,
} from "lucide-react";
import { useState } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface CollapsibleConfigSectionProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  defaultOpen?: boolean;
  accentClassName?: string;
  className?: string;
  children: React.ReactNode;
}

export function CollapsibleConfigSection({
  title,
  description,
  icon,
  badge,
  defaultOpen = true,
  accentClassName = "text-blue-600 hover:text-blue-700",
  className,
  children,
}: CollapsibleConfigSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <Collapsible open={open} onOpenChange={setOpen} className={cn("rounded-lg border bg-card p-4 space-y-3", className)}>
      <CollapsibleTrigger
        className={cn(
          "flex w-full items-center gap-2 border-b py-2 text-sm font-bold transition-colors",
          accentClassName,
        )}
      >
        {open ? (
          <ChevronDownIcon className="size-4 shrink-0" />
        ) : (
          <ChevronRightIcon className="size-4 shrink-0" />
        )}
        {icon}
        <span>{title}</span>
        {badge ? <span className="ml-1">{badge}</span> : null}
      </CollapsibleTrigger>

      <CollapsibleContent className="space-y-3 pt-1">
        {description ? (
          <p className="text-xs text-muted-foreground">{description}</p>
        ) : null}
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
