"""Frozen strict-XYZ and canonical JSON primitives for Stage M-B."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ELEMENTS_H_TO_NE = frozenset(
    {"H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne"}
)
DECIMAL_TOKEN = re.compile(
    r"\A[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE][+-]?[0-9]+)?\Z"
)
EXPONENT_TOKEN = re.compile(r"[eE]([+-]?[0-9]+)\Z")
ATOM_LINE = re.compile(
    r"^(?P<element>[A-Z][a-z]?)[\t ]+"
    r"(?P<x>[^\t ]+)[\t ]+(?P<y>[^\t ]+)[\t ]+(?P<z>[^\t ]+)[\t ]*$"
)
INTEGER_LINE = re.compile(r"^[1-9][0-9]*$")
MAX_RAW_XYZ_BYTES = 1024 * 1024
MAX_ATOM_COUNT = 32
MAX_COMMENT_BYTES = 4096
MAX_NUMBER_TOKEN_BYTES = 128
MAX_ABSOLUTE_EXPONENT = 100
MAX_COORDINATE_ABS_ANGSTROM = Decimal("10000")
MAX_CANONICAL_COORDINATE_BYTES = 128


class StrictXyzError(ValueError):
    """Raised when bytes do not conform to the frozen M-B XYZ grammar."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class StrictXyzResult:
    """Strict parser result with canonical bytes and hashes."""

    parsed_structure: dict[str, Any]
    canonical_payload: dict[str, Any]
    canonical_bytes: bytes
    canonical_sha256: str
    source_sha256: str
    comment_line_sha256: str


def canonical_decimal_coordinate(token: str) -> str:
    """Return the protocol decimal form without exponent or signed zero."""
    try:
        encoded = token.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise StrictXyzError("invalid_xyz_number", "坐标 token 必须为 ASCII。") from exc
    if len(encoded) > MAX_NUMBER_TOKEN_BYTES or not DECIMAL_TOKEN.fullmatch(token):
        raise StrictXyzError("invalid_xyz_number", f"非法坐标 token：{token!r}")
    exponent_match = EXPONENT_TOKEN.search(token)
    explicit_exponent = int(exponent_match.group(1)) if exponent_match else 0
    if abs(explicit_exponent) > MAX_ABSOLUTE_EXPONENT:
        raise StrictXyzError("xyz_exponent_out_of_range", "显式指数绝对值不得超过 100。")
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise StrictXyzError("invalid_xyz_number", "坐标不能解析为十进制数。") from exc
    if not value.is_finite():
        raise StrictXyzError("xyz_coordinate_non_finite", "坐标必须为有限十进制数。")
    if abs(value) > MAX_COORDINATE_ABS_ANGSTROM:
        raise StrictXyzError("xyz_coordinate_out_of_range", "坐标绝对值不得超过 10000 Å。")
    if value.is_zero():
        return "0"
    sign = "-" if value.is_signed() else ""
    fixed = format(abs(value), "f")
    integer_part, separator, fractional_part = fixed.partition(".")
    integer_part = integer_part.lstrip("0") or "0"
    fractional_part = fractional_part.rstrip("0")
    result = (
        f"{sign}{integer_part}.{fractional_part}"
        if separator and fractional_part
        else f"{sign}{integer_part}"
    )
    if len(result.encode("ascii")) > MAX_CANONICAL_COORDINATE_BYTES:
        raise StrictXyzError(
            "canonical_xyz_coordinate_too_long",
            "canonical coordinate 超过 128 ASCII bytes。",
        )
    return result


def _assert_unicode_scalar_string(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("JCS strings must not contain Unicode surrogate code points.")


def _utf16_sort_key(value: str) -> bytes:
    _assert_unicode_scalar_string(value)
    return value.encode("utf-16-be")


def rfc8785_jcs_bytes_v1(value: Any) -> bytes:
    """Encode the frozen JSON subset used by M-B.

    Floats are rejected. Coordinates are canonical decimal strings and numeric
    JSON values are limited to interoperable safe integers.
    """
    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise ValueError("JCS integer exceeds the interoperable safe range.")
        return str(value).encode("ascii")
    if isinstance(value, float):
        raise TypeError("M-B JCS payloads reject binary floating-point values.")
    if isinstance(value, str):
        _assert_unicode_scalar_string(value)
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    if isinstance(value, list):
        return b"[" + b",".join(rfc8785_jcs_bytes_v1(item) for item in value) + b"]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JCS object keys must be strings.")
        ordered_keys = sorted(value, key=_utf16_sort_key)
        fields = (
            rfc8785_jcs_bytes_v1(key) + b":" + rfc8785_jcs_bytes_v1(value[key])
            for key in ordered_keys
        )
        return b"{" + b",".join(fields) + b"}"
    raise TypeError(f"Unsupported JCS type: {type(value).__name__}")


def rfc8785_jcs_sha256_v1(value: Any) -> tuple[bytes, str]:
    """Return canonical bytes and their lowercase SHA-256."""
    canonical_bytes = rfc8785_jcs_bytes_v1(value)
    return canonical_bytes, hashlib.sha256(canonical_bytes).hexdigest()


def _decode_xyz(raw_bytes: bytes) -> list[str]:
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raise StrictXyzError("xyz_utf8_bom_forbidden", "XYZ 不接受 UTF-8 BOM。")
    if b"\x00" in raw_bytes:
        raise StrictXyzError("xyz_nul_forbidden", "XYZ 不接受 NUL。")
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise StrictXyzError("xyz_utf8_invalid", "XYZ 必须是严格 UTF-8。") from exc
    _assert_unicode_scalar_string(text)
    if "\r" in text.replace("\r\n", ""):
        raise StrictXyzError("xyz_line_ending_invalid", "XYZ 只接受 LF 或 CRLF。")
    normalized = text.replace("\r\n", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    return normalized.split("\n")


def _hill_formula(element_counts: Counter[str]) -> str:
    ordered: list[str] = []
    if "C" in element_counts:
        ordered.extend(["C"])
        if "H" in element_counts:
            ordered.append("H")
    ordered.extend(sorted(element for element in element_counts if element not in ordered))
    return "".join(
        element + (str(element_counts[element]) if element_counts[element] != 1 else "")
        for element in ordered
    )


def parse_strict_xyz_bytes(raw_bytes: bytes) -> StrictXyzResult:
    """Parse the exact M-B XYZ grammar and construct canonical geometry."""
    if len(raw_bytes) > MAX_RAW_XYZ_BYTES:
        raise StrictXyzError("xyz_file_too_large", "M-B XYZ 不得超过 1 MiB。")
    lines = _decode_xyz(raw_bytes)
    if len(lines) < 2 or not INTEGER_LINE.fullmatch(lines[0]):
        raise StrictXyzError("xyz_atom_count_invalid", "首行必须是无符号规范十进制原子数。")
    atom_count = int(lines[0])
    if not 1 <= atom_count <= MAX_ATOM_COUNT:
        raise StrictXyzError("xyz_atom_count_invalid", "M-B 原子数必须为 1..32。")
    if len(lines) != atom_count + 2:
        raise StrictXyzError(
            "xyz_line_count_mismatch",
            "XYZ 必须恰好包含 atom_count + 2 个逻辑行。",
        )
    comment = lines[1]
    if len(comment.encode("utf-8")) > MAX_COMMENT_BYTES:
        raise StrictXyzError("xyz_comment_too_long", "comment 行不得超过 4096 UTF-8 bytes。")
    if any(ord(character) < 0x20 and character != "\t" for character in comment):
        raise StrictXyzError("xyz_comment_control_character", "comment 行含非法控制字符。")

    atoms: list[dict[str, Any]] = []
    atomic_sites: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, line in enumerate(lines[2:]):
        match = ATOM_LINE.fullmatch(line)
        if match is None:
            raise StrictXyzError(
                "xyz_atom_line_invalid",
                f"第 {index + 3} 行必须恰好包含 element x y z。",
            )
        element = match.group("element")
        if element not in ELEMENTS_H_TO_NE:
            raise StrictXyzError(
                "xyz_element_not_supported",
                f"首版只支持 H–Ne，收到 {element}。",
            )
        canonical_position = [
            canonical_decimal_coordinate(match.group(axis))
            for axis in ("x", "y", "z")
        ]
        atoms.append(
            {
                "element": element,
                "index": index,
                "position_angstrom": canonical_position,
            }
        )
        atomic_sites.append(
            {
                "index": index,
                "element": element,
                "position_angstrom": [
                    float(value) for value in canonical_position
                ],
            }
        )
        counts[element] += 1

    canonical_payload = {
        "atom_count": atom_count,
        "atoms": atoms,
        "coordinate_unit": "angstrom",
        "dimensionality": "non_periodic",
        "schema_id": "canonical_molecular_geometry",
        "schema_version": "1.0.0",
    }
    canonical_bytes, canonical_sha256 = rfc8785_jcs_sha256_v1(canonical_payload)
    parsed_structure = {
        "formula": _hill_formula(counts),
        "elements": sorted(counts),
        "element_counts": dict(sorted(counts.items())),
        "atom_count": atom_count,
        "atomic_sites": atomic_sites,
        "lattice": None,
        "structure_type": "molecule",
        "charge": None,
        "spin_multiplicity": None,
        "dimensionality": "non_periodic",
        "parse_warnings": [],
    }
    return StrictXyzResult(
        parsed_structure=parsed_structure,
        canonical_payload=canonical_payload,
        canonical_bytes=canonical_bytes,
        canonical_sha256=canonical_sha256,
        source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        comment_line_sha256=hashlib.sha256(comment.encode("utf-8")).hexdigest(),
    )


def parse_strict_xyz_file(path: str | Path) -> StrictXyzResult:
    """Read and strictly parse an XYZ source file."""
    return parse_strict_xyz_bytes(Path(path).read_bytes())
