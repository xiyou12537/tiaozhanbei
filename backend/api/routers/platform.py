from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from backend.api.schemas.platform import (
    CandidateCatalogResponse,
    CandidateExplanationResponse,
    CaseCatalogResponse,
    ActiveSiteConfirmRequest,
    ActiveSpaceConfirmRequest,
    BenchmarkCaseCreateRequest,
    DftImportCreateRequest,
    DirectDftCalculationCreateRequest,
    ElectronicStructureCandidateConfirmRequest,
    ElectronicStructureCandidateCreateRequest,
    QubitMappingRequest,
    QuantumClosureBenchmarkCreateRequest,
    ResearchBenchmarkImportRequest,
    VqeCircuitCreateRequest,
    AdsorptionModelCreateRequest,
    GeometryOptimizationCreateRequest,
    QuantumRegionCreateRequest,
    ScreeningLeaderboardResponse,
    ScreeningWorkflowListItemResponse,
    ScreeningStageResponse,
    ScreeningWorkflowCreateRequest,
    ScreeningWorkflowCreateResponse,
    ScreeningWorkflowPayloadResponse,
    WorkflowArtifactsResponse,
    WorkflowCancelResponse,
    WorkflowCreateRequest,
    WorkflowCreateResponse,
    WorkflowDetailResponse,
    WorkflowEventResponse,
    WorkflowResultResponse,
    WorkflowStageResponse,
    WorkflowSummaryResponse,
    StructureFileListResponse,
    StructureFileResponse,
    DistributedCompilationCreateRequest,
    DistributedCompilationResponse,
    DistributedSimulationStartRequest,
    DistributedSimulationResponse,
    DistributedValidationReportResponse,
    MolecularModelCreateRequest,
    MolecularModelConfirmRequest,
    MolecularElectronicStructureCreateRequest,
)
from backend.core.config import settings
from backend.db.repositories.screening_workflow_repository import ScreeningWorkflowRepository
from backend.db.repositories.workflow_repository import WorkflowRepository
from backend.orchestrator.dispatcher import RabbitMQStageDispatcher
from backend.orchestrator.engine import OrchestratorEngine
from backend.services.candidate.service import CandidateService
from backend.services.screening_workflow import ScreeningWorkflowService
from backend.services.structure_modeling import StructureModelingService
from backend.services.structure_modeling.service import MAX_ATOMIC_SITES_PAGE_SIZE, MAX_FILE_SIZE_BYTES, StructureModelingError
from backend.services.molecular_workflow import (
    MolecularWorkflowError,
    MolecularWorkflowService,
)
from backend.db.repositories.distributed_validation_repository import (
    DistributedIdempotencyConflictError,
    DistributedNotFoundError,
    DistributedRepositoryError,
    DistributedStateConflictError,
)
from backend.services.distributed_validation.service import (
    DistributedValidationService,
    DistributedValidationServiceError,
)
from backend.middleware import get_current_user
from backend.models_db import User

router = APIRouter(prefix="/api/platform", tags=["platform"])
logger = logging.getLogger(__name__)
WORKFLOW_REPOSITORY = WorkflowRepository()
queue_dispatcher = RabbitMQStageDispatcher()
engine = OrchestratorEngine(dispatcher=queue_dispatcher, repository=WORKFLOW_REPOSITORY)
candidate_service = CandidateService()
screening_workflow_service = ScreeningWorkflowService()
screening_workflow_repository = ScreeningWorkflowRepository()
structure_modeling_service = StructureModelingService()
distributed_validation_service = DistributedValidationService()
molecular_workflow_service = MolecularWorkflowService()
SCREENING_WORKFLOWS: dict[str, dict] = {}
CASE_CATALOG = [
    {"case_id": "case-li2s6-baseline", "title": "Li2S6 baseline screening", "candidate_material": "Li2S6"},
    {"case_id": "case-s8-host-a", "title": "Sulfur host comparison A", "candidate_material": "S8-Host-A"},
    {"case_id": "li-s-demo", "title": "Li-S catalyst multi-material screening", "candidate_material": "Fe-N4/C"},
]


def _raise_structure_error(exc: StructureModelingError) -> None:
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc


def _raise_molecular_error(exc: MolecularWorkflowError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    ) from exc


def _raise_distributed_error(exc: Exception) -> None:
    if isinstance(exc, DistributedNotFoundError):
        status_code = 404
        code = "distributed_resource_not_found"
    elif isinstance(exc, DistributedIdempotencyConflictError):
        status_code = 409
        code = "idempotency_conflict"
    elif isinstance(exc, DistributedStateConflictError):
        status_code = 409
        code = "distributed_state_conflict"
    elif isinstance(exc, DistributedValidationServiceError):
        status_code = 422 if exc.code.endswith("mismatch") else 409
        code = exc.code
    elif isinstance(exc, DistributedRepositoryError):
        status_code = 409
        code = "distributed_repository_error"
    else:
        status_code = 500
        code = "distributed_validation_internal_error"
        logger.exception("Unexpected distributed-validation error.")
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _require_research_benchmark_admin(user: User) -> None:
    """Limit immutable public-dataset imports to explicitly configured administrators."""
    allowed_usernames = {name.strip() for name in settings.RESEARCH_BENCHMARK_ADMIN_USERNAMES.split(",") if name.strip()}
    if user.username not in allowed_usernames:
        raise HTTPException(status_code=403, detail={"code": "research_benchmark_admin_required", "message": "仅配置的文献基准管理员可以执行导入。"})


def _get_screening_workflow_or_404(workflow_id: str) -> dict:
    workflow = SCREENING_WORKFLOWS.get(workflow_id)
    if workflow is None:
        workflow = screening_workflow_repository.get_workflow(workflow_id)
        if workflow is not None:
            SCREENING_WORKFLOWS[workflow_id] = workflow
    if workflow is None:
        raise HTTPException(status_code=404, detail="Screening workflow not found.")
    return workflow


@router.post("/workflows", response_model=WorkflowCreateResponse)
def create_workflow(body: WorkflowCreateRequest):
    workflow_id = str(uuid4())
    payload = engine.build_initial_workflow_payload(
        workflow_id=workflow_id,
        candidate_material=body.candidate_material,
    )
    payload["case_id"] = body.case_id
    execution_mode = (body.execution_mode or settings.WORKFLOW_EXECUTION_MODE).lower()
    if execution_mode == "queued":
        try:
            workflow = engine.enqueue_workflow(payload)
        except Exception as exc:
            logger.warning("Queued workflow dispatch failed; falling back to sync execution: %s", exc)
            workflow = engine.execute_workflow(payload)
    else:
        workflow = engine.execute_workflow(payload)

    return WorkflowCreateResponse(
        workflow_id=workflow["workflow_id"],
        overall_status=workflow["overall_status"],
        current_stage=workflow["current_stage"],
    )


@router.post("/screening-workflows", response_model=ScreeningWorkflowCreateResponse)
def create_screening_workflow(body: ScreeningWorkflowCreateRequest):
    try:
        workflow = screening_workflow_service.create_workflow(
            case_id=body.case_id,
            candidate_materials=body.candidate_materials,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    workflow = screening_workflow_repository.save_workflow(workflow)
    SCREENING_WORKFLOWS[workflow["workflow_id"]] = workflow
    return ScreeningWorkflowCreateResponse(
        workflow_id=workflow["workflow_id"],
        case_id=workflow["case_id"],
        status=workflow["status"],
        candidate_count=workflow["candidate_count"],
        recommended_material=workflow["recommended_material"],
        created_at=workflow.get("created_at", ""),
        updated_at=workflow.get("updated_at", ""),
    )


@router.get("/screening-workflows/{workflow_id}", response_model=ScreeningWorkflowPayloadResponse)
def get_screening_workflow(workflow_id: str):
    workflow = _get_screening_workflow_or_404(workflow_id)
    return ScreeningWorkflowPayloadResponse(**workflow)


@router.get("/screening-workflows", response_model=list[ScreeningWorkflowListItemResponse])
def list_screening_workflows():
    return [ScreeningWorkflowListItemResponse(**item) for item in screening_workflow_repository.list_workflows()]


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetailResponse)
def get_workflow(workflow_id: str):
    payload = WORKFLOW_REPOSITORY.get_workflow(workflow_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    return WorkflowDetailResponse(
        workflow_id=payload["workflow_id"],
        overall_status=payload["overall_status"],
        current_stage=payload["current_stage"],
        candidate_material=payload["candidate_material"],
        completed_stage_count=payload["completed_stage_count"],
        total_stage_count=payload["total_stage_count"],
    )


@router.get("/workflows/{workflow_id}/stages", response_model=list[WorkflowStageResponse])
def get_workflow_stages(workflow_id: str):
    if not WORKFLOW_REPOSITORY.has_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return [WorkflowStageResponse(**item) for item in WORKFLOW_REPOSITORY.list_stage_runs(workflow_id)]


@router.get("/workflows/{workflow_id}/events", response_model=list[WorkflowEventResponse])
def get_workflow_events(workflow_id: str):
    if not WORKFLOW_REPOSITORY.has_workflow(workflow_id):
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return [WorkflowEventResponse(**item) for item in WORKFLOW_REPOSITORY.list_events(workflow_id)]


@router.get("/workflows/{workflow_id}/result", response_model=WorkflowResultResponse)
def get_workflow_result(workflow_id: str):
    workflow = WORKFLOW_REPOSITORY.get_workflow(workflow_id)
    result_view = WORKFLOW_REPOSITORY.get_result_view(workflow_id)
    if workflow is None or result_view is None:
        raise HTTPException(status_code=404, detail="Workflow result not found.")

    return WorkflowResultResponse(
        workflow_id=workflow["workflow_id"],
        overall_status=workflow["overall_status"],
        candidate_material=workflow["candidate_material"],
        result_view=result_view,
    )


@router.get("/workflows/{workflow_id}/summary", response_model=WorkflowSummaryResponse)
def get_workflow_summary(workflow_id: str):
    workflow = WORKFLOW_REPOSITORY.get_workflow(workflow_id)
    result_view = WORKFLOW_REPOSITORY.get_result_view(workflow_id)
    if workflow is None or result_view is None:
        raise HTTPException(status_code=404, detail="Workflow summary not found.")

    return WorkflowSummaryResponse(
        workflow_id=workflow["workflow_id"],
        current_stage=workflow["current_stage"],
        overall_status=workflow["overall_status"],
        summary=result_view["summary"],
    )


@router.get("/workflows/{workflow_id}/artifacts", response_model=WorkflowArtifactsResponse)
def get_workflow_artifacts(workflow_id: str):
    workflow = WORKFLOW_REPOSITORY.get_workflow(workflow_id)
    result_view = WORKFLOW_REPOSITORY.get_result_view(workflow_id)
    if workflow is None or result_view is None:
        raise HTTPException(status_code=404, detail="Workflow artifacts not found.")

    return WorkflowArtifactsResponse(
        workflow_id=workflow["workflow_id"],
        artifacts=result_view["artifacts"],
    )


@router.get("/workflows/{workflow_id}/classical-screening", response_model=ScreeningStageResponse)
def get_classical_screening(workflow_id: str):
    workflow = _get_screening_workflow_or_404(workflow_id)
    return ScreeningStageResponse(
        workflow_id=workflow_id,
        results=[
            {
                "candidate_material": item["candidate_material"],
                "material_profile": item["material_profile"],
                "screening": item["screening"],
            }
            for item in workflow["candidate_results"]
        ],
    )


@router.get("/workflows/{workflow_id}/quantum-refinement", response_model=ScreeningStageResponse)
def get_quantum_refinement(workflow_id: str):
    workflow = _get_screening_workflow_or_404(workflow_id)
    refined = [
        item
        for item in workflow["candidate_results"]
        if item["screening"]["passed"] or item["score"]["rank_position"] <= 2
    ]
    return ScreeningStageResponse(
        workflow_id=workflow_id,
        results=[
            {
                "candidate_material": item["candidate_material"],
                "chemistry_model": item["chemistry_model"],
                "quantum_problem": item["quantum_problem"],
                "distributed_execution": item["distributed_execution"],
                "quantum_refinement": item["quantum_refinement"],
            }
            for item in refined
        ],
    )


@router.get("/workflows/{workflow_id}/leaderboard", response_model=ScreeningLeaderboardResponse)
def get_screening_leaderboard(workflow_id: str):
    workflow = _get_screening_workflow_or_404(workflow_id)
    return ScreeningLeaderboardResponse(
        workflow_id=workflow_id,
        candidate_count=workflow["candidate_count"],
        recommended_material=workflow["recommended_material"],
        leaderboard=workflow["leaderboard"],
    )


@router.get(
    "/workflows/{workflow_id}/candidates/{candidate_material}/explanation",
    response_model=CandidateExplanationResponse,
)
def get_candidate_explanation(workflow_id: str, candidate_material: str):
    return _build_candidate_explanation_response(workflow_id, candidate_material)


@router.get(
    "/workflows/{workflow_id}/candidate-explanations/{material_id}",
    response_model=CandidateExplanationResponse,
)
def get_candidate_explanation_by_material_id(workflow_id: str, material_id: str):
    return _build_candidate_explanation_response(workflow_id, material_id)


def _build_candidate_explanation_response(workflow_id: str, candidate_key: str):
    workflow = _get_screening_workflow_or_404(workflow_id)
    for item in workflow["candidate_results"]:
        if item["candidate_material"] == candidate_key or item["material_profile"]["material_id"] == candidate_key:
            return CandidateExplanationResponse(
                workflow_id=workflow_id,
                candidate_material=item["candidate_material"],
                explanation=item["explanation"],
            )
    raise HTTPException(status_code=404, detail="Candidate material not found in workflow.")


@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowCancelResponse)
def cancel_workflow(workflow_id: str):
    workflow = WORKFLOW_REPOSITORY.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    if workflow["overall_status"] == "completed":
        raise HTTPException(status_code=409, detail="Completed workflow cannot be cancelled.")

    WORKFLOW_REPOSITORY.update_workflow(
        workflow_id,
        current_stage=workflow["current_stage"],
        overall_status="cancelled",
        completed_stage_count=workflow["completed_stage_count"],
    )
    WORKFLOW_REPOSITORY.append_event(workflow_id, "workflow_cancelled", workflow["current_stage"], {})
    return WorkflowCancelResponse(
        workflow_id=workflow_id,
        overall_status="cancelled",
        message="Workflow cancelled.",
    )


@router.get("/cases", response_model=list[CaseCatalogResponse])
def get_cases():
    return [CaseCatalogResponse(**item) for item in CASE_CATALOG]


@router.get("/candidates", response_model=list[CandidateCatalogResponse])
def get_candidates():
    enriched_candidates = []
    for item in screening_workflow_service.list_materials():
        enriched_candidates.append(
            CandidateCatalogResponse(
                candidate_name=item["material_name"],
                family=item["material_family"],
                adsorption_strength=abs(item["adsorption_energy_li2s6"]),
                **item,
            )
        )
    return enriched_candidates


@router.post("/structure-files", response_model=StructureFileResponse, status_code=201)
async def upload_structure_file(
    file: UploadFile = File(...),
    material_name: str = Form(..., min_length=1, max_length=100),
    material_family: str | None = Form(default=None, max_length=100),
    description: str | None = Form(default=None, max_length=1000),
    input_purpose: str = Form(..., pattern="^(legacy_screening|molecular_logical_circuit)$"),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
):
    """Store an authenticated user's structure source file without starting scientific scoring."""
    content = await file.read(MAX_FILE_SIZE_BYTES + 1)
    try:
        return structure_modeling_service.upload_structure_file(
            owner_user_id=user.id,
            material_name=material_name.strip(),
            material_family=material_family.strip() if material_family else None,
            description=description.strip() if description else None,
            original_filename=file.filename or "",
            content=content,
            input_purpose=input_purpose,
            idempotency_key=idempotency_key,
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)
    finally:
        await file.close()


@router.post("/structure-files/{file_id}/parse")
def parse_structure_file(file_id: str, user: User = Depends(get_current_user)):
    """Parse and validate a previously uploaded structure file synchronously."""
    try:
        return structure_modeling_service.parse_structure_file(file_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-files/{file_id}", response_model=StructureFileResponse)
def get_structure_file(file_id: str, user: User = Depends(get_current_user)):
    """Return a user-owned structure file's status without exposing the stored file path."""
    try:
        return structure_modeling_service.get_file(file_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-files", response_model=StructureFileListResponse)
def list_structure_files(
    parse_status: str | None = Query(default=None, max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List only the authenticated user's uploaded structure files."""
    return structure_modeling_service.list_files(user.id, parse_status, page, page_size)


@router.get("/structures/{structure_id}")
def get_structure(
    structure_id: str,
    include_atomic_sites: bool = Query(default=True),
    user: User = Depends(get_current_user),
):
    """Return normalized structural metadata and, optionally, atomic coordinates."""
    try:
        return structure_modeling_service.get_structure(structure_id, user.id, include_atomic_sites)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structures/{structure_id}/atomic-sites")
def list_structure_atomic_sites(
    structure_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, ge=1, le=MAX_ATOMIC_SITES_PAGE_SIZE),
    user: User = Depends(get_current_user),
):
    """Page atomic coordinates to prevent large structures from expanding detail responses."""
    try:
        return structure_modeling_service.list_atomic_sites(structure_id, user.id, page, page_size)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/structures/{structure_id}/molecular-models", status_code=201)
def create_molecular_model(
    structure_id: str,
    body: MolecularModelCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
):
    """Create an owner-scoped strict-XYZ draft without publishing Artifacts."""
    try:
        result = molecular_workflow_service.create_model(
            structure_id=structure_id,
            owner_user_id=user.id,
            idempotency_key=idempotency_key,
            request=body.model_dump(mode="json"),
        )
        return JSONResponse(status_code=result.status_code, content=result.payload)
    except MolecularWorkflowError as exc:
        _raise_molecular_error(exc)


@router.get("/molecular-models/{molecular_model_id}")
def get_molecular_model(
    molecular_model_id: str,
    user: User = Depends(get_current_user),
):
    """Return a molecular model only to its owner."""
    try:
        return molecular_workflow_service.get_model(molecular_model_id, user.id)
    except MolecularWorkflowError as exc:
        _raise_molecular_error(exc)


@router.post("/molecular-models/{molecular_model_id}/confirm")
def confirm_molecular_model(
    molecular_model_id: str,
    body: MolecularModelConfirmRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
):
    """Freeze charge/spin and publish the two M-B Artifacts in protocol order."""
    try:
        result = molecular_workflow_service.confirm_model(
            molecular_model_id=molecular_model_id,
            owner_user_id=user.id,
            idempotency_key=idempotency_key,
            request=body.model_dump(mode="json"),
        )
        return JSONResponse(status_code=result.status_code, content=result.payload)
    except MolecularWorkflowError as exc:
        _raise_molecular_error(exc)


@router.post(
    "/molecular-models/{molecular_model_id}/electronic-structure-calculations"
)
def create_molecular_electronic_structure_calculation(
    molecular_model_id: str,
    body: MolecularElectronicStructureCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
):
    """Reject M-C admission before any calculation, attempt, or idempotency row."""
    del body, idempotency_key
    try:
        molecular_workflow_service.reject_electronic_structure_admission(
            molecular_model_id,
            user.id,
        )
    except MolecularWorkflowError as exc:
        _raise_molecular_error(exc)


@router.get("/molecular-models/{molecular_model_id}/logical-circuit-workflow")
def get_molecular_logical_circuit_workflow(
    molecular_model_id: str,
    user: User = Depends(get_current_user),
):
    """Return persisted lineage, publication status, and sealed M-C state."""
    try:
        return molecular_workflow_service.get_logical_workflow(
            molecular_model_id,
            user.id,
        )
    except MolecularWorkflowError as exc:
        _raise_molecular_error(exc)


@router.post("/structures/{structure_id}/active-sites/suggest")
def suggest_active_sites(structure_id: str, user: User = Depends(get_current_user)):
    """Generate rule-based candidate active sites that require explicit user confirmation."""
    try:
        return structure_modeling_service.suggest_active_sites(structure_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/structures/{structure_id}/active-sites/confirm")
def confirm_active_site(
    structure_id: str,
    body: ActiveSiteConfirmRequest,
    user: User = Depends(get_current_user),
):
    """Freeze the user's selected active site for all subsequent modeling stages."""
    try:
        return structure_modeling_service.confirm_active_site(structure_id, user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/active-sites/{active_site_id}/adsorption-models")
def generate_adsorption_models(
    active_site_id: str,
    body: AdsorptionModelCreateRequest,
    user: User = Depends(get_current_user),
):
    """Generate traceable Li2S4/Li2S6 initial conformations without calculating adsorption energies."""
    species = list(dict.fromkeys(body.polysulfide_species))
    if len(species) != len(body.polysulfide_species) or any(item not in {"Li2S4", "Li2S6"} for item in species):
        raise HTTPException(status_code=422, detail={"code": "invalid_polysulfide_species", "message": "仅支持且不能重复指定 Li2S4、Li2S6。"})
    try:
        request = body.model_dump()
        request["polysulfide_species"] = species
        return structure_modeling_service.generate_adsorption_models(active_site_id, user.id, request)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/benchmark-cases", status_code=201)
def create_benchmark_case(body: BenchmarkCaseCreateRequest, user: User = Depends(get_current_user)):
    """Create a versioned research input package without treating a small FeN4 cluster as a final benchmark."""
    try:
        return structure_modeling_service.create_benchmark_case(user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/research-benchmarks/import-materials-cloud", status_code=201)
def import_materials_cloud_research_benchmark(
    body: ResearchBenchmarkImportRequest,
    user: User = Depends(get_current_user),
):
    """Import the approved Materials Cloud FeN4C66-Li2S4 dataset with source checksums."""
    _require_research_benchmark_admin(user)
    try:
        return structure_modeling_service.import_materials_cloud_benchmark(user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/research-benchmarks")
def list_research_benchmarks(
    benchmark_key: str | None = Query(default=None, max_length=128),
    user: User = Depends(get_current_user),
):
    """Discover imported benchmarks without requiring a database-generated ID."""
    try:
        response = structure_modeling_service.list_research_benchmarks(benchmark_key)
        allowed_usernames = {
            name.strip()
            for name in settings.RESEARCH_BENCHMARK_ADMIN_USERNAMES.split(",")
            if name.strip()
        }
        response["can_import"] = user.username in allowed_usernames
        return response
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/research-benchmarks/{benchmark_id}")
def get_research_benchmark(benchmark_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_research_benchmark(benchmark_id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/research-benchmarks/{benchmark_id}/candidates")
def list_research_benchmark_candidates(benchmark_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.list_research_benchmark_candidates(benchmark_id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/research-benchmarks/{benchmark_id}/candidates/{candidate_id}/artifact")
def get_research_benchmark_candidate_artifact_metadata(
    benchmark_id: str,
    candidate_id: str,
    user: User = Depends(get_current_user),
):
    """Return public-candidate coordinate metadata; bytes stay restricted to a selected user workflow."""
    try:
        return structure_modeling_service.get_research_benchmark_candidate_artifact_metadata(benchmark_id, candidate_id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/research-benchmarks/{benchmark_id}/candidates/{candidate_id}/select", status_code=201)
def select_research_benchmark_candidate(
    benchmark_id: str,
    candidate_id: str,
    user: User = Depends(get_current_user),
):
    try:
        return structure_modeling_service.select_research_benchmark_candidate(benchmark_id, candidate_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/adsorption-models/{adsorption_model_id}/geometry-optimizations")
def create_geometry_optimization(
    adsorption_model_id: str,
    body: GeometryOptimizationCreateRequest,
    user: User = Depends(get_current_user),
):
    """Relax a generated conformation or register an externally optimized geometry without assigning DFT energy."""
    try:
        return structure_modeling_service.create_geometry_optimization(adsorption_model_id, user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/adsorption-models/{adsorption_model_id}/dft-imports", status_code=201)
def import_dft_result(
    adsorption_model_id: str,
    body: DftImportCreateRequest,
    user: User = Depends(get_current_user),
):
    """Archive auditable external DFT output and only promote complete inputs to dft_optimized."""
    try:
        return structure_modeling_service.import_dft_result(adsorption_model_id, user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/dft-imports/{dft_import_id}")
def get_dft_import(dft_import_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_dft_import(dft_import_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/adsorption-models/{adsorption_model_id}/dft-calculations", status_code=202)
def submit_direct_dft_calculation(
    adsorption_model_id: str,
    body: DirectDftCalculationCreateRequest,
    user: User = Depends(get_current_user),
):
    """Queue a direct QE/CP2K job through a bounded server-side adapter."""
    try:
        return structure_modeling_service.submit_direct_dft_calculation(
            adsorption_model_id,
            user.id,
            body.model_dump(),
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/dft-runtime")
def get_dft_runtime_status(user: User = Depends(get_current_user)):
    """Report engine deployment readiness without claiming scientific approval."""
    return structure_modeling_service.get_dft_runtime_status()


@router.get("/dft-calculations/{dft_calculation_id}")
def get_direct_dft_calculation(dft_calculation_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_direct_dft_calculation(dft_calculation_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/dft-calculations/{dft_calculation_id}/cancel", status_code=202)
def cancel_direct_dft_calculation(dft_calculation_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.cancel_direct_dft_calculation(dft_calculation_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/dft-calculations/{dft_calculation_id}/retry", status_code=202)
def retry_direct_dft_calculation(dft_calculation_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.retry_direct_dft_calculation(dft_calculation_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/adsorption-models/{adsorption_model_id}/quantum-regions")
def build_quantum_region(
    adsorption_model_id: str,
    body: QuantumRegionCreateRequest,
    user: User = Depends(get_current_user),
):
    """Extract a local frozen-environment quantum region and preserve charge/spin provenance."""
    try:
        return structure_modeling_service.build_quantum_region(adsorption_model_id, user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/quantum-regions/{quantum_region_id}/active-space-candidates")
def generate_active_space_candidates(quantum_region_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.generate_active_space_candidates(quantum_region_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/quantum-regions/{quantum_region_id}/electronic-structure-candidates", status_code=202)
def submit_electronic_structure_candidates(
    quantum_region_id: str,
    body: ElectronicStructureCandidateCreateRequest,
    user: User = Depends(get_current_user),
):
    """Queue independent charge/spin candidates; no candidate is automatically accepted by energy alone."""
    try:
        return structure_modeling_service.submit_electronic_structure_candidates(
            quantum_region_id,
            user.id,
            body.model_dump(),
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/electronic-structure-candidates/{candidate_id}")
def get_electronic_structure_candidate(candidate_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_electronic_structure_candidate(candidate_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/electronic-structure-candidates/{candidate_id}/confirm")
def confirm_electronic_structure_candidate(
    candidate_id: str,
    body: ElectronicStructureCandidateConfirmRequest,
    user: User = Depends(get_current_user),
):
    try:
        return structure_modeling_service.confirm_electronic_structure_candidate(
            candidate_id,
            user.id,
            body.model_dump(),
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/quantum-regions/{quantum_region_id}/active-space-candidates/queued")
def queue_active_space_candidates(quantum_region_id: str, user: User = Depends(get_current_user)):
    try: return structure_modeling_service.submit_active_space_candidates(quantum_region_id, user.id)
    except StructureModelingError as exc: _raise_structure_error(exc)


@router.get("/structure-tasks/{task_id}")
def get_structure_task(task_id: str, user: User = Depends(get_current_user)):
    try: return structure_modeling_service.get_background_task(task_id, user.id)
    except StructureModelingError as exc: _raise_structure_error(exc)


@router.post("/quantum-regions/{quantum_region_id}/active-space-confirm")
def confirm_active_space(quantum_region_id: str, body: ActiveSpaceConfirmRequest, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.confirm_active_space(quantum_region_id, body.active_space_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/active-spaces/{active_space_id}/fermionic-hamiltonians")
def build_fermionic_hamiltonian(active_space_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.build_fermionic_hamiltonian(active_space_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/fermionic-hamiltonians/{hamiltonian_id}/qubit-mappings")
def map_fermionic_hamiltonian(hamiltonian_id: str, body: QubitMappingRequest, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.map_fermionic_hamiltonian(hamiltonian_id, user.id, body.model_dump())
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/fermionic-hamiltonians/{hamiltonian_id}/classical-references", status_code=201)
def generate_classical_reference(hamiltonian_id: str, user: User = Depends(get_current_user)):
    """Create a bounded PySCF FCI reference for closed- or open-shell active spaces when feasible."""
    try:
        return structure_modeling_service.generate_classical_reference(hamiltonian_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/fermionic-hamiltonians/{hamiltonian_id}/quantum-closure-benchmarks", status_code=201)
def create_quantum_closure_benchmark(
    hamiltonian_id: str,
    body: QuantumClosureBenchmarkCreateRequest,
    user: User = Depends(get_current_user),
):
    try:
        return structure_modeling_service.create_quantum_closure_benchmark(
            hamiltonian_id,
            user.id,
            body.model_dump(),
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post("/qubit-hamiltonians/{qubit_hamiltonian_id}/vqe-circuits")
def compile_vqe_circuit(qubit_hamiltonian_id: str, body: VqeCircuitCreateRequest, user: User = Depends(get_current_user)):
    try: return structure_modeling_service.compile_vqe_circuit(qubit_hamiltonian_id, user.id, body.model_dump())
    except StructureModelingError as exc: _raise_structure_error(exc)


@router.post("/vqe-circuits/{vqe_circuit_id}/executions")
def execute_vqe_circuit(vqe_circuit_id: str, user: User = Depends(get_current_user)):
    try: return structure_modeling_service.execute_vqe_circuit(vqe_circuit_id, user.id)
    except StructureModelingError as exc: _raise_structure_error(exc)


@router.get("/vqe-executions/{execution_id}")
def get_vqe_execution(execution_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_vqe_execution(execution_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/quantum-closure-benchmarks/{closure_benchmark_id}")
def get_quantum_closure_benchmark(closure_benchmark_id: str, user: User = Depends(get_current_user)):
    try:
        return structure_modeling_service.get_quantum_closure_benchmark(closure_benchmark_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-screening-workflows")
def list_structure_screening_workflows(
    status: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
):
    """List the authenticated user's structure-modeling workflows."""
    return structure_modeling_service.list_structure_workflows(
        user.id,
        status,
        page,
        page_size,
    )


@router.get("/structure-screening-workflows/{workflow_id}/artifacts/{artifact_id}")
def get_structure_workflow_artifact(
    workflow_id: str,
    artifact_id: str,
    user: User = Depends(get_current_user),
):
    """Return Artifact metadata only after workflow and owner checks pass."""
    try:
        return structure_modeling_service.get_structure_artifact_metadata(
            workflow_id,
            artifact_id,
            user.id,
        )
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-screening-workflows/{workflow_id}/artifacts/{artifact_id}/download")
def download_structure_workflow_artifact(
    workflow_id: str,
    artifact_id: str,
    user: User = Depends(get_current_user),
):
    """Download an owned workflow Artifact without exposing its storage path."""
    try:
        artifact_path, filename, media_type = structure_modeling_service.resolve_structure_artifact_download(
            workflow_id,
            artifact_id,
            user.id,
        )
        return FileResponse(artifact_path, media_type=media_type, filename=filename)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-screening-workflows/{workflow_id}/quantum-closure-benchmarks")
def list_structure_workflow_quantum_closure_benchmarks(
    workflow_id: str,
    user: User = Depends(get_current_user),
):
    try:
        return structure_modeling_service.list_quantum_closure_benchmarks(workflow_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.get("/structure-screening-workflows/{workflow_id}")
def get_structure_screening_workflow(workflow_id: str, user: User = Depends(get_current_user)):
    """Return the status and evidence chain for a user-uploaded structure workflow."""
    try:
        return structure_modeling_service.get_structure_workflow(workflow_id, user.id)
    except StructureModelingError as exc:
        _raise_structure_error(exc)


@router.post(
    "/vqe-executions/{execution_id}/distributed-compilations",
    response_model=DistributedCompilationResponse,
    status_code=201,
)
def create_distributed_compilation(
    execution_id: str,
    body: DistributedCompilationCreateRequest,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    user: User = Depends(get_current_user),
):
    """Compile the frozen 4q QASM; this endpoint cannot authorize Stage C."""
    del body
    try:
        return distributed_validation_service.create_and_compile(
            owner_user_id=user.id,
            vqe_execution_id=execution_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_distributed_error(exc)


@router.get(
    "/vqe-executions/{vqe_execution_id}/distributed-compilations",
    response_model=list[DistributedCompilationResponse],
)
def list_vqe_execution_distributed_compilations(
    vqe_execution_id: str,
    user: User = Depends(get_current_user),
):
    """Return compilations for exactly one owner-scoped VQE execution."""
    try:
        return (
            distributed_validation_service.repository
            .list_compilations_for_execution(
                vqe_execution_id,
                user.id,
            )
        )
    except Exception as exc:
        _raise_distributed_error(exc)


@router.get(
    "/distributed-compilations/{compilation_id}",
    response_model=DistributedCompilationResponse,
)
def get_distributed_compilation(
    compilation_id: str,
    user: User = Depends(get_current_user),
):
    """Return one owner-scoped distributed compilation."""
    record = distributed_validation_service.repository.get_compilation(
        compilation_id,
        user.id,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "distributed_resource_not_found",
                "message": "Compilation does not exist.",
            },
        )
    return record


@router.post(
    "/distributed-compilations/{compilation_id}/simulations",
    response_model=DistributedSimulationResponse,
    status_code=201,
)
def start_distributed_simulation(
    compilation_id: str,
    body: DistributedSimulationStartRequest,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
    ),
    user: User = Depends(get_current_user),
):
    """Atomically consume the only Stage-B formal statevector attempt."""
    del body
    try:
        return distributed_validation_service.run_formal_simulation(
            owner_user_id=user.id,
            compilation_id=compilation_id,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:
        _raise_distributed_error(exc)


@router.get(
    "/distributed-simulations/{simulation_id}",
    response_model=DistributedSimulationResponse,
)
def get_distributed_simulation(
    simulation_id: str,
    user: User = Depends(get_current_user),
):
    """Return one owner-scoped distributed simulation."""
    record = distributed_validation_service.repository.get_simulation(
        simulation_id,
        user.id,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "distributed_resource_not_found",
                "message": "Simulation does not exist.",
            },
        )
    return record


@router.get(
    "/distributed-simulations/{simulation_id}/validation-report",
    response_model=DistributedValidationReportResponse,
)
def get_distributed_validation_report(
    simulation_id: str,
    user: User = Depends(get_current_user),
):
    """Return immutable report metadata after an owner check."""
    record = distributed_validation_service.repository.get_simulation(
        simulation_id,
        user.id,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "distributed_resource_not_found",
                "message": "Simulation does not exist.",
            },
        )
    if not record.validation_report_path or not record.validation_report_sha256:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "validation_report_not_ready",
                "message": "Validation report is not available.",
            },
        )
    return DistributedValidationReportResponse(
        simulation_id=record.simulation_id,
        compilation_id=record.compilation_id,
        qualification_status=record.qualification_status,
        validation_report_path=record.validation_report_path,
        validation_report_sha256=record.validation_report_sha256,
        actual_distributed_hardware_execution=(
            record.actual_distributed_hardware_execution
        ),
    )
