import { InfoIcon, PlusIcon, RefreshCwIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import type {
  ConfigStatus,
  EnvironmentResponse,
  SysResponse,
} from "../common/lib/types";

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
  children: ReactNode;
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

export function ConfigToolbar({
  createLabel,
  loading,
  onCreate,
  onRefresh,
}: {
  createLabel: string;
  loading: boolean;
  onCreate: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button onClick={onCreate} className="gap-1.5" size="sm">
        <PlusIcon className="size-4" />
        {createLabel}
      </Button>
      <Button
        variant="outline"
        size="icon"
        onClick={onRefresh}
        disabled={loading}
      >
        <RefreshCwIcon className={`size-4 ${loading ? "animate-spin" : ""}`} />
      </Button>
    </div>
  );
}

export function StatusSelect({
  value,
  onChange,
}: {
  value: ConfigStatus;
  onChange: (value: ConfigStatus) => void;
}) {
  return (
    <Select value={value} onValueChange={(v) => onChange(v as ConfigStatus)}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="ENABLED">启用</SelectItem>
        <SelectItem value="DISABLED">停用</SelectItem>
      </SelectContent>
    </Select>
  );
}

export function EnvironmentSelect({
  value,
  envs,
  onChange,
}: {
  value: string;
  envs: EnvironmentResponse[];
  onChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder="选择环境" />
      </SelectTrigger>
      <SelectContent>
        {envs.map((env) => (
          <SelectItem key={env.envCode} value={env.envCode}>
            {env.envName} ({env.envCode})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function SystemSelect({
  value,
  systems,
  onChange,
}: {
  value: string;
  systems: SysResponse[];
  onChange: (value: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue placeholder="选择系统" />
      </SelectTrigger>
      <SelectContent>
        {systems.map((sys) => (
          <SelectItem key={sys.sysCode} value={sys.sysCode}>
            {sys.sysName} ({sys.sysCode})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function systemNameByCode(systems: SysResponse[], sysCode: string) {
  return systems.find((sys) => sys.sysCode === sysCode)?.sysName ?? sysCode;
}
