from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Fato do domínio que já aconteceu. Subclasses acrescentam os dados do fato."""

    occurred_at: datetime
