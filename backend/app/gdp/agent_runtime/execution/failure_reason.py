"""场景执行失败原因提取。"""

from __future__ import annotations


def extract_failure_reason(result: dict) -> str:
    """从场景执行结果中挖掘对用户最友好的失败原因。

    业务目标：用户需要看到”为什么造数失败”——如”余额不足”或”服务器连接被拒绝”，
    而不是一段机器味的英文堆栈。
    当前动作：按友好程度逐层深入场景结果，优先取业务规则层给出的中文原因，
    逐层退化到步骤级 detail、步骤级 message、顶层 errors，最终兜底。
    预期结果：返回一句人能看懂的中文失败描述。
    """
    business = result.get("businessResult") or {}
    if business.get("reason"):
        return str(business["reason"])

    for step in result.get("stepResults") or []:
        error = ((step or {}).get("rawResponse") or {}).get("error") or {}
        if error.get("detail"):
            return str(error["detail"])
        if error.get("message"):
            return str(error["message"])

    errors = result.get("errors") or []
    if errors:
        return "；".join(str(item) for item in errors)

    return "场景执行失败"
