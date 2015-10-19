"""Load a local .env file into the process environment.

Keeping credentials in one ignored file beats exporting them into every shell.
Standard library only, so there is no python-dotenv dependency.

Real environment variables always win, so an export still overrides the file.
`.env` is already covered by the repository's .gitignore.
"""

from __future__ import annotations

