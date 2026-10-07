# Gameplay alert reliability

Assessed 2026-10-06 against commit `6687c95`.

The next milestone is reliable phone alerts during gameplay, with explicit delivery
failure handling and verified screenshot behavior. Lookout is not finished against
that milestone. Automated screenshot delivery already exists; building it again
would repeat completed work.

## Evidence

The full local suite passed: `.venv/Scripts/python -m pytest -q` reported **54 passed**.
It covers the Lua addon, QR image decoding, batching, screenshot rate limits, combat
deferral, screenshot creation retries, UTF-8 truncation, partial image writes, chat
fallback, and assistant request handling. These are automated checks, not proof
that a notification appeared on a phone during a real game session.

The September 28 probe documented one successful foreground screenshot-to-phone
delivery without logout. That evidence predates the automatic watcher. No newer
live acceptance record was found in the repository. There was no existing roadmap
or open decision log; this document establishes the current milestone and order.

Four controlled observations used `unittest.mock` with the real `Watcher` and
`Folder` classes. No network calls, game interaction, or real screenshot deletion
were performed:

| Case | Observed behavior | Consequence |
| --- | --- | --- |
| Delivery callback returns false | One callback and one deletion request; a second poll makes no further attempt | An unsuccessful send cannot be recovered from its screenshot by default |
| Watcher is paused | No delivery callback, but one deletion request | Pause discards new alerts instead of holding them |
| Companion starts with an existing image | Folder startup records the filename as seen; polling never calls the decoder | Keeping a screenshot alone does not provide restart recovery |
| Two image files carry the same character and sequence | Two delivery callbacks | The screenshot route does not suppress duplicate payloads |

To reproduce the first two observations, supply a mock folder whose first `poll`
returns one `(mock_path, Shot)` and whose second returns an empty list. Set the
delivery mock to return false, or set `watcher.paused` to true, then call
`step_screenshots` twice and inspect callback and `mock_path.unlink` counts.
For startup, patch `Folder.listing` to return an existing filename and assert the
decoder is not called. For duplication, return two paths with the same `Shot`.

The root cause is visible in `companion/app.py`: `hand_over` does not return a
delivery result, and `step_screenshots` requests deletion after handing off the
batch. Both console and tray callbacks receive `sent` from `notify.send` but do
not propagate it to the watcher. `Folder.poll` marks files seen before delivery.
Assistant questions add an asynchronous boundary: their worker can still be
running when the source screenshot is deleted. Screenshot retries in the addon
only retry saving an image; they do not retry phone delivery.

## Next implementation

**Preserve alerts until delivery succeeds.** Introduce explicit delivery outcomes
and recoverable pending work before deleting a recognized alert screenshot. Test
failure, retry, pause, and restart together, because merely retaining a file does
not make the current watcher read it again.

Use bounded retry delays and show failures in the tray and console. Invalid
credentials should remain visible without a rapid retry loop. Define expiration
for time-sensitive invites, queue pops, and ready checks so recovery cannot send
an obsolete prompt to accept. A paused companion should hold eligible pending
alerts; expiration must be explicit rather than silent loss.

Track ordinary pushes and assistant answers separately so retrying a mixed batch
cannot repeatedly start the assistant or resend an already accepted ordinary
alert. This is a delivery-state change; no new AI provider or model work is needed.
Deduplication must account for client and character identity, payload contents,
and sequence reuse. A sequence number alone is not a global identifier.

Do not promise exactly-once phone delivery after an ambiguous network timeout:
the provider may have accepted the request before the response was lost. Distinguish
provider acceptance from the user actually seeing a notification.

## Milestone acceptance checks

1. Automated failure tests prove failed pushes remain recoverable, retries are
   bounded, success stops retries, and pending work survives companion restart.
2. Pause holds eligible alerts, expired urgent alerts are reported, duplicate
   screenshots do not produce repeated accepted sends, and mixed question/alert
   batches recover without repeating completed work.
3. User screenshots remain untouched. Startup recovery handles only identified
   pending Lookout work and does not replay an arbitrary historical image folder.
4. A live foreground alert and a batched long UTF-8 message reach the phone before
   logout. Record game build, display settings, timings, and user confirmation.
5. Repeat with the game in the background and minimized. Record unsupported modes
   explicitly rather than inferring success from the foreground probe.

Keep screenshots and credentials out of committed evidence. Record sanitized
results instead. The assessment uses no numeric completion estimate: the remaining
recovery implementation and live acceptance results do not yet support one.

CurseForge onboarding, companion packaging, and additional quest features remain
outside this milestone. Wago publishing is already documented as working.
