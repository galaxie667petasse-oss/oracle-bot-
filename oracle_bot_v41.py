from pathlib import Path
import runpy

SOURCE = Path(__file__).with_name("Procfile")

if not SOURCE.exists():
    raise SystemExit("Procfile source missing")

runpy.run_path(str(SOURCE), run_name="__main__")
