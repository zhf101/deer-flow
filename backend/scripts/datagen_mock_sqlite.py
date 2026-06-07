"""Generate GDP datagen SQLite mock data and matching SQL source payloads.

The script creates a small business database for exercising the SQL source
configuration page. It also writes JSON payloads that can be posted to the
datagen configuration APIs in dependency order.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / ".deer-flow/datagen/mock"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for mock SQLite DB and JSON payloads.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "gdp_mock_trade.sqlite"
    config_path = output_dir / "gdp_mock_sql_config.json"
    import_script_path = output_dir / "import_gdp_mock_sql_config.ps1"

    create_sqlite_database(db_path)
    config = build_config(db_path)

    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    import_script_path.write_text(build_import_script(config_path), encoding="utf-8")

    print(f"SQLite mock DB: {db_path}")
    print(f"GDP config JSON: {config_path}")
    print(f"Import helper: {import_script_path}")


def create_sqlite_database(db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        create_schema(conn)
        seed_data(conn)
        conn.commit()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE member_account (
          user_id TEXT PRIMARY KEY,
          mobile TEXT NOT NULL,
          member_level TEXT NOT NULL,
          account_status TEXT NOT NULL,
          points INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );

        CREATE TABLE product_sku (
          sku_id TEXT PRIMARY KEY,
          product_name TEXT NOT NULL,
          category TEXT NOT NULL,
          sale_price REAL NOT NULL,
          status TEXT NOT NULL
        );

        CREATE TABLE inventory (
          sku_id TEXT PRIMARY KEY,
          stock_num INTEGER NOT NULL,
          locked_num INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (sku_id) REFERENCES product_sku(sku_id)
        );

        CREATE TABLE trade_order (
          order_no TEXT PRIMARY KEY,
          user_id TEXT NOT NULL,
          sku_id TEXT NOT NULL,
          quantity INTEGER NOT NULL,
          order_amount REAL NOT NULL,
          order_status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          paid_at TEXT,
          FOREIGN KEY (user_id) REFERENCES member_account(user_id),
          FOREIGN KEY (sku_id) REFERENCES product_sku(sku_id)
        );

        CREATE TABLE order_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          order_no TEXT NOT NULL,
          user_id TEXT NOT NULL,
          action_type TEXT NOT NULL,
          remark TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def seed_data(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO member_account
          (user_id, mobile, member_level, account_status, points, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("U10001", "13800000001", "VIP", "ACTIVE", 6200, "2026-01-10 09:10:00"),
            ("U10002", "13800000002", "NORMAL", "ACTIVE", 800, "2026-02-14 10:20:00"),
            ("U10003", "13800000003", "NORMAL", "FROZEN", 120, "2026-03-02 16:45:00"),
            ("U10004", "13800000004", "SVIP", "ACTIVE", 18800, "2026-04-18 08:30:00"),
        ],
    )

    conn.executemany(
        """
        INSERT INTO product_sku
          (sku_id, product_name, category, sale_price, status)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("SKU10001", "机械键盘 K87", "electronics", 299.00, "ON_SALE"),
            ("SKU10002", "无线鼠标 M2", "electronics", 129.00, "ON_SALE"),
            ("SKU10003", "保温杯 500ml", "daily", 59.90, "OFF_SHELF"),
            ("SKU10004", "人体工学椅", "office", 899.00, "ON_SALE"),
        ],
    )

    conn.executemany(
        """
        INSERT INTO inventory
          (sku_id, stock_num, locked_num, status, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("SKU10001", 120, 4, "AVAILABLE", "2026-06-06 09:00:00"),
            ("SKU10002", 35, 2, "AVAILABLE", "2026-06-06 09:10:00"),
            ("SKU10003", 0, 0, "SOLD_OUT", "2026-06-06 09:20:00"),
            ("SKU10004", 8, 1, "LOW_STOCK", "2026-06-06 09:30:00"),
        ],
    )

    conn.executemany(
        """
        INSERT INTO trade_order
          (order_no, user_id, sku_id, quantity, order_amount, order_status, created_at, paid_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("T202606060001", "U10001", "SKU10001", 1, 299.00, "PAID", "2026-06-06 10:00:00", "2026-06-06 10:01:20"),
            ("T202606060002", "U10002", "SKU10002", 2, 258.00, "CREATED", "2026-06-06 10:15:00", None),
            ("T202606060003", "U10004", "SKU10004", 1, 899.00, "PAID", "2026-06-06 10:30:00", "2026-06-06 10:31:10"),
        ],
    )

    conn.executemany(
        """
        INSERT INTO order_log
          (order_no, user_id, action_type, remark, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            ("T202606060001", "U10001", "CREATE_ORDER", "创建订单", "2026-06-06 10:00:00"),
            ("T202606060001", "U10001", "PAY_ORDER", "支付完成", "2026-06-06 10:01:20"),
            ("T202606060002", "U10002", "CREATE_ORDER", "创建订单待支付", "2026-06-06 10:15:00"),
        ],
    )


def build_config(db_path: Path) -> dict[str, Any]:
    database_name = str(db_path).replace("\\", "/")
    return {
        "systems": [
            {
                "sysCode": "mockTrade",
                "sysName": "Mock 交易系统",
                "status": "ENABLED",
                "remark": "本地 SQLite mock 数据源，用于 GDP SQL 配置页面联调。",
            }
        ],
        "environments": [
            {
                "envCode": "dev",
                "envName": "开发环境",
                "status": "ENABLED",
                "remark": "本地开发 mock 环境。",
            },
            {
                "envCode": "test",
                "envName": "测试环境",
                "status": "ENABLED",
                "remark": "复用同一 SQLite 文件，便于验证数据源按环境聚合。",
            },
        ],
        "datasources": [
            build_datasource("dev", database_name),
            build_datasource("test", database_name),
        ],
        "sqlSources": [
            {
                "sourceCode": "mockQueryMemberStatus",
                "sourceName": "Mock 查询会员账户状态",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "SELECT",
                "sqlText": (
                    "SELECT user_id, mobile, member_level, account_status, points "
                    "FROM member_account WHERE user_id = :userId"
                ),
                "parameters": [
                    parameter("userId", "string", True, "U10001", "会员用户 ID"),
                ],
                "safety": {"requireWhere": True, "maxAffectedRows": None},
                "status": "ENABLED",
            },
            {
                "sourceCode": "mockQueryInventoryBySku",
                "sourceName": "Mock 按 SKU 查询库存",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "SELECT",
                "sqlText": (
                    "SELECT p.sku_id, p.product_name, p.sale_price, i.stock_num, "
                    "i.locked_num, i.status FROM product_sku p "
                    "JOIN inventory i ON p.sku_id = i.sku_id "
                    "WHERE p.sku_id = :skuId"
                ),
                "parameters": [
                    parameter("skuId", "string", True, "SKU10001", "商品 SKU 编码"),
                ],
                "safety": {"requireWhere": True, "maxAffectedRows": None},
                "status": "ENABLED",
            },
            {
                "sourceCode": "mockCreateOrder",
                "sourceName": "Mock 创建交易订单",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "INSERT",
                "sqlText": (
                    "INSERT INTO trade_order(order_no, user_id, sku_id, quantity, "
                    "order_amount, order_status, created_at) VALUES "
                    "(:orderNo, :userId, :skuId, :quantity, :orderAmount, 'CREATED', CURRENT_TIMESTAMP)"
                ),
                "parameters": [
                    parameter("orderNo", "string", True, "T202606069999", "订单号"),
                    parameter("userId", "string", True, "U10001", "下单用户 ID"),
                    parameter("skuId", "string", True, "SKU10001", "商品 SKU 编码"),
                    parameter("quantity", "number", True, 1, "购买数量"),
                    parameter("orderAmount", "number", True, 299.0, "订单金额"),
                ],
                "safety": {"requireWhere": False, "maxAffectedRows": 1},
                "status": "ENABLED",
            },
            {
                "sourceCode": "mockLockInventory",
                "sourceName": "Mock 锁定库存",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "UPDATE",
                "sqlText": (
                    "UPDATE inventory SET stock_num = stock_num - :quantity, "
                    "locked_num = locked_num + :quantity, updated_at = CURRENT_TIMESTAMP "
                    "WHERE sku_id = :skuId AND stock_num >= :quantity"
                ),
                "parameters": [
                    parameter("skuId", "string", True, "SKU10001", "商品 SKU 编码"),
                    parameter("quantity", "number", True, 1, "锁定数量"),
                ],
                "safety": {"requireWhere": True, "maxAffectedRows": 1},
                "status": "ENABLED",
            },
            {
                "sourceCode": "mockDeletePendingOrder",
                "sourceName": "Mock 删除未支付订单",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "DELETE",
                "sqlText": "DELETE FROM trade_order WHERE order_no = :orderNo AND order_status = 'CREATED'",
                "parameters": [
                    parameter("orderNo", "string", True, "T202606060002", "待删除订单号"),
                ],
                "safety": {"requireWhere": True, "maxAffectedRows": 1},
                "status": "ENABLED",
            },
            {
                "sourceCode": "mockInsertOrderLog",
                "sourceName": "Mock 写入订单日志",
                "sysCode": "mockTrade",
                "datasourceCode": "mockTradeSqlite",
                "operation": "INSERT",
                "sqlText": (
                    "INSERT INTO order_log(order_no, user_id, action_type, remark, created_at) "
                    "VALUES (:orderNo, :userId, :actionType, :remark, CURRENT_TIMESTAMP)"
                ),
                "parameters": [
                    parameter("orderNo", "string", True, "T202606060001", "订单号"),
                    parameter("userId", "string", True, "U10001", "用户 ID"),
                    parameter("actionType", "string", True, "CREATE_ORDER", "操作类型"),
                    parameter("remark", "string", False, "mock log", "日志备注"),
                ],
                "safety": {"requireWhere": False, "maxAffectedRows": 1},
                "status": "ENABLED",
            },
        ],
    }


def build_datasource(env_code: str, database_name: str) -> dict[str, Any]:
    return {
        "envCode": env_code,
        "sysCode": "mockTrade",
        "datasourceCode": "mockTradeSqlite",
        "datasourceName": "Mock 交易 SQLite",
        "dbType": "SQLite",
        "host": "localhost",
        "port": 1,
        "databaseName": database_name,
        "username": "",
        "password": "",
        "status": "ENABLED",
    }


def parameter(
    name: str,
    type_: str,
    required: bool,
    default_value: Any,
    description: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "type": type_,
        "required": required,
        "defaultValue": default_value,
        "description": description,
    }


def build_import_script(config_path: Path) -> str:
    escaped_path = str(config_path).replace("'", "''")
    return f"""$ErrorActionPreference = "Stop"
$baseUrl = $env:GDP_DATAGEN_BASE_URL
if (-not $baseUrl) {{
  $baseUrl = "http://127.0.0.1:8000/api/v1/datagen"
}}

$config = Get-Content -Raw -Encoding UTF8 '{escaped_path}' | ConvertFrom-Json

foreach ($item in $config.systems) {{
  Invoke-RestMethod -Method Post -Uri "$baseUrl/systems" -ContentType "application/json" -Body ($item | ConvertTo-Json -Depth 20)
}}
foreach ($item in $config.environments) {{
  Invoke-RestMethod -Method Post -Uri "$baseUrl/environments" -ContentType "application/json" -Body ($item | ConvertTo-Json -Depth 20)
}}
foreach ($item in $config.datasources) {{
  Invoke-RestMethod -Method Post -Uri "$baseUrl/datasources" -ContentType "application/json" -Body ($item | ConvertTo-Json -Depth 20)
}}
foreach ($item in $config.sqlSources) {{
  Invoke-RestMethod -Method Post -Uri "$baseUrl/sql-sources" -ContentType "application/json" -Body ($item | ConvertTo-Json -Depth 20)
}}
"""


if __name__ == "__main__":
    main()
