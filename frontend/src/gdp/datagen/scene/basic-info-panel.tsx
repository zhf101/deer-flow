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

import type { SceneDefinition } from "../common/lib/types";

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
        label="业务域 (Business Domain)"
        description="场景所属业务域，例如：交易、支付、库存、用户等。"
      >
        <Input
          value={scene.businessDomain ?? ""}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, businessDomain: event.target.value })
          }
          placeholder="e.g. 交易"
          className="text-sm"
        />
      </Field>
      <Field
        label="能力类型 (Capability Type)"
        description="场景提供的业务能力类型：CREATE（创建）、UPDATE（更新）、QUERY（查询）、COMPOSITE（组合）。"
      >
        <select
          value={scene.capabilityType ?? "QUERY"}
          disabled={readOnly}
          onChange={(event) =>
            onChange({ ...scene, capabilityType: event.target.value as any })
          }
          className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors"
        >
          <option value="CREATE">CREATE（创建）</option>
          <option value="UPDATE">UPDATE（更新）</option>
          <option value="QUERY">QUERY（查询）</option>
          <option value="ASSERT">ASSERT（断言）</option>
          <option value="COMPOSITE">COMPOSITE（组合）</option>
        </select>
      </Field>
      <Field
        label="业务标签 (Tags)"
        description="用于 Agent 检索的关键词标签，多个标签用逗号分隔，例如：订单,支付,已支付,造数"
      >
        <Input
          value={(scene.tags ?? []).join(", ")}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) => {
            const tags = event.target.value.split(",").map(t => t.trim()).filter(Boolean);
            onChange({ ...scene, tags });
          }}
          placeholder="e.g. 订单, 支付, 已支付, 造数"
          className="text-sm"
        />
      </Field>
      <Field
        label="Agent 描述 (Agent Description)"
        description="面向 Agent 的能力说明，描述场景能完成什么任务、适用范围和关键产出。用于 Agent 理解场景用途。"
      >
        <Textarea
          value={scene.agentDescription ?? ""}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) =>
            onChange({ ...scene, agentDescription: event.target.value })
          }
          placeholder="创建一笔已完成支付的订单，支付状态为 PAID，适用于测试订单支付后的业务流程..."
          className="min-h-24 resize-none text-sm"
        />
      </Field>
      <Field
        label="副作用 (Side Effects)"
        description="场景执行会造成的业务副作用（如创建订单、修改库存等），用于写操作确认。格式：effectType|target|description，多个用分号分隔。"
      >
        <Textarea
          value={(scene.sideEffects ?? []).map(e => `${e.effectType}|${e.target ?? ""}|${e.description ?? ""}`).join(";\n")}
          disabled={readOnly}
          readOnly={readOnly}
          onChange={(event) => {
            const lines = event.target.value.split(";").map(l => l.trim()).filter(Boolean);
            const sideEffects = lines.map(line => {
              const [effectType, target, description] = line.split("|").map(s => s.trim());
              return {
                effectType: effectType || "",
                target: target || null,
                description: description || null
              };
            }).filter(e => e.effectType); // 过滤掉空的 effectType
            onChange({ ...scene, sideEffects });
          }}
          placeholder="e.g. CREATE_ORDER|trade_order|创建订单记录;\nMODIFY_PAYMENT|payment_record|修改支付状态"
          className="min-h-20 resize-none text-sm font-mono"
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
