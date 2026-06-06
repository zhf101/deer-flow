import { InfoIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "ENABLED" ? "default" : "secondary"}>
      {status === "ENABLED" ? "启用" : "停用"}
    </Badge>
  );
}

export function FieldRow({
  label,
  children,
  className,
  tooltip,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
  tooltip?: string;
}) {
  return (
    <div className={className}>
      <label className="mb-1 flex items-center gap-1 text-xs font-medium">
        {label}
        {tooltip && (
          <Tooltip>
            <TooltipTrigger asChild>
              <InfoIcon className="size-3 text-muted-foreground cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs text-xs">
              {tooltip}
            </TooltipContent>
          </Tooltip>
        )}
      </label>
      {children}
    </div>
  );
}
