"use client";

import {
  Background,
  Controls,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { PlusIcon } from "lucide-react";
import { useEffect, useMemo } from "react";

import { Button } from "@/components/ui/button";

import { createDefaultStep, STEP_TYPES, stepLabel } from "../../common/lib/defaults";
import {
  applyEdgesToSteps,
  applyNodePositions,
  stepsToEdges,
  stepsToNodes,
  type StepNodeData,
} from "../../common/lib/flow";
import type { SceneDefinition, StepType } from "../../common/lib/types";

import { HttpStepNode, SqlStepNode } from "./flow-nodes";

type StepNode = Node<StepNodeData>;

interface FlowCanvasProps {
  scene: SceneDefinition;
  selectedStepId: string | null;
  onSceneChange: (scene: SceneDefinition) => void;
  onSelectStep: (stepId: string | null) => void;
  readOnly?: boolean;
}

export function FlowCanvas({
  scene,
  selectedStepId: _selectedStepId,
  onSceneChange,
  onSelectStep,
  readOnly,
}: FlowCanvasProps) {
  const nodeTypes = useMemo(() => ({
    httpStep: HttpStepNode,
    sqlStep: SqlStepNode,
  }), []);

  const [nodes, setNodes, onNodesChange] = useNodesState<StepNode>(
    stepsToNodes(scene.steps),
  );
  const [edges, setEdges, onEdgesChange] = useEdgesState(stepsToEdges(scene.steps));

  useEffect(() => {
    setNodes(stepsToNodes(scene.steps));
    setEdges(stepsToEdges(scene.steps));
  }, [scene.steps, setEdges, setNodes]);

  const addStep = (type: StepType) => {
    const nextStep = createDefaultStep(type, scene.steps.length);
    const nextScene = { ...scene, steps: scene.steps.concat(nextStep) };
    onSceneChange(nextScene);
    onSelectStep(nextStep.stepId);
  };

  const handleConnect = (connection: Connection) => {
    if (!connection.source || !connection.target) return;
    const sourceIndex = scene.steps.findIndex(
      (step) => step.stepId === connection.source,
    );
    const targetIndex = scene.steps.findIndex(
      (step) => step.stepId === connection.target,
    );
    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex >= targetIndex) return;
    const nextEdges = addEdge(connection, edges);
    setEdges(nextEdges);
    onSceneChange({ ...scene, steps: applyEdgesToSteps(scene.steps, nextEdges) });
  };

  const persistPositions = (
    _event: unknown,
    _node: StepNode,
    nextNodes: StepNode[],
  ) => {
    onSceneChange({ ...scene, steps: applyNodePositions(scene.steps, nextNodes) });
  };

  return (
    <div className="relative h-full min-h-0 bg-[linear-gradient(90deg,var(--border)_1px,transparent_1px),linear-gradient(var(--border)_1px,transparent_1px)] bg-[size:24px_24px]">
      {!readOnly && (
        <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-2 rounded-md border bg-background/95 p-2 shadow-sm">
          {STEP_TYPES.map((type) => (
            <Button
              key={type}
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => addStep(type)}
            >
              <PlusIcon className="size-3.5" />
              {stepLabel(type)}
            </Button>
          ))}
        </div>
      )}
      <ReactFlow<StepNode, Edge>
        nodes={nodes}
        edges={edges}
        onNodesChange={readOnly ? undefined : onNodesChange}
        onEdgesChange={readOnly ? undefined : (changes) => {
          onEdgesChange(changes);
        }}
        onConnect={readOnly ? undefined : handleConnect}
        onNodeClick={(_, node) => onSelectStep(node.id)}
        onPaneClick={() => onSelectStep(null)}
        onNodeDragStop={readOnly ? undefined : persistPositions}
        nodeTypes={nodeTypes}
        fitView
      >
        <Background gap={24} size={1} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
