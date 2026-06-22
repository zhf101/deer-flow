# -*- coding: utf-8 -*-
"""一键运行订单三步流验证场景。

运行方式:
    PYTHONPATH=. .venv/Scripts/python.exe scripts/run_order_flow_scene.py
"""

import httpx
import json

url = "http://127.0.0.1:8001/api/v1/datagen/scenes/run"
payload = {
    "sceneCode": "create_pay_query_order_flow",
    "envCode": "dev",
    "inputs": {
        "buyer_id": "U10001",
        "amount": 100.0,
        "payment_method": "ALIPAY"
    }
}

try:
    print(f"发送请求到 {url}...")
    resp = httpx.post(url, json=payload, timeout=30.0)
    print(f"响应状态码: {resp.status_code}")
    print("响应 JSON:")
    print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
except Exception as e:
    print(f"发生错误: {e}")
