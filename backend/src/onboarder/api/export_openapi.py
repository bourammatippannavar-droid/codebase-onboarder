import json
from pathlib import Path

from onboarder.api.app import app


def main() -> None:
    Path("openapi.json").write_text(
        json.dumps(app.openapi(), indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
