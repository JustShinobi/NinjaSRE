'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button, Link } from '@/components/action';
import { Input, Select } from '@/components/form';
import { StatusChip } from '@/components/status';
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
        <StatusChip locale={locale} status={canonical} />
        {reverted ? (
          <span data-testid="role-reverted" className="text-meta text-muted">
            {labels.reverted}
          </span>
        ) : null}
      </div>

      {active !== undefined && active.models.length > 0 ? (
        <Select
          label={labels.knownModel}
          name={`${role.role}-model`}
          disabled={!writable || reverted || blocked}
          value={model}
          options={active.models.map((each) => ({
            value: each.modelId,
            label: annotate(each, labels),
          }))}
          onValueChange={onModel}
        />
      ) : (
        <Input
          label={labels.freeModel}
          name={`${role.role}-model`}
          disabled={!writable || reverted || blocked}
          value={model}
          onValueChange={onModel}
        />
      )}

      {blocked ? (
        <p className="text-meta text-muted">
          {labels.notConnected}{' '}
          <Link href={integrationsHref(provider)} data-testid="connect-credential">
            {labels.connectCredential}
          </Link>
        </p>
      ) : null}

      {active !== undefined && active.configured && !active.verified ? (
        <p data-testid="model-verification-note" className="text-meta text-muted">
          {labels.verificationNote} {active.detail}
        </p>
      ) : null}

      <p className="text-meta text-muted">
        {labels.origin}{' '}
        {role.providerOrigin === role.modelOrigin
          ? role.providerOrigin
          : `${role.providerOrigin} / ${role.modelOrigin}`}
      </p>

      {writable && role.bound && !reverted ? (
        <button
          type="button"
          data-testid={`revert-${role.role}`}
          className="self-start text-meta text-strong underline"
          onClick={onRevert}
        >
          {labels.revert}
        </button>
      ) : null}
    </div>
  );
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
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{
    readonly ok: boolean;
    readonly detail: string;
  } | null>(null);

  function currentProvider(role: RoleValue): string {
    return pendingProvider[role.role] ?? role.provider;
  }
  function currentModel(role: RoleValue): string {
    return pendingModel[role.role] ?? role.model;
  }

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
      setVerifyResult({
        ok: verified,
        detail:
          typeof reason === 'string' && reason !== ''
            ? reason
            : verified
              ? labels.verified
              : labels.verificationFailed,
      });
    } catch {
      setVerifyResult({ ok: false, detail: labels.unreachable });
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

  return (
    <div data-testid="models-editor" className="flex flex-col gap-6">
      {investigator === undefined ? null : (
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
        />
      )}

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

      <div data-testid="advanced-roles" className="flex flex-col gap-2">
        <h4 className="text-strong">{labels.advancedTitle}</h4>
        <p className="text-meta text-muted">{labels.advancedLead}</p>
        {advanced.map((role) => {
          const open = expanded.has(role.role);
          return (
            <details
              key={role.role}
              data-testid={`advanced-role-${role.role}`}
              open={open}
              onToggle={(event) => {
                const isOpen = (event.target as HTMLDetailsElement).open;
                setExpanded((was) => {
                  const next = new Set(was);
                  if (isOpen) next.add(role.role);
                  else next.delete(role.role);
                  return next;
                });
              }}
              className="edge border-border rounded-2 px-3 py-2"
            >
              <summary className="cursor-pointer select-none flex items-center gap-2">
                <span className="font-mono">{role.label}</span>
                <span className="text-meta text-muted">
                  {role.bound ? role.providerOrigin : labels.inherits}
                </span>
              </summary>
              <div className="pt-3">
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
            </details>
          );
        })}
      </div>
    </div>
  );
}
