import { expect, test } from "vitest";

import {
  buildAgentRuntimeStartRequest,
  getAgentRuntimePreset,
  MVP4A_SCENE_CODE,
} from "@/gdp/datagen/agent/agent-runtime-presets";

test("MVP3 preset starts Runtime without explicit scene code", () => {
  const preset = getAgentRuntimePreset("mvp3_multi_scene");
  const request = buildAgentRuntimeStartRequest(preset.sceneCode, preset.inputs);

  expect(preset.userGoal).toBe("创建订单并支付");
  expect(request).toEqual({
    scene_code: null,
    inputs: {
      buyer_id: "U10001",
    },
  });
});

test("MVP4A preset keeps explicit composite scene entry", () => {
  const preset = getAgentRuntimePreset("mvp4a_single_scene");
  const request = buildAgentRuntimeStartRequest(preset.sceneCode, preset.inputs);

  expect(request.scene_code).toBe(MVP4A_SCENE_CODE);
  expect(request.inputs).toMatchObject({
    buyer_id: "U10001",
    approved: true,
  });
});
