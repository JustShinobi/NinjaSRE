# Seeded failures

Every file here is broken on purpose. Each one is spliced into the console's
source tree by `tests/contract/console/test_console_gate.py`, the check it
belongs to is run, and the run has to fail and name the file and the line.

A check nobody has watched fail is a check that might be walking an empty file
list, and the repository would look exactly as clean either way. That is the
whole reason this directory exists, and it is why the lint, format and type
configurations all exclude it: these files must never be checked in place, only
where a test has deliberately put them.
