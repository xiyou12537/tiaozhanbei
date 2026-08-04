"""Audit frozen sensitivity-VQE parameter hash conventions without quantum execution."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np


ARTIFACT_ROOT = Path("data/structure_artifacts")
SOURCE_ARTIFACT_ID = "literature_fragment_sensitivity_fixed_sector_vqe_4a95b573f3f54846a6f194631d8af511"
TARGET_HASH = "c207cb3f9a3773de71975f73ed54fc5b565a5cbaa856dbaec76dfbc892dbd8e7"
CANONICAL_FLOAT64_LE_HASH = "cc97b18a3485657521721957a7a6e58b61b19f7e9aec4680dc955822eaaff27f"


def _sha256_bytes(value: bytes) -> str:
    """Return a lower-case SHA-256 digest for auditable byte inputs."""
    return hashlib.sha256(value).hexdigest()


def _extract_parameter_tokens(source_text: str) -> list[str]:
    """Extract the source JSON lexical tokens so text and numeric hashes remain distinguishable."""
    pattern = r'"final_measurement"\s*:\s*\{.*?"parameters"\s*:\s*\[(.*?)\]\s*,\s*"energy_hartree"'
    match = re.search(pattern, source_text, re.DOTALL)
    if match is None:
        raise RuntimeError("Unable to locate final_measurement.parameters in the frozen source Artifact.")
    return [item.strip() for item in match.group(1).split(",")]


def _powershell_legacy_hash(source_path: Path) -> dict:
    """Reproduce the original host-side ConvertFrom-Json Decimal-to-Double byte-hash rule."""
    escaped_path = str(source_path.resolve()).replace("'", "''")
    script = f"""
$artifact = Get-Content -Raw -Encoding UTF8 '{escaped_path}' | ConvertFrom-Json
$rawParameters = $artifact.result.final_measurement.parameters
$parameters = [double[]]$rawParameters
$buffer = New-Object byte[] ($parameters.Length * 8)
for ($index = 0; $index -lt $parameters.Length; $index++) {{
    [System.BitConverter]::GetBytes($parameters[$index]).CopyTo($buffer, $index * 8)
}}
$sha256 = New-Object System.Security.Cryptography.SHA256Managed
$hash = ($sha256.ComputeHash($buffer) | ForEach-Object {{ $_.ToString('x2') }}) -join ''
[PSCustomObject]@{{
    hash = $hash
    raw_types = @($rawParameters | ForEach-Object {{ $_.GetType().FullName }} | Select-Object -Unique)
    cast_types = @($parameters | ForEach-Object {{ $_.GetType().FullName }} | Select-Object -Unique)
    round_trip_values = @($parameters | ForEach-Object {{ $_.ToString('R') }})
    powershell_version = $PSVersionTable.PSVersion.ToString()
    clr_version = [System.Environment]::Version.ToString()
}} | ConvertTo-Json -Depth 4 -Compress
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def _hash_variants(values: list[float], tokens: list[str]) -> dict[str, str]:
    """Hash documented text and binary representations without modifying the source Artifact."""
    raw_array = "[" + ",\n".join(tokens) + "]"
    text_variants = {
        "raw_json_parameter_array_utf8": raw_array,
        "normalized_json_compact_utf8": json.dumps(values, ensure_ascii=True, separators=(",", ":")),
        "python_repr_list_utf8": repr(values),
        "python_float_text_newline_utf8": "\n".join(repr(value) for value in values),
        "python_float_text_comma_utf8": ",".join(repr(value) for value in values),
        "raw_json_tokens_newline_utf8": "\n".join(tokens),
        "raw_json_tokens_comma_utf8": ",".join(tokens),
        "parameter_index_equals_float_utf8": "\n".join(
            f"parameter_{index}={repr(value)}" for index, value in enumerate(values)
        ),
        "parameter_index_colon_raw_token_utf8": "\n".join(
            f"parameter_{index}:{token}" for index, token in enumerate(tokens)
        ),
    }
    hashes = {name: _sha256_bytes(text.encode("utf-8")) for name, text in text_variants.items()}
    hashes.update(
        {
            "float64_little_endian_c_order": _sha256_bytes(np.asarray(values, dtype="<f8", order="C").tobytes(order="C")),
            "float64_big_endian_c_order": _sha256_bytes(np.asarray(values, dtype=">f8", order="C").tobytes(order="C")),
            "float64_native_c_order": _sha256_bytes(np.asarray(values, dtype=np.float64, order="C").tobytes(order="C")),
            "float32_little_endian_c_order": _sha256_bytes(np.asarray(values, dtype="<f4", order="C").tobytes(order="C")),
        }
    )
    return hashes


def _find_persistent_occurrences() -> list[dict]:
    """Locate every readable project code, log, and Artifact occurrence of the disputed hash."""
    occurrences: list[dict] = []
    for root in (Path("backend"), Path("data"), Path(".dev-logs")):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc", ".h5", ".chk"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if TARGET_HASH in text:
                occurrences.append(
                    {
                        "path": str(path).replace("\\", "/"),
                        "modified_at_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                        "line_numbers": [index for index, line in enumerate(text.splitlines(), start=1) if TARGET_HASH in line],
                    }
                )
    return sorted(occurrences, key=lambda item: item["modified_at_utc"])


def main() -> None:
    """Create one immutable provenance Artifact and propose no computational follow-up."""
    if list(ARTIFACT_ROOT.glob("parameter_hash_provenance_audit_*.json")):
        raise RuntimeError("A parameter hash provenance audit already exists; this read-only audit is single-use.")
    source_path = ARTIFACT_ROOT / f"{SOURCE_ARTIFACT_ID}.json"
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    payload = json.loads(source_text)
    values = payload["result"]["final_measurement"]["parameters"]
    tokens = _extract_parameter_tokens(source_text)
    if len(values) != 26 or len(tokens) != 26:
        raise RuntimeError("The frozen sensitivity Artifact does not contain exactly 26 final parameters.")

    legacy = _powershell_legacy_hash(source_path)
    variants = _hash_variants(values, tokens)
    occurrences = _find_persistent_occurrences()
    per_parameter = [
        {
            "index": index,
            "raw_json_token": token,
            "python_float_repr": repr(value),
            "float64_little_endian_hex": np.asarray([value], dtype="<f8").tobytes().hex(),
            "float64_big_endian_hex": np.asarray([value], dtype=">f8").tobytes().hex(),
            "legacy_powershell_decimal_to_double_round_trip": legacy["round_trip_values"][index],
        }
        for index, (token, value) in enumerate(zip(tokens, values, strict=True))
    ]
    source_script_path = Path(__file__)
    artifact = {
        "artifact_type": "parameter_hash_provenance_audit",
        "immutable": True,
        "read_only": True,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_artifact_sha256": _sha256_bytes(source_bytes),
        "parameter_count": 26,
        "parameter_order": "source_result.final_measurement.parameters ascending array index",
        "parameters": per_parameter,
        "persistent_occurrences_of_c207": occurrences,
        "first_persistent_occurrence_conclusion": (
            "The first project-persistent occurrence is the backfill script constant; no readable project log stores the interactive host command that produced it."
        ),
        "legacy_hash_rule": {
            "hash": legacy["hash"],
            "reproduces_target_c207": legacy["hash"] == TARGET_HASH,
            "input_object": "PowerShell ConvertFrom-Json result.result.final_measurement.parameters",
            "parameter_order": "source array order 0 through 25",
            "source_runtime_types": legacy["raw_types"],
            "conversion": "[double[]] cast applied after ConvertFrom-Json",
            "data_type": "System.Double after mixed System.Decimal/System.Double parsing",
            "byte_order": "BitConverter.GetBytes System.Double on Windows little-endian host",
            "serialization": "concatenated 26 x 8-byte IEEE-754 binary64 buffer; no JSON text serialization",
            "hash_algorithm": "System.Security.Cryptography.SHA256Managed.ComputeHash",
            "powershell_version": legacy["powershell_version"],
            "clr_version": legacy["clr_version"],
        },
        "canonical_hash_rule": {
            "hash": variants["float64_little_endian_c_order"],
            "matches_expected_cc97": variants["float64_little_endian_c_order"] == CANONICAL_FLOAT64_LE_HASH,
            "input_object": "Python json.loads source parameter list",
            "conversion": "numpy.asarray(values, dtype='<f8', order='C')",
            "byte_order": "explicit little-endian",
            "serialization": "C-order concatenated IEEE-754 binary64 bytes",
            "hash_algorithm": "hashlib.sha256",
        },
        "candidate_hashes": variants,
        "conclusion": {
            "c207_source": "Reproducible legacy PowerShell Decimal-to-Double conversion rule, not a direct canonical representation of the source JSON float values.",
            "cc97_source": "Canonical NumPy/Python float64 little-endian C-order representation of the source JSON parameters.",
            "c207_reproduced": legacy["hash"] == TARGET_HASH,
            "double_hash_convention_erratum": "proposed_pending_independent_authorization",
            "second_telemetry_backfill_started": False,
            "overall_status": "benchmark_not_validated_simulator_vqe_with_active_space_sensitivity_protocol_v2",
        },
        "audit_implementation": {
            "script_path": str(source_script_path).replace("\\", "/"),
            "script_sha256": _sha256_bytes(source_script_path.read_bytes()),
            "python_version": sys.version,
            "numpy_version": np.__version__,
            "platform": platform.platform(),
        },
    }
    output_path = ARTIFACT_ROOT / f"parameter_hash_provenance_audit_{uuid4().hex}.json"
    with output_path.open("x", encoding="utf-8") as output_file:
        json.dump(artifact, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")
    print(json.dumps({"artifact_id": output_path.stem, "c207_reproduced": legacy["hash"] == TARGET_HASH}, ensure_ascii=False))


if __name__ == "__main__":
    main()
