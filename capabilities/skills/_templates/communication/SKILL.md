---
name: communication-VENDOR
display_name: VENDOR incident communication
description: Structured updates that link to evidence rather than pasting it.
domain: communication
applies_when:
  alert_sources: [VENDOR]
  tags: [chat, notification, update, status]
directs_tools:
  - VENDOR_post_update
  - VENDOR_read_thread
requires:
  integrations: [VENDOR]
---

# VENDOR incident communication

Replace VENDOR throughout, delete what does not apply, and keep the ordering —
it is the part of this template that carries the methodology rather than the
shape.

## Order of operations

1. **Read the thread before posting to it.** Somebody has usually already
   said what you are about to, and an update that repeats it costs the
   responders a re-read during the minutes they have least of.
2. **Post the structure, every time.** What is affected, since when, what is
   known, what is being done, and when the next update comes. A responder
   scanning six threads reads the shape before the words.
3. **Link to the evidence; never paste it.** A query link, a run identifier, a
   dashboard at the right window. Four hundred lines of log in a channel is
   four hundred lines nobody reads and a thread nobody can scroll.
4. **Say what is not known.** An update that only states findings reads as a
   complete picture, and the next person acts on it as one.

## What this is not for

- Investigating. Nothing here reads telemetry; it reports what the
  investigation found.
- Approvals. A change that needs a human goes through the approval gate, which
  keeps a record — a message in a channel does not.

## Notes for this vendor

- The message-size limit, and what this vendor does to a message that exceeds
  it — silent truncation is common and loses the end, which is where the
  next-update time is.
- Whether threading is available, because an update posted to a channel rather
  than a thread fragments the incident record.
- Rate limits during a storm, which is exactly when several updates are queued.
