"""The apparatus one chaos experiment runs inside, and nothing about faults.

Every module here is written against the ``Cluster`` port rather than against
``kubectl``, which is what makes the lock, the preflight check, the validity
probe, and cleanup assertable on a machine with no cluster on it. The two
implementations of that port — one that shells out and one that remembers — are
the only places the difference between a live run and a test appears.
"""

from __future__ import annotations
