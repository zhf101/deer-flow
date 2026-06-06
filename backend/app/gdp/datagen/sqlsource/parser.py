"""MyBatis-aware SQL source parser.

Pipeline:
1. MyBatis XML/dynamic tags -> analysis SQL template
2. SQL template -> sqlglot AST
3. AST -> UI metadata
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from xml.etree import ElementTree

from defusedxml.ElementTree import fromstring
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError

from app.gdp.datagen.sqlsource.models import (
    SqlSourceConditionMeta,
    SqlSourceFieldMeta,
    SqlSourceParameter,
    SqlSourceParseResponse,
    SqlSourceTableMeta,
)
from app.gdp.models import InputFieldType, SqlOperation

MYBATIS_ROOT_TAGS = {"select", "insert", "update", "delete"}
MYBATIS_DYNAMIC_TAGS = {"if", "where", "set", "foreach", "choose", "when", "otherwise", "trim"}
PLACEHOLDER_RE = re.compile(r"([#\$])\{\s*([\w.]+)\s*(?:,[^}]*)?\}")
NAMED_PARAM_RE = re.compile(r"(^|[^:]):([a-zA-Z_]\w*)")
LEADING_AND_OR_RE = re.compile(r"^\s*(AND|OR)\b\s*", re.IGNORECASE)


@dataclass
class RenderContext:
    parameters: set[str] = field(default_factory=set)
    placeholder_order: list[str] = field(default_factory=list)

    def add_parameter(self, name: str, *, placeholder: bool = False) -> None:
        if not name:
            return
        self.parameters.add(name)
        if placeholder:
            self.placeholder_order.append(name)


@dataclass
class MyBatisNode:
    def render(self, ctx: RenderContext) -> str:
        raise NotImplementedError


@dataclass
class TextNode(MyBatisNode):
    text: str

    def render(self, ctx: RenderContext) -> str:
        return _replace_placeholders(self.text, ctx)


@dataclass
class ContainerNode(MyBatisNode):
    children: list[MyBatisNode] = field(default_factory=list)

    def render(self, ctx: RenderContext) -> str:
        return _join_sql(child.render(ctx) for child in self.children)


@dataclass
class IfNode(ContainerNode):
    test: str = ""


@dataclass
class WhereNode(ContainerNode):
    def render(self, ctx: RenderContext) -> str:
        body = LEADING_AND_OR_RE.sub("", super().render(ctx).strip()).strip()
        return f" WHERE {body} " if body else ""


@dataclass
class SetNode(ContainerNode):
    def render(self, ctx: RenderContext) -> str:
        body = super().render(ctx).strip().rstrip(",").strip()
        return f" SET {body} " if body else ""


@dataclass
class TrimNode(ContainerNode):
    prefix: str = ""
    suffix: str = ""
    prefix_overrides: str = ""
    suffix_overrides: str = ""

    def render(self, ctx: RenderContext) -> str:
        body = super().render(ctx).strip()
        body = _apply_overrides(body, self.prefix_overrides, from_start=True)
        body = _apply_overrides(body, self.suffix_overrides, from_start=False)
        if not body:
            return ""
        return f" {self.prefix} {body} {self.suffix} "


@dataclass
class ForeachNode(ContainerNode):
    collection: str = ""
    item: str = "item"
    open_: str = ""
    separator: str = ","
    close: str = ""

    def render(self, ctx: RenderContext) -> str:
        if self.collection:
            ctx.parameters.add(self.collection.split(".")[-1])
        body = super().render(ctx).strip() or "?"
        body = PLACEHOLDER_RE.sub("?", body)
        sample_items = self.separator.join([body, body])
        return f" {self.open_}{sample_items}{self.close} "


@dataclass
class ChooseNode(MyBatisNode):
    when_nodes: list[MyBatisNode] = field(default_factory=list)
    otherwise_node: MyBatisNode | None = None

    def render(self, ctx: RenderContext) -> str:
        rendered = [node.render(ctx) for node in self.when_nodes]
        if self.otherwise_node:
            rendered.append(self.otherwise_node.render(ctx))
        return _join_sql(rendered)


def parse_sql_source(
    sql_text: str,
    parameters: list[SqlSourceParameter] | None = None,
) -> SqlSourceParseResponse:
    """Parse SQL/MyBatis XML into backend-owned metadata for the config UI."""
    render_ctx = RenderContext()
    normalized_sql = render_sql_for_analysis(sql_text, render_ctx)
    operation = detect_operation(normalized_sql)

    try:
        ast = parse_one(normalized_sql, read="mysql")
    except ParseError:
        ast = None

    tables = parse_tables_from_ast(ast) if ast is not None else []
    result_fields = parse_result_fields_from_ast(ast, tables) if ast is not None else []
    condition_fields = (
        parse_condition_fields_from_ast(ast, tables, render_ctx.placeholder_order)
        if ast is not None
        else []
    )
    parsed_parameters = merge_parameters(
        parse_parameters(normalized_sql, condition_fields, render_ctx.parameters),
        parameters or [],
    )
    return SqlSourceParseResponse(
        normalizedSql=normalized_sql,
        operation=operation,
        tables=tables,
        resultFields=result_fields,
        conditionFields=condition_fields,
        parameters=parsed_parameters,
    )


def render_sql_for_analysis(sql_text: str, ctx: RenderContext | None = None) -> str:
    ctx = ctx or RenderContext()
    stripped = sql_text.strip()
    if _looks_like_xml(stripped):
        try:
            root = fromstring(_wrap_xml_if_needed(stripped))
            statement = _find_statement_node(root)
            if statement is not None:
                node = _element_to_node(statement)
                return _normalize_sql(node.render(ctx))
        except ElementTree.ParseError:
            pass
    return _normalize_sql(_replace_placeholders(stripped, ctx))


def _looks_like_xml(value: str) -> bool:
    return bool(re.search(r"</?(mapper|select|insert|update|delete|where|if|foreach|trim|set|choose)\b", value, re.IGNORECASE))


def _wrap_xml_if_needed(value: str) -> str:
    if re.match(r"^\s*<\s*mapper\b", value, re.IGNORECASE):
        return value
    return f"<mapper>{value}</mapper>"


def _find_statement_node(root: ElementTree.Element) -> ElementTree.Element | None:
    if _strip_namespace(root.tag) in MYBATIS_ROOT_TAGS:
        return root
    for element in root.iter():
        if _strip_namespace(element.tag) in MYBATIS_ROOT_TAGS:
            return element
    return None


def _element_to_node(element: ElementTree.Element) -> MyBatisNode:
    tag = _strip_namespace(element.tag).lower()
    if tag == "where":
        node: ContainerNode = WhereNode()
    elif tag == "set":
        node = SetNode()
    elif tag == "if":
        node = IfNode(test=element.attrib.get("test", ""))
    elif tag == "foreach":
        node = ForeachNode(
            collection=element.attrib.get("collection", ""),
            item=element.attrib.get("item", "item"),
            open_=element.attrib.get("open", ""),
            separator=element.attrib.get("separator", ","),
            close=element.attrib.get("close", ""),
        )
    elif tag == "trim":
        node = TrimNode(
            prefix=element.attrib.get("prefix", ""),
            suffix=element.attrib.get("suffix", ""),
            prefix_overrides=element.attrib.get("prefixOverrides", ""),
            suffix_overrides=element.attrib.get("suffixOverrides", ""),
        )
    elif tag == "choose":
        choose = ChooseNode()
        for child in list(element):
            child_tag = _strip_namespace(child.tag).lower()
            if child_tag == "when":
                choose.when_nodes.append(_element_to_node(child))
            elif child_tag == "otherwise":
                choose.otherwise_node = _element_to_node(child)
        return choose
    else:
        node = ContainerNode()

    if element.text:
        node.children.append(TextNode(element.text))
    for child in list(element):
        node.children.append(_element_to_node(child))
        if child.tail:
            node.children.append(TextNode(child.tail))
    return node


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _replace_placeholders(sql: str, ctx: RenderContext) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(2).split(".")[-1]
        if match.group(1) == "#":
            ctx.add_parameter(name, placeholder=True)
            return "?"
        ctx.add_parameter(name)
        return name

    sql = PLACEHOLDER_RE.sub(repl, sql)
    for match in NAMED_PARAM_RE.finditer(sql):
        ctx.add_parameter(match.group(2), placeholder=True)
    return NAMED_PARAM_RE.sub(lambda m: f"{m.group(1)}?", sql)


def _apply_overrides(body: str, overrides: str, *, from_start: bool) -> str:
    result = body
    for raw_token in overrides.split("|"):
        token = raw_token.strip()
        if not token:
            continue
        pattern = rf"^\s*{re.escape(token)}\b\s*" if from_start else rf"\s*{re.escape(token)}\s*$"
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)
    return result.strip()


def _join_sql(parts: Any) -> str:
    return " ".join(part.strip() for part in parts if str(part).strip())


def _normalize_sql(sql: str) -> str:
    sql = _decode_xml_entities(_strip_sql_comments(sql))
    return re.sub(r"\s+", " ", sql).strip()


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"--.*$", " ", sql, flags=re.MULTILINE)
    return re.sub(r"/\*[\s\S]*?\*/", " ", sql)


def _decode_xml_entities(value: str) -> str:
    return (
        value.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
    )


def detect_operation(sql: str) -> SqlOperation:
    first = (sql.strip().split() or [""])[0].upper()
    if first in {"SELECT", "INSERT", "UPDATE", "DELETE"}:
        return SqlOperation(first)
    return SqlOperation.SELECT


def parse_tables_from_ast(ast: exp.Expression) -> list[SqlSourceTableMeta]:
    tables: list[SqlSourceTableMeta] = []
    seen: set[str] = set()
    for table in ast.find_all(exp.Table):
        table_name = table.name
        alias = table.alias_or_name if table.alias else ""
        key = f"{table_name}:{alias}"
        if not table_name or key in seen:
            continue
        seen.add(key)
        tables.append(SqlSourceTableMeta(id=key, tableName=table_name, alias=alias))
    return tables


def parse_result_fields_from_ast(
    ast: exp.Expression,
    tables: list[SqlSourceTableMeta],
) -> list[SqlSourceFieldMeta]:
    select = ast.find(exp.Select)
    if select is None:
        return []
    fields: list[SqlSourceFieldMeta] = []
    for index, expression in enumerate(select.expressions):
        alias = expression.alias_or_name if expression.alias else ""
        field_name = alias or _field_name_from_expression(expression, index)
        source_table = _source_table_from_expression(expression, tables)
        fields.append(
            SqlSourceFieldMeta(
                id=f"{field_name}:{alias}:{index}",
                fieldName=field_name,
                sourceTable=source_table,
                alias=alias,
            )
        )
    return fields


def parse_condition_fields_from_ast(
    ast: exp.Expression,
    tables: list[SqlSourceTableMeta],
    placeholder_order: list[str],
) -> list[SqlSourceConditionMeta]:
    conditions: list[SqlSourceConditionMeta] = []
    seen: set[str] = set()
    placeholder_index = 0
    for predicate in ast.find_all(exp.Predicate):
        columns = list(predicate.find_all(exp.Column))
        if not columns:
            continue
        left_column = columns[0]
        field_name = left_column.name
        source_table = _resolve_table_name(left_column.table, tables)
        param_name = _param_name_for_predicate(
            predicate,
            field_name,
            placeholder_order,
            placeholder_index,
        )
        if _predicate_has_placeholder(predicate):
            placeholder_index += 1
        key = f"{source_table}:{field_name}:{param_name}"
        if key in seen:
            continue
        seen.add(key)
        conditions.append(
            SqlSourceConditionMeta(
                id=key,
                fieldName=field_name,
                sourceTable=source_table,
                paramName=param_name,
            )
        )
    return conditions


def _field_name_from_expression(expression: exp.Expression, index: int) -> str:
    if isinstance(expression, exp.Column):
        return expression.name
    if isinstance(expression, exp.Star):
        return "*"
    column = expression.find(exp.Column)
    if column is not None:
        return column.name
    return f"field_{index + 1}"


def _source_table_from_expression(expression: exp.Expression, tables: list[SqlSourceTableMeta]) -> str:
    column = expression if isinstance(expression, exp.Column) else expression.find(exp.Column)
    if column is None:
        return tables[0].tableName if len(tables) == 1 else ""
    return _resolve_table_name(column.table, tables)


def _resolve_table_name(qualifier: str, tables: list[SqlSourceTableMeta]) -> str:
    if qualifier:
        for table in tables:
            if table.alias == qualifier or table.tableName == qualifier:
                return table.tableName
        return qualifier
    return tables[0].tableName if len(tables) == 1 else ""


def _param_name_for_predicate(
    predicate: exp.Expression,
    fallback: str,
    placeholder_order: list[str],
    placeholder_index: int,
) -> str:
    for placeholder in predicate.find_all(exp.Placeholder):
        name = placeholder.name
        if name and name != "?":
            return name
        if placeholder_index < len(placeholder_order):
            return placeholder_order[placeholder_index]
    return fallback


def _predicate_has_placeholder(predicate: exp.Expression) -> bool:
    return any(True for _ in predicate.find_all(exp.Placeholder))


def parse_parameters(
    sql: str,
    conditions: list[SqlSourceConditionMeta],
    template_parameters: set[str],
) -> list[SqlSourceParameter]:
    names = set(template_parameters)
    for condition in conditions:
        if condition.paramName:
            names.add(condition.paramName)
    return [
        SqlSourceParameter(
            name=name,
            type=InputFieldType.STRING,
            required=True,
            defaultValue=None,
            description=None,
        )
        for name in sorted(names)
    ]


def merge_parameters(
    parsed: list[SqlSourceParameter],
    current: list[SqlSourceParameter],
) -> list[SqlSourceParameter]:
    current_by_name = {param.name: param for param in current}
    merged: list[SqlSourceParameter] = []
    for param in parsed:
        existing = current_by_name.get(param.name)
        if existing:
            merged.append(
                SqlSourceParameter(
                    name=param.name,
                    type=existing.type or param.type,
                    required=existing.required,
                    defaultValue=existing.defaultValue if existing.defaultValue is not None else param.defaultValue,
                    description=existing.description,
                )
            )
        else:
            merged.append(param)
    return merged
