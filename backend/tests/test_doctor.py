"""Unit tests for scripts/doctor.py."""

from __future__ import annotations

import sys

import doctor


class TestCheckPython:
    def test_current_python_passes(self):
        result = doctor.check_python()
        assert sys.version_info >= (3, 12)
        assert result.status == "ok"


class TestCheckConfigExists:
    def test_missing_config(self, tmp_path):
        result = doctor.check_config_exists(tmp_path / "config.yaml")
        assert result.status == "fail"
        assert result.fix is not None

    def test_present_config(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        result = doctor.check_config_exists(cfg)
        assert result.status == "ok"


class TestCheckConfigVersion:
    def test_up_to_date(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "ok"

    def test_outdated(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 3\n")
        example = tmp_path / "config.example.yaml"
        example.write_text("config_version: 5\n")
        result = doctor.check_config_version(cfg, tmp_path)
        assert result.status == "warn"
        assert result.fix is not None

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_config_version(tmp_path / "config.yaml", tmp_path)
        assert result.status == "skip"


class TestCheckConfigLoadable:
    def test_loadable_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        monkeypatch.setattr(doctor, "_load_app_config", lambda _path: object())
        result = doctor.check_config_loadable(cfg)
        assert result.status == "ok"

    def test_invalid_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")

        def fail(_path):
            raise ValueError("bad config")

        monkeypatch.setattr(doctor, "_load_app_config", fail)
        result = doctor.check_config_loadable(cfg)
        assert result.status == "fail"
        assert "bad config" in result.detail


class TestCheckModelsConfigured:
    def test_no_models(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nmodels: []\n")
        result = doctor.check_models_configured(cfg)
        assert result.status == "fail"

    def test_one_model(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n"
        )
        result = doctor.check_models_configured(cfg)
        assert result.status == "ok"

    def test_missing_config_skipped(self, tmp_path):
        result = doctor.check_models_configured(tmp_path / "config.yaml")
        assert result.status == "skip"


class TestCheckLLMApiKey:
    def test_key_set(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n"
        )
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        results = doctor.check_llm_api_key(cfg)
        assert any(result.status == "ok" for result in results)

    def test_key_missing(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: default\n    use: langchain_openai:ChatOpenAI\n    model: gpt-4o\n    api_key: $OPENAI_API_KEY\n"
        )
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        results = doctor.check_llm_api_key(cfg)
        failed = [result for result in results if result.status == "fail"]
        assert failed
        assert any("OPENAI_API_KEY" in (result.fix or "") for result in failed)

    def test_missing_config_returns_empty(self, tmp_path):
        assert doctor.check_llm_api_key(tmp_path / "config.yaml") == []


class TestCheckLLMAuth:
    def test_codex_auth_file_missing_fails(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: codex\n    use: deerflow.models.openai_codex_provider:CodexChatModel\n    model: gpt-5.4\n"
        )
        monkeypatch.setenv("CODEX_AUTH_PATH", str(tmp_path / "missing-auth.json"))
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "fail" and "Codex CLI auth available" in result.label for result in results)

    def test_claude_oauth_env_passes(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nmodels:\n  - name: claude\n    use: deerflow.models.claude_provider:ClaudeChatModel\n    model: claude-sonnet-4-6\n"
        )
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "token")
        results = doctor.check_llm_auth(cfg)
        assert any(result.status == "ok" and "Claude auth available" in result.label for result in results)


class TestCheckEnvFile:
    def test_missing(self, tmp_path):
        result = doctor.check_env_file(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        (tmp_path / ".env").write_text("KEY=val\n")
        result = doctor.check_env_file(tmp_path)
        assert result.status == "ok"


class TestCheckFrontendEnv:
    def test_missing(self, tmp_path):
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "warn"

    def test_present(self, tmp_path):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / ".env").write_text("KEY=val\n")
        result = doctor.check_frontend_env(tmp_path)
        assert result.status == "ok"


class TestCheckSandbox:
    def test_missing_sandbox_fails(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\n")
        results = doctor.check_sandbox(cfg)
        assert results[0].status == "fail"

    def test_local_sandbox_with_disabled_host_bash_warns(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "config_version: 5\nsandbox:\n  use: deerflow.sandbox.local:LocalSandboxProvider\n  allow_host_bash: false\ntools:\n  - name: bash\n    use: deerflow.sandbox.tools:bash_tool\n"
        )
        results = doctor.check_sandbox(cfg)
        assert any(result.status == "warn" for result in results)

    def test_container_sandbox_without_runtime_warns(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("config_version: 5\nsandbox:\n  use: deerflow.community.aio_sandbox:AioSandboxProvider\ntools: []\n")
        monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
        results = doctor.check_sandbox(cfg)
        assert any(result.label == "container runtime available" and result.status == "warn" for result in results)


class TestMainExitCode:
    def test_returns_int(self, tmp_path, monkeypatch, capsys):
        repo_root = tmp_path / "repo"
        scripts_dir = repo_root / "scripts"
        scripts_dir.mkdir(parents=True)
        fake_doctor = scripts_dir / "doctor.py"
        fake_doctor.write_text("# test-only shim for __file__ resolution\n")

        monkeypatch.chdir(repo_root)
        monkeypatch.setattr(doctor, "__file__", str(fake_doctor))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        exit_code = doctor.main()

        captured = capsys.readouterr()
        output = captured.out + captured.err
        assert exit_code in (0, 1)
        assert output
        assert "config.yaml" in output
        assert ".env" in output
