import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { may, parseViewer, ViewerRejected } from '@/session/viewer';

/**
 * Who is looking, as the server says it — and never as the console works it out.
 *
 * The console holds no opinion about what a role means. It is told a list of
 * permissions by `/auth/me`, resolved at the caller's own node, and it reads
 * that list. Deriving permissions from a role name here would be a second copy
 * of the server's catalogue, and the copy would be the one that was wrong.
 */

/** The committed capture of `/auth/me`, so this is the real payload shape. */
function principalFixture(scenario: string): unknown {
  const path = join(
    process.cwd(),
    '..',
    'fixtures',
    'scenarios',
    scenario,
    'principal.json',
  );
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const responses: unknown = Reflect.get(Object(loaded), 'responses');
  if (!Array.isArray(responses)) throw new Error('the fixture holds no responses');
  return Reflect.get(Object(responses[0]), 'body');
}

describe('resolving the viewer', () => {
  it('reads the owner the committed dataset answers with', () => {
    const viewer = parseViewer(principalFixture('populated'));

    expect(viewer.principalId).toBe('user-operator');
    expect(viewer.displayName).toBe('Avery Lockhart');
    expect(viewer.roles).toContain('owner');
    expect(viewer.permissions).toContain('audit.read');
    expect(viewer.impersonating).toBe(false);
  });

  it('reads the viewer the restricted scenario answers with', () => {
    const viewer = parseViewer(principalFixture('restricted'));

    expect(viewer.roles).toEqual(['viewer']);
    expect(viewer.permissions).not.toContain('audit.read');
  });

  it('carries both parties when the session is an impersonation', () => {
    const viewer = parseViewer({
      principal_id: 'user-viewer',
      kind: 'person',
      display_name: 'Reese Underhill',
      permissions: [],
      roles: ['viewer'],
      impersonating: true,
      impersonated_by: 'user-operator',
    });

    expect(viewer.impersonating).toBe(true);
    expect(viewer.impersonatedBy).toBe('user-operator');
  });

  it('refuses a body that is not a principal rather than rendering an empty shell', () => {
    // A shell rendered for a viewer nobody resolved is a shell whose permission
    // checks all answer "no permissions", which looks exactly like a viewer with
    // none. Failing here is the difference between the two.
    expect(() => parseViewer({ nonsense: true })).toThrow(ViewerRejected);
    expect(() => parseViewer(null)).toThrow(ViewerRejected);
  });

  it('refuses a permission list that is not a list of strings', () => {
    expect(() =>
      parseViewer({
        principal_id: 'x',
        display_name: 'X',
        permissions: [1, 2],
        roles: [],
      }),
    ).toThrow(ViewerRejected);
  });
});

describe('what the viewer may do', () => {
  const viewer = parseViewer(principalFixture('restricted'));

  it('answers yes only for a permission the server listed', () => {
    expect(may(viewer, 'approval.read')).toBe(true);
    expect(may(viewer, 'audit.read')).toBe(false);
  });

  it('does not infer one permission from another', () => {
    // `config.read` is held and `config.write` is not. A console that treated
    // the domain as the unit would let a viewer see every write control there
    // is, which is the exact failure the presence rule exists to prevent.
    expect(may(viewer, 'config.read')).toBe(true);
    expect(may(viewer, 'config.write')).toBe(false);
  });
});
