from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FilmFormat:
    name: str
    default_count: int
    allowed_counts: tuple[int, ...]
    family: str


FORMATS: dict[str, FilmFormat] = {
    "135": FilmFormat("135", 6, tuple(range(1, 7)), "35mm"),
    "135-dual": FilmFormat("135-dual", 12, (12,), "35mm"),
    "half": FilmFormat("half", 12, tuple(range(1, 13)), "35mm"),
    "xpan": FilmFormat("xpan", 3, (1, 2, 3), "35mm"),
    "120-645": FilmFormat("120-645", 4, (1, 2, 3, 4), "120"),
    "120-66": FilmFormat("120-66", 3, (1, 2, 3), "120"),
    "120-67": FilmFormat("120-67", 3, (1, 2, 3), "120"),
}

FORMAT_CHOICES = tuple(FORMATS.keys())
LAYOUT_CHOICES = ("auto", "horizontal", "vertical")
STRIP_CHOICES = ("full", "partial")
DESKEW_CHOICES = ("off", "auto")
ANALYSIS_CHOICES = ("off", "auto", "always")
COMPRESSION_CHOICES = ("none", "same")

CONTENT_ASPECTS_HORIZONTAL = {
    "135": 3.0 / 2.0,
    "135-dual": 3.0 / 2.0,
    "half": 2.0 / 3.0,
    "xpan": 65.0 / 24.0,
    "120-66": 1.0,
    "120-645": 3.0 / 4.0,
    "120-67": 5.0 / 4.0,
}


__all__ = [
    "ANALYSIS_CHOICES",
    "COMPRESSION_CHOICES",
    "CONTENT_ASPECTS_HORIZONTAL",
    "DESKEW_CHOICES",
    "FORMAT_CHOICES",
    "FORMATS",
    "LAYOUT_CHOICES",
    "STRIP_CHOICES",
    "FilmFormat",
]
