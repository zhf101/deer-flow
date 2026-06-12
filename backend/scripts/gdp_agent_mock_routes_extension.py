"""Mock Server 扩展 - GDP Agent 第二阶段测试接口。

在现有 Mock Server 中添加这些路由定义。
插入位置：在 create_app() 函数中，__mock/routes 之后，404 兜底之前。
"""

# ----------------------------------------------------------
# GDP Agent 测试接口扩展（6个新接口）
# ----------------------------------------------------------

# 1. POST /api/v1/orders/pending - 创建待支付订单
@app.post("/api/v1/orders/pending")
async def create_pending_order(request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", "/api/v1/orders/pending", headers, body)

    buyer_id = (body or {}).get("buyer_id", "UNKNOWN")
    amount = (body or {}).get("amount", 100.00)
    order_id = f"ORD-PENDING-{int(time.time()) % 100000:05d}"

    response = {
        "success": True,
        "data": {
            "order_id": order_id,
            "buyer_id": buyer_id,
            "amount": amount,
            "pay_status": "PENDING",
            "created_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("pending-order")}
    _log_response("POST", "/api/v1/orders/pending", 200, f"创建待支付订单 {order_id}")
    return JSONResponse(response, headers=resp_headers)


# 2. POST /api/v1/orders/with-items - 创建带商品订单
@app.post("/api/v1/orders/with-items")
async def create_order_with_items(request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", "/api/v1/orders/with-items", headers, body)

    buyer_id = (body or {}).get("buyer_id", "UNKNOWN")
    product_id = (body or {}).get("product_id", "P001")
    quantity = (body or {}).get("quantity", 1)
    order_id = f"ORD-ITEMS-{int(time.time()) % 100000:05d}"

    response = {
        "success": True,
        "data": {
            "order_id": order_id,
            "buyer_id": buyer_id,
            "product_id": product_id,
            "quantity": quantity,
            "pay_status": "PENDING",
            "inventory_locked": True,
            "created_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("order-items")}
    _log_response("POST", "/api/v1/orders/with-items", 200, f"创建带商品订单 {order_id}")
    return JSONResponse(response, headers=resp_headers)


# 3. POST /api/v1/payments - 发起支付（有副作用）
@app.post("/api/v1/payments")
async def create_payment(request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", "/api/v1/payments", headers, body)

    order_id = (body or {}).get("order_id", "UNKNOWN")
    payment_method = (body or {}).get("payment_method", "ALIPAY")
    payment_id = f"PAY-{int(time.time()) % 100000:05d}"

    response = {
        "success": True,
        "data": {
            "payment_id": payment_id,
            "order_id": order_id,
            "payment_method": payment_method,
            "status": "SUCCESS",
            "amount_paid": 100.00,
            "paid_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("payment")}
    _log_response("POST", "/api/v1/payments", 200, f"支付成功 {payment_id}")
    return JSONResponse(response, headers=resp_headers)


# 4. GET /api/v1/payments/{order_id}/status - 查询支付状态
@app.get("/api/v1/payments/{order_id}/status")
async def query_payment_status(order_id: str, request: Request):
    headers = _important_headers(request)
    _log_request("GET", f"/api/v1/payments/{order_id}/status", headers)

    response = {
        "success": True,
        "data": {
            "order_id": order_id,
            "pay_status": "PAID",
            "paid_at": "2026-06-12T10:00:00",
            "payment_method": "ALIPAY"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("payment-status")}
    _log_response("GET", f"/api/v1/payments/{order_id}/status", 200, f"查询支付状态 {order_id}")
    return JSONResponse(response, headers=resp_headers)


# 5. POST /api/v1/inventory/lock - 锁定库存（有副作用）
@app.post("/api/v1/inventory/lock")
async def lock_inventory(request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", "/api/v1/inventory/lock", headers, body)

    product_id = (body or {}).get("product_id", "P001")
    quantity = (body or {}).get("quantity", 1)
    lock_id = f"LOCK-{int(time.time()) % 100000:05d}"

    response = {
        "success": True,
        "data": {
            "lock_id": lock_id,
            "product_id": product_id,
            "quantity_locked": quantity,
            "expires_at": "2026-06-12T12:00:00",
            "locked_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("inventory-lock")}
    _log_response("POST", "/api/v1/inventory/lock", 200, f"锁定库存 {lock_id}")
    return JSONResponse(response, headers=resp_headers)


# 6. POST /api/v1/orders/{order_id}/refund - 订单退款
@app.post("/api/v1/orders/{order_id}/refund")
async def refund_order(order_id: str, request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", f"/api/v1/orders/{order_id}/refund", headers, body)

    refund_amount = (body or {}).get("refund_amount", 100.00)
    refund_reason = (body or {}).get("refund_reason", "")

    # 故意失败场景：refund_reason 包含 "TEST_FAIL"
    if "TEST_FAIL" in refund_reason:
        response = {
            "success": False,
            "errorCode": "REFUND_FAILED",
            "errorMessage": "退款处理失败（测试场景）"
        }
        _log_response("POST", f"/api/v1/orders/{order_id}/refund", 500, "退款失败（故意）")
        return JSONResponse(response, status_code=500)

    refund_id = f"REFUND-{int(time.time()) % 100000:05d}"
    response = {
        "success": True,
        "data": {
            "refund_id": refund_id,
            "order_id": order_id,
            "refund_amount": refund_amount,
            "status": "REFUNDED",
            "refunded_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("refund")}
    _log_response("POST", f"/api/v1/orders/{order_id}/refund", 200, f"退款成功 {refund_id}")
    return JSONResponse(response, headers=resp_headers)


# 7. POST /api/v1/orders/fail - 创建订单（黑名单测试，故意失败）
@app.post("/api/v1/orders/fail")
async def intentional_fail_order(request: Request):
    headers = _important_headers(request)
    body = await _read_body_json(request)
    _log_request("POST", "/api/v1/orders/fail", headers, body)

    buyer_id = (body or {}).get("buyer_id", "")

    # 黑名单测试：buyer_id == "FAIL_USER" 触发失败
    if buyer_id == "FAIL_USER":
        response = {
            "success": False,
            "errorCode": "ORDER_CREATE_FAILED",
            "errorMessage": "订单创建失败（测试黑名单场景）"
        }
        _log_response("POST", "/api/v1/orders/fail", 500, "订单创建失败（故意）")
        return JSONResponse(response, status_code=500)

    # 正常情况
    order_id = f"ORD-{int(time.time()) % 100000:05d}"
    response = {
        "success": True,
        "data": {
            "order_id": order_id,
            "buyer_id": buyer_id,
            "pay_status": "PENDING",
            "created_at": "2026-06-12T10:00:00"
        },
        "errorCode": "",
        "errorMessage": ""
    }
    resp_headers = {"X-Trace-Id": _trace_id("test-order")}
    _log_response("POST", "/api/v1/orders/fail", 200, f"创建订单 {order_id}")
    return JSONResponse(response, headers=resp_headers)
