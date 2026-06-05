"use client";

import type { StepDefinition } from "../../lib/types";
import { stringifyConfigValue } from "../../lib/validation";

import { JsonEditor } from "../shared/json-editor";

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
