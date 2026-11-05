from __future__ import annotations

from pathlib import Path

from quantumco.bootstrap.settings import BACKEND_ROOT, Settings


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
