"""将 MyBatis AST 渲染为 SQL。

两种渲染模式：

- **确定性模式**（``all_branches=False``）：根据提供的参数值对 OGNL 表达式求值，
  不满足条件的 ``<if>`` / ``<when>`` 分支会被跳过。适用于参数值已知的场景。

- **分析模式**（``all_branches=True``）：无论 OGNL 求值结果如何，都包含所有条件分支。
  适用于数据血缘分析、表提取，或参数值未知的场景——确保没有 SQL 路径在下游
  sqlglot 分析时不可见。
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.gdp.datagen.config.sqlsource.parsers.ast import (
    ChooseNode,
    ForeachNode,
    IfNode,
    MapperNode,
    MyBatisNode,
    RenderResult,
    SetNode,
    StatementNode,
    TextNode,
    TrimNode,
    WhenNode,
    WhereNode,
    OtherwiseNode,
)
from app.gdp.datagen.config.sqlsource.parsers.ognl import evaluate_ognl

# MyBatis 参数占位符正则：#{name}、${name}、#{obj.field}
_PARAM_RE = re.compile(r"[#\$]\{\s*([\w.]+)\s*(?:,[^}]*)?\}")


def render(
    node: MyBatisNode,
    values: dict[str, Any] | None = None,
    *,
    all_branches: bool = False,
) -> RenderResult:
    """将 MyBatis AST 节点渲染为 SQL。

    Args:
        node: AST 根节点（通常为 :class:`StatementNode` 或 :class:`MapperNode`）。
        values: 参数名 → 值 的映射，用于 OGNL 求值。
        all_branches: 为 ``True`` 时包含所有条件分支，用于分析模式。

    Returns:
        :class:`RenderResult`，包含渲染后的 SQL 和被引用的参数名集合。
    """

    ctx = _RenderContext(values=values or {}, local_to_collection={}, all_branches=all_branches)
    sql = _render_node(node, ctx)
    params = _collect_referenced_params(sql, ctx)
    return RenderResult(sql=sql.strip(), referenced_params=frozenset(params))


# ── 渲染上下文 ──────────────────────────────────────────────────────────

class _RenderContext:
    """单次渲染过程中共享的可变状态。"""

    def __init__(
        self,
        values: dict[str, Any],
        local_to_collection: dict[str, str],
        all_branches: bool,
        *,
        _foreach_mappings: dict[str, str] | None = None,
    ) -> None:
        self.values = values
        self.local_to_collection = local_to_collection
        self.all_branches = all_branches
        # 共享可变字典，累积所有 foreach item→collection 的映射关系
        self._foreach_mappings: dict[str, str] = _foreach_mappings if _foreach_mappings is not None else {}

    def child(self, **overrides: Any) -> _RenderContext:
        """创建子上下文，用于 foreach 作用域隔离。"""

        values_add = overrides.pop("values_add", {})
        local_add = overrides.pop("local_add", {})
        ctx = _RenderContext(
            values={**self.values, **values_add},
            local_to_collection={**self.local_to_collection, **local_add},
            all_branches=self.all_branches,
            _foreach_mappings=self._foreach_mappings,
        )
        # 累积 foreach 映射，供顶层参数解析使用
        self._foreach_mappings.update(local_add)
        return ctx


# ── 节点分发 ───────────────────────────────────────────────────────────

def _render_node(node: MyBatisNode, ctx: _RenderContext) -> str:
    if isinstance(node, TextNode):
        return node.text
    if isinstance(node, StatementNode):
        return _render_children(node.children, ctx)
    if isinstance(node, MapperNode):
        # 默认渲染第一条语句
        if node.statements:
            return _render_node(node.statements[0], ctx)
        return ""
    if isinstance(node, IfNode):
        return _render_if(node, ctx)
    if isinstance(node, WhereNode):
        return _render_where(node, ctx)
    if isinstance(node, SetNode):
        return _render_set(node, ctx)
    if isinstance(node, TrimNode):
        return _render_trim(node, ctx)
    if isinstance(node, ForeachNode):
        return _render_foreach(node, ctx)
    if isinstance(node, ChooseNode):
        return _render_choose(node, ctx)
    if isinstance(node, (WhenNode, OtherwiseNode)):
        return _render_children(node.children, ctx)
    return ""


def _render_children(children: list[MyBatisNode], ctx: _RenderContext) -> str:
    return "".join(_render_node(child, ctx) for child in children)


# ── 动态标签渲染器 ───────────────────────────────────────────────────────

def _render_if(node: IfNode, ctx: _RenderContext) -> str:
    if ctx.all_branches:
        return _render_children(node.children, ctx)
    result = evaluate_ognl(node.test, ctx.values)
    if result.known and not result.value:
        return ""
    # OGNL 结果未知 → 保守处理，包含该分支
    return _render_children(node.children, ctx)


def _render_where(node: WhereNode, ctx: _RenderContext) -> str:
    inner = _normalize_whitespace(_render_children(node.children, ctx))
    if not inner:
        return ""
    # 去除开头的 AND / OR
    inner = re.sub(r"^(?:AND|OR)\b\s*", "", inner, flags=re.IGNORECASE)
    return f"WHERE {inner}"


def _render_set(node: SetNode, ctx: _RenderContext) -> str:
    inner = _normalize_whitespace(_render_children(node.children, ctx))
    if not inner:
        return ""
    # 去除末尾的逗号
    inner = re.sub(r",\s*$", "", inner)
    return f"SET {inner}"


def _render_trim(node: TrimNode, ctx: _RenderContext) -> str:
    inner = _normalize_whitespace(_render_children(node.children, ctx))
    if not inner:
        return ""
    for override in node.prefix_overrides:
        inner = re.sub(rf"^{re.escape(override)}\b\s*", "", inner, flags=re.IGNORECASE)
    for override in node.suffix_overrides:
        inner = re.sub(rf"\s*{re.escape(override)}$", "", inner, flags=re.IGNORECASE)
    parts = [p for p in (node.prefix, inner, node.suffix) if p]
    return " ".join(parts)


def _render_foreach(node: ForeachNode, ctx: _RenderContext) -> str:
    collection = ctx.values.get(node.collection)
    item_count = len(collection) if isinstance(collection, list | tuple | set) else 1
    item_count = max(item_count, 1)

    if ctx.all_branches:
        # 分析模式：渲染一次，确保 item 变量可用
        child_ctx = ctx.child(
            values_add={node.item: None},
            local_add={node.item: node.collection},
        )
        rendered = _normalize_whitespace(_render_children(node.children, child_ctx))
        return f"{node.open}{rendered}{node.close}" if rendered else ""

    # 确定性模式：遍历集合逐次渲染
    items = list(collection) if isinstance(collection, list | tuple | set) else [collection]
    parts: list[str] = []
    for index, item_value in enumerate(items):
        child_ctx = ctx.child(
            values_add={node.item: item_value},
            local_add={node.item: node.collection},
        )
        if node.index:
            child_ctx.values[node.index] = index
        rendered = _normalize_whitespace(_render_children(node.children, child_ctx))
        if rendered:
            parts.append(rendered)
    joined = node.separator.join(parts)
    return f"{node.open}{joined}{node.close}" if joined else ""


def _render_choose(node: ChooseNode, ctx: _RenderContext) -> str:
    if ctx.all_branches:
        # 分析模式：渲染所有分支
        parts: list[str] = []
        for when_clause in node.when_clauses:
            rendered = _render_children(when_clause.children, ctx)
            if rendered.strip():
                parts.append(rendered)
        if node.otherwise:
            rendered = _render_children(node.otherwise.children, ctx)
            if rendered.strip():
                parts.append(rendered)
        return " ".join(parts)

    # 确定性模式：取第一个匹配的 when 分支
    unknown_branch: WhenNode | None = None
    for when_clause in node.when_clauses:
        result = evaluate_ognl(when_clause.test, ctx.values)
        if result.known and result.value:
            return _render_children(when_clause.children, ctx)
        if not result.known and unknown_branch is None:
            unknown_branch = when_clause
    # 兜底：OGNL 未知 → 包含该分支；否则尝试 <otherwise>
    if unknown_branch is not None:
        return _render_children(unknown_branch.children, ctx)
    if node.otherwise:
        return _render_children(node.otherwise.children, ctx)
    return ""


# ── 参数追踪 ───────────────────────────────────────────────────────────

def _collect_referenced_params(sql: str, ctx: _RenderContext) -> set[str]:
    """从渲染后的 SQL 中提取参数名，并解析 foreach 局部变量。"""

    raw_names = set(_PARAM_RE.findall(sql))
    resolved: set[str] = set()
    # 使用根上下文累积的 foreach 映射
    mappings = ctx._foreach_mappings
    for name in raw_names:
        # 去除属性访问：#{item.field} → item
        root_name = name.split(".")[0]
        # 将 foreach 局部变量映射回集合名
        collection = mappings.get(root_name)
        resolved.add(collection if collection else root_name)
    return resolved


# ── 工具函数 ───────────────────────────────────────────────────────────

def _normalize_whitespace(text: str) -> str:
    """将连续空白压缩为单个空格并去除首尾空白。"""

    return re.sub(r"\s+", " ", text.strip())
