# Oracle Bot V4.1 entrypoint
# Temporary compatibility loader: the full V4.1 Python source was accidentally pasted into Procfile.
# Railway starts this file, which safely executes that source until the repo is fully normalized.

from pathlib import Path
import runpy

SOURCE = Path(__file__).with_name("Procfile")

if not SOURCE.exists():
    raise SystemExit("Procfile source is missing")

runpy.run_path(str(SOURCE), run_name="__main__")
