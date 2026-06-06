"use client";

import type { StepDefinition } from "../common/lib/types";
import { stringifyConfigValue } from "../common/lib/validation";

import { JsonEditor } from "../common/editors/json-editor";

interface TransformStepFormProps {
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
}

export function TransformStepForm({ step, onChange }: TransformStepFormProps) {
  return (
    <JsonEditor
      label="变量赋值 assignments"
      value={step.assignments}
      onChange={(value) =>
        onChange({
          ...step,
          assignments: Object.fromEntries(
            Object.entries(value).map(([key, item]) => [
              key,
              stringifyConfigValue(item),
            ]),
          ),
        })
      }
    />
  );
}
