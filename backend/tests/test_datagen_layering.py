"""Datagen backend layering and dependency-chain tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

import app.gdp.models as legacy_models
import app.gdp.persistence.model as legacy_persistence_models
from app.gdp.datagen.common import models as common_models
from app.gdp.datagen.baseconfig.models import (
    DatasourceConfig,
    EnvironmentConfig,
    ServiceEndpointConfig,
)
from app.gdp.datagen.baseconfig.repository import BaseConfigRepository
from app.gdp.datagen.baseconfig.service import BaseConfigService
from app.gdp.datagen.httpsource.models import HttpSourceConfig
from app.gdp.datagen.httpsource.repository import HttpSourceRepository
from app.gdp.datagen.httpsource.service import HttpSourceService
from app.gdp.datagen.runtime.resources import DatagenRuntimeResourceLoader
from app.gdp.datagen.scene.models import BatchConfig, SceneDefinition
from app.gdp.datagen.scene.repository import SceneRepository
from app.gdp.datagen.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.sqlsource.service import SqlSourceService
from app.gdp.datagen.task.models import TaskDefinition, TaskStepDefinition
from app.gdp.datagen.task.repository import TaskRepository
from app.gdp.datagen.task.service import TaskService
from app.gdp.datagen.common.models import (
    ConfigStatus,
    HttpMethod,
    InputFieldDefinition,
    InputFieldType,
    SceneStatus,
    SqlOperation,
)
from app.gdp.persistence import models as grouped_persistence_models
from deerflow.persistence.base import Base
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine


DATAGEN_ROOT = Path(__file__).resolve().parents[1] / "app" / "gdp" / "datagen"

FORBIDDEN_LAYER_IMPORTS = {
    "common": {"base", "httpsource", "sqlsource", "scene", "task"},
    "base": {"httpsource", "sqlsource", "scene", "task"},
    "httpsource": {"sqlsource", "scene", "task"},
    "sqlsource": {"httpsource", "scene", "task"},
    "scene": {"task"},
    "task": set(),
}


@pytest.fixture
async def datagen_services(tmp_path):
    db_path = tmp_path / "datagen.db"
    await init_engine("sqlite", url=f"sqlite+aiosqlite:///{db_path}", sqlite_dir=str(tmp_path))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        base_repo = BaseConfigRepository(session_factory)
        http_repo = HttpSourceRepository(session_factory)
        sql_repo = SqlSourceRepository(session_factory)
        scene_repo = SceneRepository(session_factory)
        task_repo = TaskRepository(session_factory)
        yield {
            "base": BaseConfigService(base_repo),
            "http": HttpSourceService(http_repo, base_repo),
            "sql": SqlSourceService(sql_repo, base_repo),
            "scene_repo": scene_repo,
            "task": TaskService(task_repo, scene_repo),
            "runtime_loader": DatagenRuntimeResourceLoader(session_factory),
        }
    finally:
        await close_engine()


def test_datagen_modules_import_common_models_directly():
    offenders = []
    for path in DATAGEN_ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        imported_modules = _imported_modules(path)
        if "app.gdp.models" in imported_modules:
            offenders.append(str(path.relative_to(DATAGEN_ROOT)))

    assert offenders == []


def test_legacy_models_reexport_common_datagen_models():
    assert legacy_models.ConfigStatus is common_models.ConfigStatus
    assert legacy_models.SceneStatus is common_models.SceneStatus
    assert legacy_models.InputFieldDefinition is common_models.InputFieldDefinition
    assert legacy_models.HttpMethod is common_models.HttpMethod
    assert legacy_models.SqlOperation is common_models.SqlOperation


def test_legacy_persistence_model_reexports_grouped_rows():
    row_names = [
        "DataFactoryConfigAuditRow",
        "DataFactoryDatasourceRow",
        "DataFactoryEnvironmentRow",
        "DataFactoryHttpSourceRow",
        "DataFactorySceneRow",
        "DataFactorySceneVersionRow",
        "DataFactoryServiceEndpointRow",
        "DataFactorySqlSourceRow",
        "DataFactorySqlTemplateRow",
        "DataFactoryTaskRow",
        "DataFactoryTaskVersionRow",
    ]
    for row_name in row_names:
        assert getattr(legacy_persistence_models, row_name) is getattr(grouped_persistence_models, row_name)


def test_grouped_persistence_models_register_datagen_tables():
    table_names = {
        "df_config_audit",
        "df_datasource",
        "df_environment",
        "df_http_source",
        "df_scene",
        "df_scene_version",
        "df_service_endpoint",
        "df_sql_template",
        "df_task",
        "df_task_version",
    }

    assert table_names.issubset(Base.metadata.tables)


def test_datagen_feature_imports_do_not_reference_upper_layers():
    violations = []

    for path in DATAGEN_ROOT.rglob("*.py"):
        relative = path.relative_to(DATAGEN_ROOT)
        if relative.parts[0] == "dependencies.py":
            continue
        layer = relative.parts[0]
        forbidden_layers = FORBIDDEN_LAYER_IMPORTS.get(layer)
        if forbidden_layers is None:
            continue

        for imported_module in _imported_modules(path):
            imported_layer = _datagen_layer(imported_module)
            if imported_layer in forbidden_layers:
                violations.append(
                    f"{relative}: {layer} imports upper layer {imported_layer} via {imported_module}"
                )

    assert violations == []


def test_datagen_sqlsource_uses_source_naming_not_template_naming():
    offenders = []
    sqlsource_root = DATAGEN_ROOT / "sqlsource"
    for path in sqlsource_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and "SqlTemplate" in node.id:
                offenders.append(f"{path.relative_to(DATAGEN_ROOT)}: {node.id}")
            elif isinstance(node, ast.alias) and "SqlTemplate" in node.name:
                offenders.append(f"{path.relative_to(DATAGEN_ROOT)}: {node.name}")

    assert offenders == []


def test_datagen_runtime_does_not_import_feature_services_or_apis():
    violations = []
    runtime_root = DATAGEN_ROOT / "runtime"
    forbidden_suffixes = (".api", ".service")

    for path in runtime_root.rglob("*.py"):
        for imported_module in _imported_modules(path):
            if imported_module.startswith("app.gdp.datagen.") and imported_module.endswith(forbidden_suffixes):
                violations.append(f"{path.relative_to(DATAGEN_ROOT)} imports {imported_module}")

    assert violations == []


@pytest.mark.anyio
async def test_http_source_requires_enabled_service_endpoint(datagen_services):
    http = datagen_services["http"]

    with pytest.raises(HTTPException) as exc:
        await http.upsert_http_source(_http_source("order"))

    assert exc.value.status_code == 422
    assert "enabled service endpoint" in str(exc.value.detail)


@pytest.mark.anyio
async def test_http_source_accepts_enabled_service_endpoint(datagen_services):
    base = datagen_services["base"]
    http = datagen_services["http"]

    await _create_env(base)
    await base.create_service_endpoint(_endpoint("order", status=ConfigStatus.ENABLED))

    saved = await http.upsert_http_source(_http_source("order"))

    assert saved.serviceCode == "order"


@pytest.mark.anyio
async def test_sql_source_requires_enabled_datasource(datagen_services):
    sql = datagen_services["sql"]

    with pytest.raises(HTTPException) as exc:
        await sql.upsert_sql_source(_sql_source("tradeDb"))

    assert exc.value.status_code == 422
    assert "enabled datasource" in str(exc.value.detail)


@pytest.mark.anyio
async def test_sql_source_accepts_enabled_datasource(datagen_services):
    base = datagen_services["base"]
    sql = datagen_services["sql"]

    await _create_env(base)
    await base.create_datasource(_datasource("tradeDb", status=ConfigStatus.ENABLED))

    saved = await sql.upsert_sql_source(_sql_source("tradeDb"))

    assert saved.datasourceCode == "tradeDb"


@pytest.mark.anyio
async def test_task_publish_requires_published_scene(datagen_services):
    scene_repo = datagen_services["scene_repo"]
    task = datagen_services["task"]

    await scene_repo.create_scene(_scene("createUser"))
    await task.create_task(_task("seedUsers", "createUser"))

    with pytest.raises(HTTPException) as exc:
        await task.publish_task("seedUsers")

    assert exc.value.status_code == 422
    assert "scene must be published" in str(exc.value.detail)


@pytest.mark.anyio
async def test_runtime_resource_loader_resolves_base_config_by_env(datagen_services):
    base = datagen_services["base"]
    http = datagen_services["http"]
    sql = datagen_services["sql"]
    loader = datagen_services["runtime_loader"]

    await base.upsert_environment(EnvironmentConfig(envCode="DEV", envName="Development"))
    await base.upsert_environment(EnvironmentConfig(envCode="SIT", envName="System Integration"))
    await base.create_service_endpoint(_endpoint("order", env_code="DEV", base_url="https://dev.example.test"))
    await base.create_service_endpoint(_endpoint("order", env_code="SIT", base_url="https://sit.example.test"))
    await base.create_datasource(_datasource("tradeDb", env_code="DEV", database_name="dev_trade"))
    await base.create_datasource(_datasource("tradeDb", env_code="SIT", database_name="sit_trade"))
    await http.upsert_http_source(_http_source("order"))
    await sql.upsert_sql_source(_sql_source("tradeDb"))

    resources = await loader.load("SIT")

    assert resources.serviceEndpoints == {"order": "https://sit.example.test"}
    assert resources.datasources["tradeDb"]["databaseName"] == "sit_trade"
    assert resources.datasource_url("tradeDb") == "mysql+aiomysql://127.0.0.1:3306/sit_trade"
    assert resources.httpSources["createUserApi"]["serviceCode"] == "order"
    assert resources.sqlSources["queryUserSql"].datasourceCode == "tradeDb"
    assert resources.sqlSources["queryUserSql"].sqlText == "select * from users where id = :userId"


async def _create_env(base: BaseConfigService) -> None:
    await base.upsert_environment(
        EnvironmentConfig(envCode="DEV", envName="Development", status=ConfigStatus.ENABLED)
    )


def _endpoint(
    service_code: str,
    *,
    status: ConfigStatus = ConfigStatus.ENABLED,
    env_code: str = "DEV",
    base_url: str = "https://example.test",
) -> ServiceEndpointConfig:
    return ServiceEndpointConfig(
        envCode=env_code,
        serviceCode=service_code,
        serviceName=f"{service_code} service",
        baseUrl=base_url,
        status=status,
    )


def _datasource(
    datasource_code: str,
    *,
    status: ConfigStatus = ConfigStatus.ENABLED,
    env_code: str = "DEV",
    database_name: str = "test_db",
) -> DatasourceConfig:
    return DatasourceConfig(
        envCode=env_code,
        datasourceCode=datasource_code,
        datasourceName=f"{datasource_code} datasource",
        dbType="MySQL",
        host="127.0.0.1",
        port=3306,
        databaseName=database_name,
        status=status,
    )


def _http_source(service_code: str) -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode="createUserApi",
        sourceName="Create user API",
        serviceCode=service_code,
        path="/users",
        method=HttpMethod.POST,
        requestMapping={},
        outputMapping={},
        status=ConfigStatus.ENABLED,
    )


def _sql_source(datasource_code: str) -> SqlSourceConfig:
    return SqlSourceConfig(
        sourceCode="queryUserSql",
        sourceName="Query user SQL",
        datasourceCode=datasource_code,
        operation=SqlOperation.SELECT,
        sqlText="select * from users where id = :userId",
        parameters=[],
        status=ConfigStatus.ENABLED,
    )


def _scene(scene_code: str) -> SceneDefinition:
    return SceneDefinition(
        sceneCode=scene_code,
        sceneName="Create user",
        inputSchema=[_env_field()],
        steps=[],
        resultMapping={},
        batchConfig=BatchConfig(),
        status=SceneStatus.DRAFT,
    )


def _task(task_code: str, scene_code: str) -> TaskDefinition:
    return TaskDefinition(
        taskCode=task_code,
        taskName="Seed users",
        inputSchema=[_env_field()],
        steps=[
            TaskStepDefinition(
                stepId="runCreateUser",
                sceneCode=scene_code,
                dependsOn=[],
                inputMapping={},
                outputMapping={},
            )
        ],
        resultMapping={},
        status=SceneStatus.DRAFT,
    )


def _env_field() -> InputFieldDefinition:
    return InputFieldDefinition(
        name="env",
        label="Environment",
        type=InputFieldType.STRING,
        required=True,
        batchEnabled=False,
    )


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _datagen_layer(module_name: str) -> str | None:
    prefix = "app.gdp.datagen."
    if not module_name.startswith(prefix):
        return None
    return module_name.removeprefix(prefix).split(".", 1)[0]
