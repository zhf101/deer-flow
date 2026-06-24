"""GDP Agent Runtime 架构边界守卫测试。

本测试把 `docs/20260623/gdp-agent-runtime-架构地图.md` 中的关键不变量固化为
可执行断言，使「AI 生成代码再次违反边界」时 CI 自动失败，无需人工 review 兜底。

每条规则均在编写时对照当时代码验证为真（2026-06-23）。新增违反者将使对应用例红。
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
AGENT_RUNTIME_ROOT = BACKEND_ROOT / "app" / "gdp" / "agent_runtime"
GDP_ROOT = BACKEND_ROOT / "app" / "gdp"

# agent_runtime DDD 分层依赖规则：键=层，值=该层禁止 import 的上层/同级隔离层。
# 依据架构地图 §1/§2，编写时逐层验证为真。
FORBIDDEN_LAYER_IMPORTS: dict[str, set[str]] = {
    # 最内层：领域模型与状态机守卫，不依赖任何其他子层。
    "domain": {"api", "application", "workflows", "execution", "evidence", "verdict", "adapters", "ledger"},
    # 叶子工具/端口层，不依赖业务层。
    "support": {"api", "application", "workflows", "execution", "evidence", "verdict", "adapters", "ledger"},
    "ports": {"api", "application", "workflows", "execution", "evidence", "verdict", "adapters", "ledger"},
    # 中间服务层：使用 domain，但不得反向依赖编排/应用/接口层。
    "execution": {"api", "application", "workflows"},
    "evidence": {"api", "application", "workflows"},
    "verdict": {"api", "application", "workflows"},
    "adapters": {"api", "application", "workflows"},
    "ledger": {"api", "application", "workflows"},
    # 编排层：使用下层，但不得依赖应用门面与接口层。
    "workflows": {"api", "application"},
    # 应用门面层：不得依赖接口层。
    "application": {"api"},
    # api 为最外层，可依赖任意下层，无禁止项。
}


def _imported_modules(path: Path) -> set[str]:
    """收集一个 .py 文件 import 的所有模块全名（含相对 import 的还原）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # 相对 import：还原为 agent_runtime 下的绝对模块名。
                base_parts = path.relative_to(BACKEND_ROOT).with_suffix("").parts
                # 去掉文件名，再按 level 上溯。
                pkg_parts = list(base_parts[:-1])
                up = node.level - 1
                if up:
                    pkg_parts = pkg_parts[:-up] if up <= len(pkg_parts) else []
                target = ".".join(pkg_parts + ([node.module] if node.module else []))
                modules.add(target)
            elif node.module:
                modules.add(node.module)
    return modules


def _agent_runtime_layer(module_name: str) -> str | None:
    """把模块全名映射到 agent_runtime 子层名，非 agent_runtime 返回 None。"""
    prefix = "app.gdp.agent_runtime."
    if not module_name.startswith(prefix):
        return None
    return module_name.removeprefix(prefix).split(".", 1)[0]


def test_agent_runtime_layers_do_not_reference_upper_layers():
    """DDD 内向依赖：下层/隔离层不得 import 上层（架构地图 §1）。"""
    violations: list[str] = []
    for path in AGENT_RUNTIME_ROOT.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        relative = path.relative_to(AGENT_RUNTIME_ROOT)
        layer = relative.parts[0]
        forbidden = FORBIDDEN_LAYER_IMPORTS.get(layer)
        if not forbidden:
            continue
        for imported in _imported_modules(path):
            imported_layer = _agent_runtime_layer(imported)
            if imported_layer in forbidden:
                violations.append(f"{relative}: {layer} 违规 import 上层 {imported_layer}（{imported}）")
    assert violations == [], "agent_runtime 分层依赖被破坏：\n" + "\n".join(violations)


def test_agent_runtime_has_zero_langgraph_dependency():
    """核心不变量：运行时核心永远纯 Python，绝不依赖 langgraph（回归说明 §1）。"""
    offenders: list[str] = []
    for path in AGENT_RUNTIME_ROOT.rglob("*.py"):
        for imported in _imported_modules(path):
            if imported == "langgraph" or imported.startswith("langgraph."):
                offenders.append(f"{path.relative_to(AGENT_RUNTIME_ROOT)} imports {imported}")
    assert offenders == [], (
        "agent_runtime 必须保持纯 Python 核心，LangGraph 只能在未来的薄壳层引入：\n"
        + "\n".join(offenders)
    )


def test_deleted_legacy_langgraph_agent_is_not_resurrected():
    """已废弃的 app.gdp.agent（LangGraph 厚实现）不得被重新 import（清理任务 + 回归说明 §2）。"""
    offenders: list[str] = []
    for path in GDP_ROOT.rglob("*.py"):
        for imported in _imported_modules(path):
            # 命中 app.gdp.agent 或其子模块，但排除 app.gdp.agent_runtime / agent_logging / agent_catalog / agent_memory。
            if imported == "app.gdp.agent" or imported.startswith("app.gdp.agent."):
                if not imported.startswith(
                    ("app.gdp.agent_runtime", "app.gdp.agent_logging", "app.gdp.agent_catalog", "app.gdp.agent_memory")
                ):
                    offenders.append(f"{path.relative_to(GDP_ROOT)} imports {imported}")
    assert offenders == [], (
        "已删除的旧 LangGraph 实现 app.gdp.agent 不应被重新引入；回归请走薄壳三层（回归说明 §2/§3）：\n"
        + "\n".join(offenders)
    )


def test_every_state_transition_guards_against_llm_proposal():
    """核心安全不变量：每个 transition_* 状态机守卫都必须调用 reject_lm_proposal，
    确保 LLM 输出永不直接驱动事实状态机（架构地图 §4 / 交接文档 §3）。"""
    transitions_path = AGENT_RUNTIME_ROOT / "domain" / "transitions.py"
    tree = ast.parse(transitions_path.read_text(encoding="utf-8"), filename=str(transitions_path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("transition_"):
            calls = {
                sub.func.id
                for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            }
            if "reject_lm_proposal" not in calls:
                offenders.append(node.name)
    assert offenders == [], (
        "以下状态机守卫未调用 reject_lm_proposal，存在 LLM 直接驱动状态的风险："
        + "、".join(offenders)
    )
