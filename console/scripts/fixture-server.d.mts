/**
 * The types for the fixture server, which is JavaScript because it runs inside
 * the capture image with no build step.
 *
 * Declared rather than inferred, so the unit suite — which imports the same
 * resolution the capture serves the dataset with — is type-checked against it
 * like everything else here. `allowJs` is off deliberately: a JavaScript module
 * the compiler silently types as `any` is a module the gate has nothing to say
 * about.
 */

import type { Server } from 'node:http';

/** Every read a surface makes, and the fixture that answers it. */
export declare const SHELL_ENDPOINTS: Readonly<Record<string, string>>;

/** Which fixture answers `path`, and what its variable segments bind. */
export declare function resolveFixture(
  path: string,
): { readonly slug: string; readonly arguments: Record<string, string> } | null;

/** The recorded body for `path` in `scenario`, or `null` when nothing serves it. */
export declare function bodyFor(scenario: string, path: string): unknown;

/** Serve `scenario` on `port` and resolve once it is listening. */
export declare function serveFixtures(scenario: string, port: number): Promise<Server>;
