"use client";

import { InfoIcon } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import type { SceneDefinition } from "../lib/types";

interface BasicInfoPanelProps {
  scene: SceneDefinition;
  persisted: boolean;
  onChange: (scene: SceneDefinition) => void;
  readOnly?: boolean;
}

export function BasicInfoPanel({
  scene,
  persisted,
  onChange,
  readOnly,
}: BasicInfoPanelProps) {
  return (
    <div className="space-y-6">
      <Field 
        label="场景编码 (Scene Code)" 
        description="场景的全局唯一标识符，建议使用小写字母、数字和下划线。创建后不可修改。"
      >
        <Input
          value={scene.sceneCode}
          disabled={persisted || readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, sceneCode: event.target.value.trim() })
          }
          placeholder="e.g. create_user_order"
          className="font-mono text-sm"
        />
      </Field>
      <Field 
        label="场景名称 (Scene Name)" 
        description="简短易懂的业务场景名称，用于在列表和报告中展示。"
      >
        <Input
          value={scene.sceneName}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, sceneName: event.target.value })
          }
          placeholder="e.g. 创建测试订单并支付"
          className="text-sm"
        />
      </Field>
      <Field 
        label="场景分类 (Scene Type)" 
        description="业务归属分类，如：信用卡、消费信贷、电商业务等。"
      >
        <Input
          value={scene.sceneType ?? ""}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, sceneType: event.target.value })
          }
          placeholder="e.g. credit_card"
          className="text-sm"
        />
      </Field>
      <Field 
        label="备注说明 (Remark)" 
        description="详细描述该场景的用途、业务规则以及配置注意事项。"
      >
        <Textarea
          value={scene.sceneRemark ?? ""}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, sceneRemark: event.target.value })
          }
          placeholder="该场景用于模拟核心流程..."
          className="min-h-24 resize-none text-sm"
        />
      </Field>
    </div>
  );
}

function Field({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">{label}</span>
        {description && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <InfoIcon className="text-muted-foreground size-4" />
              </TooltipTrigger>
              <TooltipContent className="max-w-sm">
                <p className="text-xs">{description}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>
      {children}
    </div>
  );
}
