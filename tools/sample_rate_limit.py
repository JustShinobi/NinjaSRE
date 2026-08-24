"""Append one timestamped sample of the account's rate-limit state.

Estimating a wave costs nothing if nobody wrote down what the last one spent.
This samples the window a subscription actually meters — percentage used and
the instant it resets — so a later run can read the *slope* rather than a
single alarming number. A percentage on its own says nothing: eighty per cent
with four hours left is a different fact from eighty per cent with four
minutes left, and only two samples tell them apart.

Usage::

    python -m tools.sample_rate_limit           # append one sample
    python -m tools.sample_rate_limit --report  # read the slope back
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SAMPLES = Path(__file__).resolve().parent.parent / "specs_v7" / "consumo.jsonl"


def _read() -> dict[str, object] | None:
    found = subprocess.run(
        ["orca", "account", "list", "--json"], capture_output=True, text=True, check=False
    )
    if found.returncode != 0:
        return None
    try:
        limits = json.loads(found.stdout)["result"]["rateLimits"]["claude"]
    except (KeyError, json.JSONDecodeError):
        return None
    now = datetime.now()
    sample: dict[str, object] = {"at": now.isoformat(timespec="seconds")}
    for window in ("session", "weekly"):
        held = limits.get(window) or {}
        if held.get("resetsAt") is None:
            continue
        resets = datetime.fromtimestamp(held["resetsAt"] / 1000)
        sample[window] = {
            "used_percent": held.get("usedPercent"),
            "resets_in_minutes": round((resets - now).total_seconds() / 60),
        }
    return sample


def _report() -> int:
    if not SAMPLES.exists():
        print("no samples yet")
        return 1
    rows = [json.loads(line) for line in SAMPLES.read_text().splitlines() if line.strip()]
    session = [r for r in rows if "session" in r]
    if len(session) < 2:
        print(f"{len(session)} sample(s); two are needed for a slope")
        return 0
    first, last = session[0], session[-1]
    minutes = (
        datetime.fromisoformat(str(last["at"])) - datetime.fromisoformat(str(first["at"]))
    ).total_seconds() / 60
    spent = last["session"]["used_percent"] - first["session"]["used_percent"]
    left = last["session"]["resets_in_minutes"]
    print(f"  samples          {len(session)} over {minutes:.0f} min")
    print(f"  used now         {last['session']['used_percent']}%")
    print(f"  resets in        {left} min")
    if minutes <= 0:
        return 0
    rate = spent / minutes
    print(f"  rate             {rate * 60:+.1f} %/hour")
    if rate > 0:
        # The only question worth asking: does this pace reach the cap before
        # the window resets? A percentage without that answer is not a signal.
        to_cap = (100 - last["session"]["used_percent"]) / rate
        print(f"  cap reached in   {to_cap:.0f} min")
        print(f"  verdict          {'SLOW DOWN' if to_cap < left else 'pace is fine'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="read the slope back")
    if parser.parse_args().report:
        return _report()
    sample = _read()
    if sample is None:
        print("could not read the account's rate-limit state", file=sys.stderr)
        return 1
    SAMPLES.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLES.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(sample) + "\n")
    print(json.dumps(sample))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
