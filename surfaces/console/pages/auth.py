"""Sign-in, and the page an unauthenticated visitor is allowed to see.

That is the whole of it: acceptance scenario 1 says they see the sign-in and
nothing else, so this page carries no navigation, no deployment name beyond the
product's own, and no list of what the deployment has. A sign-in screen that
enumerated the areas of the console would be a sign-in screen that told an
unauthenticated visitor how the deployment is configured.

The token field is ``autocomplete="off"`` and ``type="password"``. Neither is
security — anybody who can read the DOM can read the field — and both are worth
setting anyway: the first keeps a token out of the browser's saved-values store
on a shared machine, and the second keeps it off the screen during the
screen-share that is running because there is an incident.
"""

from __future__ import annotations

from collections.abc import Sequence

from surfaces.console.html import Document, Element, element
from surfaces.console.pages.shell import (
    PageContext,
    card,
    form,
    form_field,
    heading,
    signed_out_page,
)
from surfaces.console.session import SsoProvider

#: Where the token form posts. A console route rather than the API's, because
#: what comes back has to become a session cookie — which is a thing only the
#: console can set.
SIGN_IN_ACTION = "/sign-in"


def sign_in_body(
    context: PageContext,
    *,
    providers: Sequence[SsoProvider] = (),
    failed: bool = False,
) -> Element:
    """Return the sign-in form: single sign-on first, a token as the fallback (FR-022).

    SSO first because it is what a team uses. The token entry stays because it
    is what works when the identity provider is the thing that is broken, which
    is a situation this product exists to be usable during.
    """
    return element(
        "div",
        heading(1, context.text("auth.heading")),
        element("p", context.text("auth.failed"), role="alert", class_="notice")
        if failed
        else None,
        card(
            *[
                element(
                    "p",
                    element(
                        "a",
                        f"{context.text('auth.sso')} ({provider.name})",
                        href=provider.authorize_url,
                        class_="button",
                    ),
                )
                for provider in providers
                if provider.enabled
            ],
        )
        if any(provider.enabled for provider in providers)
        else None,
        card(
            form(
                form_field(
                    identifier="token",
                    label=context.text("auth.token_label"),
                    kind="password",
                    help_text=context.text("auth.token_help"),
                    required=True,
                    autocomplete="off",
                ),
                element("button", context.text("auth.submit"), type="submit", class_="primary"),
                action=SIGN_IN_ACTION,
                label=context.text("auth.title"),
            )
        ),
        class_="sign-in",
    )


def sign_in_page(
    context: PageContext,
    *,
    providers: Sequence[SsoProvider] = (),
    failed: bool = False,
) -> Document:
    """Return the whole sign-in page."""
    return signed_out_page(
        context,
        title_key="auth.title",
        body=sign_in_body(context, providers=providers, failed=failed),
    )


__all__ = ["SIGN_IN_ACTION", "sign_in_body", "sign_in_page"]
