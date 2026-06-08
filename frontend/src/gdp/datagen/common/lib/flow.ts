import type { Edge, Node } from "@xyflow/react";

import { stepLabel } from "./defaults";
import type { StepDefinition } from "./types";

export interface StepNodeData extends Record<string, unknown> {
  label: string;
  type: string;
  enabled: boolean;
  order: number;
  url?: string;
  sql?: string;
  outputCount: number;
  hasErrors: boolean;
}

export function stepsToNodes(steps: StepDefinition[]): Node<StepNodeData>[] {
  return steps.map((step, index) => {
    const isHttp = step.type === 'HTTP';
    const outputCount = Object.keys(step.outputMapping ?? {}).length;
    // 简单判断：HTTP 缺 path 或 SQL 缺 normalizedSql 视为有错误
    const hasErrors = isHttp
      // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty string path/url should fall through
      ? !(step.path || step.url) || !step.sysCode
      : !step.normalizedSql || !step.datasourceCode || !step.sysCode;
    return {
      id: step.stepId,
      type: isHttp ? "httpStep" : step.type === 'SQL' ? "sqlStep" : "default",
      position: step.position ?? { x: 120 + index * 140, y: 120 },
      data: {
        label: step.stepName ?? stepLabel(step.type),
        type: step.type,
        enabled: step.enabled,
        order: index + 1,
        // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty strings should fall through
        url: step.url || step.path || undefined,
        // eslint-disable-next-line @typescript-eslint/prefer-nullish-coalescing -- empty strings should fall through
        sql: step.sqlText || step.normalizedSql || step.sqlTemplateCode || undefined,
        outputCount,
        hasErrors,
      },
    };
  });
}

export function stepsToEdges(steps: StepDefinition[]): Edge[] {
  const edges: Edge[] = [];

  steps.forEach((step) => {
    // 1. 显式步骤依赖（Depends On）
    step.dependsOn.forEach((source) => {
      edges.push({
        id: `${source}-${step.stepId}-dep`,
        source,
        target: step.stepId,
        animated: step.enabled,
        label: "执行顺序",
        labelStyle: { fontSize: '9px', fill: '#94a3b8' },
        style: { stroke: '#cbd5e1', strokeWidth: 1.5 },
      });
    });

    // 2. 隐式数据映射依赖
    const stepStr = JSON.stringify(step);
    const varRegex = /\$\{steps\.([\w-]+)\.outputs\.([\w-]+)\}/g;
    let match;
    const dataEdges = new Map<string, Set<string>>();

    while ((match = varRegex.exec(stepStr)) !== null) {
        const source = match[1];
        const varName = match[2];
        if (source !== step.stepId) {
            if (!dataEdges.has(source)) dataEdges.set(source, new Set());
            dataEdges.get(source)!.add(varName);
        }
    }

    dataEdges.forEach((vars, source) => {
        const varList = Array.from(vars).join(', ');
        edges.push({
            id: `${source}-${step.stepId}-data`,
            source,
            target: step.stepId,
            animated: true,
            label: varList,
            labelBgPadding: [4, 4],
            labelBgBorderRadius: 4,
            labelBgStyle: { fill: '#eff6ff', color: '#3b82f6', fillOpacity: 0.9 },
            labelStyle: { fontSize: '10px', fill: '#2563eb', fontWeight: 'bold' },
            style: { stroke: '#3b82f6', strokeWidth: 2, strokeDasharray: '4,4' },
        });
    });
  });

  return edges;
}

export function applyNodePositions(
  steps: StepDefinition[],
  nodes: Node[],
): StepDefinition[] {
  const positions = new Map(nodes.map((node) => [node.id, node.position]));
  return steps.map((step) => ({
    ...step,
    position: positions.get(step.stepId) ?? step.position ?? null,
  }));
}

export function applyEdgesToSteps(
  steps: StepDefinition[],
  edges: Edge[],
): StepDefinition[] {
  return steps.map((step) => ({
    ...step,
    dependsOn: edges
      .filter((edge) => edge.target === step.stepId)
      .map((edge) => edge.source),
  }));
}
