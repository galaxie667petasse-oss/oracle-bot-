# Compatibility wrapper for Railway services still configured with:
# python oracle_bot_v4.py
#
# The real current bot is Oracle Bot V4.1.

from pathlib import Path
import runpy

V41 = Path(__file__).with_name("oracle_bot_v41.py")
PROCFILE_SOURCE = Path(__file__).with_name("Procfile")

if V41.exists():
    runpy.run_path(str(V41), run_name="__main__")
elif PROCFILE_SOURCE.exists():
    runpy.run_path(str(PROCFILE_SOURCE), run_name="__main__")
else:
    raise SystemExit("Oracle Bot V4.1 source not found")
