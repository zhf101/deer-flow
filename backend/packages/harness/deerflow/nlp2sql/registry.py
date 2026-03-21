from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from deerflow.config.paths import get_paths
from deerflow.nlp2sql.errors import DataSourceAlreadyExistsError, DataSourceNotFoundError
from deerflow.nlp2sql.types import DataSourceConfig


def _data_sources_file() -> Path:
    return get_paths().base_dir / "data_sources.json"


class DataSourceRegistry:
    """Filesystem-backed registry for configured database data sources."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._storage_path = storage_path or _data_sources_file()
        self._lock = threading.Lock()
        self._cached_mtime_ns: int | None = None
        self._cached_configs: dict[str, DataSourceConfig] = {}

    def _load_locked(self) -> dict[str, DataSourceConfig]:
        if not self._storage_path.exists():
            self._cached_mtime_ns = None
            self._cached_configs = {}
            return {}

        mtime_ns = self._storage_path.stat().st_mtime_ns
        if self._cached_mtime_ns == mtime_ns:
            return dict(self._cached_configs)

        data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        items = data.get("data_sources", []) if isinstance(data, dict) else data
        configs = {}
        for item in items:
            config = DataSourceConfig.model_validate(item)
            configs[config.id] = config

        self._cached_mtime_ns = mtime_ns
        self._cached_configs = configs
        return dict(configs)

    def _write_locked(self, configs: dict[str, DataSourceConfig]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "data_sources": [
                configs[key].model_dump(mode="json")
                for key in sorted(configs)
            ]
        }
        fd, tmp_name = tempfile.mkstemp(prefix="data_sources.", suffix=".json.tmp", dir=self._storage_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(payload, tmp_file, indent=2, ensure_ascii=False)
            os.replace(tmp_name, self._storage_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        self._cached_mtime_ns = None
        self._cached_configs = {}

    def list(self, *, enabled_only: bool = True) -> list[DataSourceConfig]:
        with self._lock:
            configs = self._load_locked()
        values = list(configs.values())
        if enabled_only:
            values = [config for config in values if config.enabled]
        return sorted(values, key=lambda config: config.name.lower())

    def get(self, data_source_id: str) -> DataSourceConfig:
        with self._lock:
            configs = self._load_locked()
        config = configs.get(data_source_id)
        if config is None:
            raise DataSourceNotFoundError(f"Data source '{data_source_id}' not found")
        return config

    def upsert(self, config: DataSourceConfig) -> DataSourceConfig:
        with self._lock:
            configs = self._load_locked()
            configs[config.id] = config
            self._write_locked(configs)
        return config

    def create(self, config: DataSourceConfig) -> DataSourceConfig:
        with self._lock:
            configs = self._load_locked()
            if config.id in configs:
                raise DataSourceAlreadyExistsError(f"Data source '{config.id}' already exists")
            configs[config.id] = config
            self._write_locked(configs)
        return config

    def delete(self, data_source_id: str) -> None:
        with self._lock:
            configs = self._load_locked()
            if data_source_id not in configs:
                raise DataSourceNotFoundError(f"Data source '{data_source_id}' not found")
            del configs[data_source_id]
            self._write_locked(configs)

    def test_connection(self, data_source_id: str) -> dict:
        from deerflow.nlp2sql.adapters.factory import create_adapter

        config = self.get(data_source_id)
        adapter = create_adapter(config)
        try:
            adapter.connect()
            return {
                "ok": True,
                "data_source_id": config.id,
                "message": f"Connected successfully to {config.name}",
            }
        finally:
            try:
                adapter.disconnect()
            except Exception:
                pass


_registry: DataSourceRegistry | None = None


def get_data_source_registry() -> DataSourceRegistry:
    global _registry
    if _registry is None:
        _registry = DataSourceRegistry()
    return _registry


def _reset_data_source_registry() -> None:
    global _registry
    _registry = None
