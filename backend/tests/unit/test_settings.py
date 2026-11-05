from __future__ import annotations

from pathlib import Path

from quantumco.bootstrap.settings import REPO_ROOT, Settings


def test_defaults_resolve_inside_repo() -> None:
    settings = Settings.from_env({})
    assert settings.methodology_dir == REPO_ROOT / "methodology" / "v1"
    assert settings.data_dir == REPO_ROOT / "data"
    assert settings.overpass_timeout_s == 300.0
    assert settings.log_level == "INFO"
    assert (settings.methodology_dir / "VERSION").is_file()


def test_env_overrides(tmp_path: Path) -> None:
    settings = Settings.from_env(
        {"QC_DATA_DIR": str(tmp_path), "QC_LOG_LEVEL": "debug", "QC_OVERPASS_TIMEOUT_S": "60"}
    )
    assert settings.data_dir == tmp_path
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
