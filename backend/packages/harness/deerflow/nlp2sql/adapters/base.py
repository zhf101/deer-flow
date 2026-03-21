from __future__ import annotations

from typing import Any, Protocol


class DbAdapter(Protocol):
    dialect: str

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def execute_query(
        self,
        sql: str,
        params: list[Any] | None = None,
        max_rows: int | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]: ...

    def explain_query(self, sql: str, params: list[Any] | None = None) -> dict[str, Any]: ...

    def get_schema(
        self,
        schema_whitelist: list[str] | None = None,
        table_whitelist: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def get_table_info(self, table_name: str, schema: str | None = None) -> dict[str, Any] | None: ...

    def get_enum_values(
        self,
        table_name: str,
        column_name: str,
        schema: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]: ...

    def get_sample_rows(
        self,
        table_name: str,
        schema: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]: ...
