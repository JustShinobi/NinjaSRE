/**
 * What this deployment is called, and which clock it keeps.
 *
 * Read from the environment at request time rather than baked into the build,
 * for the same reason the API address is: one image serves every deployment, and
 * an artefact with an operator's name compiled into it is an artefact only that
 * operator can run.
 *
 * The name reaches the document title of every page. That is not decoration —
 * an operator with three deployments open has three tabs, and a tab that says
 * only "Approvals" is a tab they act on in the wrong one.
 */

/** The name shown in the utility bar and in every document title. */
export const DEPLOYMENT_NAME_ENV = 'NINJASRE_CONSOLE_DEPLOYMENT';

/** The zone every absolute timestamp is rendered in. */
export const DEPLOYMENT_TIMEZONE_ENV = 'NINJASRE_CONSOLE_TIMEZONE';

/** What a deployment is called when nobody has said. */
export const DEFAULT_DEPLOYMENT_NAME = 'NinjaSRE';

/** The zone to read timestamps in when nobody has said, which is the one nobody argues about. */
export const DEFAULT_TIMEZONE = 'UTC';

/** How this deployment identifies itself. */
export interface Deployment {
  readonly name: string;
  readonly timezone: string;
}

/** The deployment `environment` describes. */
export function deploymentFrom(
  environment: Readonly<Record<string, string | undefined>>,
): Deployment {
  const name = environment[DEPLOYMENT_NAME_ENV]?.trim();
  const timezone = environment[DEPLOYMENT_TIMEZONE_ENV]?.trim();
  return {
    name: name === undefined || name === '' ? DEFAULT_DEPLOYMENT_NAME : name,
    timezone: timezone === undefined || timezone === '' ? DEFAULT_TIMEZONE : timezone,
  };
}

/** The deployment this process is serving. */
export function deployment(): Deployment {
  return deploymentFrom(process.env);
}

/**
 * A document title: the page, then the deployment.
 *
 * That order rather than the reverse, because a browser truncates a tab from the
 * right and the page is the part that distinguishes one tab from the next.
 */
export function documentTitle(page: string, name: string): string {
  return `${page} · ${name}`;
}
