from __future__ import annotations

from dataclasses import dataclass

from ...spans import FilmSpan


@dataclass(frozen=True)
class OuterCorrectionProposal:
    corrected_span: FilmSpan
    family: str
    reason: str

    @property
    def box(self):
        return self.corrected_span.box
