from __future__ import annotations

from backend.core.enums import StageName

ORDER = [
    StageName.SCREENING,
    StageName.CHEM_MODELING,
    StageName.QUANTUM_ENCODING,
    StageName.DISTRIBUTED_COMPILING,
    StageName.SIMULATION_EVALUATING,
    StageName.SCORING,
    StageName.AGGREGATING,
]


def execution_stage_names() -> list[str]:
    return [stage.value for stage in ORDER if stage is not StageName.AGGREGATING]


def result_stage_names() -> list[str]:
    return [StageName.AGGREGATING.value]


def next_stage_after_success(stage_name: StageName) -> StageName | None:
    index = ORDER.index(stage_name)
    if index == len(ORDER) - 1:
        return None
    return ORDER[index + 1]
