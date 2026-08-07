/**
 * One element, or a failure that says which selector found nothing.
 *
 * `querySelector` returns `T | null`, and a test that narrows it with `as` or
 * with `!` is a test that reports "cannot read property of null" when the
 * component stops rendering the thing. Both of those are also forbidden by the
 * lint configuration, for the same reason. This throws with the selector in the
 * message, so a component that changed shape says so.
 */
export function only(root: ParentNode, selector: string): Element {
  const found = root.querySelector(selector);
  if (found === null) {
    throw new Error(`nothing matched ${selector}`);
  }
  return found;
}
