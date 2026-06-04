"use client";

import { InfoIcon, VariableIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { listServiceEndpoints } from "../lib/api";
import { HTTP_METHODS } from "../lib/defaults";
import type {
  HttpMethod,
  SceneDefinition,
  ServiceEndpointResponse,
  StepDefinition,
} from "../lib/types";
import { stringifyConfigValue } from "../lib/validation";

import { JsonEditor } from "./json-editor";
import { VariableSelector } from "./variable-selector";
import { HttpRequestMappingEditor } from "./http-request-mapping-editor";
import { HttpResponseMappingEditor } from "./http-response-mapping-editor";

interface HttpStepFormProps {
  scene: SceneDefinition;
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
}

export function HttpStepForm({ scene, step, onChange }: HttpStepFormProps) {
  const [endpoints, setEndpoints] = useState<ServiceEndpointResponse[]>([]);

  const loadEndpoints = useCallback(async () => {
    try {
      setEndpoints(await listServiceEndpoints());
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void loadEndpoints();
  }, [loadEndpoints]);

  const serviceCodes = useMemo(() => {
    const seen = new Map<string, string>();
    for (const ep of endpoints) {
      if (!seen.has(ep.serviceCode)) {
        seen.set(ep.serviceCode, ep.serviceName);
      }
    }
    return Array.from(seen.entries()).map(([code, name]) => ({ code, name }));
  }, [endpoints]);

  const selectedEndpoint = endpoints.find(
    (ep) => ep.serviceCode === step.serviceCode,
  );

  const responseHandling = step.responseHandling ?? {
    expectedContentType: "JSON" as const,
    statusCode: { success: [200] },
    businessSuccess: { allOf: [] },
    businessFailure: { anyOf: [] },
  };
  const retryPolicy = step.retryPolicy ?? {
    enabled: false,
    maxAttempts: 1,
    intervalMs: 1000,
    retryOn: [],
  };

  return (
    <div className="space-y-6">
      {/* Request Section */}
      <div className="space-y-4 border-l-2 border-blue-500/20 pl-5 py-1">
        <div className="flex items-center gap-2 border-b pb-2 mb-2">
          <h4 className="text-sm font-bold">1. 请求配置 (Request)</h4>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            接口地址 (URL)
          </div>
          <div className="grid grid-cols-[100px_160px_1fr] gap-2">
            <Select
              value={step.method ?? "POST"}
              onValueChange={(value) =>
                onChange({ ...step, method: value as HttpMethod })
              }
            >
              <SelectTrigger className="h-8 text-xs font-bold">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HTTP_METHODS.map((method) => (
                  <SelectItem key={method} value={method} className="text-xs">
                    {method}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={step.serviceCode ?? "__none__"}
              onValueChange={(value) =>
                onChange({
                  ...step,
                  serviceCode: value === "__none__" ? "" : value,
                })
              }
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue placeholder="选择服务" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__" className="text-xs">
                  无服务前缀
                </SelectItem>
                {serviceCodes.map((svc) => (
                  <SelectItem key={svc.code} value={svc.code} className="text-xs">
                    {svc.name} ({svc.code})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              value={step.url ?? ""}
              onChange={(event) =>
                onChange({ ...step, url: event.target.value })
              }
              placeholder={
                selectedEndpoint
                  ? `/v1/resource (前缀: ${selectedEndpoint.baseUrl})`
                  : "https://api.example.com/v1/resource"
              }
              className="h-8 text-xs font-mono"
            />
          </div>
          {selectedEndpoint && (
            <p className="text-[10px] text-muted-foreground">
              当前环境前缀:{" "}
              <span className="font-mono text-blue-600">
                {selectedEndpoint.baseUrl}
              </span>
            </p>
          )}
        </div>

        <HttpRequestMappingEditor
          scene={scene}
          step={step}
          onChange={(updates) => onChange({ ...step, ...updates })}
        />
      </div>

      {/* Response Section */}
      <div className="space-y-4 border-l-2 border-emerald-500/20 pl-5 py-1">
        <div className="flex items-center gap-2 border-b pb-2 mb-2">
          <h4 className="text-sm font-bold">2. 响应处理 (Response)</h4>
        </div>

        <HttpResponseMappingEditor
          step={step}
          onChange={(updates) => onChange({ ...step, ...updates })}
        />
      </div>

      {/* Policy Section */}
      <div className="space-y-4 border-l-2 border-amber-500/20 pl-5 py-1">
        <div className="flex items-center gap-2 border-b pb-2 mb-2">
          <h4 className="text-sm font-bold">3. 容错与策略 (Policy)</h4>
        </div>
        
        <div className="bg-muted/30 rounded-md border p-3">
          <label className="mb-2 flex items-center justify-between gap-3 text-xs font-medium">
            失败自动重试
            <Switch
              checked={retryPolicy.enabled}
              onCheckedChange={(checked) =>
                onChange({
                  ...step,
                  retryPolicy: { ...retryPolicy, enabled: checked },
                })
              }
            />
          </label>
          {retryPolicy.enabled && (
            <div className="grid grid-cols-2 gap-3 mt-3">
              <div className="space-y-1">
                <span className="text-[10px] text-muted-foreground">最大重试次数</span>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  value={retryPolicy.maxAttempts}
                  onChange={(event) =>
                    onChange({
                      ...step,
                      retryPolicy: {
                        ...retryPolicy,
                        maxAttempts: Number(event.target.value || 1),
                      },
                    })
                  }
                  className="h-7 text-xs"
                />
              </div>
              <div className="space-y-1">
                <span className="text-[10px] text-muted-foreground">重试间隔 (ms)</span>
                <Input
                  type="number"
                  min={0}
                  value={retryPolicy.intervalMs}
                  onChange={(event) =>
                    onChange({
                      ...step,
                      retryPolicy: {
                        ...retryPolicy,
                        intervalMs: Number(event.target.value || 0),
                      },
                    })
                  }
                  className="h-7 text-xs"
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function stringRecord(value: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key,
      stringifyConfigValue(item),
    ]),
  );
}
