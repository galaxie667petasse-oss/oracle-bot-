# Universal Railway entrypoint for Oracle Bot.
#
# This repository currently keeps the full Oracle V4.1 source in Procfile by mistake.
# To keep Railway working whatever start command is configured, bot.py delegates to it.

from pathlib import Path
import runpy

SOURCE = Path(__file__).with_name("Procfile")

if not SOURCE.exists():
    raise SystemExit("Oracle source Procfile is missing")

runpy.run_path(str(SOURCE), run_name="__main__")
