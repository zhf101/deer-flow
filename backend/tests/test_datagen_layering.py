"""造数后端分层和依赖边界测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.gdp.datagen.config.base.models import (
    DatasourceConfig,
    EnvironmentConfig,
    ServiceEndpointConfig,
    SysConfig,
)
from app.gdp.datagen.config.base.repository import (
    BaseConfigRepository,
    DataFactoryConfigAuditRow,
    DataFactoryDatasourceRow,
    DataFactoryEnvironmentRow,
    DataFactoryIdentifierReferenceRow,
    DataFactoryServiceEndpointRow,
    DataFactorySystemRow,
)
from app.gdp.datagen.config.base.service import BaseConfigService
from app.gdp.datagen.config.common import models as common_models
from app.gdp.datagen.config.common.models import ConfigStatus, HttpMethod, SqlOperation
from app.gdp.datagen.config.httpsource.models import HttpSourceConfig, HttpSourceTestRequest
from app.gdp.datagen.config.httpsource.repository import DataFactoryHttpSourceRow, HttpSourceRepository
from app.gdp.datagen.config.httpsource.service import HttpSourceService
from app.gdp.datagen.config.scene.repository import (
    DataFactorySceneRow,
    DataFactorySceneRunRow,
    DataFactorySceneRunStepRow,
    DataFactorySceneStepAssertConfigRow,
    DataFactorySceneStepHttpConfigRow,
    DataFactorySceneStepRow,
    DataFactorySceneStepSqlConfigRow,
    DataFactorySceneStepTransformConfigRow,
    DataFactorySceneVersionRow,
    SceneRepository,
)
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.config.sqlsource.repository import DataFactorySqlSourceRow, SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from deerflow.persistence import models as grouped_persistence_models
from deerflow.persistence.base import Base
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine

DATAGEN_CONFIG_ROOT = Path(__file__).resolve().parents[1] / "app" / "gdp" / "datagen" / "config"
DATAGEN_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / "app" / "gdp" / "datagen" / "runtime"

FORBIDDEN_LAYER_IMPORTS = {
    "common": {"base", "httpsource", "sqlsource", "scene", "task"},
    "base": {"httpsource", "sqlsource", "scene", "task"},
    "httpsource": {"sqlsource", "scene", "task"},
    "sqlsource": {"httpsource", "scene", "task"},
    "scene": {"task"},
    "task": set(),
}

CURRENT_ROW_CLASSES = {
    "DataFactoryConfigAuditRow": DataFactoryConfigAuditRow,
    "DataFactoryDatasourceRow": DataFactoryDatasourceRow,
    "DataFactoryEnvironmentRow": DataFactoryEnvironmentRow,
    "DataFactoryHttpSourceRow": DataFactoryHttpSourceRow,
    "DataFactoryIdentifierReferenceRow": DataFactoryIdentifierReferenceRow,
    "DataFactorySceneRow": DataFactorySceneRow,
    "DataFactorySceneRunRow": DataFactorySceneRunRow,
    "DataFactorySceneRunStepRow": DataFactorySceneRunStepRow,
    "DataFactorySceneStepAssertConfigRow": DataFactorySceneStepAssertConfigRow,
    "DataFactorySceneStepHttpConfigRow": DataFactorySceneStepHttpConfigRow,
    "DataFactorySceneStepRow": DataFactorySceneStepRow,
    "DataFactorySceneStepSqlConfigRow": DataFactorySceneStepSqlConfigRow,
    "DataFactorySceneStepTransformConfigRow": DataFactorySceneStepTransformConfigRow,
    "DataFactorySceneVersionRow": DataFactorySceneVersionRow,
    "DataFactoryServiceEndpointRow": DataFactoryServiceEndpointRow,
    "DataFactorySqlSourceRow": DataFactorySqlSourceRow,
    "DataFactorySystemRow": DataFactorySystemRow,
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
        yield {
            "base": BaseConfigService(base_repo),
            "base_repo": base_repo,
            "http": HttpSourceService(http_repo, base_repo),
            "sql": SqlSourceService(sql_repo, base_repo),
            "scene_repo": scene_repo,
        }
    finally:
        await close_engine()


def test_datagen_config_modules_do_not_import_removed_legacy_modules():
    forbidden_imports = {
        "app.gdp.models",
        "app.gdp.persistence.model",
        "app.gdp.persistence.models",
        "app.gdp.datagen.baseconfig",
        "app.gdp.datagen.httpsource",
        "app.gdp.datagen.scene",
        "app.gdp.datagen.sqlsource",
        "app.gdp.datagen.task",
    }
    offenders = []
    for path in DATAGEN_CONFIG_ROOT.rglob("*.py"):
        imported_modules = _imported_modules(path)
        legacy_imports = sorted(imported_modules & forbidden_imports)
        if legacy_imports:
            offenders.append(f"{path.relative_to(DATAGEN_CONFIG_ROOT)} imports {', '.join(legacy_imports)}")

    assert offenders == []


def test_common_models_are_current_datagen_contract_source():
    assert common_models.ConfigStatus is ConfigStatus
    assert common_models.HttpMethod is HttpMethod
    assert common_models.SqlOperation is SqlOperation


def test_grouped_persistence_models_reexport_current_datagen_rows():
    for row_name, row_class in CURRENT_ROW_CLASSES.items():
        assert getattr(grouped_persistence_models, row_name) is row_class


def test_grouped_persistence_models_register_datagen_tables():
    table_names = {
        "df_config_audit",
        "df_datasource",
        "df_environment",
        "df_http_source",
        "df_identifier_reference",
        "df_scene",
        "df_scene_run",
        "df_scene_run_step",
        "df_scene_step",
        "df_scene_step_assert_config",
        "df_scene_step_http_config",
        "df_scene_step_sql_config",
        "df_scene_step_transform_config",
        "df_scene_version",
        "df_service_endpoint",
        "df_sql_source",
        "df_system",
    }

    assert table_names.issubset(Base.metadata.tables)


def test_datagen_config_layers_do_not_reference_upper_layers():
    violations = []

    for path in DATAGEN_CONFIG_ROOT.rglob("*.py"):
        relative = path.relative_to(DATAGEN_CONFIG_ROOT)
        if path.name == "__init__.py":
            continue
        layer = relative.parts[0]
        forbidden_layers = FORBIDDEN_LAYER_IMPORTS.get(layer)
        if forbidden_layers is None:
            continue

        for imported_module in _imported_modules(path):
            imported_layer = _datagen_config_layer(imported_module)
            if imported_layer in forbidden_layers:
                violations.append(
                    f"{relative}: {layer} imports upper layer {imported_layer} via {imported_module}"
                )

    assert violations == []


def test_datagen_sqlsource_uses_source_naming_not_template_naming():
    offenders = []
    sqlsource_root = DATAGEN_CONFIG_ROOT / "sqlsource"
    for path in sqlsource_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and "SqlTemplate" in node.id:
                offenders.append(f"{path.relative_to(DATAGEN_CONFIG_ROOT)}: {node.id}")
            elif isinstance(node, ast.alias) and "SqlTemplate" in node.name:
                offenders.append(f"{path.relative_to(DATAGEN_CONFIG_ROOT)}: {node.name}")

    assert offenders == []


def test_datagen_runtime_does_not_import_config_services_or_apis():
    violations = []
    forbidden_suffixes = (".api", ".service")

    for path in DATAGEN_RUNTIME_ROOT.rglob("*.py"):
        for imported_module in _imported_modules(path):
            if imported_module.startswith("app.gdp.datagen.config.") and imported_module.endswith(forbidden_suffixes):
                violations.append(f"{path.relative_to(DATAGEN_RUNTIME_ROOT)} imports {imported_module}")

    assert violations == []


@pytest.mark.anyio
async def test_http_source_requires_enabled_system(datagen_services):
    http = datagen_services["http"]

    with pytest.raises(HTTPException) as exc:
        await http.upsert_http_source(_http_source("order"))

    assert exc.value.status_code == 422
    assert "enabled system" in str(exc.value.detail)


@pytest.mark.anyio
async def test_http_source_accepts_enabled_system(datagen_services):
    base = datagen_services["base"]
    http = datagen_services["http"]

    await _create_system(base, "order")

    saved = await http.upsert_http_source(_http_source("order"))

    assert saved.sysCode == "order"


@pytest.mark.anyio
async def test_http_source_test_requires_enabled_service_endpoint(datagen_services):
    base = datagen_services["base"]
    http = datagen_services["http"]

    await _create_system(base, "order")

    with pytest.raises(HTTPException) as exc:
        await http.test_http_source(HttpSourceTestRequest(envCode="DEV", config=_http_source("order")))

    assert exc.value.status_code == 422
    assert "服务端点" in str(exc.value.detail)


@pytest.mark.anyio
async def test_sql_source_requires_enabled_system(datagen_services):
    sql = datagen_services["sql"]

    with pytest.raises(HTTPException) as exc:
        await sql.upsert_sql_source(_sql_source("trade", "tradeDb"))

    assert exc.value.status_code == 422
    assert "enabled system" in str(exc.value.detail)


@pytest.mark.anyio
async def test_sql_source_requires_enabled_datasource(datagen_services):
    base = datagen_services["base"]
    sql = datagen_services["sql"]

    await _create_env(base)
    await _create_system(base, "trade")

    with pytest.raises(HTTPException) as exc:
        await sql.upsert_sql_source(_sql_source("trade", "tradeDb"))

    assert exc.value.status_code == 422
    assert "enabled datasource" in str(exc.value.detail)


@pytest.mark.anyio
async def test_sql_source_accepts_enabled_datasource(datagen_services):
    base = datagen_services["base"]
    sql = datagen_services["sql"]

    await _create_env(base)
    await _create_system(base, "trade")
    await base.create_datasource(_datasource("trade", "tradeDb", status=ConfigStatus.ENABLED))

    saved = await sql.upsert_sql_source(_sql_source("trade", "tradeDb"))

    assert saved.sysCode == "trade"
    assert saved.datasourceCode == "tradeDb"


@pytest.mark.anyio
async def test_base_config_resolves_endpoint_and_datasource(datagen_services):
    base = datagen_services["base"]
    base_repo = datagen_services["base_repo"]

    await _create_env(base)
    await _create_system(base, "trade")
    await base.create_service_endpoint(_endpoint("trade", base_url="https://sit.example.test"))
    await base.create_datasource(_datasource("trade", "tradeDb", database_name="sit_trade"))

    endpoint = await base_repo.get_enabled_service_endpoint(env_code="DEV", sys_code="trade")
    datasource = await base_repo.get_enabled_datasource(env_code="DEV", sys_code="trade", datasource_code="tradeDb")

    assert endpoint.baseUrl == "https://sit.example.test"
    assert datasource.databaseName == "sit_trade"


async def _create_env(base: BaseConfigService) -> None:
    await base.upsert_environment(
        EnvironmentConfig(envCode="DEV", envName="Development", status=ConfigStatus.ENABLED)
    )


async def _create_system(base: BaseConfigService, sys_code: str) -> None:
    await base.upsert_system(
        SysConfig(sysCode=sys_code, sysName=f"{sys_code} system", status=ConfigStatus.ENABLED)
    )


def _endpoint(
    sys_code: str,
    *,
    status: ConfigStatus = ConfigStatus.ENABLED,
    env_code: str = "DEV",
    base_url: str = "https://example.test",
) -> ServiceEndpointConfig:
    return ServiceEndpointConfig(
        envCode=env_code,
        sysCode=sys_code,
        baseUrl=base_url,
        status=status,
    )


def _datasource(
    sys_code: str,
    datasource_code: str,
    *,
    status: ConfigStatus = ConfigStatus.ENABLED,
    env_code: str = "DEV",
    database_name: str = "test_db",
) -> DatasourceConfig:
    return DatasourceConfig(
        envCode=env_code,
        sysCode=sys_code,
        datasourceCode=datasource_code,
        datasourceName=f"{datasource_code} datasource",
        dbType="MySQL",
        host="127.0.0.1",
        port=3306,
        databaseName=database_name,
        status=status,
    )


def _http_source(sys_code: str) -> HttpSourceConfig:
    return HttpSourceConfig(
        sourceCode="createUserApi",
        sourceName="Create user API",
        sysCode=sys_code,
        path="/users",
        method=HttpMethod.POST,
        requestMapping={},
        outputMapping={},
        status=ConfigStatus.ENABLED,
    )


def _sql_source(sys_code: str, datasource_code: str) -> SqlSourceConfig:
    return SqlSourceConfig(
        sourceCode="queryUserSql",
        sourceName="Query user SQL",
        sysCode=sys_code,
        datasourceCode=datasource_code,
        operation=SqlOperation.SELECT,
        sqlText="select * from users where id = :userId",
        parameters=[],
        status=ConfigStatus.ENABLED,
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


def _datagen_config_layer(module_name: str) -> str | None:
    prefix = "app.gdp.datagen.config."
    if not module_name.startswith(prefix):
        return None
    return module_name.removeprefix(prefix).split(".", 1)[0]
