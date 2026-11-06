"""Foto de perfil: pequena (o navegador já recorta e reduz para 256 px) e de formato conhecido."""

from __future__ import annotations

from dataclasses import dataclass

MAX_BYTES = 512 * 1024
_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


class InvalidAvatarError(ValueError):
    pass


def _sniff(content: bytes) -> str | None:
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    for media, signatures in _SIGNATURES.items():
        if content.startswith(signatures):
            return media
    return None


@dataclass(frozen=True, slots=True)
class Avatar:
    content: bytes
    media_type: str

    def __post_init__(self) -> None:
        if not self.content:
            raise InvalidAvatarError("Arquivo vazio.")
        if len(self.content) > MAX_BYTES:
            raise InvalidAvatarError("A foto pode ter no máximo 512 KB.")
        # o tipo vem do conteúdo, nunca do cabeçalho enviado
        sniffed = _sniff(self.content)
        if sniffed is None:
            raise InvalidAvatarError("Use uma imagem PNG, JPEG ou WebP.")
        object.__setattr__(self, "media_type", sniffed)
