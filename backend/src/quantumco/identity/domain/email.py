from __future__ import annotations

import re
from dataclasses import dataclass

# Validação deliberadamente simples: a prova real de que o endereço existe é a confirmação
# por e-mail (Q48), não uma regex.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InvalidEmailError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EmailAddress:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL.match(normalized) or len(normalized) > 254:
            raise InvalidEmailError(f"e-mail inválido: {self.value!r}")
        object.__setattr__(self, "value", normalized)

    @property
    def domain(self) -> str:
        return self.value.rsplit("@", 1)[1]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Sender:
    address: EmailAddress
    display_name: str = ""

    def formatted(self) -> str:
        name = self.display_name.replace('"', "").strip()
        return f'"{name}" <{self.address}>' if name else str(self.address)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: tuple[EmailAddress, ...]
    subject: str
    text: str
    html: str | None = None

    def __post_init__(self) -> None:
        if not self.to:
            raise ValueError("mensagem sem destinatário")
        if not self.subject.strip():
            raise ValueError("mensagem sem assunto")
        if not self.text.strip():
            raise ValueError("mensagem sem corpo em texto")
