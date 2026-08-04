"""Stage M-B molecular input freezing services.

This package intentionally contains no electronic-structure or quantum runtime.
"""

from .service import (
    ConfirmationCrashInjected,
    MolecularWorkflowError,
    MolecularWorkflowService,
)
from .runtime_promotion import (
    MolecularRuntimePromotionError,
    MolecularRuntimePromotionResult,
    promote_molecular_runtime_no_clobber,
    validate_promoted_runtime_lineage,
)

__all__ = [
    "ConfirmationCrashInjected",
    "MolecularWorkflowError",
    "MolecularWorkflowService",
    "MolecularRuntimePromotionError",
    "MolecularRuntimePromotionResult",
    "promote_molecular_runtime_no_clobber",
    "validate_promoted_runtime_lineage",
]
