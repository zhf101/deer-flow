"""GDP Datagen API HTTP 方法契约测试。"""

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
GDP_ROOT = BACKEND_ROOT / "app" / "gdp"
FORBIDDEN_ROUTE_MARKERS = ("@router.put", "@router.delete", "@router.patch")


def test_gdp_datagen_related_apis_only_use_get_or_post_routes():
    """Datagen 相关控制面只允许 GET/POST，修改和删除语义统一走 POST。"""

    api_files = [
        *sorted((GDP_ROOT / "datagen").rglob("api.py")),
        *sorted((GDP_ROOT / "agent").rglob("api.py")),
        *sorted((GDP_ROOT / "agent_runtime").rglob("api.py")),
    ]

    violations: list[str] = []
    for api_file in api_files:
        text = api_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(marker in line for marker in FORBIDDEN_ROUTE_MARKERS):
                violations.append(f"{api_file.relative_to(BACKEND_ROOT)}:{line_no}:{line.strip()}")

    assert violations == []
