import { describe, expect, it } from 'vitest';

import { configurationRedirectTarget } from '@/shell/configuration-redirect';

/**
 * Where the retired editor's address sends a visitor now.
 *
 * The retired screen answered two different questions with two different
 * mechanisms: `?node=<id>` named which node's configuration to show, read on
 * the server; the section a visitor was looking at was an anchor its table of
 * contents wrote (`preview.tsx`'s own `sectionId`), which a server never sees
 * at all — a fragment is not part of an HTTP request. So a bare address, and
 * one that only ever carried a node, both land on the Settings hub; only a
 * fragment naming a real section resolves to the page that owns it, and only
 * a browser can hand this function that fragment.
 */

describe('a bare address, or one with nothing this table recognises', () => {
  it('goes to the Settings hub when there is no fragment at all', () => {
    expect(configurationRedirectTarget('')).toBe('/settings');
  });

  it('goes to the Settings hub for a fragment that is just the hash mark', () => {
    expect(configurationRedirectTarget('#')).toBe('/settings');
  });

  it('goes to the Settings hub for a fragment naming no section this table has', () => {
    expect(configurationRedirectTarget('#config-section-not-a-real-group')).toBe(
      '/settings',
    );
  });
});

describe('a fragment naming a section this console still owns', () => {
  it('sends a section on a page cut into tabs to the tab that owns it, not just the page', () => {
    // `policies.autonomy.dry_run` sits in the `policies.autonomy` section,
    // owned by Autonomy & guardrails — a page split into three tabs since
    // this section was last read here, so landing on the bare page and not
    // naming a tab reopens the exact problem tabs introduced: the address
    // resolves, but the control the old table of contents pointed at may not
    // be on the tab a visitor lands on.
    expect(configurationRedirectTarget('#config-section-policies-autonomy')).toBe(
      '/settings/autonomy-guardrails?tab=rules-windows#config-section-policies-autonomy',
    );
  });

  it('sends a section one single tab owns outright to that tab, not a fixed default', () => {
    // Every `policies.guardrails.*` field belongs to the Guardrails tab
    // alone, unlike `policies.autonomy` above, which splits across two —
    // proving the tab named in the address tracks the field actually being
    // linked to, rather than one tab every autonomy-guardrails link shares.
    expect(configurationRedirectTarget('#config-section-policies-guardrails')).toBe(
      '/settings/autonomy-guardrails?tab=guardrails#config-section-policies-guardrails',
    );
  });

  it('sends a section owned by an area outside Settings to that area', () => {
    // `agents.subagents` sits in the `agents` section, owned by The agent —
    // an area, not a Settings page, and the table has to resolve both alike.
    expect(configurationRedirectTarget('#config-section-agents')).toBe(
      '/agent#config-section-agents',
    );
  });

  it('resolves a section with no working control yet to its named responsible page', () => {
    // `capabilities.disabled` has no control anywhere, but the parity map
    // still names The agent as responsible for it — a link into it should
    // land there rather than fall back to the generic hub.
    expect(configurationRedirectTarget('#config-section-capabilities')).toBe(
      '/agent#config-section-capabilities',
    );
  });

  it('tells apart two roles under the same models section prefix', () => {
    expect(configurationRedirectTarget('#config-section-models-investigator')).toBe(
      '/settings/models-providers#config-section-models-investigator',
    );
    expect(configurationRedirectTarget('#config-section-models-embedding')).toBe(
      '/settings/models-providers#config-section-models-embedding',
    );
  });

  it('resolves a nested claims section to single sign-on', () => {
    // `policies.sso.claims.email` sits in `policies.sso.claims`, a section
    // nested two levels below the field the raw editor's TOC grouped by.
    expect(configurationRedirectTarget('#config-section-policies-sso-claims')).toBe(
      '/settings/single-sign-on#config-section-policies-sso-claims',
    );
  });
});
