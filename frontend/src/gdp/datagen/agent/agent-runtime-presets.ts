import type { AgentRuntimeTaskRunStartRequest, SceneSummary } from "../common/lib/types";

export type AgentRuntimePresetId = "mvp3_multi_scene" | "mvp4a_single_scene";

export interface AgentRuntimeStartPreset {
  id: AgentRuntimePresetId;
  label: string;
  badge: string;
  description: string;
  userGoal: string;
  sceneCode: string | null;
  inputs: Record<string, unknown>;
}

export const MVP4A_SCENE_CODE = "mvp4a_order_payment_inventory_sql_flow";

export const AGENT_RUNTIME_PRESETS: AgentRuntimeStartPreset[] = [
  {
    id: "mvp3_multi_scene",
    label: "MVP3 多 Scene",
    badge: "Planner",
    description: "创建订单、支付订单、查询订单状态由 Runtime 串联。",
    userGoal: "创建订单并支付",
    sceneCode: null,
    inputs: {
      buyer_id: "U10001",
    },
  },
  {
    id: "mvp4a_single_scene",
    label: "MVP4A 五步闭环",
    badge: "Scene",
    description: "固定执行订单、库存、支付、查询、SQL 校验场景。",
    userGoal: "MVP4A 订单支付库存 SQL 五步闭环",
    sceneCode: MVP4A_SCENE_CODE,
    inputs: {
      buyer_id: "U10001",
      sku_id: "SKU10001",
      quantity: 1,
      unit_price: 299.0,
      amount: 299.0,
      payment_method: "ALIPAY",
      request_id: "req-mvp4a-001",
      warehouse_code: "WH-SH-01",
      city: "上海",
      address: "浦东新区测试路 100 号",
      approved: true,
    },
  },
];

export function getAgentRuntimePreset(id: AgentRuntimePresetId): AgentRuntimeStartPreset {
  const preset = AGENT_RUNTIME_PRESETS.find((item) => item.id === id);
  if (!preset) {
    throw new Error(`未知运行台 preset: ${id}`);
  }
  return preset;
}

export function findPresetBySceneCode(sceneCode: string | null): AgentRuntimePresetId | null {
  return AGENT_RUNTIME_PRESETS.find((item) => item.sceneCode === sceneCode)?.id ?? null;
}

export function getSceneDefaultInputs(scene: SceneSummary | null): Record<string, unknown> {
  if (!scene) return {};
  return AGENT_RUNTIME_PRESETS.find((item) => item.sceneCode === scene.sceneCode)?.inputs ?? {};
}

export function buildAgentRuntimeStartRequest(
  sceneCode: string | null,
  inputs: Record<string, unknown>,
): AgentRuntimeTaskRunStartRequest {
  return {
    scene_code: sceneCode,
    inputs,
  };
}
