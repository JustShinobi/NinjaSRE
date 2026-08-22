'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { cx } from '@/design/cx';
import { AlertTriangleIcon } from '@/design/icons';
import {
  CredentialField,
  type CredentialFieldSpec,
  type CredentialLabels,
} from '../credential';
import { ModelStep, type ModelStepLabels } from './model';

/**
 * The provider's key, and the question only a working key can answer.
 *
 * Storing a credential and having a usable one are two different facts, and
 * this step used to establish only the first: the form wrote to the vault, said
 * "stored", and left. What that costs is discovered one screen later — a
 * mistyped key looks exactly like a correct one until something tries to use
 * it, and the sentence somebody gets then is about a credential that does not
 * resolve, which reads like the deployment's fault rather than the key's.
 *
 * So the write is followed by the cheapest question that cannot be answered
 * without a working key: **what do you serve?** The provider's own listing
 * endpoint is a `GET`, it spends no tokens, and it authenticates with the key
 * that was just written. An answer proves the key. And the answer *is* the list
 * of models — so the choice that used to be a separate step, made against a
 * static list this build shipped, is made here against what the operator's own
 * account can actually reach.
 *
 * **The static list is a fallback, never a silent one.** A provider that
 * declares no listing implementation, an endpoint that is unreachable, and a
 * key the endpoint rejected are three different things, and the deployment
 * distinguishes them in one field: `reason`. It is shown verbatim. A step that
 * quietly showed the shipped list instead would be telling somebody their key
 * works, which is the claim this whole step exists to stop making.
 *
 * Nothing here holds the key. `CredentialField` drops what was typed the moment
 * the write is accepted, and the listing call carries no credential at all —
 * the deployment resolves that from its own vault.
 */

/** Where the console asks what a provider currently serves. */
export const MODELS_ENDPOINT = '/api/models';

export interface ProviderCredentialStepLabels {
  readonly credential: CredentialLabels;
  readonly model: ModelStepLabels;
  /** While the provider is being asked. */
  readonly checking: string;
  /** The provider answered, so the key works and the list below is its own. */
  readonly accepted: string;
  /** It would not answer. Followed by the deployment's own reason, verbatim. */
  readonly notListed: string;
  /** What sits above the chooser. */
  readonly chooseModel: string;
}

export interface ProviderCredentialStepProps {
  readonly provider: string;
  readonly fields: readonly CredentialFieldSpec[];
  readonly whereToGetIt?: string;
  /** The models this build ships for the provider — the fallback list. */
  readonly staticModels: readonly string[];
  readonly defaultModel: string;
  /** The node this deployment writes configuration at. */
  readonly nodeId: string;
  readonly labels: ProviderCredentialStepLabels;
}

/** What the listing answered, once. */
interface Listing {
  /** `true` when the provider's own endpoint answered — which proves the key. */
  readonly live: boolean;
  readonly models: readonly string[];
  /** Why the list is the static one. Empty when it is not. */
  readonly reason: string;
}

/** The model identifiers a listing answer names, in the order it gave them. */
function modelsOf(body: unknown): readonly string[] {
  const models: unknown = Reflect.get(Object(body), 'models');
  if (!Array.isArray(models)) return [];
  return models
    .map((entry) => String(Reflect.get(Object(entry), 'model_id') ?? ''))
    .filter((modelId) => modelId !== '');
}

/**
 * Which of `models` to start the chooser on.
 *
 * The provider's default when the endpoint still serves it, and otherwise the
 * first thing it does serve. Seeding a chooser with a name absent from its own
 * options is how a step saves a model the endpoint has retired.
 */
function startOn(models: readonly string[], preferred: string): string {
  if (models.includes(preferred)) return preferred;
  return models[0] ?? preferred;
}

/** Store a provider key, prove it against the provider, then choose a model. */
export function ProviderCredentialStep({
  provider,
  fields,
  whereToGetIt = '',
  staticModels,
  defaultModel,
  nodeId,
  labels,
}: ProviderCredentialStepProps): ReactNode {
  const [checking, setChecking] = useState(false);
  const [listing, setListing] = useState<Listing | null>(null);

  async function ask(): Promise<void> {
    setChecking(true);
    setListing(null);
    const address = `${MODELS_ENDPOINT}?provider=${encodeURIComponent(provider)}&refresh=true`;
    let answer: Response;
    try {
      answer = await fetch(address, {
        headers: { accept: 'application/json' },
        cache: 'no-store',
      });
    } catch {
      setChecking(false);
      setListing({
        live: false,
        models: staticModels,
        reason: labels.credential.unreachable,
      });
      return;
    }
    const body: unknown = await answer.json().catch(() => ({}));
    setChecking(false);
    const live = String(Reflect.get(Object(body), 'source') ?? '') === 'endpoint';
    const offered = modelsOf(body);
    setListing({
      live,
      models: live ? offered : offered.length > 0 ? offered : staticModels,
      reason: live ? '' : String(Reflect.get(Object(body), 'reason') ?? ''),
    });
  }

  const models = listing?.models ?? [];

  return (
    <div
      data-testid="provider-credential-step"
      data-provider={provider}
      className="flex flex-col gap-4"
    >
      <CredentialField
        integration={provider}
        fields={fields}
        whereToGetIt={whereToGetIt}
        labels={labels.credential}
        onStored={() => {
          void ask();
        }}
      />

      {checking ? (
        <p
          className="text-meta text-muted"
          role="status"
          data-testid="credential-checking"
        >
          {labels.checking}
        </p>
      ) : null}

      {listing === null ? null : (
        <p
          // `status` for an answer and `alert` for one that did not come:
          // colour is not what tells somebody their key was never proved.
          role={listing.live ? 'status' : 'alert'}
          data-testid="credential-check"
          className={cx(
            'flex items-center gap-2 rounded-2 edge px-3 py-2 text-meta',
            listing.live
              ? 'bg-success-bg text-success border-success'
              : 'bg-warning-bg text-warning border-warning',
          )}
        >
          {listing.live ? null : (
            <span aria-hidden="true">
              <AlertTriangleIcon />
            </span>
          )}
          {listing.live
            ? labels.accepted
            : `${labels.notListed} ${listing.reason}`.trim()}
        </p>
      )}

      {listing === null ? null : (
        <div className="flex flex-col gap-2">
          <p className="text-small text-muted">{labels.chooseModel}</p>
          <ModelStep
            // Remounted when the list changes: the chooser seeds itself from
            // `defaultModel` once, and a second listing has to re-seed it
            // rather than keep a selection the new list may not contain.
            key={models.join('|')}
            provider={provider}
            models={models}
            defaultModel={startOn(models, defaultModel)}
            nodeId={nodeId}
            labels={labels.model}
          />
        </div>
      )}
    </div>
  );
}
