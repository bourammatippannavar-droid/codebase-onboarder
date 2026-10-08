from pathlib import Path

from onboarder.core.models import Edge
from onboarder.core.resolver import resolve_project

PROJECT = Path(__file__).parent / "fixtures" / "graph_project"


def test_resolves_absolute_relative_and_from_package_imports() -> None:
    edges = resolve_project(PROJECT)
    main = PROJECT / "main.py"
    alpha = PROJECT / "pkg" / "alpha.py"

    def edge(src: Path, dst_name: str) -> Edge:
        return next(item for item in edges if item.src_file == src and item.dst_name == dst_name)

    assert edge(main, "pkg.core").dst_file == PROJECT / "pkg" / "core.py"
    assert edge(main, "pkg.nested").dst_file == PROJECT / "pkg" / "nested" / "__init__.py"
    assert edge(main, "pkg.submodule").dst_file == PROJECT / "pkg" / "submodule.py"
    assert edge(main, "pkg.EXPORTED").dst_file == PROJECT / "pkg" / "__init__.py"
    assert edge(alpha, "pkg.submodule").dst_file == PROJECT / "pkg" / "submodule.py"
    assert edge(alpha, "pkg.beta").dst_file == PROJECT / "pkg" / "beta.py"
    assert edge(main, "srcpkg.module").dst_file == PROJECT / "src" / "srcpkg" / "module.py"


def test_marks_external_and_unresolved_imports() -> None:
    edges = resolve_project(PROJECT)
    main = PROJECT / "main.py"

    assert (edge := next(item for item in edges if item.src_file == main and item.dst_name == "json"))
    assert edge.confidence == "external"
    assert edge.origin == "stdlib"
    assert edge.dst_file is None
    assert (edge := next(item for item in edges if item.src_file == main and item.dst_name == "requests"))
    assert edge.confidence == "external"
    assert edge.origin == "third-party"
    assert (edge := next(item for item in edges if item.src_file == main and item.dst_name == "pkg.missing_child"))
    assert edge.confidence == "unresolved"
    assert (edge := next(item for item in edges if item.src_file == main and item.dst_name == "pkg.missing_name"))
    assert edge.confidence == "unresolved"
    assert edge.dst_file is None


def test_syntax_error_file_does_not_break_project_resolution() -> None:
    edges = resolve_project(PROJECT)

    assert any(edge.src_file == PROJECT / "main.py" for edge in edges)
    assert all(edge.src_file != PROJECT / "broken.py" for edge in edges)