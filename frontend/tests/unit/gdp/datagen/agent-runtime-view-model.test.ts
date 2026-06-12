import { expect, test } from "vitest";

import { deriveWaitingInteraction } from "@/gdp/datagen/agent/agent-runtime-view-model";
import type {
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTimelineResponse,
} from "@/gdp/datagen/common/lib/types";

function makeTaskRun(pendingQuestion: string): AgentRuntimeTaskRunResponse {
  return {
    task_run_id: "tr-1",
    status: "WAITING_USER",
    user_goal: "造一笔已支付订单",
    env_code: "SIT1",
    pending_question: pendingQuestion,
    failure_reason: null,
    created_at: "2026-06-12T00:00:00Z",
    updated_at: "2026-06-12T00:00:00Z",
    finished_at: null,
  };
}

const emptyTimeline: AgentRuntimeTimelineResponse = {
  task_run_id: "tr-1",
  steps: [],
  actions: [],
  attempts: [],
  observations: [],
  evidences: [],
  verdicts: [],
  variables: [],
  requirements: [],
  proposals: [],
  decisions: [],
  approval_records: [],
};

test("deriveWaitingInteraction strips backend input prefixes from missing fields", () => {
  const interaction = deriveWaitingInteraction(
    makeTaskRun("缺少必填信息：inputs.buyer_id。请补充后继续。"),
    emptyTimeline,
  );

  expect(interaction).toEqual({ type: "missing_input", fields: ["buyer_id"] });
});
