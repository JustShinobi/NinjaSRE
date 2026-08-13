/**
 * Where the tutorial's dismissal is recorded, and how it is read and written.
 *
 * Its own module, with no `'use client'` on it, and that is the whole reason it
 * exists. The overlay is a client component; the dashboard that decides whether
 * to mount it is a server component. With the read living beside the overlay,
 * rendering the dashboard called a client function from the server and Next
 * refused — the page threw before it painted anything, which is a crash on the
 * first screen of the product for every deployment.
 *
 * Neither half may move to the other side: the overlay needs state and a
 * router, and the dashboard must not become a client component to read one
 * boolean. So the shared part is here, where both sides may import it.
 *
 * **Dismissal is a fact about the deployment, not about the browser.** It is
 * written through the ordinary configuration path, because a `localStorage`
 * flag would show the whole thing again on the second machine, to the same
 * person, on the same deployment.
 */

/** Where the dismissal is recorded, at the viewer's own node. */
export const TUTORIAL_SETTING = 'surfaces.console.tutorial_dismissed';

/** The query parameter that explicitly reopens the tutorial. */
export const TUTORIAL_QUERY_PARAM = 'tour';

/** The query value that means "show the tutorial now". */
export const TUTORIAL_REPLAY_VALUE = '1';

/** The stable address used by the account menu and command palette. */
export const TUTORIAL_REPLAY_HREF = `/?${TUTORIAL_QUERY_PARAM}=${TUTORIAL_REPLAY_VALUE}`;

/**
 * Whether `values` — a node's effective configuration — records the dismissal.
 *
 * The effective document is nested the way the schema is, so the dotted setting
 * is walked one segment at a time. Read as one flat key it would answer false
 * forever, which is exactly the overlay that never stops coming back.
 */
export function tutorialDismissed(values: unknown): boolean {
  let cursor: unknown = values;
  for (const segment of TUTORIAL_SETTING.split('.')) {
    cursor = Reflect.get(Object(cursor), segment);
  }
  return cursor === true;
}

/**
 * The dismissal as the nested document the deployment validates.
 *
 * Built from the same dotted setting the read walks, so the two halves of the
 * persistence cannot name different fields. A flat dotted key would be a field
 * the closed schema has never heard of, and the write would be refused.
 */
export function dismissalPatch(): Record<string, unknown> {
  let patch: unknown = true;
  for (const segment of [...TUTORIAL_SETTING.split('.')].reverse()) {
    patch = { [segment]: patch };
  }
  return patch as Record<string, unknown>;
}
