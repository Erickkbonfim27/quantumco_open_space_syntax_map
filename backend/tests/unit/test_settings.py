from __future__ import annotations

import os
from pathlib import Path

import pytest

from quantumco.bootstrap.settings import BACKEND_ROOT, Settings, load_env_file


def test_defaults_resolve_inside_repo() -> None:
    settings = Settings.from_env({})
    assert settings.methodology_dir == BACKEND_ROOT / "methodology" / "v1"
    assert settings.database_url == ""
    assert settings.overpass_timeout_s == 300.0
    assert settings.log_level == "INFO"
    assert (settings.methodology_dir / "VERSION").is_file()


def test_env_overrides(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {
            "QC_DATABASE_URL": "postgresql://x",
            "QC_LOG_LEVEL": "debug",
            "QC_OVERPASS_TIMEOUT_S": "60",
        }
    )
    assert settings.require_database() == "postgresql://x"
    assert settings.log_level == "DEBUG"
    assert settings.overpass_timeout_s == 60.0


def test_mail_settings() -> None:
    settings = Settings.from_env(
        {
            "RESEND_API_KEY": " re_x ",
            "MAIL_FROM": "spacesyntax@erickkbonfim.com.br",
            "OWNER_EMAIL": "a@b.com",
        }
    )
    assert settings.resend_api_key == "re_x"
    assert settings.mail_from == "spacesyntax@erickkbonfim.com.br"
    assert settings.owner_email == "a@b.com"


def test_database_is_mandatory() -> None:
    import pytest  # noqa: PLC0415

    with pytest.raises(RuntimeError, match="PostGIS"):
        Settings.from_env({}).require_database()


def test_env_file_is_reread_but_real_environment_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com `serve --reload`, mudar o .env vale na próxima recarga (caso do MAIL_FROM)."""
    env = tmp_path / ".env"
    monkeypatch.delenv("MAIL_FROM", raising=False)
    monkeypatch.delenv("_QC_FROM_DOTENV", raising=False)
    monkeypatch.setenv("QC_LOG_LEVEL", "WARNING")  # definido "de verdade" no ambiente
    env.write_text("MAIL_FROM=antigo@quantumco.com.br\nQC_LOG_LEVEL=DEBUG\n")
    load_env_file(env)
    assert os.environ["MAIL_FROM"] == "antigo@quantumco.com.br"
    env.write_text("MAIL_FROM=noreply@quantumco.com.br\nQC_LOG_LEVEL=DEBUG\n")
    load_env_file(env)  # o processo filho herda o ambiente do pai e lê o .env de novo
    assert os.environ["MAIL_FROM"] == "noreply@quantumco.com.br"
    assert os.environ["QC_LOG_LEVEL"] == "WARNING"
    assert Settings.from_env({}).mail_from == "noreply@quantumco.com.br"  # padrão do código
    monkeypatch.delenv("MAIL_FROM")
