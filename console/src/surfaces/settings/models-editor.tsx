'use client';

import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';

import { Button, Link } from '@/components/action';
import { Input, Select } from '@/components/form';
import { CheckChip, StatusChip } from '@/components/status';
import type { Locale } from '@/i18n/messages';

import {
  patchOf,
  ResolutionPreview,
  useConfigWrite,
} from '@/design/resolution-preview';

/**
 * Choosing what drives an investigation, role by role, without opening the
 * raw editor.
 *
 * The investigator's own row opens inside a state card: its display name, the
 * chip of the last verification, and the action to check again. A degraded or
 * failed check surfaces its own row — name, consequence, an exit written with
 * a verb — mirrored from the checks the preflight actually produced, never
 * translated into a word the backend did not report. The seven advanced roles
 * collapse into one line until asked for: nobody who has never touched one
 * pays for seven open accordions.
 *
 * One editor for all eight roles rather than one save button each: the
 * document a save writes is the whole `models` section
 * (`platform/config_service/schema/agents.py`'s `ModelsConfig`), so two
 * saves racing on overlapping roles would be the same hazard a second
 * autonomy editor would be. Every pending edit — the investigator's, and any
 * advanced role's — accumulates here and travels in one patch.
 */

export interface ModelOption {
  readonly modelId: string;
  /** `null` when the model registry holds no row for it — "not known", never "does not support". */
  readonly supportsTools: boolean | null;
}

export interface ProviderOption {
  readonly providerId: string;
  readonly displayName: string;
  readonly configured: boolean;
  readonly verified: boolean;
  /** The gateway's own four-state sentence: nothing stored, stored and unchecked, working, or broken. */
  readonly detail: string;
  readonly models: readonly ModelOption[];
}

export interface RoleValue {
  readonly role: string;
  readonly label: string;
  readonly provider: string;
  readonly model: string;
  /** Set here or by an ancestor, as opposed to resolving to the deployment default. */
  readonly bound: boolean;
  readonly providerOrigin: string;
  readonly modelOrigin: string;
}

/** One preflight check, exactly as the backend reported it. */
export interface CheckView {
  readonly name: string;
  readonly status: 'passed' | 'degraded' | 'failed' | 'skipped';
  readonly detail: string;
  readonly durationMs: number;
}

export interface ModelsEditorLabels {
  readonly provider: string;
  readonly knownModel: string;
  readonly freeModel: string;
  readonly toolCallingSupported: string;
  readonly toolCallingUnsupported: string;
  readonly toolCallingUnknown: string;
  readonly verificationNote: string;
  readonly notConnected: string;
  readonly connectCredential: string;
  readonly advancedTitle: string;
  readonly advancedLead: string;
  readonly advancedSummaryAll: string;
  readonly advancedSummaryPartial: string;
  readonly inherits: string;
  readonly revert: string;
  readonly reverted: string;
  readonly saveAndVerify: string;
  readonly saving: string;
  readonly testWithoutSaving: string;
  readonly verifying: string;
  readonly verified: string;
  readonly verificationFailed: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly before: string;
  readonly after: string;
  readonly nothingChanges: string;
  readonly origin: string;
  readonly checkAgain: string;
  readonly checking: string;
  readonly chooseVerifiedModel: string;
  readonly reloadModels: string;
  readonly reloadingModels: string;
  readonly staticModelsLabel: string;
  /** Each keyed by the preflight's own check name — "credentials", "tool calling", and so on. */
  readonly checkLabels: Readonly<Record<string, string>>;
  readonly checkConsequences: Readonly<Record<string, string>>;
}

export interface ModelsEditorProps {
  readonly nodeId: string;
  readonly locale: Locale;
  readonly writable: boolean;
  readonly providers: readonly ProviderOption[];
  readonly roles: readonly RoleValue[];
  readonly labels: ModelsEditorLabels;
}

/** The path pair one role's selection lives at. */
function pathsFor(role: string): readonly [provider: string, model: string] {
  return [`models.${role}.provider`, `models.${role}.model`];
}

/**
 * Where a provider's own connect-a-credential panel lives, in the catalogue.
 *
 * A plain function defined in this client module rather than a prop handed
 * down from the server: a function is not serialisable across the server/
 * client boundary, and a server component that tried to pass one here would
 * fail only in a real build — never in a unit test, which has no boundary to
 * enforce. `${providerId}` is the same route segment `/integrations/[name]`
 * already resolves.
 */
function integrationsHref(providerId: string): string {
  return `/integrations/${encodeURIComponent(providerId)}`;
}

/** `model`, annotated with what the registry knows about tool calling. */
function annotate(model: ModelOption, labels: ModelsEditorLabels): string {
  const suffix =
    model.supportsTools === true
      ? labels.toolCallingSupported
      : model.supportsTools === false
        ? labels.toolCallingUnsupported
        : labels.toolCallingUnknown;
  return `${model.modelId}${suffix}`;
}

/**
 * `text`, with every occurrence of the raw provider identifier replaced by
 * its display name.
 *
 * The backend's own sentences are written for an operator reading logs and
 * the audit trail, where the raw identifier is the right word. A screen is a
 * different reader: the identifier is reserved for a technical context there,
 * and this is the one seam where a backend sentence becomes screen text.
 */
function humanised(text: string, providerId: string, displayName: string): string {
  if (providerId === '' || text === '') return text;
  return text.split(providerId).join(displayName);
}

interface RoleControlsProps {
  readonly role: RoleValue;
  readonly locale: Locale;
  readonly writable: boolean;
  readonly providers: readonly ProviderOption[];
  readonly provider: string;
  readonly model: string;
  readonly reverted: boolean;
  readonly labels: ModelsEditorLabels;
  readonly onProvider: (value: string) => void;
  readonly onModel: (value: string) => void;
  readonly onRevert: () => void;
  /** The investigator's own card already shows a chip and the static-fallback
   * label; every other role keeps drawing both inline, the way it always has. */
  readonly isInvestigator?: boolean | undefined;
  /** Present only for the investigator: the dynamic listing replaces `active.models`. */
  readonly dynamicModels?:
    readonly { modelId: string; displayName: string }[] | undefined;
  readonly dynamicSource?: 'endpoint' | 'static' | '' | undefined;
}

/** One role's provider and model controls, shared by the investigator row and every advanced role. */
function RoleControls({
  role,
  locale,
  writable,
  providers,
  provider,
  model,
  reverted,
  labels,
  onProvider,
  onModel,
  onRevert,
  isInvestigator = false,
  dynamicModels,
  dynamicSource,
}: RoleControlsProps): ReactNode {
  const active = providers.find((each) => each.providerId === provider);
  // A raw spelling `credentialStatus` does not recognise, deliberately: its
  // own alias table maps the legacy `HealthStatus` word `'unknown'` onto the
  // canonical `'stored'`, which is the wrong badge for "no provider is
  // selected" — the console's own state, not a fact the deployment reported.
  const canonical =
    active === undefined
      ? 'no-provider-selected'
      : active.configured
        ? active.verified
          ? 'healthy'
          : 'configured'
        : 'unconfigured';
  const blocked = active !== undefined && !active.configured;
  // The dynamic listing only replaces the registry's own list once it has
  // actually answered with a recognised source — an unmocked or still-loading
  // fetch must not blank a select that already has something to offer.
  const modelOptions =
    dynamicModels !== undefined && dynamicSource !== '' && dynamicSource !== undefined
      ? dynamicModels
      : active?.models.map((each) => ({
          modelId: each.modelId,
          displayName: annotate(each, labels),
        }));

  return (
    <div data-testid={`model-role-${role.role}`} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          label={labels.provider}
          name={`${role.role}-provider`}
          data-testid={`model-role-${role.role}-provider`}
          disabled={!writable || reverted}
          value={provider}
          options={providers.map((each) => ({
            value: each.providerId,
            label: each.displayName,
          }))}
          onValueChange={onProvider}
        />
        {isInvestigator ? null : <StatusChip locale={locale} status={canonical} />}
      </div>

      {modelOptions !== undefined && modelOptions.length > 0 ? (
        <Select
          label={labels.knownModel}
          name={`${role.role}-model`}
          data-testid={`model-role-${role.role}-model`}
          disabled={!writable || reverted || blocked}
          value={model}
          options={modelOptions.map((each) => ({
            value: each.modelId,
            label: each.displayName,
          }))}
          onValueChange={onModel}
        />
      ) : (
        <Input
          label={labels.freeModel}
          name={`${role.role}-model`}
          data-testid={`model-role-${role.role}-model`}
          disabled={!writable || reverted || blocked}
          value={model}
          onValueChange={onModel}
        />
      )}
      {dynamicSource === 'static' ? (
        <p data-testid="model-list-static-label" className="text-meta text-muted">
          {labels.staticModelsLabel}
        </p>
      ) : null}

      {blocked ? (
        <p className="text-meta text-muted">
          {labels.notConnected}{' '}
          <Link href={integrationsHref(provider)} data-testid="connect-credential">
            {labels.connectCredential}
          </Link>
        </p>
      ) : null}

      {active !== undefined &&
      active.configured &&
      !active.verified &&
      !isInvestigator ? (
        <p data-testid="model-verification-note" className="text-meta text-muted">
          {labels.verificationNote}{' '}
          {humanised(active.detail, active.providerId, active.displayName)}
        </p>
      ) : null}

      {/* "Set at" appears exactly once here — `role.providerOrigin` is
          already the full sentence (`provenanceLabel`'s own "Set at: X" or
          "Deployment default"), so nothing here repeats the label — with the
          action to return to the default right beside it. */}
      <span
        data-testid={isInvestigator ? 'inheritance-line' : undefined}
        className="text-meta text-muted"
      >
        {role.providerOrigin === role.modelOrigin
          ? role.providerOrigin
          : `${role.providerOrigin} / ${role.modelOrigin}`}
        {writable && role.bound && !reverted ? (
          <>
            {' · '}
            <button
              type="button"
              data-testid={
                isInvestigator ? 'revert-investigator' : `revert-${role.role}`
              }
              className="text-strong underline"
              onClick={onRevert}
            >
              {labels.revert}
            </button>
          </>
        ) : null}
        {reverted ? <span data-testid="role-reverted"> {labels.reverted}</span> : null}
      </span>
    </div>
  );
}

/** One check's label, humanised: "tool calling" becomes "Tool calling". */
function checkLabel(name: string, labels: ModelsEditorLabels): string {
  const declared = labels.checkLabels[name];
  if (declared !== undefined) return declared;
  return name.length === 0 ? name : name.charAt(0).toUpperCase() + name.slice(1);
}

interface ModelListingState {
  readonly models: readonly { modelId: string; displayName: string }[];
  readonly source: 'endpoint' | 'static' | '';
}

async function fetchListing(
  providerId: string,
  refresh: boolean,
): Promise<ModelListingState> {
  try {
    const query = refresh ? '&refresh=true' : '';
    const response = await fetch(
      `/api/models?provider=${encodeURIComponent(providerId)}${query}`,
    );
    const body: unknown = await response.json().catch(() => ({}));
    const rawModels: unknown = Reflect.get(Object(body), 'models');
    const models = Array.isArray(rawModels)
      ? rawModels
          .map((entry) => ({
            modelId: String(Reflect.get(Object(entry), 'model_id') ?? ''),
            displayName: String(Reflect.get(Object(entry), 'display_name') ?? ''),
          }))
          .filter((entry) => entry.modelId !== '')
      : [];
    const source: unknown = Reflect.get(Object(body), 'source');
    return {
      models,
      source: source === 'endpoint' || source === 'static' ? source : '',
    };
  } catch {
    return { models: [], source: '' };
  }
}

export function ModelsEditor({
  nodeId,
  locale,
  writable,
  providers,
  roles,
  labels,
}: ModelsEditorProps): ReactNode {
  const investigator = roles.find((each) => each.role === 'investigator');
  const advanced = roles.filter((each) => each.role !== 'investigator');

  const [pendingProvider, setPendingProvider] = useState<
    Readonly<Record<string, string>>
  >({});
  const [pendingModel, setPendingModel] = useState<Readonly<Record<string, string>>>(
    {},
  );
  const [reverted, setReverted] = useState<ReadonlySet<string>>(new Set());
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    readonly ok: boolean;
    readonly detail: string;
    readonly checks: readonly CheckView[];
  } | null>(null);
  const [listings, setListings] = useState<Readonly<Record<string, ModelListingState>>>(
    {},
  );
  const [listingBusy, setListingBusy] = useState<ReadonlySet<string>>(new Set());

  function currentProvider(role: RoleValue): string {
    return pendingProvider[role.role] ?? role.provider;
  }
  function currentModel(role: RoleValue): string {
    return pendingModel[role.role] ?? role.model;
  }

  const investigatorProvider =
    investigator === undefined ? '' : currentProvider(investigator);

  async function loadListing(providerId: string, refresh: boolean): Promise<void> {
    if (providerId === '') return;
    setListingBusy((was) => new Set(was).add(providerId));
    const listing = await fetchListing(providerId, refresh);
    setListings((was) => ({ ...was, [providerId]: listing }));
    setListingBusy((was) => {
      const next = new Set(was);
      next.delete(providerId);
      return next;
    });
  }

  useEffect(() => {
    if (investigatorProvider === '') return;
    if (listings[investigatorProvider] !== undefined) return;
    // Deferred a microtask past the effect's own body: `loadListing` sets
    // state as its first statement, and calling it synchronously here would
    // be a state update in the same flush as the effect itself.
    const providerId = investigatorProvider;
    void Promise.resolve().then(() => loadListing(providerId, false));
    // Only the investigator's own model list is fetched dynamically here —
    // exactly the role the state card is about.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [investigatorProvider]);

  function setProvider(role: RoleValue, value: string): void {
    setReverted((was) => {
      if (!was.has(role.role)) return was;
      const next = new Set(was);
      next.delete(role.role);
      return next;
    });
    setPendingProvider((was) => ({ ...was, [role.role]: value }));
  }
  function setModel(role: RoleValue, value: string): void {
    setPendingModel((was) => ({ ...was, [role.role]: value }));
  }
  function without(
    from: Readonly<Record<string, string>>,
    role: string,
  ): Readonly<Record<string, string>> {
    return Object.fromEntries(Object.entries(from).filter(([key]) => key !== role));
  }

  function revert(role: RoleValue): void {
    setReverted((was) => new Set(was).add(role.role));
    setPendingProvider((was) => without(was, role.role));
    setPendingModel((was) => without(was, role.role));
  }

  const changedRoles = roles.filter(
    (role) =>
      reverted.has(role.role) ||
      currentProvider(role) !== role.provider ||
      currentModel(role) !== role.model,
  );
  const entries: (readonly [string, unknown])[] = [];
  for (const role of changedRoles) {
    if (reverted.has(role.role)) continue;
    const [providerPath, modelPath] = pathsFor(role.role);
    entries.push([providerPath, currentProvider(role)]);
    entries.push([modelPath, currentModel(role)]);
  }
  const patch = patchOf(entries);
  const remove = [...reverted].flatMap((role) => pathsFor(role));

  const write = useConfigWrite(nodeId, patch, remove, {
    unreachable: labels.unreachable,
    failed: labels.failed,
  });
  const dirty = changedRoles.length > 0;

  async function verify(providerId: string): Promise<void> {
    setVerifyBusy(true);
    setVerifyResult(null);
    try {
      const response = await fetch('/api/verify', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ kind: 'provider', name: providerId }),
      });
      const body: unknown = await response.json().catch(() => ({}));
      const verified = Reflect.get(Object(body), 'verified') === true;
      const reason: unknown = Reflect.get(Object(body), 'reason');
      const rawChecks: unknown = Reflect.get(Object(body), 'checks');
      const checks: CheckView[] = Array.isArray(rawChecks)
        ? rawChecks.map((entry) => ({
            name: String(Reflect.get(Object(entry), 'name') ?? ''),
            status:
              (Reflect.get(Object(entry), 'status') as
                CheckView['status'] | undefined) ?? 'skipped',
            detail: String(Reflect.get(Object(entry), 'detail') ?? ''),
            durationMs: Number(Reflect.get(Object(entry), 'duration_ms') ?? 0),
          }))
        : [];
      // The backend writes its summary sentence for an operator reading logs,
      // where the raw provider identifier is the right word — the same reason
      // `humanised` exists for the structured error block below. A screen is a
      // different reader, so the same substitution applies here too.
      const verifiedProvider = providers.find((each) => each.providerId === providerId);
      setVerifyResult({
        ok: verified,
        detail:
          typeof reason === 'string' && reason !== ''
            ? humanised(reason, providerId, verifiedProvider?.displayName ?? providerId)
            : verified
              ? labels.verified
              : labels.verificationFailed,
        checks,
      });
    } catch {
      setVerifyResult({ ok: false, detail: labels.unreachable, checks: [] });
    } finally {
      setVerifyBusy(false);
    }
  }

  async function saveAndVerify(): Promise<void> {
    const resolved = dirty ? await write.preview() : null;
    if (dirty && !resolved?.accepted) return;
    if (dirty) {
      const ok = await write.save();
      if (!ok) return;
    }
    if (investigator !== undefined) await verify(currentProvider(investigator));
  }

  async function testWithoutSaving(): Promise<void> {
    if (investigator !== undefined) await verify(investigator.provider);
  }

  const activeInvestigatorProvider = providers.find(
    (each) => each.providerId === investigatorProvider,
  );
  const listing = listings[investigatorProvider];
  const listingLoading = listingBusy.has(investigatorProvider);

  // The chip mirrors a live check when one exists; otherwise it falls back to
  // what was last recorded — "verified"/"configured"/"unconfigured" via the
  // same canonical mapping every other credential chip in this console uses.
  const failingCheck = verifyResult?.checks.find((check) => check.status === 'failed');
  const degradedCheck = verifyResult?.checks.find(
    (check) => check.status === 'degraded',
  );
  const problemCheck = failingCheck ?? degradedCheck;
  const headlineStatus =
    verifyResult === null
      ? activeInvestigatorProvider === undefined
        ? 'no-provider-selected'
        : activeInvestigatorProvider.configured
          ? activeInvestigatorProvider.verified
            ? 'verified'
            : 'stored'
          : 'not_connected'
      : failingCheck !== undefined
        ? 'failing'
        : degradedCheck !== undefined
          ? 'degraded'
          : 'verified';

  return (
    <div data-testid="models-editor" className="flex flex-col gap-6">
      {investigator === undefined ? null : (
        <div
          data-testid="provider-state-card"
          className="flex flex-col gap-3 rounded-3 edge border-border p-4"
        >
          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="provider-state-header"
          >
            <span data-testid="provider-state-name" className="text-strong">
              {activeInvestigatorProvider?.displayName ?? ''}
            </span>
            <StatusChip
              locale={locale}
              status={headlineStatus}
              data-testid="provider-state-chip"
            />
            <span className="grow" />
            <Button
              data-testid="check-again"
              state={verifyBusy ? 'loading' : 'default'}
              onClick={() => {
                void verify(currentProvider(investigator));
              }}
            >
              {verifyBusy ? labels.checking : labels.checkAgain}
            </Button>
          </div>

          <RoleControls
            role={investigator}
            locale={locale}
            writable={writable}
            providers={providers}
            provider={currentProvider(investigator)}
            model={currentModel(investigator)}
            reverted={reverted.has('investigator')}
            labels={labels}
            onProvider={(value) => {
              setProvider(investigator, value);
            }}
            onModel={(value) => {
              setModel(investigator, value);
            }}
            onRevert={() => {
              revert(investigator);
            }}
            isInvestigator
            dynamicModels={listing?.models}
            dynamicSource={listing?.source}
          />
          <div className="flex items-center gap-2">
            <Button
              data-testid="reload-models"
              state={listingLoading ? 'loading' : 'default'}
              onClick={() => {
                void loadListing(investigatorProvider, true);
              }}
            >
              {listingLoading ? labels.reloadingModels : labels.reloadModels}
            </Button>
          </div>

          {problemCheck !== undefined ? (
            <div
              data-testid="verification-error-block"
              className="flex flex-col gap-1 rounded-2 edge border-border p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <CheckChip
                  name={checkLabel(problemCheck.name, labels)}
                  status={problemCheck.status === 'failed' ? 'failed' : 'degraded'}
                  data-testid="verification-error-chip"
                />
                <span
                  className="text-meta text-muted"
                  data-testid="verification-error-detail"
                >
                  {humanised(
                    problemCheck.detail,
                    activeInvestigatorProvider?.providerId ?? '',
                    activeInvestigatorProvider?.displayName ?? '',
                  )}
                </span>
              </div>
              <p
                className="text-meta text-muted"
                data-testid="verification-error-consequence"
              >
                {labels.checkConsequences[problemCheck.name] ?? ''}{' '}
                <Link href="#" data-testid="verification-error-exit">
                  {labels.chooseVerifiedModel}
                </Link>
              </p>
            </div>
          ) : null}

          {writable ? (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="primary"
                data-testid="save-and-verify"
                state={write.status !== '' || verifyBusy ? 'loading' : 'default'}
                onClick={() => {
                  void saveAndVerify();
                }}
              >
                {write.status !== '' ? labels.saving : labels.saveAndVerify}
              </Button>
              <Button
                data-testid="test-without-saving"
                state={verifyBusy ? 'loading' : 'default'}
                onClick={() => {
                  void testWithoutSaving();
                }}
              >
                {verifyBusy ? labels.verifying : labels.testWithoutSaving}
              </Button>
            </div>
          ) : null}

          {verifyResult !== null ? (
            <p
              data-testid="verify-result"
              className={
                verifyResult.ok ? 'text-meta text-success' : 'text-meta text-danger'
              }
            >
              {verifyResult.detail}
            </p>
          ) : null}

          {write.resolved !== null && write.current ? (
            <ResolutionPreview
              changes={write.resolved.changes}
              labels={{
                before: labels.before,
                after: labels.after,
                nothingChanges: labels.nothingChanges,
              }}
            />
          ) : null}
          {write.saved ? (
            <p data-testid="models-saved" className="text-meta text-success">
              {labels.saved}
            </p>
          ) : null}
          {write.failure === '' ? null : (
            <p data-testid="models-failure" className="text-meta text-danger">
              {write.failure}
            </p>
          )}
        </div>
      )}

      <div
        data-testid="advanced-roles"
        className="flex flex-col gap-2 rounded-3 edge border-border p-3"
      >
        <button
          type="button"
          data-testid="advanced-roles-toggle"
          className="flex items-center gap-2 text-left"
          onClick={() => {
            setAdvancedOpen((was) => !was);
          }}
        >
          <h4 className="text-strong">{labels.advancedTitle}</h4>
          <span data-testid="advanced-roles-summary" className="text-meta text-muted">
            {advanced.every((role) => !role.bound)
              ? labels.advancedSummaryAll.replace('{total}', String(advanced.length))
              : labels.advancedSummaryPartial
                  .replace('{total}', String(advanced.length))
                  .replace(
                    '{inheriting}',
                    String(advanced.filter((role) => !role.bound).length),
                  )}
          </span>
          <span className="text-meta text-muted">{advancedOpen ? '▾' : '▸'}</span>
        </button>
        <p className="text-meta text-muted">{labels.advancedLead}</p>
        {advancedOpen
          ? advanced.map((role) => (
              <div key={role.role} className="edge border-border rounded-2 px-3 py-2">
                <p className="font-mono text-meta">{role.label}</p>
                <RoleControls
                  role={role}
                  locale={locale}
                  writable={writable}
                  providers={providers}
                  provider={currentProvider(role)}
                  model={currentModel(role)}
                  reverted={reverted.has(role.role)}
                  labels={labels}
                  onProvider={(value) => {
                    setProvider(role, value);
                  }}
                  onModel={(value) => {
                    setModel(role, value);
                  }}
                  onRevert={() => {
                    revert(role);
                  }}
                />
              </div>
            ))
          : null}
      </div>
    </div>
  );
}
