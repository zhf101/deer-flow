"""ContextItem 抽取、查询过滤和导入工作流。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from ..models import ContextItem, TaskRun, Variable, VariableProvenance, VariableSource
from ..store import EntityNotFoundError, Store
from ..support.errors import RuntimeConflictError

_SHORT_LIVED_SEMANTIC_TYPES = {"OTP", "SMS_CODE", "TOKEN", "PAYMENT_QR", "CAPTCHA"}


def extract_context_items(task_run: TaskRun, store: Store) -> list[ContextItem]:
    """从已完成任务的可信场景输出变量中抽取可复用上下文项。"""

    existing_variable_ids = {
        item.source_variable_id for item in store.list_context_items(source_task_run_id=task_run.task_run_id)
    }
    created: list[ContextItem] = []
    now = datetime.now(UTC)

    for variable in store.list_variables(task_run.task_run_id):
        if variable.variable_id in existing_variable_ids:
            continue
        if not _is_extractable(variable):
            continue

        item = ContextItem(
            context_item_id=_gen_id("ctx"),
            source_task_run_id=task_run.task_run_id,
            source_variable_id=variable.variable_id,
            thread_id=task_run.thread_id,
            user_id=task_run.user_id,
            env_code=task_run.env_code,
            name=variable.name,
            semantic_type=variable.semantic_type,
            value_ref=variable.value_ref,
            value_preview=variable.value_preview,
            sensitive=variable.sensitive,
            tainted=variable.tainted,
            reusable=True,
            expires_at=None,
            created_at=now,
        )
        store.save_context_item(item)
        created.append(item)

    return created


def filter_reusable_context_items(
    items: list[ContextItem],
    *,
    user_id: str | None,
    thread_id: str | None,
    env_code: str | None,
    semantic_type: str | None,
    now: datetime | None = None,
) -> list[ContextItem]:
    """按用户可见性、环境、语义类型和安全状态过滤上下文项。"""

    now = now or datetime.now(UTC)
    filtered: list[ContextItem] = []
    for item in items:
        if user_id is not None and item.user_id != user_id:
            continue
        if thread_id is not None and item.thread_id != thread_id:
            continue
        if env_code is not None and item.env_code != env_code:
            continue
        if semantic_type is not None and item.semantic_type != semantic_type:
            continue
        if not _is_reusable(item, now=now):
            continue
        filtered.append(item)
    return filtered


def import_context_items(task_run: TaskRun, context_item_ids: list[str], store: Store) -> list[Variable]:
    """把用户显式选择的 ContextItem 导入为目标任务的 CONTEXT 变量。"""

    imported: list[Variable] = []
    for context_item_id in dict.fromkeys(context_item_ids):
        try:
            item = store.get_context_item(context_item_id)
        except EntityNotFoundError as exc:
            raise RuntimeConflictError(f"ContextItem 不存在或不可复用：{context_item_id}") from exc

        _ensure_importable(task_run, item)
        try:
            value = store.get_payload(item.source_task_run_id, item.value_ref)
        except EntityNotFoundError as exc:
            raise RuntimeConflictError(f"ContextItem 缺少可复用 payload：{context_item_id}") from exc

        variable_id = _gen_id("var")
        value_ref = f"ref:context/{context_item_id}/{variable_id}"
        variable = Variable(
            variable_id=variable_id,
            task_run_id=task_run.task_run_id,
            name=item.name,
            semantic_type=item.semantic_type,
            value_ref=value_ref,
            value_preview=item.value_preview,
            sensitive=item.sensitive,
            tainted=False,
            provenance=VariableProvenance(
                source_type=VariableSource.CONTEXT,
                source_id=item.context_item_id,
            ),
            created_at=datetime.now(UTC),
        )
        store.save_payload(task_run.task_run_id, value_ref, value)
        store.save_variable(variable)
        imported.append(variable)

    return imported


def _ensure_importable(task_run: TaskRun, item: ContextItem) -> None:
    now = datetime.now(UTC)
    if item.user_id != task_run.user_id:
        raise RuntimeConflictError("ContextItem 不属于当前用户，不能导入")
    if item.thread_id != task_run.thread_id:
        raise RuntimeConflictError("ContextItem 不属于当前线程，不能导入")
    if task_run.env_code is not None and item.env_code is not None and item.env_code != task_run.env_code:
        raise RuntimeConflictError("ContextItem 所属环境与目标任务不匹配")
    if not _is_reusable(item, now=now):
        raise RuntimeConflictError("ContextItem 已过期、被污染或不可复用")


def _is_extractable(variable: Variable) -> bool:
    return (
        variable.provenance.source_type == VariableSource.SCENE_OUTPUT
        and not variable.tainted
        and variable.semantic_type.upper() not in _SHORT_LIVED_SEMANTIC_TYPES
    )


def _is_reusable(item: ContextItem, *, now: datetime) -> bool:
    if item.tainted or not item.reusable:
        return False
    if item.semantic_type.upper() in _SHORT_LIVED_SEMANTIC_TYPES:
        return False
    if item.expires_at is not None and item.expires_at <= now:
        return False
    return True


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
