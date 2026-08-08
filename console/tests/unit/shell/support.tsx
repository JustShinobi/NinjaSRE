import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { Viewer } from '@/session/viewer';

/**
 * What every shell test needs: a viewer at a named role, from the catalogue the
 * server generates rather than from a list written here.
 *
 * `fixtures/contract/roles.json` is produced from the platform's own permission
 * catalogue and compared against a fresh generation by the Python suite. Reading
 * it means the role matrix walks the roles that exist, with the permissions they
 * actually hold — and a permission added to `operator` next month changes what
 * this proves without anybody editing a test.
 */

interface RoleCatalogue {
  readonly order: readonly string[];
  readonly permissions: readonly string[];
  readonly roles: Readonly<Record<string, readonly string[]>>;
}

function readCatalogue(): RoleCatalogue {
  const path = join(process.cwd(), '..', 'fixtures', 'contract', 'roles.json');
  const loaded: unknown = JSON.parse(readFileSync(path, 'utf8'));
  const order: unknown = Reflect.get(Object(loaded), 'order');
  const roles: unknown = Reflect.get(Object(loaded), 'roles');
  const permissions: unknown = Reflect.get(Object(loaded), 'permissions');
  if (!Array.isArray(order) || typeof roles !== 'object' || roles === null) {
    throw new Error('fixtures/contract/roles.json is not the generated catalogue');
  }
  return {
    order: order as readonly string[],
    permissions: Array.isArray(permissions) ? (permissions as readonly string[]) : [],
    roles: roles as Readonly<Record<string, readonly string[]>>,
  };
}

export const ROLES = readCatalogue();

/** Least privileged first, as the platform orders them. */
export const ROLE_ORDER = ROLES.order;

/** A viewer holding exactly what `role` holds. */
export function viewerAt(role: string, overrides: Partial<Viewer> = {}): Viewer {
  const permissions = ROLES.roles[role];
  if (permissions === undefined) {
    throw new Error(`${role} is not a role the platform declares`);
  }
  return {
    principalId: `user-${role}`,
    displayName: 'Avery Lockhart',
    email: null,
    roles: [role],
    permissions,
    teamNodeId: 'org-northwind',
    impersonating: false,
    impersonatedBy: null,
    ...overrides,
  };
}

/** The most privileged role there is, which is what most tests want. */
export function owner(overrides: Partial<Viewer> = {}): Viewer {
  const last = ROLE_ORDER[ROLE_ORDER.length - 1];
  if (last === undefined) throw new Error('the role catalogue is empty');
  return viewerAt(last, overrides);
}
