from pathlib import Path

Path(__file__).with_name("canary_created.txt").write_text("executed")