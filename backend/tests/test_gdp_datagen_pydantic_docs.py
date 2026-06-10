"""GDP Datagen Pydantic 文档契约测试。"""

from __future__ import annotations

from pydantic import BaseModel

from app.gdp.agent import api as agent_api
from app.gdp.datagen.config.base import api as base_api
from app.gdp.datagen.config.scene import api as scene_api
from app.gdp.datagen.config.scene import models as scene_models
from app.gdp.datagen.runtime.sql import models as sql_models

MODEL_MODULES = (agent_api, base_api, scene_api, scene_models, sql_models)


def test_selected_datagen_pydantic_models_have_docstrings_and_field_descriptions():
    """Datagen OpenAPI 模型必须让类用途和字段含义能直接显示在文档里。"""

    violations: list[str] = []
    for model in _iter_module_models():
        if not (model.__doc__ and model.__doc__.strip()):
            violations.append(f"{model.__module__}.{model.__name__} 缺少类 docstring")
        for field_name, field_info in model.model_fields.items():
            if field_name == "model_config":
                continue
            description = field_info.description
            if not description or not description.strip():
                violations.append(f"{model.__module__}.{model.__name__}.{field_name} 缺少 Field(description=...)")

    assert violations == []


def _iter_module_models() -> list[type[BaseModel]]:
    models: list[type[BaseModel]] = []
    seen: set[type[BaseModel]] = set()
    for module in MODEL_MODULES:
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value is not BaseModel
                and value.__module__ == module.__name__
                and value not in seen
            ):
                seen.add(value)
                models.append(value)
    return models
