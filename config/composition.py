"""State and long-running jobs shared by the Vela editor views."""

from dataclasses import dataclass, field
from threading import Lock

from vela.jobs import JobManager

from apps.editor.service import ImageDocument
from apps.model_library.native import NativeModelRegistry
from apps.model_library.service import KokentauModel
from apps.projects.batch import Batch
from apps.projects.catalog import Catalog, Session
from apps.projects.recent import RecentProjects
from apps.projects.service import ProjectRepository


@dataclass(slots=True)
class Workspace:
    """Own the active document, model and the serial inference executor."""

    projects: ProjectRepository = field(default_factory=ProjectRepository)
    jobs: JobManager = field(default_factory=lambda: JobManager(io_workers=1, max_pending_jobs=1))
    inference_jobs: JobManager = field(
        default_factory=lambda: JobManager(io_workers=1, max_pending_jobs=3)
    )
    batch_jobs: JobManager = field(
        default_factory=lambda: JobManager(io_workers=1, max_pending_jobs=1)
    )
    batch: Batch = field(default_factory=Batch)
    inference_lock: Lock = field(default_factory=Lock)
    recent: RecentProjects = field(default_factory=RecentProjects)
    catalog: Catalog | None = None
    photo: str | None = None
    standalone_view: Session = field(default_factory=Session)
    native_models: NativeModelRegistry = field(default_factory=NativeModelRegistry)
    document: ImageDocument | None = None
    model: KokentauModel | None = None

    def close(self) -> None:
        """Wait for the running operation before releasing loaded models."""
        self.batch.control("cancel")
        self.batch_jobs.shutdown()
        self.inference_jobs.shutdown()
        self.jobs.shutdown()
        self.native_models.clear()
        self.model = None
        self.document = None
