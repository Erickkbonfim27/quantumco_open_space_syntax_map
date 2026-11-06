from __future__ import annotations

import pytest
from psycopg.conninfo import conninfo_to_dict

from quantumco.bootstrap.identity import build_mailer
from quantumco.bootstrap.settings import Settings
from quantumco.identity.domain.email import EmailAddress, EmailMessage, Sender
from quantumco.identity.infrastructure.log_mailer import LogMailer
from quantumco.identity.infrastructure.redirect_mailer import RedirectingMailer
from quantumco.platform.homolog import (
    HomologGuardError,
    _check,
    database_name,
    homolog_url_for,
    is_homolog,
)

PROD = "postgresql://qc:s3nha@vps.example:5433/quantumco"


def test_homolog_url_keeps_server_and_credentials_and_renames_database() -> None:
    url = homolog_url_for(PROD)
    params = conninfo_to_dict(url)
    assert params["dbname"] == "quantumco_homolog"
    assert (params["host"], params["port"], params["user"]) == ("vps.example", "5433", "qc")
    assert params["password"] == "s3nha"
    assert is_homolog(url)
    assert not is_homolog(PROD)
    assert database_name("postgresql+psycopg://u@h/quantumco") == "quantumco"
    assert homolog_url_for("") == ""


def test_guards_refuse_wrong_direction_or_other_server() -> None:
    homolog = homolog_url_for(PROD)
    _check(PROD, homolog)  # o caminho certo passa
    with pytest.raises(HomologGuardError, match="precisa ter 'homolog'"):
        _check(PROD, "postgresql://qc:s3nha@vps.example:5433/quantumco_copia")
    with pytest.raises(HomologGuardError, match="origem já é"):
        _check(homolog, homolog)
    with pytest.raises(HomologGuardError, match="mesmo servidor"):
        _check(PROD, "postgresql://qc:s3nha@outra.example:5433/quantumco_homolog")
    with pytest.raises(HomologGuardError, match="QC_DATABASE_URL"):
        _check("", homolog)


def settings(**env: str) -> Settings:
    return Settings.from_env({"QC_DATABASE_URL": PROD, **env})


def test_use_homolog_switches_database_queue_but_keeps_production_url() -> None:
    normal = settings()
    assert normal.database_url == PROD
    assert normal.scenario_queue == "scenarios"
    homo = settings(QC_USE_HOMOLOG="1")
    assert is_homolog(homo.database_url)
    assert homo.production_database_url == PROD
    assert homo.scenario_queue == "scenarios-homolog"
    with pytest.raises(ValueError, match="não tem 'homolog'"):
        settings(QC_USE_HOMOLOG="1", QC_HOMOLOG_DATABASE_URL=PROD)


def test_homolog_mail_goes_to_owner_with_original_recipient_noted() -> None:
    inner = LogMailer(Sender(EmailAddress("noreply@quantumco.com.br")))
    mailer = RedirectingMailer(inner, EmailAddress("dono@exemplo.com"))
    mailer.send(
        EmailMessage(
            to=(EmailAddress("usuario.real@exemplo.com"),),
            subject="Confirme seu e-mail",
            text="Olá",
            html="<p>Olá</p>",
        )
    )
    [sent] = inner.sent
    assert [str(a) for a in sent.to] == ["dono@exemplo.com"]
    assert sent.subject == "[homologação] Confirme seu e-mail"
    assert "usuario.real@exemplo.com" in sent.text
    assert sent.html is not None
    assert "usuario.real@exemplo.com" in sent.html


def test_homolog_without_owner_email_never_sends() -> None:
    mailer = build_mailer(settings(QC_USE_HOMOLOG="1", RESEND_API_KEY="re_x"))
    assert isinstance(mailer, LogMailer)
    with_owner = build_mailer(
        settings(QC_USE_HOMOLOG="1", RESEND_API_KEY="re_x", OWNER_EMAIL="dono@exemplo.com")
    )
    assert isinstance(with_owner, RedirectingMailer)
