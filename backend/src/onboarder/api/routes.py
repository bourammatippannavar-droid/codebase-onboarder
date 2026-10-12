from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response, status

from onboarder.api.schemas import (
    EdgeResponse,
    FileResponse,
    GraphResponse,
    GuideResponse,
    HealthResponse,
    ModuleGraphResponse,
    OverviewResponse,
    PageResponse,
    Problem,
    ReadyResponse,
    RepositoryCreate,
    RepositoryResponse,
    SearchResponseItem,
    SourceResponse,
    TreeResponse,
)
from onboarder.bootstrap import AnalysisSchedulingError, ApplicationContainer
from onboarder.services.api import ServiceError

router = APIRouter(prefix="/api/v1")
health_router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]
MinimumConfidence = Annotated[
    Literal["exact", "inferred", "unresolved"], Query()
]


def _container(request: Request) -> ApplicationContainer:
    return cast(ApplicationContainer, request.app.state.container)


@router.post(
    "/repositories",
    response_model=RepositoryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_repository(
    body: RepositoryCreate, request: Request
) -> RepositoryResponse:
    container = _container(request)
    created = container.api.create_repository(body.path, body.name)
    try:
        container.submit_analysis(
            created.repository.id, created.analysis_path, request.state.request_id
        )
    except AnalysisSchedulingError as exc:
        raise ServiceError(
            500, "analysis_failed", "Repository analysis could not be started."
        ) from exc
    return RepositoryResponse.model_validate(created.repository)


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(request: Request) -> list[RepositoryResponse]:
    return [
        RepositoryResponse.model_validate(item)
        for item in _container(request).api.list_repositories()
    ]


@router.get("/repositories/{repository_id}", response_model=RepositoryResponse)
def get_repository(repository_id: UUID, request: Request) -> RepositoryResponse:
    return RepositoryResponse.model_validate(
        _container(request).api.get_repository(repository_id)
    )


@router.delete(
    "/repositories/{repository_id}",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_repository(repository_id: UUID, request: Request) -> Response:
    _container(request).api.delete_repository(repository_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/repositories/{repository_id}/files",
    response_model=PageResponse[FileResponse],
)
def list_files(
    repository_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PageResponse[FileResponse]:
    page = _container(request).api.files(repository_id, limit, offset)
    return PageResponse[FileResponse](
        items=tuple(FileResponse.model_validate(item) for item in page.items),
        total=page.total,
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}",
    response_model=FileResponse,
)
def get_file(repository_id: UUID, file_id: UUID, request: Request) -> FileResponse:
    return FileResponse.model_validate(_container(request).api.file(repository_id, file_id))


@router.get(
    "/repositories/{repository_id}/tree",
    response_model=TreeResponse,
)
def get_tree(
    repository_id: UUID,
    request: Request,
    path_prefix: str = "",
) -> TreeResponse:
    return TreeResponse.model_validate(
        _container(request).api.tree(repository_id, path_prefix)
    )


@router.get(
    "/repositories/{repository_id}/overview",
    response_model=OverviewResponse,
)
def get_overview(repository_id: UUID, request: Request) -> OverviewResponse:
    return OverviewResponse.model_validate(
        _container(request).api.overview(repository_id)
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}/source",
    response_model=SourceResponse,
    responses={413: {"model": Problem}, 415: {"model": Problem}},
)
def get_source(
    repository_id: UUID, file_id: UUID, request: Request
) -> SourceResponse:
    return SourceResponse.model_validate(
        _container(request).api.source(repository_id, file_id)
    )


def _file_relations(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    dependent: bool,
    transitive: bool,
    depth: int,
    limit: int,
    offset: int,
) -> PageResponse[FileResponse]:
    page = _container(request).api.file_relations(
        repository_id, file_id, dependent, transitive, depth, limit, offset
    )
    return PageResponse[FileResponse](
        items=tuple(FileResponse.model_validate(item) for item in page.items),
        total=page.total,
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}/dependents",
    response_model=PageResponse[FileResponse],
)
def get_dependents(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    transitive: bool = False,
    depth: Annotated[int, Query(ge=1, le=5)] = 1,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PageResponse[FileResponse]:
    return _file_relations(
        repository_id, file_id, request, True, transitive, depth, limit, offset
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}/dependencies",
    response_model=PageResponse[FileResponse],
)
def get_dependencies(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    transitive: bool = False,
    depth: Annotated[int, Query(ge=1, le=5)] = 1,
    limit: Limit = 50,
    offset: Offset = 0,
) -> PageResponse[FileResponse]:
    return _file_relations(
        repository_id, file_id, request, False, transitive, depth, limit, offset
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}/imports",
    response_model=PageResponse[EdgeResponse],
)
def get_file_imports(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    min_confidence: MinimumConfidence = "inferred",
) -> PageResponse[EdgeResponse]:
    return _file_import_edges(
        repository_id, file_id, request, "imports", limit, offset, min_confidence
    )


@router.get(
    "/repositories/{repository_id}/files/{file_id}/imported-by",
    response_model=PageResponse[EdgeResponse],
)
def get_file_imported_by(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    min_confidence: MinimumConfidence = "inferred",
) -> PageResponse[EdgeResponse]:
    return _file_import_edges(
        repository_id, file_id, request, "imported-by", limit, offset, min_confidence
    )


def _file_import_edges(
    repository_id: UUID,
    file_id: UUID,
    request: Request,
    relation: str,
    limit: int,
    offset: int,
    min_confidence: str,
) -> PageResponse[EdgeResponse]:
    page = _container(request).api.file_import_edges(
        repository_id, file_id, relation, limit, offset, min_confidence
    )
    return PageResponse[EdgeResponse](
        items=tuple(EdgeResponse.model_validate(item) for item in page.items),
        total=page.total,
    )


def _symbol_edges(
    repository_id: UUID,
    symbol_id: UUID,
    request: Request,
    kind: str,
    limit: int,
    offset: int,
    min_confidence: str,
) -> PageResponse[EdgeResponse]:
    page = _container(request).api.symbol_edges(
        repository_id, symbol_id, kind, limit, offset, min_confidence
    )
    return PageResponse[EdgeResponse](
        items=tuple(EdgeResponse.model_validate(item) for item in page.items),
        total=page.total,
    )


@router.get(
    "/repositories/{repository_id}/symbols/{symbol_id}/usages",
    response_model=PageResponse[EdgeResponse],
)
def get_usages(
    repository_id: UUID,
    symbol_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    min_confidence: MinimumConfidence = "inferred",
) -> PageResponse[EdgeResponse]:
    return _symbol_edges(
        repository_id, symbol_id, request, "usages", limit, offset, min_confidence
    )


@router.get(
    "/repositories/{repository_id}/symbols/{symbol_id}/callers",
    response_model=PageResponse[EdgeResponse],
)
def get_callers(
    repository_id: UUID,
    symbol_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    min_confidence: MinimumConfidence = "inferred",
) -> PageResponse[EdgeResponse]:
    return _symbol_edges(
        repository_id, symbol_id, request, "callers", limit, offset, min_confidence
    )


@router.get(
    "/repositories/{repository_id}/symbols/{symbol_id}/callees",
    response_model=PageResponse[EdgeResponse],
)
def get_callees(
    repository_id: UUID,
    symbol_id: UUID,
    request: Request,
    limit: Limit = 50,
    offset: Offset = 0,
    min_confidence: MinimumConfidence = "inferred",
) -> PageResponse[EdgeResponse]:
    return _symbol_edges(
        repository_id, symbol_id, request, "callees", limit, offset, min_confidence
    )


@router.get(
    "/repositories/{repository_id}/search",
    response_model=PageResponse[SearchResponseItem],
)
def search(
    repository_id: UUID,
    request: Request,
    q: Annotated[str, Query(min_length=2)],
    limit: Limit = 50,
    offset: Offset = 0,
) -> PageResponse[SearchResponseItem]:
    page = _container(request).api.search(repository_id, q, limit, offset)
    return PageResponse[SearchResponseItem](
        items=tuple(SearchResponseItem.model_validate(item) for item in page.items),
        total=page.total,
    )


@router.get("/repositories/{repository_id}/graph", response_model=GraphResponse)
def get_graph(
    repository_id: UUID,
    request: Request,
    max_nodes: Annotated[int, Query(ge=1, le=150)] = 150,
) -> GraphResponse:
    return GraphResponse.model_validate(_container(request).api.graph(repository_id, max_nodes))


@router.get(
    "/repositories/{repository_id}/graph/modules",
    response_model=ModuleGraphResponse,
)
def get_module_graph(
    repository_id: UUID,
    request: Request,
    path_prefix: str = "",
    include_tests: bool = False,
) -> ModuleGraphResponse:
    return ModuleGraphResponse.model_validate(
        _container(request).api.module_graph(repository_id, path_prefix, include_tests)
    )


@router.get(
    "/repositories/{repository_id}/guide",
    response_model=GuideResponse,
)
def get_guide(repository_id: UUID, request: Request) -> GuideResponse:
    return GuideResponse.model_validate(_container(request).api.guide(repository_id))


@health_router.get("/healthz", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@health_router.get("/readyz", response_model=ReadyResponse)
def ready(request: Request) -> ReadyResponse:
    _container(request).api.ready()
    return ReadyResponse(status="ready")
