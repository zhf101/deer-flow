"""Step: optional web capability configuration."""

from __future__ import annotations

from dataclasses import dataclass

from wizard.ui import print_header, print_info


@dataclass
class SearchStepResult:
    search_provider: None = None
    search_api_key: str | None = None
    fetch_provider: None = None
    fetch_api_key: str | None = None


def run_search_step(step_label: str = "Step 3/3") -> SearchStepResult:
    print_header(f"{step_label} · Web Search & Fetch")
    print_info("External web search, web fetch, and image search have been removed from this project configuration.")
    return SearchStepResult()
