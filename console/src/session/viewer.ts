/**
 * Who is looking, and what they may do — as the server resolved it.
 *
 * The console holds no opinion about what a role means. `/auth/me` answers with
 * the permissions the caller holds *at their own node*, and this module reads
 * that answer. Deriving a permission from a role name here would be a second
 * copy of the server's catalogue, kept in a language the server does not
 * compile, and the copy would be the one that was wrong on the day it mattered.
 *
 * The parse is strict. A body that is not a principal raises rather than
 * producing an empty viewer: a viewer with no permissions and a viewer nobody
 * resolved render identically, and the difference between them is whether the
 * console is working.
 */

/** A body that is not the principal the API documents. */
export class ViewerRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ViewerRejected';
  }
}

/**
 * The resolved viewer, as every surface reads it.
 *
 * `permissions` is a list of `domain.verb` strings exactly as the server spells
 * them. It is deliberately not an enumeration here: an enumeration would have to
 * be kept level with the server's, and a permission the console has never heard
 * of has to be carried rather than dropped.
 */
export interface Viewer {
  readonly principalId: string;
  readonly displayName: string;
  readonly email: string | null;
  readonly roles: readonly string[];
  readonly permissions: readonly string[];
  readonly teamNodeId: string;
  /** Whether this session is somebody acting as somebody else. */
  readonly impersonating: boolean;
  /** Who is doing the acting, when it is. */
  readonly impersonatedBy: string | null;
}

function field(body: object, name: string): unknown {
  return Reflect.get(body, name);
}

function stringList(value: unknown, name: string): readonly string[] {
  if (!Array.isArray(value)) {
    throw new ViewerRejected(`the principal's ${name} is not a list`);
  }
  for (const element of value) {
    if (typeof element !== 'string') {
      throw new ViewerRejected(
        `the principal's ${name} holds something that is not a name`,
      );
    }
  }
  return value as readonly string[];
}

/** The viewer `body` describes, or a `ViewerRejected` saying what was wrong with it. */
export function parseViewer(body: unknown): Viewer {
  if (typeof body !== 'object' || body === null) {
    throw new ViewerRejected(
      'the principal endpoint answered with something that is not an object',
    );
  }
  const principalId = field(body, 'principal_id');
  const displayName = field(body, 'display_name');
  if (typeof principalId !== 'string' || principalId === '') {
    throw new ViewerRejected('the principal has no identifier');
  }
  if (typeof displayName !== 'string') {
    throw new ViewerRejected('the principal has no display name');
  }
  const email = field(body, 'email');
  const teamNodeId = field(body, 'team_node_id');
  const impersonatedBy = field(body, 'impersonated_by');
  return {
    principalId,
    displayName,
    email: typeof email === 'string' ? email : null,
    roles: stringList(field(body, 'roles'), 'roles'),
    permissions: stringList(field(body, 'permissions'), 'permissions'),
    teamNodeId: typeof teamNodeId === 'string' ? teamNodeId : '',
    impersonating: field(body, 'impersonating') === true,
    impersonatedBy: typeof impersonatedBy === 'string' ? impersonatedBy : null,
  };
}

/**
 * Whether `viewer` holds `permission`, by exact name.
 *
 * Exact, never by domain. `config.read` does not imply `config.write`, and a
 * console that treated the domain as the unit would show a viewer every write
 * control there is — which is the presence rule failing in the one direction it
 * exists to prevent.
 */
export function may(viewer: Viewer, permission: string): boolean {
  return viewer.permissions.includes(permission);
}
