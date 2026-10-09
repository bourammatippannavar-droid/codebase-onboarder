from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from onboarder.core.calls import resolve_calls
from onboarder.core.models import Edge
from onboarder.core.parser import parse_python_file
from onboarder.core.resolver import resolve_project
from onboarder.core.scanner import find_python_files
from onboarder.services.protocols import (
    AnalysisRepository,
    EdgeInput,
    FileInput,
    SymbolInput,
)
from onboarder.settings import Settings, get_settings


class AnalysisPathError(ValueError):
    """Raised when an analysis root is outside the configured allowlist."""


def validate_analysis_path(path: Path, allowed_root: Path) -> Path:
    root = allowed_root.resolve(strict=True)
    candidate = path.resolve(strict=True)
    if not candidate.is_dir() or not candidate.is_relative_to(root):
        raise AnalysisPathError("analysis path is outside the configured root")
    return candidate


class AnalyzeRepository:
    def __init__(
        self,
        repository: AnalysisRepository,
        settings: Settings | None = None,
        pipeline: Callable[[Path], tuple[tuple[FileInput, ...], tuple[SymbolInput, ...], tuple[EdgeInput, ...], dict[str, int]]] | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings or get_settings()
        self._pipeline = pipeline or (
            lambda root: _analyze(root, self._settings.MAX_FILE_BYTES)
        )

    def __call__(self, path: Path, name: str) -> tuple[UUID, dict[str, int]]:
        root = validate_analysis_path(path, self._settings.ANALYSIS_ROOT)
        repository_id = self._repository.start_analysis(name, root)
        try:
            files, symbols, edges, stats = self._pipeline(root)
            self._repository.complete_analysis(repository_id, files, symbols, edges, stats)
        except Exception as exc:
            self._repository.fail_analysis(repository_id, _safe_error(exc))
            raise
        return repository_id, stats


def _safe_error(error: Exception) -> str:
    return f"Analysis failed ({type(error).__name__})"[:120]


def _analyze(
    root: Path,
    max_file_bytes: int,
) -> tuple[tuple[FileInput, ...], tuple[SymbolInput, ...], tuple[EdgeInput, ...], dict[str, int]]:
    paths = tuple(find_python_files(root))
    if any(file.stat().st_size > max_file_bytes for file in paths):
        raise ValueError("analysis file size limit exceeded")
    facts = {file: parse_python_file(file, project_root=root) for file in paths}
    file_inputs = tuple(
        FileInput(
            path=file.relative_to(root).as_posix(),
            loc=_line_count(file),
            is_entry_point=(
                facts[file].has_main_guard
                or file.name.lower() in {"main.py", "app.py", "manage.py"}
            ),
            parse_status=(
                "ok"
                if not facts[file].diagnostics
                else (
                    "skipped"
                    if facts[file].diagnostics[0].startswith("could not read file")
                    else "syntax_error"
                )
            ),
        )
        for file in paths
    )
    symbols = tuple(
        SymbolInput(
            file_path=symbol.file.relative_to(root).as_posix(),
            kind=symbol.kind,
            name=symbol.name,
            qualified_name=symbol.qualified_name,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
        )
        for file in paths
        for symbol in facts[file].symbols
    )
    valid_paths = set(paths)
    call_resolution = resolve_calls(root)
    all_edges = (*resolve_project(root), *call_resolution.edges)
    edges = tuple(
        _edge_input(edge, root)
        for edge in all_edges
        if edge.src_file in valid_paths and (edge.dst_file is None or edge.dst_file in valid_paths)
    )
    stats = {
        "files": len(file_inputs),
        "symbols": len(symbols),
        "edges": len(edges),
        "syntax_errors": sum(item.parse_status == "syntax_error" for item in file_inputs),
        "skipped_files": sum(item.parse_status == "skipped" for item in file_inputs),
        "call_unknown_receiver": call_resolution.stats.unknown_receiver,
        "call_external_package": call_resolution.stats.external_package,
        "call_builtin": call_resolution.stats.builtin,
    }
    return file_inputs, symbols, edges, stats


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeError):
        return 0


def _edge_input(edge: Edge, root: Path) -> EdgeInput:
    return EdgeInput(
        kind=edge.kind.value.upper(),
        src_file=edge.src_file.relative_to(root).as_posix(),
        src_symbol=edge.src_symbol,
        dst_file=edge.dst_file.relative_to(root).as_posix() if edge.dst_file is not None else None,
        dst_symbol=edge.dst_symbol,
        dst_name=edge.dst_name or None,
        confidence=edge.confidence.value,
        origin=edge.origin,
        is_constructor=edge.constructor,
        line=edge.line,
    )
