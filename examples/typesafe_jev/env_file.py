"""Load a local .env file into the process environment.

Keeping credentials in one ignored file beats exporting them into every shell.
Standard library only, so there is no python-dotenv dependency.

Real environment variables always win, so an export still overrides the file.
`.env` is already covered by the repository's .gitignore.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / ".env"


def load(path: Path | str = DEFAULT_PATH) -> list[str]:
    """Read KEY=value lines into os.environ without overwriting what is set.

    Args:
        path: The file to read. Missing files are ignored.
