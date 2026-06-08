"use client";

import { JsonEditor } from "../common/editors/json-editor";
import type { TransformStepDefinition } from "../common/lib/types";
import { stringifyConfigValue } from "../common/lib/validation";


interface TransformStepFormProps {
  step: TransformStepDefinition;
  onChange: (step: TransformStepDefinition) => void;
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
