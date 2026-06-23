import type {
  AgentRuntimeAction,
  AgentRuntimeActionAttempt,
  AgentRuntimeEvidence,
  AgentRuntimeInfraCandidate,
  AgentRuntimeProposal,
  AgentRuntimeRequirement,
  AgentRuntimeSceneCandidate,
  AgentRuntimeSourceCandidate,
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTimelineResponse,
  AgentRuntimeVerdict,
  DecisionKind,
  DecisionOption,
  DecisionRejection,
  DecisionSource,
} from "../common/lib/types";

// ── 等待交互类型 ────────────────────────────────────────────────────────

export type WaitingInteraction =
  | { type: "approval"; candidate: AgentRuntimeSceneCandidate; stepId?: string }
  | {
      type: "candidate_selection";
      proposal: AgentRuntimeProposal;
      stepId?: string;
    }
  | {
      type: "manual_scene_code";
      proposal: AgentRuntimeProposal;
      stepId?: string;
    }
  | {
      type: "resource_discovery";
      proposal: AgentRuntimeProposal;
      sourceCandidates: AgentRuntimeSourceCandidate[];
      infraCandidates: AgentRuntimeInfraCandidate[];
      stepId?: string;
    }
  | { type: "missing_input"; fields: string[]; stepId?: string }
  | { type: "unknown_state"; reason: string; stepId?: string }
  | { type: "generic"; message: string; stepId?: string };

// ── 聊天消息类型 ────────────────────────────────────────────────────────

export type ChatMessageRole = "user" | "agent";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  timestamp: string;
  detail?: unknown;
}

// ── 完成结果数据 ────────────────────────────────────────────────────────

export interface CompletionFact {
  subject: string;
  passed: boolean;
  expected: unknown;
  actual: unknown;
  detail?: string | null;
}

export interface CompletionResult {
  verdict_type: "DONE" | "FAILED" | "UNKNOWN_STATE";
  reason: string;
  scene_code: string;
  response_preview: Record<string, unknown>;
  facts: CompletionFact[];
  missing_facts: string[];
  finished_at: string;
}

// ── 资源缺口树 ──────────────────────────────────────────────────────────

export interface ResourceGapTreeNode {
  requirement: AgentRuntimeRequirement;
  proposal?: AgentRuntimeProposal;
  children: ResourceGapTreeNode[];
}

// ── 派生函数 ────────────────────────────────────────────────────────────

function normalizeMissingInputField(field: string): string {
  return field
    .replace(/[。；;].*$/, "")
    .replace(/^inputs\./, "")
    .trim();
}

function getProposalCandidates(
  proposal: AgentRuntimeProposal | null | undefined,
): AgentRuntimeSceneCandidate[] {
  return Array.isArray(proposal?.candidates) ? proposal.candidates : [];
}

function getSourceCandidates(
  proposal: AgentRuntimeProposal | null | undefined,
): AgentRuntimeSourceCandidate[] {
  return Array.isArray(proposal?.source_candidates)
    ? proposal.source_candidates
    : [];
}

function getInfraCandidates(
  proposal: AgentRuntimeProposal | null | undefined,
): AgentRuntimeInfraCandidate[] {
  return Array.isArray(proposal?.infra_candidates)
    ? proposal.infra_candidates
    : [];
}

function normalizeCompletionVerdictType(
  verdictType: AgentRuntimeVerdict["verdict_type"] | string,
): CompletionResult["verdict_type"] | null {
  if (
    verdictType === "DONE" ||
    verdictType === "FAILED" ||
    verdictType === "UNKNOWN_STATE"
  ) {
    return verdictType;
  }
  if (verdictType === "NEED_USER") {
    return "UNKNOWN_STATE";
  }
  return null;
}

function proposalForRequirement(
  requirement: AgentRuntimeRequirement,
  proposalsById: Map<string, AgentRuntimeProposal>,
  proposalsByRequirement: Map<string, AgentRuntimeProposal>,
): AgentRuntimeProposal | undefined {
  if (requirement.proposal_id) {
    return (
      proposalsById.get(requirement.proposal_id) ??
      proposalsByRequirement.get(requirement.requirement_id)
    );
  }
  return proposalsByRequirement.get(requirement.requirement_id);
}

export function deriveResourceGapTree(
  timeline: AgentRuntimeTimelineResponse | null,
): ResourceGapTreeNode[] {
  if (!timeline) return [];

  const proposalsById = new Map(
    timeline.proposals.map((proposal) => [proposal.proposal_id, proposal]),
  );
  const proposalsByRequirement = new Map(
    timeline.proposals.map((proposal) => [proposal.requirement_id, proposal]),
  );
  const nodesById = new Map<string, ResourceGapTreeNode>();

  for (const requirement of timeline.requirements) {
    nodesById.set(requirement.requirement_id, {
      requirement,
      proposal: proposalForRequirement(
        requirement,
        proposalsById,
        proposalsByRequirement,
      ),
      children: [],
    });
  }

  const roots: ResourceGapTreeNode[] = [];
  for (const node of nodesById.values()) {
    const parentId = node.requirement.parent_requirement_id;
    const parent = parentId ? nodesById.get(parentId) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }

  const sortTree = (nodes: ResourceGapTreeNode[]) => {
    nodes.sort((a, b) =>
      a.requirement.created_at.localeCompare(b.requirement.created_at),
    );
    for (const node of nodes) sortTree(node.children);
  };
  sortTree(roots);

  return roots;
}
/** 从 taskRun + timeline 派生当前等待交互 */
export function deriveWaitingInteraction(
  taskRun: AgentRuntimeTaskRunResponse | null,
  timeline: AgentRuntimeTimelineResponse | null,
): WaitingInteraction | null {
  if (taskRun?.status !== "WAITING_USER" || !timeline) return null;

  const latestVerdict = timeline.verdicts.at(-1);
  const latestProposal = timeline.proposals.at(-1);
  const latestCandidates = getProposalCandidates(latestProposal);
  const latestSourceCandidates = getSourceCandidates(latestProposal);
  const latestInfraCandidates = getInfraCandidates(latestProposal);
  const activeStepId = timeline.task_run?.active_step_id ?? undefined;

  // 1. 最新 Verdict 是 UNKNOWN_STATE
  if (latestVerdict?.verdict_type === "UNKNOWN_STATE") {
    return {
      type: "unknown_state",
      reason: latestVerdict.reason,
      stepId: activeStepId,
    };
  }

  // 2. 最新 Proposal 是 PENDING 且有候选
  if (latestProposal?.status === "PENDING" && latestCandidates.length > 0) {
    return {
      type: "candidate_selection",
      proposal: latestProposal,
      stepId: activeStepId,
    };
  }

  // 3. 最新 Proposal 是 PENDING 且包含 Source / Infra 发现结果
  if (
    latestProposal?.status === "PENDING" &&
    (latestSourceCandidates.length > 0 || latestInfraCandidates.length > 0)
  ) {
    return {
      type: "resource_discovery",
      proposal: latestProposal,
      sourceCandidates: latestSourceCandidates,
      infraCandidates: latestInfraCandidates,
      stepId: activeStepId,
    };
  }

  // 4. 最新 Proposal 是 PENDING 且无候选
  if (latestProposal?.status === "PENDING" && latestCandidates.length === 0) {
    return {
      type: "manual_scene_code",
      proposal: latestProposal,
      stepId: activeStepId,
    };
  }

  // 5. 最新 Proposal 是 SELECTED，候选 requires_confirmation 且无 approval record
  if (
    latestProposal?.status === "SELECTED" &&
    latestProposal.selected_scene_code
  ) {
    const candidate = latestCandidates.find(
      (c) => c.scene_code === latestProposal.selected_scene_code,
    );
    if (candidate?.requires_confirmation) {
      const hasApproval = timeline.approval_records.some(
        (r) => r.proposal_id === latestProposal.proposal_id,
      );
      if (!hasApproval) {
        return { type: "approval", candidate, stepId: activeStepId };
      }
    }
  }

  // 6. pending_question 包含缺少必填信息
  if (taskRun.pending_question) {
    const missingMatch = /缺少(?:必填信息)?[：:]\s*(.+)/.exec(
      taskRun.pending_question,
    );
    if (missingMatch?.[1]) {
      const fields = missingMatch[1]
        .split(/[,，、]/)
        .map((s) => normalizeMissingInputField(s))
        .filter(Boolean);
      return { type: "missing_input", fields, stepId: activeStepId };
    }
  }

  // 7. 兜底
  if (taskRun.pending_question) {
    return {
      type: "generic",
      message: taskRun.pending_question,
      stepId: activeStepId,
    };
  }

  return null;
}

/** 从 taskRun + timeline 派生聊天消息流 */
export function deriveChatMessages(
  taskRun: AgentRuntimeTaskRunResponse | null,
  timeline: AgentRuntimeTimelineResponse | null,
): ChatMessage[] {
  const messages: ChatMessage[] = [];

  if (!taskRun) return messages;

  // 用户消息：造数目标
  messages.push({
    id: "msg:goal",
    role: "user",
    content: taskRun.user_goal,
    timestamp: taskRun.created_at,
    detail: {
      env_code: taskRun.env_code,
    },
  });

  if (!timeline) return messages;

  // Agent 消息：已创建任务
  messages.push({
    id: "msg:created",
    role: "agent",
    content: `已创建任务，环境：${taskRun.env_code ?? "未指定"}`,
    timestamp: taskRun.created_at,
  });

  // 从 steps 派生
  for (const step of timeline.steps) {
    if (step.status === "RUNNING") {
      messages.push({
        id: `msg:step-running:${step.step_id}`,
        role: "agent",
        content: `正在执行：${step.goal}`,
        timestamp: step.status as string,
      });
    } else if (step.status === "DONE") {
      messages.push({
        id: `msg:step-done:${step.step_id}`,
        role: "agent",
        content: `已完成：${step.goal}`,
        timestamp: step.status as string,
      });
    } else if (step.status === "FAILED") {
      messages.push({
        id: `msg:step-failed:${step.step_id}`,
        role: "agent",
        content: `执行失败：${step.goal}`,
        timestamp: step.status as string,
      });
    }
  }

  // 从 proposals 派生候选搜索
  for (const proposal of timeline.proposals) {
    const candidates = getProposalCandidates(proposal);
    const sourceCandidates = getSourceCandidates(proposal);
    const infraCandidates = getInfraCandidates(proposal);
    if (candidates.length > 0) {
      messages.push({
        id: `msg:proposal-found:${proposal.proposal_id}`,
        role: "agent",
        content: `找到 ${candidates.length} 个候选场景`,
        timestamp: proposal.created_at,
        detail: candidates,
      });
    }
    if (sourceCandidates.length > 0 || infraCandidates.length > 0) {
      messages.push({
        id: `msg:resource-discovery:${proposal.proposal_id}`,
        role: "agent",
        content: `发现 ${sourceCandidates.length} 个 Source 线索，${infraCandidates.length} 项基础配置诊断`,
        timestamp: proposal.created_at,
        detail: { sourceCandidates, infraCandidates },
      });
    }
    if (proposal.status === "SELECTED" && proposal.selected_scene_code) {
      const candidate = candidates.find(
        (c) => c.scene_code === proposal.selected_scene_code,
      );
      if (candidate) {
        messages.push({
          id: `msg:proposal-selected:${proposal.proposal_id}`,
          role: "agent",
          content: `已选定 ${candidate.scene_name}（${candidate.scene_code}）`,
          timestamp: proposal.created_at,
        });
      }
    }
  }

  // 从 actions 派生执行状态
  for (const action of timeline.actions) {
    if (action.status === "RUNNING") {
      messages.push({
        id: `msg:action-running:${action.action_id}`,
        role: "agent",
        content: `正在执行场景 ${action.scene_code}`,
        timestamp: action.status,
      });
    } else if (action.status === "SUCCEEDED") {
      messages.push({
        id: `msg:action-succeeded:${action.action_id}`,
        role: "agent",
        content: `场景 ${action.scene_code} 执行成功`,
        timestamp: action.status,
      });
    } else if (action.status === "FAILED") {
      messages.push({
        id: `msg:action-failed:${action.action_id}`,
        role: "agent",
        content: `场景 ${action.scene_code} 执行失败`,
        timestamp: action.status,
      });
    } else if (action.status === "UNKNOWN_STATE") {
      messages.push({
        id: `msg:action-unknown:${action.action_id}`,
        role: "agent",
        content: `场景 ${action.scene_code} 执行结果未知，写请求可能已发出`,
        timestamp: action.status,
      });
    }
  }

  // 从 verdicts 派生最终判定
  for (const verdict of timeline.verdicts) {
    if (verdict.verdict_type === "DONE") {
      messages.push({
        id: `msg:verdict-done:${verdict.verdict_id}`,
        role: "agent",
        content: `业务判定成功：${verdict.reason}`,
        timestamp: verdict.created_at,
      });
    } else if (verdict.verdict_type === "FAILED") {
      messages.push({
        id: `msg:verdict-failed:${verdict.verdict_id}`,
        role: "agent",
        content: `业务判定失败：${verdict.reason}`,
        timestamp: verdict.created_at,
      });
    } else if (verdict.verdict_type === "UNKNOWN_STATE") {
      messages.push({
        id: `msg:verdict-unknown:${verdict.verdict_id}`,
        role: "agent",
        content: `执行结果未知：${verdict.reason}`,
        timestamp: verdict.created_at,
      });
    }
  }

  // 终态消息
  if (taskRun.status === "COMPLETED") {
    messages.push({
      id: "msg:completed",
      role: "agent",
      content: "任务已完成",
      timestamp: taskRun.finished_at ?? taskRun.updated_at,
    });
  } else if (taskRun.status === "FAILED") {
    messages.push({
      id: "msg:failed",
      role: "agent",
      content: `任务失败：${taskRun.failure_reason ?? "未知原因"}`,
      timestamp: taskRun.finished_at ?? taskRun.updated_at,
    });
  } else if (taskRun.status === "CANCELLED") {
    messages.push({
      id: "msg:cancelled",
      role: "agent",
      content: "任务已取消",
      timestamp: taskRun.finished_at ?? taskRun.updated_at,
    });
  }

  return messages;
}

/** 从 taskRun + timeline 派生完成结果，仅在终态时有值 */
export function deriveCompletionResult(
  taskRun: AgentRuntimeTaskRunResponse | null,
  timeline: AgentRuntimeTimelineResponse | null,
): CompletionResult | null {
  if (!taskRun || !timeline) return null;
  if (taskRun.status !== "COMPLETED" && taskRun.status !== "FAILED")
    return null;

  const verdict = timeline.verdicts.at(-1);
  if (!verdict) return null;
  const verdictType = normalizeCompletionVerdictType(verdict.verdict_type);
  if (!verdictType) return null;

  const action = timeline.actions.at(-1);
  const attempt = timeline.attempts.at(-1);
  const evidence = timeline.evidences.at(-1);

  return {
    verdict_type: verdictType,
    reason: verdict.reason,
    scene_code: action?.scene_code ?? "",
    response_preview: attempt?.response_preview ?? {},
    facts:
      evidence?.facts.map((f) => ({
        subject: f.subject,
        passed: f.passed,
        expected: f.expected,
        actual: f.actual,
        detail: f.detail,
      })) ?? [],
    missing_facts: evidence?.missing_facts ?? [],
    finished_at: taskRun.finished_at ?? taskRun.updated_at,
  };
}

// ── 审计数据派生 ────────────────────────────────────────────────────────

/** 决策层审计数据 */
export interface AuditDecision {
  decision_id: string;
  kind: DecisionKind;
  source: DecisionSource;
  summary: string;
  options: DecisionOption[];
  selected?: DecisionOption | null;
  selectedReasons: string[];
  rejections: DecisionRejection[];
  criteria: string[];
  createdAt: string;
}

/** 编排层审计数据 */
export interface AuditStep {
  stepId: string;
  stepNo: number;
  goal: string;
  status: string;
  dependsOn: string[];
  consumes: string[];
  produces: string[];
  isActive: boolean;
  incomingEdges: { fromStepId: string; variableIds: string[] }[];
}

/** 执行层审计数据 */
export interface AuditExecution {
  action: AgentRuntimeAction;
  attempts: AgentRuntimeActionAttempt[];
  evidence?: AgentRuntimeEvidence;
  verdict?: AgentRuntimeVerdict;
}

/** 从 timeline 派生决策层审计数据 */
export function deriveAuditDecisions(
  timeline: AgentRuntimeTimelineResponse | null,
): AuditDecision[] {
  if (!timeline) return [];
  return timeline.decisions.map((d) => ({
    decision_id: d.decision_id,
    kind: d.decision_kind,
    source: d.decision_source,
    summary: d.summary,
    options: d.options,
    selected: d.selected_option,
    selectedReasons: d.selected_reasons,
    rejections: d.rejected_reasons,
    criteria: d.criteria,
    createdAt: d.created_at,
  }));
}

/** 从 timeline 派生编排层审计数据 */
export function deriveAuditSteps(
  timeline: AgentRuntimeTimelineResponse | null,
): AuditStep[] {
  if (!timeline) return [];
  const activeStepId = timeline.task_run?.active_step_id;

  return timeline.steps.map((step) => {
    const incomingEdges = (timeline.step_edges ?? [])
      .filter((e) => e.to_step_id === step.step_id)
      .map((e) => ({
        fromStepId: e.from_step_id,
        variableIds: e.variable_ids ?? [],
      }));

    return {
      stepId: step.step_id,
      stepNo: step.step_no,
      goal: step.goal,
      status: step.status,
      dependsOn: step.depends_on,
      consumes: step.consumes,
      produces: step.produces,
      isActive: activeStepId === step.step_id,
      incomingEdges,
    };
  });
}

/** 从 timeline 派生执行层审计数据 */
export function deriveAuditExecutions(
  timeline: AgentRuntimeTimelineResponse | null,
): AuditExecution[] {
  if (!timeline) return [];

  const verdictByStep = new Map<string, AgentRuntimeVerdict>();
  for (const v of timeline.verdicts) {
    verdictByStep.set(v.step_id, v);
  }

  return timeline.actions.map((action) => {
    const step = timeline.steps.find((s) => s.step_id === action.step_id);
    const attempts = timeline.attempts.filter(
      (a) => a.action_id === action.action_id,
    );
    const evidence = timeline.evidences.find(
      (e) => e.action_id === action.action_id,
    );
    const verdict = step ? verdictByStep.get(step.step_id) : undefined;

    return {
      action,
      attempts,
      evidence,
      verdict,
    };
  });
}
