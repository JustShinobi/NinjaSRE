import type { ReactNode } from 'react';

import { ApiError, read } from '@/lib/api';
import { roleFor } from '@/design/status';

/**
 * The first screen there is: what the deployment has been doing.
 *
 * The information architecture arrives with the application shell. This exists
 * so that the gate has a real page to lint, type-check, build, drive a browser
 * against and screenshot — a gate proven against nothing is a gate proven
 * against nothing.
 */
export const dynamic = 'force-dynamic';

interface Run {
  readonly run_id: string;
  readonly status: string;
  readonly summary: string | null;
  readonly started_at: string | null;
}

function isRun(value: unknown): value is Run {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  return (
    typeof Reflect.get(value, 'run_id') === 'string' &&
    typeof Reflect.get(value, 'status') === 'string'
  );
}

async function loadRuns(): Promise<{ runs: readonly Run[]; failure: string | null }> {
  try {
    const body = await read('/v1/runs', { cache: 'no-store' });
    const listed: unknown = Reflect.get(body, 'runs');
    const runs = Array.isArray(listed) ? listed.filter(isRun) : [];
    return { runs, failure: null };
  } catch (error) {
    if (error instanceof ApiError) {
      return { runs: [], failure: `The gateway answered ${String(error.status)}.` };
    }
    return { runs: [], failure: 'The gateway could not be reached.' };
  }
}

/** The runs the deployment has recorded, newest first as the gateway orders them. */
export default async function RunsPage(): Promise<ReactNode> {
  const { runs, failure } = await loadRuns();

  return (
    <main data-testid="runs">
      <h1>Investigations</h1>
      {failure === null ? null : <p data-testid="failure">{failure}</p>}
      {failure === null && runs.length === 0 ? (
        <p data-testid="empty">Nothing has been investigated yet.</p>
      ) : null}
      <ul>
        {runs.map((run) => (
          <li key={run.run_id} data-testid="run" data-role={roleFor(run.status)}>
            <span data-testid="run-id">{run.run_id}</span>
            <span data-testid="run-status">{run.status}</span>
            <span data-testid="run-summary">{run.summary ?? ''}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
