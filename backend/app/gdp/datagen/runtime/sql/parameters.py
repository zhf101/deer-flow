"""SQL 运行时参数校验和绑定辅助函数。"""

from __future__ import annotations

from typing import Any

from app.gdp.datagen.config.common.models import InputFieldType
from app.gdp.datagen.config.sqlsource.models import SqlSourceParameter
from app.gdp.datagen.config.sqlsource.parsers.common import ordered_parameter_names
from app.gdp.datagen.runtime.sql.errors import SqlParameterError


def bind_source_parameters(
    *,
    sql_text: str,
    definitions: list[SqlSourceParameter],
    values: dict[str, Any],
) -> dict[str, Any]:
    """校验并转换已保存 SQL 配置的参数值。"""

    definitions_by_name = {item.name: item for item in definitions}
    referenced_names = ordered_parameter_names(sql_text)
    if not referenced_names:
        referenced_names = [item.name for item in definitions]

    bound: dict[str, Any] = {}
    for name in referenced_names:
        definition = definitions_by_name.get(name)
        if name in values:
            raw_value = values[name]
        elif definition is not None and definition.defaultValue is not None:
            raw_value = definition.defaultValue
        elif definition is not None and definition.required:
            raise SqlParameterError(f"missing required SQL parameter: {name}")
        else:
            raw_value = None
        bound[name] = coerce_parameter_value(raw_value, definition)
    return bound


def bind_direct_parameters(sql_text: str, values: dict[str, Any]) -> dict[str, Any]:
    """校验直接执行请求的参数覆盖情况。"""

    names = ordered_parameter_names(sql_text)
    missing = [name for name in names if name not in values]
    if missing:
        raise SqlParameterError(f"missing required SQL parameter: {', '.join(missing)}")
    return {name: values[name] for name in names}


def coerce_parameter_value(value: Any, definition: SqlSourceParameter | None) -> Any:
    """根据 SQL 参数类型做轻量值转换。"""

    if value is None or definition is None:
        return value

    field_type = str(definition.type.value if isinstance(definition.type, InputFieldType) else definition.type)
    if field_type == InputFieldType.NUMBER.value:
        if isinstance(value, int | float):
            return value
        text = str(value).strip()
        if text == "":
            if definition.required:
                raise SqlParameterError(f"empty numeric SQL parameter: {definition.name}")
            return None
        try:
            return int(text) if "." not in text else float(text)
        except ValueError as exc:
            raise SqlParameterError(f"invalid numeric SQL parameter: {definition.name}") from exc
    if field_type == InputFieldType.BOOLEAN.value:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n"}:
            return False
        raise SqlParameterError(f"invalid boolean SQL parameter: {definition.name}")
    return value
