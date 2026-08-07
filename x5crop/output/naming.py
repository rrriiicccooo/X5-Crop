from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import unicodedata


MAX_COMPONENT_UTF16_UNITS = 120
MAX_PORTABLE_PATH_UTF16_UNITS = 240
MAX_TRANSACTION_TOKEN_UTF16_UNITS = 64
_INVALID_WINDOWS_CHARACTERS = frozenset('<>:"/\\|?*')
_SUPERSCRIPT_DIGITS = str.maketrans({"¹": "1", "²": "2", "³": "3"})
_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


class PortableNameError(ValueError):
    pass


@dataclass(frozen=True)
class PortableOutputName:
    value: str
    collision_key: str

    def __post_init__(self) -> None:
        validate_portable_component(self.value)
        if self.collision_key != collision_key(self.value):
            raise PortableNameError("portable name collision key is inconsistent")


def utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _truncate_utf16(value: str, limit: int) -> str:
    if limit < 0:
        raise PortableNameError("portable name limit cannot be negative")
    result: list[str] = []
    used = 0
    for character in value:
        width = utf16_units(character)
        if used + width > limit:
            break
        result.append(character)
        used += width
    return "".join(result)


def _is_control(character: str) -> bool:
    return unicodedata.category(character).startswith("C")


def normalized_name_string(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def short_name_digest(value: str) -> str:
    """Hash only a short normalized name string, never source content."""

    return sha256(normalized_name_string(value).encode("utf-8")).hexdigest()[:8]


def is_windows_reserved_name(value: str) -> bool:
    normalized = normalized_name_string(value).rstrip(" .")
    if not normalized:
        return False
    base = normalized.split(".", 1)[0].rstrip(" .")
    folded = base.upper().translate(_SUPERSCRIPT_DIGITS)
    return folded in _DEVICE_NAMES


def _sanitize(value: str, fallback: str) -> str:
    normalized = normalized_name_string(value)
    pieces: list[str] = []
    replacing = False
    for character in normalized:
        invalid = character in _INVALID_WINDOWS_CHARACTERS or _is_control(character)
        if invalid:
            if not replacing:
                pieces.append("_")
            replacing = True
        else:
            pieces.append(character)
            replacing = False
    sanitized = "".join(pieces).rstrip(" .")
    if sanitized in {"", ".", ".."}:
        sanitized = fallback
    if is_windows_reserved_name(sanitized):
        sanitized = f"{fallback}_{sanitized}"
    return sanitized


def collision_key(value: str) -> str:
    return normalized_name_string(value).casefold()


def validate_portable_component(value: str) -> None:
    if (
        not value
        or value in {".", ".."}
        or value != normalized_name_string(value)
        or value.endswith((" ", "."))
        or any(
            character in _INVALID_WINDOWS_CHARACTERS or _is_control(character)
            for character in value
        )
        or is_windows_reserved_name(value)
        or utf16_units(value) > MAX_COMPONENT_UTF16_UNITS
    ):
        raise PortableNameError(f"Not a portable output component: {value!r}")


def validate_explicit_output_leaf(value: str) -> PortableOutputName:
    validate_portable_component(value)
    return PortableOutputName(value, collision_key(value))


def portable_component(
    raw_value: str,
    *,
    input_ordinal: int,
    suffix: str = "",
    fallback: str = "source",
) -> PortableOutputName:
    if input_ordinal <= 0:
        raise PortableNameError("input ordinal must be positive")
    if suffix and (
        suffix != normalized_name_string(suffix)
        or any(
            character in _INVALID_WINDOWS_CHARACTERS or _is_control(character)
            for character in suffix
        )
    ):
        raise PortableNameError("portable output suffix is invalid")
    base = _sanitize(raw_value, fallback)
    candidate = base + suffix
    if utf16_units(candidate) > MAX_COMPONENT_UTF16_UNITS:
        marker = f"~{input_ordinal:04d}-{short_name_digest(raw_value)}"
        base_limit = MAX_COMPONENT_UTF16_UNITS - utf16_units(marker + suffix)
        base = _truncate_utf16(base, base_limit).rstrip(" .") or fallback
        candidate = base + marker + suffix
    validate_portable_component(candidate)
    return PortableOutputName(candidate, collision_key(candidate))


def portable_frame_name(
    source_name: str,
    *,
    input_ordinal: int,
    slot_index: int,
) -> PortableOutputName:
    if slot_index <= 0:
        raise PortableNameError("output slot index must be positive")
    stem = Path(source_name).stem
    return portable_component(
        stem,
        input_ordinal=input_ordinal,
        suffix=f"_{slot_index:02d}.tif",
    )


def portable_source_stems(source_names: tuple[str, ...]) -> tuple[PortableOutputName, ...]:
    """Plan every source stem together so conflicts fail before TIFF decode."""

    initial = tuple(
        portable_component(
            Path(name).stem,
            input_ordinal=ordinal,
        )
        for ordinal, name in enumerate(source_names, 1)
    )
    counts: dict[str, int] = {}
    for item in initial:
        counts[item.collision_key] = counts.get(item.collision_key, 0) + 1
    planned: list[PortableOutputName] = []
    for ordinal, (source_name, item) in enumerate(
        zip(source_names, initial, strict=True),
        1,
    ):
        if counts[item.collision_key] == 1:
            planned.append(item)
            continue
        marker = f"~{ordinal:04d}-{short_name_digest(Path(source_name).stem)}"
        planned.append(
            portable_component(
                item.value,
                input_ordinal=ordinal,
                suffix=marker,
            )
        )
    reject_collisions(planned)
    return tuple(planned)


def transaction_token_for_target(target: Path) -> str:
    leaf = validate_explicit_output_leaf(target.name).value
    if utf16_units(leaf) <= MAX_TRANSACTION_TOKEN_UTF16_UNITS:
        return leaf
    digest = short_name_digest(str(target.absolute()))
    marker = f"~{digest}"
    prefix = _truncate_utf16(
        leaf,
        MAX_TRANSACTION_TOKEN_UTF16_UNITS - utf16_units(marker),
    ).rstrip(" .")
    token = prefix + marker
    validate_portable_component(token)
    return token


def validate_portable_path(path: Path) -> None:
    if utf16_units(str(path.absolute())) > MAX_PORTABLE_PATH_UTF16_UNITS:
        raise PortableNameError(
            f"Output path exceeds {MAX_PORTABLE_PATH_UTF16_UNITS} UTF-16 units: {path}"
        )
    for part in path.parts:
        if part in {path.anchor, "", ".", ".."}:
            continue
        validate_portable_component(part)


def reject_collisions(names: list[PortableOutputName]) -> None:
    keys: dict[str, str] = {}
    for name in names:
        previous = keys.get(name.collision_key)
        if previous is not None:
            raise PortableNameError(
                f"Portable output collision: {previous!r} and {name.value!r}"
            )
        keys[name.collision_key] = name.value
