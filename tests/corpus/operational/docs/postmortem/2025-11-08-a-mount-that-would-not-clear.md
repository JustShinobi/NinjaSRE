# A mount that would not clear

Writing this down while it is fresh rather than filing it properly.

The backup target stopped answering some time on the Thursday and by Friday
morning every process that had touched it was stuck. Nothing on the node would
shut down cleanly. What actually caused it was the target's own controller
rebooting into a firmware update that never finished, so the export was gone but
the address still answered — which is the worst version of the problem, because
the client keeps waiting instead of failing.

What fixed it was forcing the unmount and then bringing the controller back by
hand. What should have caught it is a check on the target answering rather than
on the address answering, which we do not have.
