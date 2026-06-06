"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import type { StepDefinition } from "../common/lib/types";

interface AssertStepFormProps {
  step: StepDefinition;
  onChange: (step: StepDefinition) => void;
}

export function AssertStepForm({ step, onChange }: AssertStepFormProps) {
  const assertions = step.assertions ?? [];
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">断言</span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() =>
            onChange({
              ...step,
              assertions: assertions.concat({ expression: "", message: "" }),
            })
          }
        >
          <PlusIcon className="size-4" />
          新增
        </Button>
      </div>
      {assertions.map((assertion, index) => (
        <div key={index} className="grid grid-cols-[1fr_34px] gap-2">
          <Input
            value={assertion.expression}
            onChange={(event) =>
              onChange({
                ...step,
                assertions: assertions.map((item, i) =>
                  i === index
                    ? { ...item, expression: event.target.value }
                    : item,
                ),
              })
            }
            placeholder="${steps.createOrder.outputs.orderNo} NOT_EMPTY"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() =>
              onChange({
                ...step,
                assertions: assertions.filter((_, i) => i !== index),
              })
            }
          >
            <Trash2Icon className="size-4" />
          </Button>
        </div>
      ))}
    </div>
  );
}
