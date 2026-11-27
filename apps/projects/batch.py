"""Cooperative serial batch queue for shared native models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Condition
from time import perf_counter
from typing import Callable


@dataclass(slots=True)
class Task:
    """A single photograph and technique, with independent failure state."""

    photo: str
    technique: str
    state: str = "queued"
    seconds: float = 0
    error: str = ""
    result: str = ""
    device: str = ""


class Batch:
    """Coordinate pause, retry and cancellation at task boundaries."""

    def __init__(self) -> None:
        self.tasks: list[Task] = []
        self.running = False
        self.paused = False
        self._condition = Condition()

    def snapshot(self) -> dict:
        """Provide one consistent status snapshot to the Vela event bus."""
        with self._condition:
            return {
                "tasks": [asdict(task) for task in self.tasks],
                "running": self.running,
                "paused": self.paused,
            }

    def prepare(self, tasks: list[Task] | None = None) -> None:
        """Reserve the queue before scheduling work."""
        with self._condition:
            if self.running:
                raise ValueError("Já existe um lote em andamento.")
            if tasks is not None:
                self.tasks = tasks
            else:
                for task in self.tasks:
                    if task.state == "failed":
                        task.state, task.error = "queued", ""
            self.running = True
            self.paused = False

    def control(self, action: str, index: int | None = None) -> None:
        """Pause, resume or cancel pending work without interrupting an active kernel."""
        with self._condition:
            if action in {"pause", "resume"}:
                self.paused = self.running and action == "pause"
            elif action == "cancel":
                for task in self.tasks:
                    if task.state == "queued":
                        task.state = "cancelled"
                self.paused = False
            elif action == "cancel-task" and type(index) is int and 0 <= index < len(self.tasks):
                if self.tasks[index].state == "queued":
                    self.tasks[index].state = "cancelled"
            else:
                raise ValueError("Ação de fila inválida.")
            self._condition.notify_all()

    def run(self, process: Callable[[Task], dict], notify: Callable[[], None]) -> None:
        """Process one task at a time and continue after a recoverable photo failure."""
        try:
            for task in self.tasks:
                with self._condition:
                    self._condition.wait_for(lambda: not self.paused)
                    if task.state != "queued":
                        continue
                    task.state = "running"
                notify()
                start = perf_counter()
                try:
                    result = process(task)
                except (OSError, ImportError, ValueError, RuntimeError) as error:
                    with self._condition:
                        task.state = "failed"
                        task.error = str(error)
                else:
                    with self._condition:
                        task.state = "done" if result else "skipped"
                        task.result = result.get("id", "")
                        task.device = result.get("device", "")
                with self._condition:
                    task.seconds = perf_counter() - start
                notify()
        finally:
            with self._condition:
                self.running = self.paused = False
            notify()
