"""Import generated GDP datagen mock SQL config into the local app database."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.gdp.datagen.config.base.models import DatasourceConfig, EnvironmentConfig, SysConfig
from app.gdp.datagen.config.base.repository import BaseConfigRepository
from app.gdp.datagen.config.base.service import BaseConfigService
from app.gdp.datagen.config.sqlsource.models import SqlSourceConfig
from app.gdp.datagen.config.sqlsource.repository import SqlSourceRepository
from app.gdp.datagen.config.sqlsource.service import SqlSourceService
from deerflow.config import get_app_config
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / ".deer-flow/datagen/mock/gdp_mock_sql_config.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to gdp_mock_sql_config.json.",
    )
    args = parser.parse_args()
    asyncio.run(import_config(args.config.resolve()))


async def import_config(config_path: Path) -> None:
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    app_config = get_app_config()
    await init_engine_from_config(app_config.database)
    try:
        session_factory = get_session_factory()
        if session_factory is None:
            raise RuntimeError("database backend is memory; cannot import persistent datagen config")

        base_repo = BaseConfigRepository(session_factory)
        base_service = BaseConfigService(base_repo)
        sql_service = SqlSourceService(
            SqlSourceRepository(session_factory),
            base_repo,
        )

        for item in payload.get("systems", []):
            await base_service.upsert_system(SysConfig.model_validate(item), operator="datagen-mock-import")

        for item in payload.get("environments", []):
            await base_service.upsert_environment(EnvironmentConfig.model_validate(item), operator="datagen-mock-import")

        for item in payload.get("datasources", []):
            await upsert_datasource(base_service, item)

        for item in payload.get("sqlSources", []):
            await sql_service.upsert_sql_source(SqlSourceConfig.model_validate(item), operator="datagen-mock-import")

        print(f"Imported systems: {len(payload.get('systems', []))}")
        print(f"Imported environments: {len(payload.get('environments', []))}")
        print(f"Imported datasources: {len(payload.get('datasources', []))}")
        print(f"Imported sqlSources: {len(payload.get('sqlSources', []))}")
    finally:
        await close_engine()


async def upsert_datasource(base_service: BaseConfigService, raw: dict[str, Any]) -> None:
    config = DatasourceConfig.model_validate(raw)
    existing = await base_service.list_datasources(
        env_code=config.envCode,
        sys_code=config.sysCode,
    )
    match = next((item for item in existing if item.datasourceCode == config.datasourceCode), None)
    if match is None:
        await base_service.create_datasource(config, operator="datagen-mock-import")
    else:
        await base_service.update_datasource(match.id, config, operator="datagen-mock-import")


if __name__ == "__main__":
    main()
