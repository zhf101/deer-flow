/**
 * ============================================================================
 * 步骤测试工具函数
 * ============================================================================
 *
 * 将内联 StepDefinition 适配为 testHttpSource API 所需的 HttpSourceConfig。
 * 构造运行时变量上下文（输入参数默认值、前序步骤输出等）。
 */

import type {
  HttpSourceConfig,
  InputFieldDefinition,
  SceneDefinition,
  StepDefinition,
} from "./types";
import { createDefaultHttpTimeoutConfig } from "./defaults";

/** 将内联 HTTP StepDefinition 转换为 testHttpSource 所需的配置 */
export function stepToHttpTestConfig(step: StepDefinition): HttpSourceConfig {
  return {
    sourceCode: step.stepId,
    sourceName: step.stepName ?? step.stepId,
    sysCode: step.sysCode ?? "",
    // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty string path should fall through to url
    path: step.path || step.url || "",
    method: step.method ?? "POST",
    timeoutConfig: step.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
    requestMapping: step.requestMapping ?? {},
    bodySchema: step.bodySchema ?? null,
    responseSchema: step.responseSchema ?? null,
    responseHeadersSchema: step.responseHeadersSchema ?? null,
    responseCookiesSchema: step.responseCookiesSchema ?? null,
    responseHandling: step.responseHandling ?? null,
    errorMapping: step.errorMapping ?? null,
    businessErrorMapping: step.businessErrorMapping ?? null,
    outputMapping: step.outputMapping ?? {},
    outputMeta: step.outputMeta ?? null,
    retryPolicy: step.retryPolicy ?? null,
    status: "ENABLED",
  };
}

/**
 * 将运行时变量值替换到配置中，用于单步测试。
 *
 * 替换规则：
 *   - ${input.xxx} -> inputs[xxx]
 *   - ${steps.xxx.outputs.yyy} -> depOutputs[xxx][yyy]
 *   - 无法解析的变量保留原样（后端会用空字符串兜底）
 */
export function resolveRuntimeVariables(
  config: HttpSourceConfig,
  inputs: Record<string, unknown>,
  depOutputs: Record<string, Record<string, unknown>>,
): HttpSourceConfig {
  const stringify = (val: unknown): string => {
    if (val == null) return "";
    if (typeof val === "string") return val;
    return JSON.stringify(val);
  };

  const resolve = (value: unknown): unknown => {
    if (typeof value !== "string") return value;
    return value.replace(
      /\$\{(input|steps)\.([^}]+)\}/g,
      (_match, type: string, path: string) => {
        if (type === "input") {
          return stringify(inputs[path]);
        }
        // steps.xxx.outputs.yyy -> depOutputs[xxx][yyy]
        const parts = path.split(".outputs.");
        if (parts.length === 2) {
          const [stepId, outputName] = parts;
          return stringify(depOutputs[stepId ?? ""]?.[outputName ?? ""]);
        }
        return _match;
      },
    );
  };

  const resolveRecord = (
    obj: Record<string, unknown> | null | undefined,
  ): Record<string, unknown> => {
    if (!obj) return {};
    const result: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(obj)) {
      result[key] = resolve(val);
    }
    return result;
  };

  return {
    ...config,
    requestMapping: resolveRecord(config.requestMapping),
  };
}

/** 从 inputSchema 提取默认输入值，作为测试的初始参数 */
export function buildDefaultInputs(
  inputSchema: InputFieldDefinition[],
): Record<string, unknown> {
  const inputs: Record<string, unknown> = {};
  const walk = (fields: InputFieldDefinition[]) => {
    for (const field of fields) {
      if (field.defaultValue != null) {
        inputs[field.name] = field.defaultValue;
      } else if (field.type === "object" && field.children) {
        inputs[field.name] = buildDefaultInputs(field.children);
      } else {
        inputs[field.name] = "";
      }
    }
  };
  walk(inputSchema);
  return inputs;
}

/** 收集前序依赖步骤的输出变量（用于测试时提供上下文） */
export function collectDependencyOutputs(
  step: StepDefinition,
  scene: SceneDefinition,
): Record<string, Record<string, unknown>> {
  const outputs: Record<string, Record<string, unknown>> = {};
  const stepsById = new Map(scene.steps.map((s) => [s.stepId, s]));

  for (const depId of step.dependsOn) {
    const depStep = stepsById.get(depId);
    if (!depStep) continue;
    // 用 outputMapping 的 key 作为占位，值为空字符串（用户可手动填写）
    const stepOutputs: Record<string, unknown> = {};
    for (const key of Object.keys(depStep.outputMapping ?? {})) {
      stepOutputs[key] = "";
    }
    outputs[depId] = stepOutputs;
  }
  return outputs;
}
