"""Where signals come from, and the one thing none of them may hold.

Three sources ship: a poller that calls an integration on its declared interval,
the estate's own health transitions, and a query against a metrics system the
operator already runs. A fourth is a new module here, not a new concept.

None of them can carry a credential. ``SignalReader.read`` takes the resources
to read about, the instant to read as at, and a budget; there is no parameter a
token fits in, and the tick that calls it does not have one either. An
implementation reaches its provider through ``integrations/_base/client.py``,
which lets the credential proxy inject the secret at the network edge.
"""

from __future__ import annotations
