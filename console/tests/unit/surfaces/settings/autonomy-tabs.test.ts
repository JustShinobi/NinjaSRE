import { describe, expect, it } from 'vitest';

import { CONFIG_FIELD_OWNERS, type ConfigFieldOwner } from '@/shell/config-ownership';
import {
  AUTONOMY_TAB_FIELDS,
  AUTONOMY_TAB_FILTERS,
  AUTONOMY_TABS,
  hrefForTab,
  tabFrom,
  tabLabel,
  tabOwning,
  type AutonomyTabField,
} from '@/surfaces/settings/autonomy-tabs';
import { DEFAULT_VIEW_STATE, withFilter } from '@/surfaces/url-state';

/**
 * The three questions Autonomy & guardrails answers, as an address rather
 * than a paragraph, and the map that says which one owns which field.
 *
 * Resolution and the field map are tested here at the unit level precisely so
 * "which tab does this open to" and "which tab owns this field" are provable
 * without standing up the whole screen — the same reason `tabFrom` exists as
 * a named, tested function on every other tabbed screen in this console.
 */

describe('AUTONOMY_TABS', () => {
  it('declares the three questions in the order the product presents them', () => {
    expect(AUTONOMY_TABS).toEqual(['posture', 'rules-windows', 'guardrails']);
  });
});

describe('tabFrom', () => {
  it('opens Posture when the address names no tab', () => {
    expect(tabFrom('')).toBe('posture');
  });

  it('opens Posture for a name the product does not declare, rather than erroring', () => {
    expect(tabFrom('not-a-real-tab')).toBe('posture');
  });

  it('opens the tab the address actually names', () => {
    expect(tabFrom('posture')).toBe('posture');
    expect(tabFrom('rules-windows')).toBe('rules-windows');
    expect(tabFrom('guardrails')).toBe('guardrails');
  });
});

describe('tabLabel', () => {
  it('names every tab in English, matching the mockup’s own words', () => {
    expect(tabLabel('en', 'posture')).toBe('Posture');
    expect(tabLabel('en', 'rules-windows')).toBe('Rules & windows');
    expect(tabLabel('en', 'guardrails')).toBe('Guardrails');
  });

  it('translates Posture and Rules & windows rather than carrying English into pt-BR', () => {
    expect(tabLabel('pt-BR', 'posture')).not.toBe(tabLabel('en', 'posture'));
    expect(tabLabel('pt-BR', 'rules-windows')).not.toBe(
      tabLabel('en', 'rules-windows'),
    );
  });
});

describe('AUTONOMY_TAB_FILTERS', () => {
  it('declares the scope node alongside the tab, so reading one never reads the other away', () => {
    expect(AUTONOMY_TAB_FILTERS).toEqual(['node', 'tab']);
  });
});

describe('hrefForTab — scope-node preservation across a tab switch', () => {
  it('carries a node already named in the address forward onto the new tab', () => {
    const state = withFilter(
      withFilter(DEFAULT_VIEW_STATE, 'node', 'org-northwind'),
      'tab',
      'posture',
    );

    const href = hrefForTab(state, 'guardrails', 'org-northwind');

    expect(href).toBe('?node=org-northwind&tab=guardrails');
  });

  it('pins the resolved node even when the address never named one explicitly', () => {
    // The first visit to the route carries no `?node=` at all; the screen
    // still resolves a node (the viewer's own team, or the tree root) and
    // must not lose it the moment somebody switches tabs.
    const href = hrefForTab(DEFAULT_VIEW_STATE, 'rules-windows', 'org-northwind');

    expect(href).toBe('?node=org-northwind&tab=rules-windows');
  });

  it('carries no node parameter when the deployment resolves to none', () => {
    const href = hrefForTab(DEFAULT_VIEW_STATE, 'posture', '');

    expect(href).toBe('?tab=posture');
    expect(href).not.toContain('node=');
  });

  it('switches only the tab when the state already agrees with the resolved node', () => {
    const state = withFilter(DEFAULT_VIEW_STATE, 'node', 'team-alpha');

    expect(hrefForTab(state, 'posture', 'team-alpha')).toBe(
      '?node=team-alpha&tab=posture',
    );
    expect(hrefForTab(state, 'rules-windows', 'team-alpha')).toBe(
      '?node=team-alpha&tab=rules-windows',
    );
    expect(hrefForTab(state, 'guardrails', 'team-alpha')).toBe(
      '?node=team-alpha&tab=guardrails',
    );
  });
});

describe('tabOwning — the field-to-tab map', () => {
  it('claims each of its declared paths exactly once', () => {
    const seen = new Set<string>();
    for (const entry of AUTONOMY_TAB_FIELDS) {
      expect(seen.has(entry.path), `"${entry.path}" is declared more than once`).toBe(
        false,
      );
      seen.add(entry.path);
    }
  });

  it('only ever assigns one of the three declared tabs', () => {
    const valid: readonly string[] = AUTONOMY_TABS;
    for (const entry of AUTONOMY_TAB_FIELDS) {
      expect(
        valid,
        `"${entry.path}" is assigned to an unknown tab "${entry.tab}"`,
      ).toContain(entry.tab);
    }
  });

  it('says a field nobody assigned has no owner, rather than defaulting to one', () => {
    expect(tabOwning('policies.nonexistent.field')).toBeUndefined();
    expect(tabOwning('')).toBeUndefined();
  });

  it('gives the temporary override to Posture — the tab that shows what posture is currently in effect', () => {
    // The hard case: an override is reachable from every tab's own header,
    // not from inside any one tab's body, so ownership here is a genuine
    // decision rather than a lookup. Posture is where the subtitle declares
    // the posture actually in force, including when an override is why —
    // the one question an override exists to answer.
    expect(tabOwning('policies.autonomy.overrides')).toBe('posture');
  });

  it('gives rule evaluation — rules, freezes, budgets, and simulation — to Rules & windows', () => {
    expect(tabOwning('policies.autonomy.rules')).toBe('rules-windows');
    expect(tabOwning('policies.autonomy.freezes')).toBe('rules-windows');
    expect(tabOwning('policies.autonomy.budgets')).toBe('rules-windows');
    expect(tabOwning('policies.autonomy.dry_run')).toBe('rules-windows');
    expect(tabOwning('policies.autonomy.allow_unverifiable_actions')).toBe(
      'rules-windows',
    );
    expect(tabOwning('policies.autonomy.recurrence_threshold')).toBe('rules-windows');
    expect(tabOwning('policies.autonomy.recurrence_window_seconds')).toBe(
      'rules-windows',
    );
  });

  it('gives masking, secret detection and approvals to Guardrails', () => {
    expect(tabOwning('policies.masking.enabled')).toBe('guardrails');
    expect(tabOwning('policies.masking.level')).toBe('guardrails');
    expect(tabOwning('policies.masking.custom_patterns')).toBe('guardrails');
    expect(tabOwning('policies.guardrails.mode')).toBe('guardrails');
    expect(tabOwning('policies.guardrails.ruleset')).toBe('guardrails');
    expect(tabOwning('policies.guardrails.disabled_rules')).toBe('guardrails');
    expect(tabOwning('policies.approvals.threshold')).toBe('guardrails');
    expect(tabOwning('policies.approvals.expiry_hours')).toBe('guardrails');
    expect(tabOwning('policies.approvals.autonomous_capabilities')).toBe('guardrails');
  });
});

/**
 * Cross-checked against `shell/config-ownership.ts` itself, not a hand-typed
 * inventory: the console-wide map is the one thing that knows which fields
 * this page owns, so a field it adds or drops for this page has to change
 * this test — without anybody editing a second, hand-written list to match.
 */
describe('AUTONOMY_TAB_FIELDS — parity against shell/config-ownership.ts', () => {
  /** Every path `config-ownership.ts` assigns to this screen, read from the source itself. */
  function ownedByThisPage(
    owners: readonly ConfigFieldOwner[] = CONFIG_FIELD_OWNERS,
  ): readonly string[] {
    return owners
      .filter((owner) => owner.page === 'settings-autonomy-guardrails')
      .map((owner) => owner.path);
  }

  /**
   * Every path in `owned` that `fields` claims zero times or more than
   * once — named, not counted, so a field with no tab, or two, fails by the
   * exact string a person can search `AUTONOMY_TAB_FIELDS` for.
   */
  function unclaimedOrMisclaimed(
    owned: readonly string[],
    fields: readonly AutonomyTabField[],
  ): readonly string[] {
    const claims = new Map<string, number>();
    for (const { path } of fields) claims.set(path, (claims.get(path) ?? 0) + 1);
    return owned.filter((path) => claims.get(path) !== 1);
  }

  /** Every path a tab claims that `config-ownership.ts` does not assign to this page. */
  function claimedNotOwned(
    owned: readonly string[],
    fields: readonly AutonomyTabField[],
  ): readonly string[] {
    const ownedSet = new Set(owned);
    return fields.map((entry) => entry.path).filter((path) => !ownedSet.has(path));
  }

  it('claims every field config-ownership.ts assigns here, and none it does not', () => {
    const owned = ownedByThisPage();
    expect(unclaimedOrMisclaimed(owned, AUTONOMY_TAB_FIELDS)).toEqual([]);
    expect(claimedNotOwned(owned, AUTONOMY_TAB_FIELDS)).toEqual([]);
  });

  it('names the field when config-ownership.ts assigns this page one no tab claims yet', () => {
    // A field a future change adds to `CONFIG_FIELD_OWNERS` for this page,
    // constructed here rather than assumed: the check has to name it, not
    // merely notice that a count changed.
    const grown = [...ownedByThisPage(), 'policies.autonomy.a_future_field'];

    expect(unclaimedOrMisclaimed(grown, AUTONOMY_TAB_FIELDS)).toEqual([
      'policies.autonomy.a_future_field',
    ]);
  });

  it('names the field when a tab stops claiming a path config-ownership.ts still assigns', () => {
    const owned = ownedByThisPage();
    const orphaned = owned[0];
    if (orphaned === undefined) throw new Error('this page owns no fields to orphan');
    const shrunk = AUTONOMY_TAB_FIELDS.filter((entry) => entry.path !== orphaned);

    expect(unclaimedOrMisclaimed(owned, shrunk)).toEqual([orphaned]);
  });

  it('names a path twice when two tabs both claim it', () => {
    const owned = ownedByThisPage();
    const doubled = owned[0];
    if (doubled === undefined)
      throw new Error('this page owns no fields to double-claim');
    const overlapping: readonly AutonomyTabField[] = [
      ...AUTONOMY_TAB_FIELDS,
      { path: doubled, tab: 'guardrails' },
    ];

    expect(unclaimedOrMisclaimed(owned, overlapping)).toEqual([doubled]);
  });
});
