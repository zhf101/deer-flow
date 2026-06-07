"""MyBatis 动态 SQL AST 节点定义。

本模块定义了 MyBatis 动态 SQL 的中间表示（IR）。处理流水线如下：

    MyBatis XML  →  mybatis_parser  →  MyBatis AST  →  mybatis_renderer  →  SQL

在解析与渲染之间引入显式 AST 的好处：
- 分支枚举，用于数据血缘分析（可包含所有 <if> 分支）
- 已知参数值下的确定性渲染
- 便于未来 AI Provider 理解动态 SQL 结构
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── 基类 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MyBatisNode:
    """所有 MyBatis AST 节点的基类。"""


# ── 叶子节点 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TextNode(MyBatisNode):
    """原始 SQL 文本片段，例如 ``SELECT * FROM t_user``。"""

    text: str


# ── 动态标签节点 ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IfNode(MyBatisNode):
    """``<if test="...">`` 条件分支块。"""

    test: str
    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class WhereNode(MyBatisNode):
    """``<where>`` — 自动拼接 WHERE 前缀并去除开头多余的 AND/OR。"""

    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class SetNode(MyBatisNode):
    """``<set>`` — 自动拼接 SET 前缀并去除末尾多余的逗号。"""

    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class ForeachNode(MyBatisNode):
    """``<foreach>`` — 遍历集合生成 SQL 片段。

    Attributes:
        collection: 可迭代对象的 OGNL 表达式（如 ``ids``、``list.items``）。
        item: 每次迭代时元素的变量名。
        index: 迭代索引的变量名（可选）。
        open: 迭代输出前拼接的文本（如 ``(``）。
        separator: 每次迭代之间的分隔符（如 ``,``）。
        close: 迭代输出后追加的文本（如 ``)``）。
    """

    collection: str
    item: str = "item"
    index: str = ""
    open: str = ""
    separator: str = ""
    close: str = ""
    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class WhenNode(MyBatisNode):
    """``<choose>`` 内部的 ``<when test="...">`` 分支。"""

    test: str
    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class OtherwiseNode(MyBatisNode):
    """``<choose>`` 内部的 ``<otherwise>`` 兜底分支。"""

    children: list[MyBatisNode] = field(default_factory=list)


@dataclass(frozen=True)
class ChooseNode(MyBatisNode):
    """``<choose>`` — 类似 switch 的分支结构，匹配第一个成立的 when 分支。"""

    when_clauses: list[WhenNode] = field(default_factory=list)
    otherwise: OtherwiseNode | None = None


@dataclass(frozen=True)
class TrimNode(MyBatisNode):
    """``<trim>`` — 通用的前缀/后缀裁剪标签。

    ``<where>`` 和 ``<set>`` 可视为 ``<trim>`` 的特殊形式。
    """

    prefix: str = ""
    suffix: str = ""
    prefix_overrides: list[str] = field(default_factory=list)
    suffix_overrides: list[str] = field(default_factory=list)
    children: list[MyBatisNode] = field(default_factory=list)


# ── 语句节点（根节点） ───────────────────────────────────────────────────

@dataclass(frozen=True)
class StatementNode(MyBatisNode):
    """根节点，表示单条 ``<select|insert|update|delete>`` 语句。"""

    statement_type: str  # "select"、"insert"、"update"、"delete"
    statement_id: str = ""
    children: list[MyBatisNode] = field(default_factory=list)


# ── Mapper 节点（完整文件） ──────────────────────────────────────────────

@dataclass(frozen=True)
class MapperNode(MyBatisNode):
    """根节点，表示包含多条语句的完整 ``<mapper>`` XML 文件。"""

    namespace: str = ""
    statements: list[StatementNode] = field(default_factory=list)


# ── 渲染结果 ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RenderResult:
    """MyBatis AST 渲染为 SQL 后的输出结果。

    Attributes:
        sql: 渲染后的 SQL 文本（可能仍包含 ``#{}`` 占位符）。
        referenced_params: 渲染后 SQL 中引用到的参数名集合，
            用于判断哪些参数实际被使用。
        parameter_aliases: 动态 SQL 局部变量到真实参数名的映射，例如 foreach
            中的 item → ids。
    """

    sql: str
    referenced_params: frozenset[str] = frozenset()
    parameter_aliases: dict[str, str] = field(default_factory=dict)
