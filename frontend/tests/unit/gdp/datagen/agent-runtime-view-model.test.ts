import { expect, test } from "vitest";

import {
  deriveCompletionResult,
  deriveWaitingInteraction,
} from "@/gdp/datagen/agent/agent-runtime-view-model";
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
  task_run: {
    task_run_id: "tr-1",
    status: "WAITING_USER",
    active_step_id: null,
    suspend_reason: null,
  },
  steps: [],
  step_edges: [],
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

  expect(interaction).toEqual({ type: "missing_input", fields: ["buyer_id"], stepId: undefined });
});

test("deriveWaitingInteraction treats malformed null candidates as empty candidates", () => {
  const timeline = {
    ...emptyTimeline,
    proposals: [
      {
        proposal_id: "prop-1",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-1",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: [],
        created_at: "2026-06-12T00:00:00Z",
        candidates: null,
      },
    ],
  } as unknown as AgentRuntimeTimelineResponse;

  const interaction = deriveWaitingInteraction(makeTaskRun("请选择场景"), timeline);

  expect(interaction).toEqual({ type: "manual_scene_code", proposal: timeline.proposals[0], stepId: undefined });
});

test("deriveCompletionResult rejects unknown verdict types", () => {
  const taskRun: AgentRuntimeTaskRunResponse = {
    ...makeTaskRun(""),
    status: "FAILED",
    failure_reason: "后端返回了未知判定",
    finished_at: "2026-06-12T00:01:00Z",
  };
  const timeline = {
    ...emptyTimeline,
    verdicts: [
      {
        verdict_id: "vrd-1",
        task_run_id: "tr-1",
        step_id: "step-1",
        evidence_id: "evi-1",
        verdict_type: "PENDING",
        reason: "未知判定",
        tainted_variable_ids: [],
        created_at: "2026-06-12T00:01:00Z",
      },
    ],
  } as unknown as AgentRuntimeTimelineResponse;

  expect(deriveCompletionResult(taskRun, timeline)).toBeNull();
});
