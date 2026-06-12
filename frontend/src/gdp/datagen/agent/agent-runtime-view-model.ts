import type {
  AgentRuntimeAction,
  AgentRuntimeActionAttempt,
  AgentRuntimeApprovalRecord,
  AgentRuntimeEvidence,
  AgentRuntimeObservation,
  AgentRuntimePlanStep,
  AgentRuntimeProposal,
  AgentRuntimeSceneCandidate,
  AgentRuntimeTaskRunResponse,
  AgentRuntimeTimelineResponse,
  AgentRuntimeVariable,
  AgentRuntimeVerdict,
} from "../common/lib/types";

// ── 等待交互类型 ────────────────────────────────────────────────────────

export type WaitingInteraction =
  | { type: "approval"; candidate: AgentRuntimeSceneCandidate }
  | { type: "candidate_selection"; proposal: AgentRuntimeProposal }
  | { type: "manual_scene_code"; proposal: AgentRuntimeProposal }
  | { type: "missing_input"; fields: string[] }
  | { type: "unknown_state"; reason: string }
  | { type: "generic"; message: string };

// ── 聊天消息类型 ────────────────────────────────────────────────────────

export type ChatMessageRole = "user" | "agent";

export interface ChatMessage {
  id: string;
  role: ChatMessageRole;
  content: string;
  timestamp: string;
  detail?: unknown;
}

// ── 详情面板数据 ────────────────────────────────────────────────────────

export interface TimelineDetailItem {
  key: string;
  kind: string;
  title: string;
  subtitle: string;
  status?: string;
  payload: unknown;
}

// ── 派生函数 ────────────────────────────────────────────────────────────

/** 从 taskRun + timeline 派生当前等待交互 */
export function deriveWaitingInteraction(
  taskRun: AgentRuntimeTaskRunResponse | null,
  timeline: AgentRuntimeTimelineResponse | null,
): WaitingInteraction | null {
  if (!taskRun || taskRun.status !== "WAITING_USER" || !timeline) return null;

  const latestVerdict = timeline.verdicts.at(-1);
  const latestProposal = timeline.proposals.at(-1);

  // 1. 最新 Verdict 是 UNKNOWN_STATE
  if (latestVerdict?.verdict_type === "UNKNOWN_STATE") {
    return { type: "unknown_state", reason: latestVerdict.reason };
  }

  // 2. 最新 Proposal 是 PENDING 且有候选
  if (latestProposal?.status === "PENDING" && latestProposal.candidates.length > 0) {
    return { type: "candidate_selection", proposal: latestProposal };
  }

  // 3. 最新 Proposal 是 PENDING 且无候选
  if (latestProposal?.status === "PENDING" && latestProposal.candidates.length === 0) {
    return { type: "manual_scene_code", proposal: latestProposal };
  }

  // 4. 最新 Proposal 是 SELECTED，候选 requires_confirmation 且无 approval record
  if (latestProposal?.status === "SELECTED" && latestProposal.selected_scene_code) {
    const candidate = latestProposal.candidates.find(
      (c) => c.scene_code === latestProposal.selected_scene_code,
    );
    if (candidate?.requires_confirmation) {
      const hasApproval = timeline.approval_records.some(
        (r) => r.proposal_id === latestProposal.proposal_id,
      );
      if (!hasApproval) {
        return { type: "approval", candidate };
      }
    }
  }

  // 5. pending_question 包含缺少必填信息
  if (taskRun.pending_question) {
    const missingMatch = taskRun.pending_question.match(/缺少[：:]\s*(.+)/);
    if (missingMatch && missingMatch[1]) {
      const fields = missingMatch[1].split(/[,，、]/).map((s) => s.trim());
      return { type: "missing_input", fields };
    }
  }

  // 6. 兜底
  if (taskRun.pending_question) {
    return { type: "generic", message: taskRun.pending_question };
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
    if (proposal.candidates.length > 0) {
      messages.push({
        id: `msg:proposal-found:${proposal.proposal_id}`,
        role: "agent",
        content: `找到 ${proposal.candidates.length} 个候选场景`,
        timestamp: proposal.created_at,
        detail: proposal.candidates,
      });
    }
    if (proposal.status === "SELECTED" && proposal.selected_scene_code) {
      const candidate = proposal.candidates.find(
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
    if (action.status === "WAITING_APPROVAL") {
      messages.push({
        id: `msg:action-waiting:${action.action_id}`,
        role: "agent",
        content: `场景 ${action.scene_code} 需要批准后执行`,
        timestamp: action.status,
      });
    } else if (action.status === "RUNNING") {
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

/** 从 timeline 派生详情面板时间线条目 */
export function deriveTimelineDetailItems(
  timeline: AgentRuntimeTimelineResponse | null,
): TimelineDetailItem[] {
  if (!timeline) return [];
  return [
    ...timeline.steps.map((step) => ({
      key: `step:${step.step_id}`,
      kind: "step",
      title: `Step #${step.step_no}`,
      subtitle: step.goal,
      status: step.status,
      payload: step as unknown,
    })),
    ...timeline.actions.map((action) => ({
      key: `action:${action.action_id}`,
      kind: "action",
      title: "Action",
      subtitle: action.scene_code,
      status: action.status,
      payload: action as unknown,
    })),
    ...timeline.attempts.map((attempt) => ({
      key: `attempt:${attempt.attempt_id}`,
      kind: "attempt",
      title: `Attempt #${attempt.attempt_no}`,
      subtitle: attempt.error_message ?? attempt.request_ref,
      status: attempt.status,
      payload: attempt as unknown,
    })),
    ...timeline.observations.map((observation) => ({
      key: `observation:${observation.observation_id}`,
      kind: "observation",
      title: "Observation",
      subtitle: observation.raw_ref,
      payload: observation as unknown,
    })),
    ...timeline.evidences.map((evidence) => ({
      key: `evidence:${evidence.evidence_id}`,
      kind: "evidence",
      title: "Evidence",
      subtitle: `${evidence.facts.length} facts / ${evidence.missing_facts.length} missing / ${evidence.unknown_facts.length} unknown`,
      status:
        evidence.unknown_facts.length > 0
          ? "UNKNOWN_STATE"
          : evidence.missing_facts.length > 0
            ? "NEED_USER"
            : evidence.facts.every((fact) => fact.passed)
              ? "DONE"
              : "FAILED",
      payload: evidence as unknown,
    })),
    ...timeline.verdicts.map((verdict) => ({
      key: `verdict:${verdict.verdict_id}`,
      kind: "verdict",
      title: "Verdict",
      subtitle: verdict.reason,
      status: verdict.verdict_type,
      payload: verdict as unknown,
    })),
    ...timeline.variables.map((variable) => ({
      key: `variable:${variable.variable_id}`,
      kind: "variable",
      title: variable.name,
      subtitle: variable.semantic_type,
      status: variable.tainted ? "FAILED" : variable.sensitive ? "NEED_USER" : "DONE",
      payload: variable as unknown,
    })),
  ];
}
