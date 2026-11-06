"""E-mails da conta no design da Quantumco (Vácuo, Grafite, Branco e os feixes verde e azul).

HTML pensado para clientes de e-mail: tabelas, estilos inline, 600 px de largura máxima e
fontes da marca (Outfit, IBM Plex Mono) com alternativas do sistema. Toda mensagem também vai
em texto puro. Valores do usuário passam sempre por `html.escape`.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from string import Template

from quantumco.identity.domain.email import EmailAddress, EmailMessage

_LAYOUT = Template(files(__package__).joinpath("layout.html").read_text(encoding="utf-8"))
_SANS = "'Outfit','Segoe UI',Helvetica,Arial,sans-serif"
_MONO = "'IBM Plex Mono',ui-monospace,Menlo,Consolas,monospace"
_BRT = timezone(timedelta(hours=-3), "BRT")  # sem horário de verão desde 2019
_IGNORE = "Se não foi você, ignore este e-mail: nada muda na sua conta."
_SECURITY = "Este é um aviso de segurança da sua conta no quantumco."
SIGNATURE = "quantumco · Sintaxe espacial de Brusque · https://quantumco.com.br"


def _first(name: str) -> str:
    return (name.split() or [""])[0]


def _p(text: str) -> str:
    return (
        f'<p style="margin:0 0 14px 0;font-family:{_SANS};font-size:15px;font-weight:300;'
        f'line-height:1.65;color:#C9CFD1;">{text}</p>'
    )


def _strong(text: str) -> str:
    return f'<span style="color:#F4F6F5;font-weight:400;">{html.escape(text)}</span>'


def _button(label: str, link: str) -> str:
    href = html.escape(link, quote=True)
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:28px 0 22px 0;"><tr>'
        '<td bgcolor="#2BD46B" style="background:#2BD46B;border-radius:999px;">'
        f'<a href="{href}" target="_blank" style="display:inline-block;padding:15px 28px;'
        f"font-family:{_SANS};font-size:16px;font-weight:500;line-height:1;color:#050607;"
        f'text-decoration:none;border-radius:999px;">{html.escape(label)} &rarr;</a>'
        "</td></tr></table>"
        f'<p style="margin:0 0 6px 0;font-family:{_MONO};font-size:10px;letter-spacing:1.8px;'
        'text-transform:uppercase;color:#6E777A;">Ou copie o endereço</p>'
        f'<p style="margin:0 0 6px 0;font-family:{_MONO};font-size:12px;line-height:1.6;'
        f'word-break:break-all;"><a href="{href}" target="_blank" '
        f'style="color:#3B8CFF;text-decoration:none;">{html.escape(link)}</a></p>'
    )


def _note(text: str) -> str:
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        'style="margin:22px 0 0 0;"><tr>'
        '<td style="border-top:1px solid #1E2427;padding-top:16px;'
        f'font-family:{_MONO};font-size:11px;letter-spacing:0.6px;line-height:1.6;color:#9BA3A6;">'
        f"{html.escape(text)}</td></tr></table>"
    )


@dataclass(frozen=True, slots=True)
class _Mail:
    subject: str
    preheader: str
    label: str
    title: str
    paragraphs: list[str]  # HTML já escapado
    text: str
    action: tuple[str, str] | None = None  # (rótulo, link)
    note: str = ""
    footer: str = _IGNORE

    def render(self, to: EmailAddress) -> EmailMessage:
        page = _LAYOUT.substitute(
            subject=html.escape(self.subject),
            preheader=html.escape(self.preheader),
            label=html.escape(self.label),
            title=html.escape(self.title),
            body="".join(_p(par) for par in self.paragraphs),
            action=_button(*self.action) if self.action else "",
            note=_note(self.note) if self.note else "",
            footer=html.escape(self.footer),
        )
        return EmailMessage(to=(to,), subject=self.subject, text=self.text, html=page)


def _text(*lines: str) -> str:
    return "\n".join([*lines, "", "—", SIGNATURE]).strip() + "\n"


class BrandedAccountMessages:
    """Implementa `AccountMessages`: um modelo por mensagem sobre o mesmo layout."""

    def confirm_email(self, *, to: EmailAddress, name: str, link: str) -> EmailMessage:
        first = _first(name)
        return _Mail(
            subject="Confirme seu e-mail · quantumco",
            preheader="Falta um clique para ativar sua conta no mapa sintático de Brusque.",
            label="Confirmação de e-mail",
            title=f"Olá, {first}. Falta confirmar seu e-mail.",
            paragraphs=[
                "Você criou uma conta no quantumco, o mapa sintático aberto de Brusque. "
                "Confirme o endereço para poder recuperar a senha e receber os avisos dos "
                "seus cenários.",
            ],
            action=("Confirmar e-mail", link),
            note="O link vale por 48 horas e só pode ser usado uma vez.",
            text=_text(
                f"Olá, {first}.",
                "",
                "Você criou uma conta no quantumco, o mapa sintático aberto de Brusque.",
                "Confirme seu e-mail abrindo o link abaixo (vale por 48 horas):",
                "",
                link,
                "",
                _IGNORE,
            ),
        ).render(to)

    def confirm_new_email(
        self, *, to: EmailAddress, name: str, link: str, old_email: EmailAddress
    ) -> EmailMessage:
        first = _first(name)
        return _Mail(
            subject="Confirme seu novo e-mail · quantumco",
            preheader="Confirme o endereço novo da sua conta no quantumco.",
            label="Troca de e-mail",
            title="Confirme o seu novo endereço",
            paragraphs=[
                f"Olá, {html.escape(first)}. Pediram para trocar o e-mail da sua conta de "
                f"{_strong(str(old_email))} para este endereço.",
                "A troca só vale depois que você confirmar. Até lá, a conta continua com o "
                "e-mail antigo.",
            ],
            action=("Confirmar novo e-mail", link),
            note="O link vale por 48 horas e só pode ser usado uma vez.",
            text=_text(
                f"Olá, {first}.",
                "",
                f"Pediram para trocar o e-mail da sua conta no quantumco de {old_email} "
                "para este endereço. A troca só vale depois da confirmação:",
                "",
                link,
                "",
                _IGNORE,
            ),
        ).render(to)

    def email_change_notice(
        self, *, to: EmailAddress, name: str, new_email: EmailAddress, profile_link: str
    ) -> EmailMessage:
        first = _first(name)
        return _Mail(
            subject="Pedido de troca de e-mail · quantumco",
            preheader="Pediram para trocar o e-mail da sua conta.",
            label="Aviso de segurança",
            title="Pediram para trocar o e-mail da sua conta",
            paragraphs=[
                f"Olá, {html.escape(first)}. O endereço {_strong(str(new_email))} recebeu um "
                "link para confirmar a troca do e-mail da sua conta.",
                "Enquanto ele não for confirmado, nada muda: você continua entrando com este "
                "e-mail. Se não foi você, entre no seu perfil, cancele a troca e crie uma "
                "senha nova.",
            ],
            action=("Abrir meu perfil", profile_link),
            footer=_SECURITY,
            text=_text(
                f"Olá, {first}.",
                "",
                f"Pediram para trocar o e-mail da sua conta no quantumco para {new_email}.",
                "A troca só vale depois que o endereço novo confirmar.",
                "Se não foi você, cancele a troca no seu perfil e crie uma senha nova:",
                "",
                profile_link,
            ),
        ).render(to)

    def password_link(
        self, *, to: EmailAddress, name: str, link: str, forgot: bool
    ) -> EmailMessage:
        first = _first(name)
        if forgot:
            subject, label, title = (
                "Recupere sua senha · quantumco",
                "Recuperação de senha",
                "Vamos criar uma senha nova",
            )
            why = "Recebemos um pedido para recuperar o acesso à sua conta."
        else:
            subject, label, title = (
                "Troque sua senha · quantumco",
                "Troca de senha",
                "Crie a sua senha nova",
            )
            why = "Você pediu, no seu perfil, para trocar a senha da conta."
        return _Mail(
            subject=subject,
            preheader="Link para criar uma senha nova (vale por 1 hora).",
            label=label,
            title=title,
            paragraphs=[
                f"Olá, {html.escape(first)}. {why}",
                "Abra o link e escolha a senha nova. Por segurança, as sessões abertas em "
                "outros aparelhos serão encerradas.",
            ],
            action=("Criar senha nova", link),
            note="O link vale por 1 hora e só pode ser usado uma vez.",
            footer="Se não foi você, ignore este e-mail: sua senha atual continua valendo.",
            text=_text(
                f"Olá, {first}.",
                "",
                why,
                "Crie a senha nova pelo link abaixo (vale por 1 hora, uso único):",
                "",
                link,
                "",
                "Se não foi você, ignore este e-mail: sua senha atual continua valendo.",
            ),
        ).render(to)

    def password_changed(
        self, *, to: EmailAddress, name: str, when: datetime, recover_link: str
    ) -> EmailMessage:
        first = _first(name)
        moment = when.astimezone(_BRT).strftime("%d/%m/%Y às %H:%M")
        return _Mail(
            subject="Sua senha foi alterada · quantumco",
            preheader=f"A senha da sua conta foi trocada em {moment}.",
            label="Aviso de segurança",
            title="Sua senha foi alterada",
            paragraphs=[
                f"Olá, {html.escape(first)}. A senha da sua conta foi trocada em "
                f"{_strong(moment)} (horário de Brasília).",
                "Encerramos as sessões abertas em outros aparelhos. Se foi você, não precisa "
                "fazer nada.",
                "Se não foi você, recupere o acesso agora:",
            ],
            action=("Recuperar acesso", recover_link),
            footer=_SECURITY,
            text=_text(
                f"Olá, {first}.",
                "",
                f"A senha da sua conta no quantumco foi trocada em {moment} (horário de "
                "Brasília). As sessões em outros aparelhos foram encerradas.",
                "Se não foi você, recupere o acesso agora:",
                "",
                recover_link,
            ),
        ).render(to)
