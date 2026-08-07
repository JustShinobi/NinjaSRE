"""The guided first run: provider, credentials, integrations, verification.

``flow`` orchestrates; ``providers/`` declares what each of the nine needs;
``integrations/`` generates its prompts from the integration's own credential
schema; ``prompts`` is how a person is asked, and the reason a secret is never
echoed and never becomes a command argument.
"""

from __future__ import annotations
