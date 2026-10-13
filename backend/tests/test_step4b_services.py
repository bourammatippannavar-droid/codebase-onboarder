from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from onboarder.services.analyze import AnalysisPathError, AnalyzeRepository
from onboarder.services.protocols import EdgeInput, FileInput, SymbolInput
from onboarder.settings import Settings


@dataclass
class FakeRow:
    name: str
    path: Path
    status: str = "running"
    files: tuple[FileInput, ...] = ()
    symbols: tuple[SymbolInput, ...] = ()
    edges: tuple[EdgeInput, ...] = ()
    stats: dict[str, int] = field(default_factory=dict)
    error: str | None = None


@dataclass
class FakeRepository:
    repositories: dict[UUID, FakeRow] = field(default_factory=dict)
    fail_during_complete: bool = False

    def start_analysis(self, name: str, local_path: Path) -> UUID:
        for repository_id, row in tuple(self.repositories.items()):
            if row.path == local_path:
                del self.repositories[repository_id]
        repository_id = uuid4()
        self.repositories[repository_id] = FakeRow(name, local_path)
        return repository_id

    def complete_analysis(
        self,
        repository_id: UUID,
        files: tuple[FileInput, ...],
        symbols: tuple[SymbolInput, ...],
        edges: tuple[EdgeInput, ...],
        stats: dict[str, int],
    ) -> None:
        row = self.repositories[repository_id]
        row.files = files
        row.symbols = symbols
        row.edges = edges
        row.stats = stats
        row.status = "ready"
        if self.fail_during_complete:
            raise RuntimeError("failed at C:\\private\\source.py")

    def fail_analysis(self, repository_id: UUID, error: str) -> None:
        row = self.repositories[repository_id]
        row.files = ()
        row.symbols = ()
        row.edges = ()
        row.stats = {}
        row.status = "failed"
        row.error = error


def _settings(analysis_root: Path) -> Settings:
    return Settings(
        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/unused",
        ANALYSIS_ROOT=analysis_root,
    )


def test_analysis_failure_rolls_back_all_rows_and_sanitizes_error(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    (root / "module.py").write_text("def run():\n    pass\n", encoding="utf-8")
    repository = FakeRepository(fail_during_complete=True)

    with pytest.raises(RuntimeError):
        AnalyzeRepository(repository, _settings(root))(root, "example")

    row = next(iter(repository.repositories.values()))
    assert row.status == "failed"
    assert row.files == ()
    assert row.symbols == ()
    assert row.edges == ()
    assert row.stats == {}
    assert "C:\\private" not in str(row.error)


def test_analysis_rejects_parent_directory_escape(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    service = AnalyzeRepository(FakeRepository(), _settings(allowed))

    with pytest.raises(AnalysisPathError, match="outside"):
        service(allowed / ".." / "outside", "escape")


def test_analysis_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reject an escaping link, simulating resolution when link creation is restricted."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    simulated_link = allowed / "link"
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        simulated_link.symlink_to(outside, target_is_directory=True)
    except OSError:
        simulated_link.mkdir()
        original_resolve = Path.resolve

        def resolve(path: Path, strict: bool = False) -> Path:
            if path == simulated_link:
                return outside
            return original_resolve(path, strict=strict)

        monkeypatch.setattr(Path, "resolve", resolve)
    service = AnalyzeRepository(FakeRepository(), _settings(allowed))

    with pytest.raises(AnalysisPathError, match="outside"):
        service(simulated_link, "escape")


def test_reanalysis_replaces_repository_data(tmp_path: Path) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    (root / "first.py").write_text("def first():\n    return 1\n", encoding="utf-8")
    repository = FakeRepository()
    service = AnalyzeRepository(repository, _settings(root))
    previous_id, _ = service(root, "old name")

    (root / "second.py").write_text("class Second:\n    pass\n", encoding="utf-8")
    (root / "first.py").unlink()
    current_id, current_stats = service(root, "new name")

    assert current_id != previous_id
    assert len(repository.repositories) == 1
    row = repository.repositories[current_id]
    assert row.name == "new name"
    assert row.status == "ready"
    assert [file.path for file in row.files] == ["second.py"]
    assert current_stats["files"] == 1
