"""将 MyBatis XML 解析为 AST 节点。

支持两种输入形式：

1. **单条语句片段**（SQL 编辑器提交的格式）::

       <select id="queryUser">
           SELECT * FROM t_user
           <where>
               <if test="name != null">AND name = #{name}</if>
           </where>
       </select>

2. **完整 Mapper XML 文件**（从源码上传或扫描获取）::

       <?xml version="1.0" encoding="UTF-8"?>
       <!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "...">
       <mapper namespace="com.example.UserMapper">
           <select id="queryUser">...</select>
           <insert id="createUser">...</insert>
       </mapper>

入口函数为 :func:`parse_mybatis_xml`，返回 :class:`StatementNode`（单条语句）
或 :class:`MapperNode`（完整 Mapper 文件）。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.gdp.datagen.config.sqlsource.parsers.ast import (
    ChooseNode,
    ForeachNode,
    IfNode,
    MapperNode,
    MyBatisNode,
    OtherwiseNode,
    SetNode,
    StatementNode,
    TextNode,
    TrimNode,
    WhenNode,
    WhereNode,
)

STATEMENT_TAGS = frozenset({"select", "insert", "update", "delete"})


def parse_mybatis_xml(sql_text: str) -> StatementNode | MapperNode:
    """将 MyBatis XML 文本解析为 AST。

    Returns:
        如果输入包含单条语句标签则返回 :class:`StatementNode`，
        如果是 ``<mapper>`` 包裹的完整文件则返回 :class:`MapperNode`。

    Raises:
        ValueError: 未找到有效的 MyBatis 语句标签。
    """

    stripped = sql_text.strip()

    # 先直接尝试解析（可能是 <mapper>...</mapper> 或 <select>...</select>）
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        # 将片段包裹在 <mapper> 中使其成为合法 XML
        root = ET.fromstring(f"<mapper>{stripped}</mapper>")

    tag = _local_tag(root)

    # 完整 Mapper 文件
    if tag == "mapper":
        return _parse_mapper(root)

    # 根节点即为单条语句
    if tag in STATEMENT_TAGS:
        return _parse_statement_element(root)

    # 根节点是其他标签 —— 在子元素中搜索语句标签
    for child in root:
        if _local_tag(child) in STATEMENT_TAGS:
            return _parse_statement_element(child)

    raise ValueError("No MyBatis statement tag (select/insert/update/delete) found in XML")


# ── 内部解析 ────────────────────────────────────────────────────────────

def _parse_mapper(element: ET.Element) -> MapperNode:
    """将 ``<mapper>`` 根元素解析为 :class:`MapperNode`。"""

    namespace = element.attrib.get("namespace", "")
    statements: list[StatementNode] = []
    for child in element:
        if _local_tag(child) in STATEMENT_TAGS:
            statements.append(_parse_statement_element(child))
    if not statements:
        raise ValueError("Mapper XML contains no statement tags")
    return MapperNode(namespace=namespace, statements=statements)


def _parse_statement_element(element: ET.Element) -> StatementNode:
    """解析单条 ``<select|insert|update|delete>`` 元素。"""

    return StatementNode(
        statement_type=_local_tag(element),
        statement_id=element.attrib.get("id", ""),
        children=_parse_children(element),
    )


def _parse_children(element: ET.Element) -> list[MyBatisNode]:
    """递归解析 XML 元素的子节点（文本 + 子元素）。"""

    nodes: list[MyBatisNode] = []

    # 元素开头的文本
    if element.text:
        text = element.text
        if text.strip():
            nodes.append(TextNode(text=text))

    for child in element:
        node = _parse_element(child)
        if node is not None:
            nodes.append(node)
        # 尾随文本（子元素闭合标签之后、下一个兄弟元素之前的文本）
        if child.tail:
            tail = child.tail
            if tail.strip():
                nodes.append(TextNode(text=tail))

    return nodes


def _parse_element(element: ET.Element) -> MyBatisNode | None:
    """将单个 XML 元素解析为对应的 AST 节点。"""

    tag = _local_tag(element)

    if tag == "if":
        return IfNode(
            test=element.attrib.get("test", ""),
            children=_parse_children(element),
        )

    if tag == "where":
        return WhereNode(children=_parse_children(element))

    if tag == "set":
        return SetNode(children=_parse_children(element))

    if tag == "trim":
        prefix_overrides_raw = element.attrib.get("prefixOverrides", "")
        suffix_overrides_raw = element.attrib.get("suffixOverrides", "")
        return TrimNode(
            prefix=element.attrib.get("prefix", ""),
            suffix=element.attrib.get("suffix", ""),
            prefix_overrides=_split_pipe_list(prefix_overrides_raw),
            suffix_overrides=_split_pipe_list(suffix_overrides_raw),
            children=_parse_children(element),
        )

    if tag == "foreach":
        return ForeachNode(
            collection=element.attrib.get("collection", ""),
            item=element.attrib.get("item", "item"),
            index=element.attrib.get("index", ""),
            open=element.attrib.get("open", ""),
            separator=element.attrib.get("separator", ""),
            close=element.attrib.get("close", ""),
            children=_parse_children(element),
        )

    if tag == "choose":
        return _parse_choose(element)

    # when/otherwise 出现在 choose 外部 —— 作为透传文本处理
    if tag in {"when", "otherwise"}:
        return TextNode(text=_collect_all_text(element))

    # CDATA、include 或未知标签 —— 收集为文本
    return TextNode(text=_collect_all_text(element))


def _parse_choose(element: ET.Element) -> ChooseNode:
    """将 ``<choose>`` 解析为 :class:`ChooseNode`。"""

    when_clauses: list[WhenNode] = []
    otherwise: OtherwiseNode | None = None

    for child in element:
        tag = _local_tag(child)
        if tag == "when":
            when_clauses.append(
                WhenNode(
                    test=child.attrib.get("test", ""),
                    children=_parse_children(child),
                )
            )
        elif tag == "otherwise":
            otherwise = OtherwiseNode(children=_parse_children(child))

    return ChooseNode(when_clauses=when_clauses, otherwise=otherwise)


# ── 工具函数 ───────────────────────────────────────────────────────────

def _local_tag(element: ET.Element) -> str:
    """返回去除 XML 命名空间后的本地标签名。"""

    return element.tag.rsplit("}", maxsplit=1)[-1].lower()


def _split_pipe_list(value: str) -> list[str]:
    """按 ``|`` 分隔的属性值拆分（如 ``"AND|OR"``）。"""

    return [item.strip() for item in value.split("|") if item.strip()]


def _collect_all_text(element: ET.Element) -> str:
    """递归收集元素中的所有文本内容（用于透传处理）。"""

    parts: list[str] = []
    if element.text:
        parts.append(element.text)
    for child in element:
        parts.append(_collect_all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)
