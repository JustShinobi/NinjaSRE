"""The console's toolchain pin, its gate budgets, and where its artefacts live.

The console is a TypeScript application rather than a Python package, so nothing
here is imported by the console itself — it is read by the repository tooling
that provisions the toolchain, runs the checks, and asserts that the two agree.
The names still belong in this tier: ``tools/check_constants.py`` does not care
which language ends up consuming them.

Two numbers are budgets rather than settings. ``CONSOLE_COVERAGE_THRESHOLD`` is
declared here and asserted against the console's own runner configuration, so
lowering it is a change to this file and shows up in review. The cold and warm
verify budgets are the ones that keep the gate a thing people run rather than a
thing they push and wait for.
"""

from __future__ import annotations

from typing import Final

# --- Environment ---------------------------------------------------------------

#: ``required`` turns "the console toolchain is not provisioned" from a skip
#: into a failure. CI sets it; a contributor iterating on the Python half does
#: not, and gets a named skip instead of a red gate they cannot act on.
NINJASRE_CONSOLE_TOOLCHAIN_ENV: Final = "NINJASRE_CONSOLE_TOOLCHAIN"

#: Where the browser tests find the console under test.
NINJASRE_CONSOLE_BASE_URL_ENV: Final = "NINJASRE_CONSOLE_BASE_URL"

#: Where the console's generated client sends its requests. The end-to-end
#: harness points this at the stack it started; a deployment points it at the
#: gateway behind its own proxy.
NINJASRE_CONSOLE_API_URL_ENV: Final = "NINJASRE_CONSOLE_API_URL"

#: The path the built console is served under, for a deployment that puts it
#: somewhere other than the root of its reverse proxy.
NINJASRE_CONSOLE_BASE_PATH_ENV: Final = "NINJASRE_CONSOLE_BASE_PATH"

#: A mirror of the Node distribution, for a build with no route to the public
#: one. The archive is still checked against the committed digest, so a mirror
#: is a different address rather than a different level of trust.
NINJASRE_NODE_MIRROR_ENV: Final = "NINJASRE_NODE_MIRROR"

# --- Layout ---------------------------------------------------------------------

#: The console's directory, a peer of the Python tiers rather than a member of
#: one. Nothing in the Python tree may import it, and it imports no Python.
CONSOLE_DIR_NAME: Final = "console"

#: Where the provisioned Node and pnpm are unpacked. Inside the console
#: directory, ignored by git, and removable without losing anything committed.
CONSOLE_TOOLCHAIN_DIR_NAME: Final = ".toolchain"

#: The pinned Node version, on its own line, in the file every Node version
#: manager already reads.
CONSOLE_NODE_VERSION_FILENAME: Final = ".node-version"

#: The digests of the Node archives, one per platform the workflow covers.
CONSOLE_TOOLCHAIN_LOCK_FILENAME: Final = "toolchain.lock.json"

CONSOLE_MANIFEST_FILENAME: Final = "package.json"
CONSOLE_LOCKFILE_FILENAME: Final = "pnpm-lock.yaml"

#: The generated API client, committed, and compared against a fresh generation
#: by the gate.
CONSOLE_GENERATED_CLIENT_PATH: Final = "src/api/schema.ts"

#: Where the visual regression suite keeps its three kinds of image: the design
#: references the first acceptance is reviewed against, the accepted baselines,
#: and the registry that ties a screen to both.
CONSOLE_VISUAL_DIR_NAME: Final = "visual"
CONSOLE_MOCKUP_DIR_NAME: Final = "mockups"
CONSOLE_BASELINE_DIR_NAME: Final = "baselines"
CONSOLE_SCREEN_REGISTRY_FILENAME: Final = "screens.json"

# --- The distribution the provisioning target fetches ----------------------------

#: Where a Node archive comes from when the machine has none. Pinned by version
#: and verified against a committed digest, so this is an address rather than a
#: trust boundary.
NODE_DIST_BASE_URL: Final = "https://nodejs.org/dist"

#: The platform keys the toolchain lock carries, matching the three operating
#: systems the workflow covers on both architectures each of them ships.
CONSOLE_PLATFORM_KEYS: Final[tuple[str, ...]] = (
    "darwin-arm64",
    "darwin-x64",
    "linux-arm64",
    "linux-x64",
    "win-arm64",
    "win-x64",
)

# --- The gate --------------------------------------------------------------------

#: The console's unit test coverage floor, enforced by its own runner and
#: asserted against that configuration by the suite, so the two cannot drift.
CONSOLE_COVERAGE_THRESHOLD: Final = 90.0

#: The compiled stylesheet for the whole design system, in bytes.
#:
#: A design system that has stopped being a system shows up here first: every
#: component that writes its own values adds rules nothing else shares, and the
#: sheet grows faster than the console does. The number is generous enough to
#: hold the screens features 035 to 037 add and tight enough that a doubling
#: fails rather than being noticed a year later.
CONSOLE_STYLESHEET_BUDGET_BYTES: Final = 40960

#: The whole icon set, in bytes, as it would ship to a page that used every icon.
#:
#: Measured against the set rather than against a page, because the per-page
#: figure depends on which icons that page happens to use — and the property
#: worth holding is that the *set* stays small enough that carrying all of it
#: would still be acceptable. Each icon is a named export, so a page carries
#: only what it imports; this is the ceiling, not the typical case.
CONSOLE_ICON_BUDGET_BYTES: Final = 16384

#: One image captures every baseline and every comparison. Font rendering
#: differs between platforms, so a baseline captured anywhere else produces a
#: difference that means nothing. Pinned by digest rather than by tag: a tag
#: moves, and a moved tag is a whole suite of meaningless differences.
CONSOLE_VISUAL_IMAGE: Final = (
    "mcr.microsoft.com/playwright:v1.62.1-noble"
    "@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e"
)

#: How many pixels may differ before a screen counts as changed. Zero, because
#: a threshold is where a visual gate goes to become advisory.
CONSOLE_VISUAL_MAX_DIFFERING_PIXELS: Final = 0

#: The console's first contentful paint, in milliseconds, measured in the
#: browser suite against the built artefact and the committed dataset.
#:
#: This is the chrome, not the content: the shell has to be on screen before any
#: page data resolves, and a number nothing checks is an intention.
CONSOLE_FIRST_PAINT_BUDGET_MS: Final = 2000.0

#: A warm route transition — the router serving a route it already has the frame
#: for. This is the one that decides whether people use the navigation or the
#: browser's address bar.
CONSOLE_ROUTE_TRANSITION_BUDGET_MS: Final = 1200.0

#: Drawing a ten-thousand-event transcript, in milliseconds.
#:
#: A budget on the *drawing* rather than on the fetch, and it is held alongside a
#: stronger claim: the number of entries in the document does not depend on how
#: many events there are, so this number is a sanity check on that rather than
#: the thing keeping the page usable.
CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS: Final = 1500.0

#: Drawing a five-hundred-node configuration tree, in milliseconds.
#:
#: Every node present, because a tree that hid the deep ones would be a tree an
#: operator cannot find their own team in. The tree is one pass over a flat list
#: rather than a recursive render, which is why every node can be there.
CONSOLE_CONFIG_TREE_RENDER_BUDGET_MS: Final = 1000.0

#: How long one of the shell's own auxiliary reads gets before the frame is
#: rendered without it.
#:
#: The notification count, the recent runs and the guardian line are all things
#: the frame is better with and none of them is a thing the frame waits for. The
#: viewer has no deadline: there is no honest shell to draw without one.
#: Mirrored in ``console/src/shell/load.ts`` and asserted equal by the suite.
CONSOLE_SHELL_READ_TIMEOUT_MS: Final = 2000

# --- The console's own session ---------------------------------------------------

#: The cookie the credential lives in. HTTP-only, so nothing in a component can
#: read it and no bug in a component can leak one.
CONSOLE_SESSION_COOKIE: Final = "ninjasre_session"

#: The cookie carrying only the instant the session ends. Readable on purpose:
#: the warning has to be rendered before the expiry, so the browser has to know
#: when that is, and an instant is not a secret.
CONSOLE_SESSION_EXPIRY_COOKIE: Final = "ninjasre_session_expires"

#: Where a viewer's chosen language is kept.
CONSOLE_LOCALE_COOKIE: Final = "ninjasre_locale"

#: How long a console session lasts before it has to be established again.
CONSOLE_SESSION_LIFETIME_SECONDS: Final = 43200

#: How long before the end the console says the session is ending.
CONSOLE_SESSION_WARNING_SECONDS: Final = 300

#: The one route an unauthenticated visitor may reach.
CONSOLE_SIGN_IN_PATH: Final = "/sign-in"

#: The width below which the sidebar becomes a drawer.
CONSOLE_SIDEBAR_BREAKPOINT_PX: Final = 768

#: The sidebar's width and the utility bar's height, as the design draws them.
CONSOLE_SIDEBAR_WIDTH_PX: Final = 236
CONSOLE_TOPBAR_HEIGHT_PX: Final = 52

#: The locales the console carries, in the order the catalogue declares them.
CONSOLE_LOCALES: Final[tuple[str, ...]] = ("en", "pt-BR")

#: What the deployment calls itself in the utility bar and in every document
#: title, and which clock its absolute timestamps are rendered in.
NINJASRE_CONSOLE_DEPLOYMENT_ENV: Final = "NINJASRE_CONSOLE_DEPLOYMENT"
NINJASRE_CONSOLE_TIMEZONE_ENV: Final = "NINJASRE_CONSOLE_TIMEZONE"

#: An instant to render every relative time against, instead of the clock.
#:
#: The visual capture exists to produce the same image twice. Every timestamp in
#: the committed dataset is shifted to one fixed instant for exactly that reason
#: — and a screen that renders "17 hours ago" against the real clock says
#: "18 hours ago" an hour later, which is a baseline that fails on the hour and
#: on nothing else. Unset in a deployment, where the clock is the right answer.
NINJASRE_CONSOLE_CLOCK_ENV: Final = "NINJASRE_CONSOLE_CLOCK"

# --- The gate's wall clock -------------------------------------------------------

#: A clean checkout, nothing cached, both halves of the gate. Generous, because
#: it includes provisioning a Node distribution and a browser.
CONSOLE_COLD_VERIFY_BUDGET_SECONDS: Final = 1800.0

#: The same gate with the toolchain already provisioned and the caches warm.
#: This is the number that decides whether people run it before pushing.
CONSOLE_WARM_VERIFY_BUDGET_SECONDS: Final = 600.0

# --- Ports the harnesses bind ----------------------------------------------------

#: The built console, under test. One above the port a deployment serves it on,
#: so an end-to-end run does not collide with a console somebody left running.
CONSOLE_E2E_PORT: Final = 8423

#: The mock data plane the deterministic end-to-end suite runs against.
CONSOLE_E2E_MOCK_PORT: Final = 8424


__all__ = [
    "CONSOLE_BASELINE_DIR_NAME",
    "CONSOLE_COLD_VERIFY_BUDGET_SECONDS",
    "CONSOLE_CONFIG_TREE_RENDER_BUDGET_MS",
    "CONSOLE_COVERAGE_THRESHOLD",
    "CONSOLE_DIR_NAME",
    "CONSOLE_E2E_MOCK_PORT",
    "CONSOLE_FIRST_PAINT_BUDGET_MS",
    "CONSOLE_ICON_BUDGET_BYTES",
    "CONSOLE_LOCALE_COOKIE",
    "CONSOLE_LOCALES",
    "CONSOLE_ROUTE_TRANSITION_BUDGET_MS",
    "CONSOLE_SESSION_COOKIE",
    "CONSOLE_SESSION_EXPIRY_COOKIE",
    "CONSOLE_SESSION_LIFETIME_SECONDS",
    "CONSOLE_SESSION_WARNING_SECONDS",
    "CONSOLE_SHELL_READ_TIMEOUT_MS",
    "CONSOLE_SIDEBAR_BREAKPOINT_PX",
    "CONSOLE_SIDEBAR_WIDTH_PX",
    "CONSOLE_SIGN_IN_PATH",
    "CONSOLE_TOPBAR_HEIGHT_PX",
    "CONSOLE_TRANSCRIPT_RENDER_BUDGET_MS",
    "NINJASRE_CONSOLE_CLOCK_ENV",
    "NINJASRE_CONSOLE_DEPLOYMENT_ENV",
    "NINJASRE_CONSOLE_TIMEZONE_ENV",
    "CONSOLE_E2E_PORT",
    "CONSOLE_GENERATED_CLIENT_PATH",
    "CONSOLE_LOCKFILE_FILENAME",
    "CONSOLE_MANIFEST_FILENAME",
    "CONSOLE_MOCKUP_DIR_NAME",
    "CONSOLE_NODE_VERSION_FILENAME",
    "CONSOLE_PLATFORM_KEYS",
    "CONSOLE_SCREEN_REGISTRY_FILENAME",
    "CONSOLE_STYLESHEET_BUDGET_BYTES",
    "CONSOLE_TOOLCHAIN_DIR_NAME",
    "CONSOLE_TOOLCHAIN_LOCK_FILENAME",
    "CONSOLE_VISUAL_DIR_NAME",
    "CONSOLE_VISUAL_IMAGE",
    "CONSOLE_VISUAL_MAX_DIFFERING_PIXELS",
    "CONSOLE_WARM_VERIFY_BUDGET_SECONDS",
    "NINJASRE_CONSOLE_API_URL_ENV",
    "NINJASRE_CONSOLE_BASE_PATH_ENV",
    "NINJASRE_CONSOLE_BASE_URL_ENV",
    "NINJASRE_CONSOLE_TOOLCHAIN_ENV",
    "NINJASRE_NODE_MIRROR_ENV",
    "NODE_DIST_BASE_URL",
]
