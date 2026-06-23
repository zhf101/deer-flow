import { expect, test } from "vitest";

import {
  deriveChatMessages,
  deriveCompletionResult,
  deriveResourceGapTree,
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

  expect(interaction).toEqual({
    type: "missing_input",
    fields: ["buyer_id"],
    stepId: undefined,
  });
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
        source_candidates: null,
        infra_candidates: null,
      },
    ],
  } as unknown as AgentRuntimeTimelineResponse;

  const interaction = deriveWaitingInteraction(
    makeTaskRun("请选择场景"),
    timeline,
  );

  expect(interaction).toEqual({
    type: "manual_scene_code",
    proposal: timeline.proposals[0],
    stepId: undefined,
  });
});

test("deriveWaitingInteraction shows resource discovery before manual scene fallback", () => {
  const timeline = {
    ...emptyTimeline,
    proposals: [
      {
        proposal_id: "prop-source",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-source",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: ["订单"],
        created_at: "2026-06-12T00:00:00Z",
        candidates: [],
        source_candidates: [
          {
            source_type: "HTTP",
            source_code: "createOrderApi",
            source_name: "创建订单接口",
            score: 0.8,
            reasons: ["命中订单"],
            missing_inputs: [],
            requires_confirmation: true,
            sys_code: "TRADE",
            method: "POST",
            path: "/api/orders",
            datasource_code: null,
            operation: null,
          },
        ],
        infra_candidates: [
          {
            resource_type: "HTTP",
            ready: false,
            confidence: 0.4,
            missing_fields: ["serviceEndpoint"],
            matched_systems: [],
            matched_environments: [],
            matched_service_endpoints: [],
            matched_datasources: [],
          },
        ],
      },
    ],
  } as AgentRuntimeTimelineResponse;

  const interaction = deriveWaitingInteraction(
    makeTaskRun("没有完整场景"),
    timeline,
  );

  expect(interaction?.type).toBe("resource_discovery");
  if (interaction?.type === "resource_discovery") {
    expect(interaction.sourceCandidates[0]!.source_code).toBe("createOrderApi");
    expect(interaction.infraCandidates[0]!.missing_fields).toEqual([
      "serviceEndpoint",
    ]);
  }
});

test("deriveChatMessages includes resource discovery summary", () => {
  const timeline = {
    ...emptyTimeline,
    proposals: [
      {
        proposal_id: "prop-source",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-source",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: [],
        created_at: "2026-06-12T00:00:00Z",
        candidates: [],
        source_candidates: [
          {
            source_type: "SQL",
            source_code: "queryOrderSql",
            source_name: "查询订单 SQL",
            score: 0.7,
            reasons: [],
            missing_inputs: [],
            requires_confirmation: false,
            sys_code: "TRADE",
            method: null,
            path: null,
            datasource_code: "orderDb",
            operation: "SELECT",
          },
        ],
        infra_candidates: [],
      },
    ],
  } as AgentRuntimeTimelineResponse;

  const messages = deriveChatMessages(makeTaskRun("等待处理"), timeline);

  expect(
    messages.some((message) =>
      message.content.includes("发现 1 个 Source 线索"),
    ),
  ).toBe(true);
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

test("deriveResourceGapTree builds SCENE_SOURCE_INFRA hierarchy with proposals", () => {
  const timeline = {
    ...emptyTimeline,
    requirements: [
      {
        requirement_id: "req-scene",
        task_run_id: "tr-1",
        step_id: "step-1",
        layer: "SCENE",
        goal: "造一笔已支付订单",
        status: "RESOLVING",
        proposal_id: "prop-scene",
        parent_requirement_id: null,
        selected_scene_code: null,
        blacklist: [],
        created_at: "2026-06-12T00:00:00Z",
        updated_at: "2026-06-12T00:00:00Z",
      },
      {
        requirement_id: "req-source",
        task_run_id: "tr-1",
        step_id: "step-1",
        layer: "SOURCE",
        goal: "造一笔已支付订单",
        status: "RESOLVING",
        proposal_id: "prop-source",
        parent_requirement_id: "req-scene",
        selected_scene_code: null,
        blacklist: [],
        created_at: "2026-06-12T00:00:01Z",
        updated_at: "2026-06-12T00:00:01Z",
      },
      {
        requirement_id: "req-infra",
        task_run_id: "tr-1",
        step_id: "step-1",
        layer: "INFRA",
        goal: "造一笔已支付订单",
        status: "RESOLVING",
        proposal_id: "prop-infra",
        parent_requirement_id: "req-source",
        selected_scene_code: null,
        blacklist: [],
        created_at: "2026-06-12T00:00:02Z",
        updated_at: "2026-06-12T00:00:02Z",
      },
    ],
    proposals: [
      {
        proposal_id: "prop-scene",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-scene",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: ["订单"],
        created_at: "2026-06-12T00:00:00Z",
        candidates: [],
        source_candidates: [],
        infra_candidates: [],
      },
      {
        proposal_id: "prop-source",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-source",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: ["订单"],
        created_at: "2026-06-12T00:00:01Z",
        candidates: [],
        source_candidates: [
          {
            source_type: "HTTP",
            source_code: "createOrderApi",
            source_name: "创建订单接口",
            score: 0.8,
            reasons: ["命中订单"],
            missing_inputs: [],
            requires_confirmation: true,
            sys_code: "TRADE",
            method: "POST",
            path: "/api/orders",
            datasource_code: null,
            operation: null,
          },
        ],
        infra_candidates: [],
      },
      {
        proposal_id: "prop-infra",
        task_run_id: "tr-1",
        step_id: "step-1",
        requirement_id: "req-infra",
        status: "PENDING",
        selected_scene_code: null,
        selection_source: null,
        query_terms: [],
        created_at: "2026-06-12T00:00:02Z",
        candidates: [],
        source_candidates: [],
        infra_candidates: [
          {
            resource_type: "HTTP",
            ready: false,
            confidence: 0.4,
            missing_fields: ["serviceEndpoint"],
            matched_systems: [],
            matched_environments: [],
            matched_service_endpoints: [],
            matched_datasources: [],
          },
        ],
      },
    ],
  } as AgentRuntimeTimelineResponse;

  const tree = deriveResourceGapTree(timeline);

  expect(tree).toHaveLength(1);
  expect(tree[0]!.requirement.layer).toBe("SCENE");
  expect(tree[0]!.proposal?.proposal_id).toBe("prop-scene");
  expect(tree[0]!.children[0]!.requirement.layer).toBe("SOURCE");
  expect(
    tree[0]!.children[0]!.proposal?.source_candidates[0]!.source_code,
  ).toBe("createOrderApi");
  expect(tree[0]!.children[0]!.children[0]!.requirement.layer).toBe("INFRA");
  expect(
    tree[0]!.children[0]!.children[0]!.proposal?.infra_candidates[0]!
      .missing_fields,
  ).toEqual(["serviceEndpoint"]);
});
