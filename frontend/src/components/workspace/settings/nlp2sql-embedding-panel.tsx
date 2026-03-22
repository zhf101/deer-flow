"use client";

import { SparklesIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@/components/ui/item";
import { useI18n } from "@/core/i18n/hooks";
import {
  useActivateEmbeddingProfile,
  useCreateEmbeddingProfile,
  useEmbeddingProfiles,
  useRebuildEmbeddingProfile,
  type CreateEmbeddingProfileRequest,
} from "@/core/nlp2sql";

function createEmptyEmbeddingDraft(): CreateEmbeddingProfileRequest {
  return {
    name: "",
    provider: "deterministic",
    model: "hash-v1",
    dimensions: 64,
    distance_metric: "cosine",
    config: {},
  };
}

export function Nlp2SqlEmbeddingPanel({
  controlsDisabled,
  dataSourceId,
}: {
  controlsDisabled: boolean;
  dataSourceId?: string | null;
}) {
  const { t } = useI18n();
  const { embeddingProfiles, isLoading, error } = useEmbeddingProfiles();
  const createMutation = useCreateEmbeddingProfile();
  const activateMutation = useActivateEmbeddingProfile();
  const rebuildMutation = useRebuildEmbeddingProfile();
  const [draft, setDraft] = useState<CreateEmbeddingProfileRequest>(
    createEmptyEmbeddingDraft(),
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  async function handleCreate() {
    try {
      await createMutation.mutateAsync({
        ...draft,
        name: draft.name.trim(),
        provider: draft.provider.trim(),
        model: draft.model.trim(),
      });
      setStatusMessage(t.settings.nlp2sql.embeddingCreateSuccess);
      toast.success(t.settings.nlp2sql.embeddingCreateSuccess);
      setDraft(createEmptyEmbeddingDraft());
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleActivate(profileId: string) {
    try {
      await activateMutation.mutateAsync(profileId);
      setStatusMessage(t.settings.nlp2sql.embeddingActivateSuccess);
      toast.success(t.settings.nlp2sql.embeddingActivateSuccess);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  async function handleRebuild(profileId: string, scope: "selected" | "all") {
    try {
      const jobs = await rebuildMutation.mutateAsync({
        profileId,
        request:
          scope === "selected"
            ? { data_source_id: dataSourceId }
            : { all_data_sources: true },
      });
      const message =
        scope === "selected"
          ? t.settings.nlp2sql.embeddingRebuildSelectedSuccess
          : t.settings.nlp2sql.embeddingRebuildAllSuccess(jobs.length);
      setStatusMessage(message);
      toast.success(message);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setStatusMessage(message);
      toast.error(message);
    }
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_1fr]">
      <section className="space-y-3">
        <div className="text-sm font-medium">
          {t.settings.nlp2sql.embeddingListTitle}
        </div>
        {isLoading ? (
          <div className="text-muted-foreground text-sm">
            {t.common.loading}
          </div>
        ) : error ? (
          <div className="text-destructive text-sm">{error.message}</div>
        ) : embeddingProfiles.length === 0 ? (
          <div className="text-muted-foreground rounded-lg border border-dashed p-4 text-sm">
            {t.settings.nlp2sql.embeddingEmptyTitle}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {embeddingProfiles.map((profile) => (
              <Item key={profile.id} variant="outline">
                <ItemContent>
                  <ItemTitle>{profile.name}</ItemTitle>
                  <ItemDescription>
                    {profile.provider} · {profile.model} · {profile.dimensions}d
                  </ItemDescription>
                </ItemContent>
                <ItemActions className="flex flex-wrap gap-2">
                  <Badge variant={profile.is_active ? "default" : "outline"}>
                    {profile.is_active
                      ? t.settings.nlp2sql.embeddingActiveBadge
                      : t.settings.nlp2sql.embeddingInactiveBadge}
                  </Badge>
                  {!profile.is_active ? (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={controlsDisabled || activateMutation.isPending}
                      onClick={() => handleActivate(profile.id)}
                    >
                      {t.settings.nlp2sql.embeddingActivate}
                    </Button>
                  ) : null}
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={
                      controlsDisabled ||
                      rebuildMutation.isPending ||
                      !dataSourceId
                    }
                    onClick={() => handleRebuild(profile.id, "selected")}
                  >
                    {t.settings.nlp2sql.embeddingRebuildSelected}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={controlsDisabled || rebuildMutation.isPending}
                    onClick={() => handleRebuild(profile.id, "all")}
                  >
                    {t.settings.nlp2sql.embeddingRebuildAll}
                  </Button>
                </ItemActions>
              </Item>
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4 rounded-lg border p-4">
        <div className="flex items-center gap-2 text-sm font-medium">
          <SparklesIcon className="size-4" />
          {t.settings.nlp2sql.embeddingEditorTitle}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label={t.settings.nlp2sql.embeddingNameLabel}>
            <Input
              value={draft.name}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({ ...current, name: e.target.value }))
              }
            />
          </Field>
          <Field label={t.settings.nlp2sql.embeddingProviderLabel}>
            <Input
              value={draft.provider}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  provider: e.target.value,
                }))
              }
            />
          </Field>
          <Field label={t.settings.nlp2sql.embeddingModelLabel}>
            <Input
              value={draft.model}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({ ...current, model: e.target.value }))
              }
            />
          </Field>
          <Field label={t.settings.nlp2sql.embeddingDimensionsLabel}>
            <Input
              type="number"
              value={draft.dimensions}
              disabled={controlsDisabled}
              onChange={(e) =>
                setDraft((current) => ({
                  ...current,
                  dimensions: Number(e.target.value || 0),
                }))
              }
            />
          </Field>
        </div>

        {statusMessage ? (
          <div className="bg-muted rounded-md px-3 py-2 text-sm">
            {statusMessage}
          </div>
        ) : null}

        {!dataSourceId ? (
          <div className="text-muted-foreground text-sm">
            {t.settings.nlp2sql.embeddingRebuildSelectedHint}
          </div>
        ) : null}

        <Button
          disabled={controlsDisabled || createMutation.isPending}
          onClick={handleCreate}
        >
          {t.common.create}
        </Button>
      </section>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="flex flex-col gap-2 text-sm">
      <span className="font-medium">{label}</span>
      {children}
    </label>
  );
}
