import os
from pathlib import Path

from backend.app.core.env import load_dotenv, provider_status


def test_load_dotenv_reads_values_without_overriding_existing_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local configuration",
                "LLM_PROVIDER=openai_compatible",
                "LLM_MODEL=deepseek-v4-flash",
                "EXISTING=from-file",
                "export PRON_PROVIDER=tencent_soe",
                "QUOTED='quoted value'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EXISTING", "from-env")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("PRON_PROVIDER", raising=False)

    loaded = load_dotenv(env_file, force=True)

    assert loaded is True
    assert provider_status()["llm_provider"] == "openai_compatible"
    assert provider_status()["llm_model"] == "deepseek-v4-flash"
    assert provider_status()["pronunciation_provider"] == "tencent_soe"
    assert provider_status()["external_services_enabled"] is True
    assert provider_status()["dotenv_loaded"] is True
    assert os.environ["EXISTING"] == "from-env"
    assert os.environ["QUOTED"] == "quoted value"


def test_load_dotenv_can_be_disabled(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openai_compatible", encoding="utf-8")
    monkeypatch.setenv("APP_AUTO_LOAD_DOTENV", "0")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    loaded = load_dotenv(env_file)

    assert loaded is False
