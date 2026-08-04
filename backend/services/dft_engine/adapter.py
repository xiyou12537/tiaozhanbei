from __future__ import annotations

import math
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

RY_TO_HARTREE = 0.5
POLL_INTERVAL_SECONDS = 0.2


class DftEngineError(RuntimeError):
    """Raised when an external DFT engine cannot safely produce an auditable result."""


class DftExecutionCancelled(DftEngineError):
    """Raised after a cooperative cancellation terminates the child process."""


class BaseDftAdapter:
    """Keep engine commands out of business services and preserve every input/output artifact."""

    engine_name: str

    def __init__(self, executable: str, pseudo_directory: str | None = None) -> None:
        self.executable = executable
        self.pseudo_directory = pseudo_directory

    def run(
        self,
        specification: dict,
        working_directory: Path,
        timeout_seconds: int,
        is_cancel_requested: Callable[[], bool],
    ) -> dict:
        working_directory.mkdir(parents=True, exist_ok=True)
        input_path = self.write_input(specification, working_directory)
        output_path = working_directory / "engine.out"
        command = self.command(input_path)
        executable = shutil.which(command[0])
        if executable is None:
            raise DftEngineError(f"未找到 {self.engine_name} 可执行文件：{command[0]}。请通过服务端环境变量配置后重试。")
        command[0] = executable
        started_at = time.monotonic()
        with input_path.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as output:
            process = subprocess.Popen(
                command,
                stdin=source,
                stdout=output,
                stderr=subprocess.STDOUT,
                cwd=working_directory,
                text=True,
            )
            while process.poll() is None:
                if is_cancel_requested():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise DftExecutionCancelled("DFT 任务已取消，子进程已终止。")
                if time.monotonic() - started_at > timeout_seconds:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    raise DftEngineError(f"{self.engine_name} 超过 {timeout_seconds} 秒资源时限。")
                time.sleep(POLL_INTERVAL_SECONDS)
        if process.returncode != 0:
            raise DftEngineError(f"{self.engine_name} 退出码为 {process.returncode}，请检查输出 Artifact。")
        parsed = self.parse_output(output_path, len(specification["atomic_sites"]))
        return {
            "engine_name": self.engine_name,
            "input_artifact_path": str(input_path),
            "output_artifact_path": str(output_path),
            "parsed_result": parsed,
        }

    def runtime_status(self) -> dict:
        """Report deployment readiness without executing a scientific calculation."""
        executable_path = shutil.which(self.executable)
        return {
            "engine_name": self.engine_name,
            "ready": executable_path is not None,
            "executable_configured": self.executable,
            "executable_resolved": executable_path,
        }

    def _electronic_state(self, metadata: dict) -> tuple[int, int, bool]:
        total_charge = metadata.get("total_charge")
        spin_multiplicity = metadata.get("spin_multiplicity")
        spin_polarization = metadata.get("spin_polarization")
        if isinstance(total_charge, bool) or not isinstance(total_charge, int):
            raise DftEngineError(f"{self.engine_name} total_charge 必须是整数。")
        if isinstance(spin_multiplicity, bool) or not isinstance(spin_multiplicity, int) or spin_multiplicity < 1:
            raise DftEngineError(f"{self.engine_name} spin_multiplicity 必须是正整数。")
        if not isinstance(spin_polarization, bool):
            raise DftEngineError(f"{self.engine_name} spin_polarization 必须是布尔值。")
        if spin_multiplicity > 1 and not spin_polarization:
            raise DftEngineError(f"开壳层 {self.engine_name} 任务必须启用自旋极化。")
        return total_charge, spin_multiplicity, spin_polarization

    @staticmethod
    def _is_finite_number(value) -> bool:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))

    def write_input(self, specification: dict, working_directory: Path) -> Path:
        raise NotImplementedError

    def command(self, input_path: Path) -> list[str]:
        raise NotImplementedError

    def parse_output(self, output_path: Path, expected_atom_count: int) -> dict:
        raise NotImplementedError


class QuantumEspressoAdapter(BaseDftAdapter):
    """Quantum ESPRESSO pw.x adapter for periodic, spin-polarized geometry calculations."""

    engine_name = "quantum_espresso"

    def runtime_status(self) -> dict:
        status = super().runtime_status()
        pseudo_directory = Path(self.pseudo_directory) if self.pseudo_directory else None
        return {
            **status,
            "pseudo_directory_configured": pseudo_directory is not None,
            "pseudo_directory_exists": bool(pseudo_directory and pseudo_directory.is_dir()),
            "request_specific_pseudopotentials_required": True,
        }

    def write_input(self, specification: dict, working_directory: Path) -> Path:
        settings = specification["engine_settings"]
        metadata = specification["calculation_metadata"]
        sites = specification["atomic_sites"]
        pseudo_map = settings.get("pseudopotentials", {})
        missing_pseudos = sorted({site["element"] for site in sites} - set(pseudo_map))
        if missing_pseudos:
            raise DftEngineError(f"Quantum ESPRESSO 缺少赝势映射：{', '.join(missing_pseudos)}。")
        k_points = settings.get("k_points", [1, 1, 1])
        if not isinstance(k_points, list) or len(k_points) != 3 or any(not isinstance(value, int) or value < 1 for value in k_points):
            raise DftEngineError("k_points 必须是三个正整数。")
        cell = settings.get("cell_parameters_angstrom")
        if cell is None:
            raise DftEngineError("Quantum ESPRESSO 周期性计算必须提供 cell_parameters_angstrom。")
        if not isinstance(cell, list) or len(cell) != 3 or any(not isinstance(row, list) or len(row) != 3 for row in cell):
            raise DftEngineError("cell_parameters_angstrom 必须是 3x3 矩阵。")
        calculation_map = {
            "geometry_optimization": "relax",
            "single_point": "scf",
            "adsorption_energy": "scf",
        }
        calculation = calculation_map.get(specification["calculation_type"])
        if calculation is None:
            raise DftEngineError("当前 Quantum ESPRESSO Adapter 未实现 NEB 或其他反应路径计算。")
        unique_elements = list(dict.fromkeys(site["element"] for site in sites))
        total_charge, spin_multiplicity, spin_polarization = self._electronic_state(metadata)
        magnetization = metadata.get("initial_magnetization_by_element") or {}
        if spin_polarization:
            missing_magnetization = sorted(set(unique_elements) - set(magnetization))
            if missing_magnetization:
                raise DftEngineError(
                    "Quantum ESPRESSO 自旋极化任务缺少元素初始磁化："
                    f"{', '.join(missing_magnetization)}。"
                )
            invalid_magnetization = [
                element
                for element in unique_elements
                if not self._is_finite_number(magnetization[element])
            ]
            if invalid_magnetization:
                raise DftEngineError(
                    "Quantum ESPRESSO 元素初始磁化必须是有限数值："
                    f"{', '.join(invalid_magnetization)}。"
                )
            if not any(abs(float(magnetization[element])) > 0 for element in unique_elements):
                raise DftEngineError("Quantum ESPRESSO 自旋极化任务至少需要一个非零元素初始磁化。")
        control_lines = ["&CONTROL", f"  calculation = '{calculation}'", "  prefix = 'liangzhi'", "  outdir = './out'", "/"]
        system_lines = [
            "&SYSTEM",
            "  ibrav = 0",
            f"  nat = {len(sites)}",
            f"  ntyp = {len(unique_elements)}",
            f"  ecutwfc = {float(settings.get('ecutwfc_ry', 60.0))}",
            f"  ecutrho = {float(settings.get('ecutrho_ry', 480.0))}",
            f"  tot_charge = {total_charge}",
            f"  nspin = {2 if spin_polarization else 1}",
        ]
        if spin_polarization:
            system_lines.extend(
                f"  starting_magnetization({index}) = {float(magnetization[element])}"
                for index, element in enumerate(unique_elements, start=1)
            )
        system_lines.extend([f"  ! requested_spin_multiplicity = {spin_multiplicity}", "/"])
        electron_lines = ["&ELECTRONS", f"  conv_thr = {float(settings.get('electronic_convergence', 1e-8))}", "/"]
        species_lines = ["ATOMIC_SPECIES"]
        for element in unique_elements:
            pseudo_path = Path(pseudo_map[element])
            if not pseudo_path.is_absolute():
                if not self.pseudo_directory:
                    raise DftEngineError(
                        "Quantum ESPRESSO 相对赝势路径需要配置 QE_PSEUDO_DIR，"
                        "或在 pseudopotentials 中提供绝对路径。"
                    )
                pseudo_path = Path(self.pseudo_directory) / pseudo_path
            if not pseudo_path.is_file():
                raise DftEngineError(f"Quantum ESPRESSO 赝势文件不存在：{pseudo_path}。")
            species_lines.append(f"{element} 1.0 {pseudo_path}")
        position_lines = ["ATOMIC_POSITIONS angstrom"] + [
            f"{site['element']} {' '.join(f'{float(value):.10f}' for value in site['position_angstrom'])}"
            for site in sites
        ]
        cell_lines = ["CELL_PARAMETERS angstrom", *[" ".join(str(float(value)) for value in row) for row in cell]]
        content = "\n".join([*control_lines, *system_lines, *electron_lines, *species_lines, *position_lines, *cell_lines, f"K_POINTS automatic\n{k_points[0]} {k_points[1]} {k_points[2]} 0 0 0", ""])
        input_path = working_directory / "pw.in"
        input_path.write_text(content, encoding="utf-8")
        return input_path

    def command(self, input_path: Path) -> list[str]:
        return [self.executable]

    def parse_output(self, output_path: Path, expected_atom_count: int) -> dict:
        content = output_path.read_text(encoding="utf-8", errors="replace")
        energies = re.findall(r"!\s+total energy\s+=\s+([+-]?[0-9.]+)\s+Ry", content)
        if not energies:
            raise DftEngineError("Quantum ESPRESSO 输出中未找到总能量。")
        result = {
            "converged": "convergence has been achieved" in content.lower(),
            "total_energy_hartree": float(energies[-1]) * RY_TO_HARTREE,
            "energy_unit": "Hartree",
        }
        optimized_sites = self._parse_last_atomic_positions(content, expected_atom_count)
        if optimized_sites:
            result["optimized_atomic_sites"] = optimized_sites
        return result

    @staticmethod
    def _parse_last_atomic_positions(content: str, expected_atom_count: int) -> list[dict] | None:
        lines = content.splitlines()
        blocks: list[list[dict]] = []
        for index, line in enumerate(lines):
            if not line.strip().upper().startswith("ATOMIC_POSITIONS"):
                continue
            block: list[dict] = []
            for raw_site in lines[index + 1 : index + 1 + expected_atom_count]:
                tokens = raw_site.split()
                if len(tokens) < 4:
                    break
                try:
                    position = [float(tokens[1]), float(tokens[2]), float(tokens[3])]
                except ValueError:
                    break
                block.append({"index": len(block), "element": tokens[0], "position_angstrom": position})
            if len(block) == expected_atom_count:
                blocks.append(block)
        return blocks[-1] if blocks else None


class Cp2kAdapter(BaseDftAdapter):
    """CP2K adapter with the same provenance contract as Quantum ESPRESSO."""

    engine_name = "cp2k"

    def runtime_status(self) -> dict:
        return {
            **super().runtime_status(),
            "request_specific_basis_and_potential_configuration_required": True,
        }

    def write_input(self, specification: dict, working_directory: Path) -> Path:
        settings = specification["engine_settings"]
        metadata = specification["calculation_metadata"]
        sites = specification["atomic_sites"]
        basis_map = settings.get("basis_sets", {})
        potential_map = settings.get("potentials", {})
        missing = sorted({site["element"] for site in sites if site["element"] not in basis_map or site["element"] not in potential_map})
        if missing:
            raise DftEngineError(f"CP2K 缺少 basis_sets 或 potentials 映射：{', '.join(missing)}。")
        coordinates = "\n".join(
            f"      {site['element']} {' '.join(f'{float(value):.10f}' for value in site['position_angstrom'])}"
            for site in sites
        )
        kind_blocks = "\n".join(
            f"    &KIND {element}\n      BASIS_SET {basis_map[element]}\n      POTENTIAL {potential_map[element]}\n    &END KIND"
            for element in sorted({site["element"] for site in sites})
        )
        run_type_map = {
            "geometry_optimization": "GEO_OPT",
            "single_point": "ENERGY",
            "adsorption_energy": "ENERGY",
        }
        run_type = run_type_map.get(specification["calculation_type"])
        if run_type is None:
            raise DftEngineError("当前 CP2K Adapter 未实现 NEB 或其他反应路径计算。")
        total_charge, spin_multiplicity, spin_polarization = self._electronic_state(metadata)
        content = f"""&GLOBAL
  PROJECT liangzhi
  RUN_TYPE {run_type}
&END GLOBAL
&FORCE_EVAL
  METHOD Quickstep
  &DFT
    BASIS_SET_FILE_NAME {settings.get('basis_set_file', 'BASIS_MOLOPT')}
    POTENTIAL_FILE_NAME {settings.get('potential_file', 'GTH_POTENTIALS')}
    CHARGE {total_charge}
    MULTIPLICITY {spin_multiplicity}
    UKS {'.TRUE.' if spin_polarization else '.FALSE.'}
    &SCF
      EPS_SCF {float(settings.get('electronic_convergence', 1e-6))}
    &END SCF
  &END DFT
  &SUBSYS
    &COORD
{coordinates}
    &END COORD
{kind_blocks}
  &END SUBSYS
&END FORCE_EVAL
"""
        input_path = working_directory / "cp2k.inp"
        input_path.write_text(content, encoding="utf-8")
        return input_path

    def command(self, input_path: Path) -> list[str]:
        return [self.executable, "-i", str(input_path)]

    def parse_output(self, output_path: Path, expected_atom_count: int) -> dict:
        content = output_path.read_text(encoding="utf-8", errors="replace")
        energies = re.findall(r"ENERGY\| Total FORCE_EVAL.*?:\s*([+-]?[0-9.]+)", content)
        if not energies:
            raise DftEngineError("CP2K 输出中未找到总能量。")
        return {
            "converged": "PROGRAM ENDED AT" in content,
            "total_energy_hartree": float(energies[-1]),
            "energy_unit": "Hartree",
        }
