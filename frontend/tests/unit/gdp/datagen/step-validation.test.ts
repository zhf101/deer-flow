import { expect, test } from "vitest";

import { validateSceneForPublish } from "@/gdp/datagen/common/lib/step-validation";
import type { SceneDefinition } from "@/gdp/datagen/common/lib/types";

function makeScene(rulePath: unknown): SceneDefinition {
  return {
    sceneCode: "createPaidOrder",
    sceneName: "创建已支付订单",
    environmentField: "env",
    inputSchema: [],
    steps: [],
    resultMapping: {},
    successCriteria: {
      enabled: true,
      businessSuccess: {
        allOf: [{ path: rulePath as string, op: "EXISTS" }],
        anyOf: [],
      },
      businessFailure: {
        allOf: [],
        anyOf: [],
      },
    },
    batchConfig: {
      enabled: false,
      failurePolicy: "STOP_ON_ERROR",
      maxConcurrency: 1,
    },
    status: "DRAFT",
  };
}

test("validateSceneForPublish reports missing rule path instead of throwing", () => {
  const issues = validateSceneForPublish(makeScene(null));

  expect(issues).toContainEqual({
    field: "successCriteria.businessSuccess.allOf[0].path",
    message: "业务判定规则字段路径不能为空。",
    level: "ERROR",
  });
});
