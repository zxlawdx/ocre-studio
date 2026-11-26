"""State and long-running jobs shared by the Vela editor views."""

from dataclasses import dataclass, field

from vela.jobs import JobManager

from apps.editor.service import ImageDocument
from apps.model_library.native import NativeModelRegistry
from apps.model_library.service import KokentauModel
from apps.projects.service import ProjectRepository


@dataclass(slots=True)
class Workspace:
    """Own the active document, model and the serial inference executor."""

    projects: ProjectRepository = field(default_factory=ProjectRepository)
    jobs: JobManager = field(default_factory=lambda: JobManager(io_workers=1, max_pending_jobs=1))
    native_models: NativeModelRegistry = field(default_factory=NativeModelRegistry)
    document: ImageDocument | None = None
    model: KokentauModel | None = None

    def close(self) -> None:
        """Wait for the running operation before releasing loaded models."""
        self.jobs.shutdown()
        self.native_models.clear()
        self.model = None
        self.document = None
