---
name: close-task
description: Close a finished SDD task branch (fast-forward master to it) and open the next specs/NNN-* task's branch from master. Use when a feat/NNN-slug branch's work is done and it's time to move to the next spec instead of stacking a new branch on top of this one.
---

# Closing an SDD task branch

This repository's task branches (`feat/NNN-slug`, one per `specs/NNN-slug/`)
must each branch off `master`, not off the previous task's branch. Branching
off the previous branch silently stacks tasks, leaves `master` frozen at the
initial commit, and makes every later branch depend on every earlier one being
correct. `tools/close_task_branch.py` and the `make close-task` target exist to
close that gap: fast-forward `master` to the finished branch, then cut the next
task's branch from the updated `master`.

## When to run this

Only after the current task's work is actually done: `make verify` green and
the user has confirmed the task is complete. Never run it mid-task.

## Steps

1. Confirm the checked-out branch is `feat/NNN-slug` and that `specs/NNN-slug/`
   exists. If not, stop — this only makes sense at the end of a task branch.
2. Run `make verify`. If anything fails, stop and report it; do not proceed.
   (`make close-task` already depends on `verify`, so step 2 and 4 can be done
   in one command if you skip the preview in step 3.)
3. Preview with `uv run python tools/close_task_branch.py --dry-run` and show
   the user what will happen — which branch merges into `master` and what the
   next branch will be called. This changes branch state, so confirm before
   acting rather than after.
4. Run `make close-task` (or `uv run python tools/close_task_branch.py` if
   `verify` was already confirmed green in this conversation).
5. Report the result plainly: what `master` now points at, and the name of
   the branch just created. If the closed task was the last entry under
   `specs/`, say so — there is no next branch to create.

## Explicitly out of scope

- Pushing anything to `origin`. This tool only touches local branches; treat
  pushing as a separate action that needs its own confirmation.
- Deleting the old task branch. It now points at the same commit as `master`
  and is harmless to leave around; removing branches is a separate, deliberate
  choice for the user to make.
