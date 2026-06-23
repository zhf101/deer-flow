import {
  AlertTriangleIcon,
  CheckCircle2Icon,
  Loader2Icon,
  ShieldCheckIcon,
  XCircleIcon,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import type {
  AgentRuntimeInfraCandidate,
  AgentRuntimeSceneCandidate,
  AgentRuntimeProposal,
  AgentRuntimeSourceCandidate,
} from "../common/lib/types";
import type { WaitingInteraction } from "./agent-runtime-view-model";

// ── 候选卡片 ────────────────────────────────────────────────────────────

function CandidateCard({
  candidate,
  busy,
  onSelect,
}: {
  candidate: AgentRuntimeSceneCandidate;
  busy: boolean;
  onSelect: (candidate: AgentRuntimeSceneCandidate, approved: boolean) => void;
}) {
  return (
    <div className="space-y-2 rounded-lg border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-medium">
            {candidate.scene_name}
            <span className="ml-1.5 font-mono text-xs text-muted-foreground">({candidate.scene_code})</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>评分 {candidate.score}</span>
            {candidate.requires_confirmation ? (
              <Badge variant="outline" className="border-amber-200 bg-amber-50 text-amber-700">
                需审批
              </Badge>
            ) : null}
          </div>
        </div>
      </div>
      {candidate.reasons.length > 0 ? (
        <div className="text-xs text-muted-foreground">{candidate.reasons.join("；")}</div>
      ) : null}
      {candidate.missing_inputs.length > 0 ? (
        <div className="text-xs text-amber-700">缺少：{candidate.missing_inputs.join("，")}</div>
      ) : null}
      <div className="flex gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={() => onSelect(candidate, false)} disabled={busy}>
          选择并执行
        </Button>
        {candidate.requires_confirmation ? (
          <Button size="sm" onClick={() => onSelect(candidate, true)} disabled={busy}>
            <ShieldCheckIcon className="mr-1.5 size-3.5" />
            选择并批准执行
          </Button>
        ) : null}
      </div>
    </div>
  );
}

// ── 候选选择卡 ──────────────────────────────────────────────────────────

export function CandidateSelectionCard({
  proposal,
  busy,
  onSelect,
}: {
  proposal: AgentRuntimeProposal;
  busy: boolean;
  onSelect: (candidate: AgentRuntimeSceneCandidate, approved: boolean) => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-sky-200 bg-sky-50/60 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-sky-800">
        <CheckCircle2Icon className="size-4" />
        找到 {proposal.candidates.length} 个候选场景
      </div>
      <div className="space-y-2">
        {proposal.candidates.map((candidate) => (
          <CandidateCard key={candidate.scene_code} candidate={candidate} busy={busy} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}

// ── 审批卡 ──────────────────────────────────────────────────────────────

export function ApprovalCard({
  candidate,
  busy,
  onApprove,
  onCancel,
}: {
  candidate: AgentRuntimeSceneCandidate;
  busy: boolean;
  onApprove: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
        <ShieldCheckIcon className="size-4" />
        需要批准后执行
      </div>
      <p className="text-sm text-amber-800">
        场景「{candidate.scene_name}」会产生写入副作用，执行前需要你确认。
      </p>
      <div className="flex gap-2 pt-1">
        <Button size="sm" onClick={onApprove} disabled={busy}>
          <ShieldCheckIcon className="mr-1.5 size-3.5" />
          批准并执行
        </Button>
        <Button variant="outline" size="sm" onClick={onCancel} disabled={busy}>
          <XCircleIcon className="mr-1.5 size-3.5" />
          取消任务
        </Button>
      </div>
    </div>
  );
}

// ── 手动补场景卡 ────────────────────────────────────────────────────────

export function ManualSceneCard({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (sceneCode: string) => void;
}) {
  const [sceneCode, setSceneCode] = useState("");

  return (
    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
        <AlertTriangleIcon className="size-4" />
        未找到匹配场景，请手动指定
      </div>
      <div className="flex gap-2">
        <Input
          value={sceneCode}
          onChange={(e) => setSceneCode(e.target.value)}
          placeholder="例如 create_paid_order"
          className="flex-1"
        />
        <Button
          variant="outline"
          onClick={() => onSubmit(sceneCode.trim())}
          disabled={busy || !sceneCode.trim()}
        >
          使用该场景继续
        </Button>
      </div>
    </div>
  );
}

// ── 补参卡 ──────────────────────────────────────────────────────────────

export function MissingInputCard({
  fields,
  busy,
  onSubmit,
}: {
  fields: string[];
  busy: boolean;
  onSubmit: (inputs: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const field of fields) {
      init[field] = "";
    }
    return init;
  });

  const handleSubmit = () => {
    const parsed: Record<string, unknown> = {};
    for (const field of fields) {
      const val = values[field]?.trim();
      if (val) {
        try {
          parsed[field] = JSON.parse(val);
        } catch {
          parsed[field] = val;
        }
      }
    }
    onSubmit(parsed);
  };

  return (
    <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-amber-800">
        <AlertTriangleIcon className="size-4" />
        缺少必填参数
      </div>
      <div className="space-y-2">
        {fields.map((field) => (
          <div key={field} className="space-y-1">
            <label className="text-xs font-medium text-amber-800">{field}</label>
            <Input
              value={values[field] ?? ""}
              onChange={(e) => setValues((prev) => ({ ...prev, [field]: e.target.value }))}
              placeholder={`输入 ${field}`}
              className="bg-background"
            />
          </div>
        ))}
      </div>
      <Button variant="outline" onClick={handleSubmit} disabled={busy}>
        补充并继续
      </Button>
    </div>
  );
}

// ── 未知状态卡 ──────────────────────────────────────────────────────────

export function UnknownStateCard({
  reason,
  busy,
  onConfirm,
  onViewAttempts,
}: {
  reason: string;
  busy: boolean;
  onConfirm: () => void;
  onViewAttempts: () => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-destructive">
        <AlertTriangleIcon className="size-4" />
        执行结果未知
      </div>
      <p className="text-sm text-destructive/80">{reason}</p>
      <p className="text-xs text-destructive/60">写请求可能已经发出，系统无法确认结果。</p>
      <div className="flex gap-2 pt-1">
        <Button variant="outline" size="sm" onClick={onConfirm} disabled={busy}>
          确认停止任务
        </Button>
        <Button variant="ghost" size="sm" onClick={onViewAttempts}>
          查看执行尝试
        </Button>
      </div>
    </div>
  );
}

// ── 通用等待卡 ──────────────────────────────────────────────────────────

export function GenericWaitingCard({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-4">
      <div className="flex items-center gap-2 text-sm text-amber-800">
        <Loader2Icon className="size-4 animate-spin" />
        {message}
      </div>
    </div>
  );
}

// ── Source / Infra 发现卡 ───────────────────────────────────────────────

function ResourceDiscoveryCard({
  sourceCandidates,
  infraCandidates,
}: {
  sourceCandidates: AgentRuntimeSourceCandidate[];
  infraCandidates: AgentRuntimeInfraCandidate[];
}) {
  const missingFields = Array.from(new Set(infraCandidates.flatMap((item) => item.missing_fields)));
  return (
    <div className="space-y-3 rounded-lg border border-violet-200 bg-violet-50/60 p-4">
      <div className="flex items-center gap-2 text-sm font-medium text-violet-800">
        <AlertTriangleIcon className="size-4" />
        未找到完整场景，发现下层资源线索
      </div>
      {sourceCandidates.length > 0 ? (
        <div className="space-y-2">
          {sourceCandidates.map((candidate) => (
            <div key={`${candidate.source_type}:${candidate.source_code}`} className="rounded-md border bg-background p-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="outline">{candidate.source_type}</Badge>
                <span className="font-medium">{candidate.source_name}</span>
                <span className="font-mono text-xs text-muted-foreground">{candidate.source_code}</span>
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {candidate.source_type === "SQL"
                  ? `数据源 ${candidate.datasource_code ?? "-"} · ${candidate.operation ?? "-"}`
                  : `${candidate.method ?? "-"} ${candidate.path ?? "-"}`}
              </div>
              {candidate.reasons.length > 0 ? (
                <div className="mt-1 text-xs text-muted-foreground">{candidate.reasons.join("；")}</div>
              ) : null}
              {candidate.missing_inputs.length > 0 ? (
                <div className="mt-1 text-xs text-amber-700">缺少：{candidate.missing_inputs.join("，")}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-violet-800">没有发现可复用的 HTTP/SQL Source。</p>
      )}
      {infraCandidates.length > 0 ? (
        <div className="rounded-md border bg-background p-3 text-xs text-muted-foreground">
          <div className="mb-1 font-medium text-foreground">基础配置诊断</div>
          <div>
            {infraCandidates.filter((item) => item.ready).length}/{infraCandidates.length} 项 ready
            {missingFields.length > 0 ? `，仍缺：${missingFields.join("，")}` : "，未发现阻塞项"}
          </div>
        </div>
      ) : null}
      <p className="text-xs text-violet-800">
        当前仅做只读发现。请先在场景管理中基于这些 Source 创建并发布组合场景，再回到任务补充 scene_code。
      </p>
    </div>
  );
}

// ── 动作卡统一入口 ──────────────────────────────────────────────────────

export function ActionCard({
  interaction,
  busy,
  onSelectCandidate,
  onApprove,
  onCancel,
  onSupplySceneCode,
  onSupplyInput,
  onConfirmUnknownState,
  onViewAttempts,
}: {
  interaction: WaitingInteraction;
  busy: boolean;
  onSelectCandidate: (candidate: AgentRuntimeSceneCandidate, approved: boolean) => void;
  onApprove: () => void;
  onCancel: () => void;
  onSupplySceneCode: (sceneCode: string) => void;
  onSupplyInput: (inputs: Record<string, unknown>) => void;
  onConfirmUnknownState: () => void;
  onViewAttempts: () => void;
}) {
  const renderCard = () => {
    switch (interaction.type) {
      case "candidate_selection":
        return (
          <CandidateSelectionCard proposal={interaction.proposal} busy={busy} onSelect={onSelectCandidate} />
        );
      case "approval":
        return (
          <ApprovalCard candidate={interaction.candidate} busy={busy} onApprove={onApprove} onCancel={onCancel} />
        );
      case "manual_scene_code":
        return <ManualSceneCard busy={busy} onSubmit={onSupplySceneCode} />;
      case "resource_discovery":
        return (
          <ResourceDiscoveryCard
            sourceCandidates={interaction.sourceCandidates}
            infraCandidates={interaction.infraCandidates}
          />
        );
      case "missing_input":
        return <MissingInputCard fields={interaction.fields} busy={busy} onSubmit={onSupplyInput} />;
      case "unknown_state":
        return (
          <UnknownStateCard
            reason={interaction.reason}
            busy={busy}
            onConfirm={onConfirmUnknownState}
            onViewAttempts={onViewAttempts}
          />
        );
      case "generic":
        return <GenericWaitingCard message={interaction.message} />;
      default:
        return null;
    }
  };

  const card = renderCard();
  if (!card) return null;

  return (
    <div className="space-y-2">
      {interaction.stepId ? (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-1">
          <AlertTriangleIcon className="size-3 text-amber-500" />
          <span>阻塞于编排步骤:</span>
          <Badge variant="outline" className="font-mono text-[9px] bg-background">
            {interaction.stepId}
          </Badge>
        </div>
      ) : null}
      {card}
    </div>
  );
}
