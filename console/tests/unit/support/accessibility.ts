/**
 * The accessibility audit, and the level it declares.
 *
 * Written here rather than depended upon, for the reason Article X gives about
 * every other dependency: an audit package is a package an operator has to
 * audit, and this suite runs in the gate on every machine including the ones
 * with no network. What is checked is the set of failures that are (a)
 * mechanically decidable from a rendered tree and (b) the ones that actually
 * happen — an unnamed control, a form field with no label, a reference to an
 * element that is not there, an `aria-hidden` region a keyboard can still walk
 * into.
 *
 * **The declared level is: no violation of any rule below, anywhere in the
 * gallery.** Rules that need layout, colour rendering or a real screen reader
 * are outside it and are covered elsewhere — contrast by the token test, focus
 * visibility by the single ring in the base layer, and reading order by the
 * component tests that press Tab.
 */

/** One thing that is wrong, and where. */
export interface Violation {
  readonly rule: string;
  readonly detail: string;
  readonly element: string;
}

/** Elements that must have an accessible name because they do something. */
const INTERACTIVE = 'a[href], button, [role="button"], [role="switch"], [role="tab"]';

/** Elements a label names. */
const FORM = 'input, select, textarea';

/** Input types that are not user-facing fields. */
const UNLABELLED_INPUTS = new Set(['hidden', 'submit', 'reset', 'button', 'image']);

/** The roles this console uses. An unknown role is a typo with no symptom. */
const KNOWN_ROLES = new Set([
  'alert',
  'button',
  'combobox',
  'dialog',
  'img',
  'listbox',
  'navigation',
  'none',
  'option',
  'presentation',
  'progressbar',
  'region',
  'status',
  'switch',
  'tab',
  'tablist',
  'tabpanel',
  'tooltip',
]);

/**
 * The text of `element` as a screen reader would hear it.
 *
 * `textContent` is not that: it includes the contents of every `aria-hidden`
 * subtree, so a button holding nothing but a hidden glyph looks named and is
 * not. That is the exact case an icon-only control fails on, so an audit using
 * `textContent` would pass the one thing it exists to catch.
 */
function readableText(element: Element): string {
  if (element.getAttribute('aria-hidden') === 'true') return '';
  let text = '';
  for (const node of element.childNodes) {
    if (node.nodeType === node.TEXT_NODE) {
      text += node.textContent ?? '';
    } else if (node instanceof Element) {
      text += readableText(node);
    }
  }
  return text;
}

/** A short, readable description of `element`, for the failure message. */
function describe(element: Element): string {
  const attributes = [...element.attributes]
    .filter((attribute) => attribute.name !== 'class')
    .map((attribute) => `${attribute.name}="${attribute.value}"`)
    .join(' ');
  return `<${element.tagName.toLowerCase()}${attributes === '' ? '' : ` ${attributes}`}>`;
}

/** The accessible name of `element`, as far as a static tree can tell. */
function accessibleName(root: ParentNode, element: Element): string {
  const label = element.getAttribute('aria-label');
  if (label !== null && label.trim() !== '') return label.trim();

  const labelledBy = element.getAttribute('aria-labelledby');
  if (labelledBy !== null) {
    const named = labelledBy
      .split(/\s+/)
      .map((id) => {
        const named = root.querySelector(`#${CSS.escape(id)}`);
        return named === null ? '' : readableText(named);
      })
      .join(' ')
      .trim();
    if (named !== '') return named;
  }

  const id = element.getAttribute('id');
  if (id !== null) {
    const explicit = root.querySelector(`label[for="${CSS.escape(id)}"]`);
    if (explicit !== null && readableText(explicit).trim() !== '') {
      return readableText(explicit).trim();
    }
  }

  const wrapping = element.closest('label');
  if (wrapping !== null && readableText(wrapping).trim() !== '') {
    return readableText(wrapping).trim();
  }

  const title = element.getAttribute('title');
  if (title !== null && title.trim() !== '') return title.trim();

  return readableText(element).trim();
}

/** Every violation in `root`. An empty list is the declared level. */
export function audit(root: ParentNode): readonly Violation[] {
  const found: Violation[] = [];

  for (const element of root.querySelectorAll(INTERACTIVE)) {
    if (accessibleName(root, element) === '') {
      found.push({
        rule: 'interactive-element-has-a-name',
        detail: 'a control with no accessible name is announced as its tag',
        element: describe(element),
      });
    }
  }

  for (const element of root.querySelectorAll(FORM)) {
    const type = element.getAttribute('type');
    if (type !== null && UNLABELLED_INPUTS.has(type)) continue;
    if (accessibleName(root, element) === '') {
      found.push({
        rule: 'form-field-has-a-label',
        detail: 'a placeholder disappears the moment somebody types; a label does not',
        element: describe(element),
      });
    }
  }

  for (const element of root.querySelectorAll('img')) {
    if (!element.hasAttribute('alt')) {
      found.push({
        rule: 'image-has-alternative-text',
        detail:
          'an image with no alt is either content nobody can read or noise nobody can skip',
        element: describe(element),
      });
    }
  }

  const seen = new Set<string>();
  for (const element of root.querySelectorAll('[id]')) {
    const id = element.getAttribute('id') ?? '';
    if (seen.has(id)) {
      found.push({
        rule: 'identifiers-are-unique',
        detail:
          'a duplicated id makes every reference to it point at whichever came first',
        element: describe(element),
      });
    }
    seen.add(id);
  }

  for (const attribute of ['aria-labelledby', 'aria-describedby', 'aria-controls']) {
    for (const element of root.querySelectorAll(`[${attribute}]`)) {
      for (const id of (element.getAttribute(attribute) ?? '')
        .split(/\s+/)
        .filter(Boolean)) {
        if (root.querySelector(`#${CSS.escape(id)}`) === null) {
          found.push({
            rule: 'references-point-at-something',
            detail: `${attribute} names ${id}, which is not in the tree`,
            element: describe(element),
          });
        }
      }
    }
  }

  for (const element of root.querySelectorAll('[tabindex]')) {
    const index = Number(element.getAttribute('tabindex'));
    if (index > 0) {
      found.push({
        rule: 'no-positive-tabindex',
        detail:
          'a positive tabindex reorders the whole document, not just this control',
        element: describe(element),
      });
    }
  }

  for (const element of root.querySelectorAll('[aria-hidden="true"]')) {
    if (element.querySelector(`${INTERACTIVE}, ${FORM}, [tabindex]`) !== null) {
      found.push({
        rule: 'hidden-regions-hold-nothing-focusable',
        detail: 'a keyboard can reach into it while a screen reader cannot see it',
        element: describe(element),
      });
    }
  }

  for (const element of root.querySelectorAll('[role]')) {
    const role = element.getAttribute('role') ?? '';
    if (!KNOWN_ROLES.has(role)) {
      found.push({
        rule: 'roles-are-real',
        detail: `${role} is not a role this console declares, so it announces as nothing`,
        element: describe(element),
      });
    }
  }

  return found;
}

/** The violations, formatted so a failure says what to fix rather than a count. */
export function report(violations: readonly Violation[]): string {
  return violations
    .map(
      (violation) =>
        `  ${violation.rule}: ${violation.detail}\n    ${violation.element}`,
    )
    .join('\n');
}
