# Limitations

- **Python only:** the analyzer currently scans `.py` files. JavaScript and TypeScript support is not implemented.
- **Static analysis:** source is parsed, not executed. Runtime behavior such as dynamic dispatch, reflection, `getattr`, and decorators cannot be reliably evaluated.
- **Unknown receiver calls:** calls through receivers whose type or target cannot be established are counted in guide quality statistics but are not stored as call relationship edges.
- **Conservative resolution:** unresolved and external references are not treated as confirmed project dependencies; static analysis can miss runtime-created relationships.
- **Local folders only:** analysis reads directories accessible to the running application. GitHub URL cloning/import is not implemented, including for private repositories.
- **No hosted product:** this repository does not include a hosted read-only demo or a multi-user cloud service.
- **File limits:** files larger than 1 MiB are skipped by the scanner; source display also rejects oversized and binary files.

Possible future work includes Tree-sitter-based JavaScript/TypeScript support, GitHub URL import, incremental re-analysis, and a hosted read-only demo.
