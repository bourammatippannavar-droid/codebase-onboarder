import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from onboarder.db.repository import SqlAlchemyRepository
from onboarder.db.session import SessionResources, create_session_resources
from onboarder.services.analyze import AnalyzeRepository
from onboarder.services.api import OnboarderAPI
from onboarder.services.protocols import AnalysisRepository, QueryRepository
from onboarder.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class ApplicationRepository(QueryRepository, AnalysisRepository, Protocol):
    pass


@dataclass
class ApplicationContainer:
    api: OnboarderAPI
    repository: ApplicationRepository
    executor: ThreadPoolExecutor
    settings: Settings
    resources: SessionResources

    def submit_analysis(
        self, repository_id: UUID, path: Path, request_id: str
    ) -> Future[None]:
        try:
            return self.executor.submit(
                self._run_analysis, repository_id, path, request_id
            )
        except Exception as exc:
            safe_error = f"Analysis failed ({type(exc).__name__})"[:120]
            self.repository.fail_analysis(repository_id, safe_error)
            raise AnalysisSchedulingError from exc

    def _run_analysis(self, repository_id: UUID, path: Path, request_id: str) -> None:
        worker_resources: SessionResources | None = None
        worker_repository: ApplicationRepository = self.repository
        try:
            worker_resources = create_session_resources(self.settings.DATABASE_URL)
            worker_repository = SqlAlchemyRepository(worker_resources.sessions)
            AnalyzeRepository(worker_repository, self.settings).run_registered(
                repository_id, path
            )
        except Exception as exc:  # noqa: BLE001
            safe_error = f"Analysis failed ({type(exc).__name__})"[:120]
            try:
                worker_repository.fail_analysis(repository_id, safe_error)
            except Exception as persist_error:  # noqa: BLE001
                logger.error(
                    '{"event":"analysis_failure_persist_failed","request_id":%r,"error_type":%r}',
                    request_id,
                    type(persist_error).__name__,
                )
            logger.error(
                '{"event":"analysis_failed","request_id":%r,"error_type":%r}',
                request_id,
                type(exc).__name__,
            )
        finally:
            if worker_resources is not None:
                worker_resources.engine.dispose()

    def recover_interrupted(self) -> None:
        self.repository.recover_interrupted()

    def fail_analysis(self, repository_id: UUID, error: str) -> None:
        self.repository.fail_analysis(repository_id, error)

    def shutdown(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
        self.resources.engine.dispose()


def create_container(settings: Settings | None = None) -> ApplicationContainer:
    active_settings = settings or get_settings()
    resources = create_session_resources(active_settings.DATABASE_URL)
    repository = SqlAlchemyRepository(resources.sessions)
    return ApplicationContainer(
        api=OnboarderAPI(repository, active_settings),
        repository=repository,
        executor=ThreadPoolExecutor(max_workers=2, thread_name_prefix="onboarder-analysis"),
        settings=active_settings,
        resources=resources,
    )


def create_cli_analyzer(settings: Settings | None = None) -> AnalyzeRepository:
    active_settings = settings or get_settings()
    resources = create_session_resources(active_settings.DATABASE_URL)
    repository = SqlAlchemyRepository(resources.sessions)
    return AnalyzeRepository(repository, active_settings)


def create_cli_query_service(settings: Settings | None = None) -> OnboarderAPI:
    active_settings = settings or get_settings()
    resources = create_session_resources(active_settings.DATABASE_URL)
    repository = SqlAlchemyRepository(resources.sessions)
    return OnboarderAPI(repository, active_settings)


class AnalysisSchedulingError(RuntimeError):
    """Raised when an analysis job cannot be submitted to the worker pool."""
