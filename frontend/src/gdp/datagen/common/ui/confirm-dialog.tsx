"use client";

import { AlertTriangleIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: () => void;
  title?: string;
  description?: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "danger" | "warning";
  loading?: boolean;
}

export function ConfirmDialog({
  open,
  onOpenChange,
  onConfirm,
  title = "确认删除",
  description = "此操作不可撤销，确定要继续吗？",
  confirmText = "删除",
  cancelText = "取消",
  variant = "danger",
  loading = false,
}: ConfirmDialogProps) {
  const handleConfirm = () => {
    onConfirm();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-full",
              variant === "danger" && "bg-red-50 dark:bg-red-950/50",
              variant === "warning" && "bg-amber-50 dark:bg-amber-950/50",
            )}
          >
            <AlertTriangleIcon
              className={cn(
                "size-5",
                variant === "danger" && "text-red-600",
                variant === "warning" && "text-amber-600",
              )}
            />
          </div>
          <div className="flex-1 space-y-1.5 pt-0.5">
            <DialogTitle className="text-base">{title}</DialogTitle>
            <DialogDescription className="text-sm leading-relaxed">
              {description}
            </DialogDescription>
          </div>
        </div>
        <DialogFooter className="mt-2 sm:justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onOpenChange(false)}
            disabled={loading}
          >
            {cancelText}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleConfirm}
            disabled={loading}
          >
            {loading ? "处理中..." : confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
