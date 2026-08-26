import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EN } from '@/i18n/en';
import { message } from '@/i18n/messages';
import {
  LOCALE_COOKIE,
  SESSION_COOKIE,
  SESSION_EXPIRY_COOKIE,
} from '@/session/cookies';
import { AREAS, areaFor } from '@/shell/routes';

/**
 * Every route, opened cold: it renders, it has a title, and the title names both
 * the page and the deployment.
 *
 * Enumerated from the manifest, so a route added tomorrow is covered by having
 * been added. The deployment's name is in the title because an operator with
 * three deployments open has three tabs, and a tab that says only "Approvals" is
 * a tab they act in by mistake.
 */

const cookieJar = new Map<string, string>();
const headerJar = new Map<string, string>();

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) => {
        const value = cookieJar.get(name);
        return value === undefined ? undefined : { name, value };
      },
    }),
  headers: () =>
    Promise.resolve({
      get: (name: string) => headerJar.get(name) ?? null,
    }),
}));

beforeEach(() => {
  cookieJar.clear();
  headerJar.clear();
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('the title of every route', () => {
  it.each(AREAS.map((area) => [area.id] as const))(
    '%s names the page and the deployment',
    async (id) => {
      const { areaMetadata } = await import('@/shell/area');
      const metadata = await areaMetadata(id);

      expect(metadata.title).toBe(`${message('en', areaFor(id).title)} · HAL9000`);
      expect(metadata.description).toBe(message('en', areaFor(id).context));
    },
  );

  it('is in the viewer&apos;s language, not only in the source one', async () => {
    cookieJar.set(LOCALE_COOKIE, 'pt-BR');
    const { areaMetadata } = await import('@/shell/area');

    const metadata = await areaMetadata('administration');
    expect(metadata.title).toBe(
      `${message('pt-BR', 'page.administration.title')} · HAL9000`,
    );
  });

  it('falls back to a name when the deployment has not been given one', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', '');
    const { areaMetadata } = await import('@/shell/area');

    expect(await areaMetadata('runs')).toMatchObject({
      title: `${EN['page.runs.title']} · NinjaSRE`,
    });
  });
});

describe('every route file is wired to the manifest', () => {
  it.each(AREAS.map((area) => [area.id, area.path] as const))(
    '%s renders its own header cold',
    async (id) => {
      const { AreaPage } = await import('@/shell/area');
      render(await AreaPage({ id }));

      const header = screen.getByTestId('page-header');
      expect(header).toHaveAttribute('data-area', id);
      expect(header.textContent).toContain(message('en', areaFor(id).title));
    },
  );

  it('says what a surface without a data screen is, rather than showing nothing', async () => {
    // Any registered area does — `AreaPage` itself is not wired to a real
    // route any more (every area has its own data screen), so this pins its
    // generic fallback in isolation, against an area chosen only because it
    // is a valid one.
    const { AreaPage } = await import('@/shell/area');
    render(await AreaPage({ id: 'resources' }));

    expect(screen.getByTestId('area-pending')).toHaveTextContent(EN['page.pending']);
  });
});

describe('the breadcrumb the header carries', () => {
  it('is absent for a top-level area, because it would only say where you are', async () => {
    const { AreaHeader } = await import('@/shell/area');
    render(<AreaHeader area={areaFor('runs')} locale="en" />);

    expect(
      screen.queryByRole('navigation', { name: EN['breadcrumb.label'] }),
    ).toBeNull();
  });

  it('appears once the route is nested, with the area in front', async () => {
    const { AreaHeader } = await import('@/shell/area');
    render(
      <AreaHeader
        area={areaFor('runs')}
        locale="en"
        nested={[{ label: 'run-0001' }]}
      />,
    );

    const trail = screen.getByRole('navigation', { name: EN['breadcrumb.label'] });
    expect(trail.textContent).toContain(EN['page.runs.title']);
    expect(trail.textContent).toContain('run-0001');
  });
});

/**
 * The header's fourth slot: what state the page is in, as counts.
 *
 * Separate from the actions slot because they are different things wearing the
 * same corner — an action is something to press, a count is something to read —
 * and a screen that put its statistics through the actions slot got them styled
 * as a control and sized like a caption. Resources did exactly that.
 */
describe('the counts a header carries', () => {
  it('renders them where a screen supplies them', async () => {
    const { AreaHeader } = await import('@/shell/area');
    render(
      <AreaHeader
        area={areaFor('resources')}
        locale="en"
        meta={<span data-testid="counts">97 watched</span>}
      />,
    );

    expect(screen.getByTestId('counts')).toHaveTextContent('97 watched');
  });

  it('renders nothing there for a screen with no counts to give', async () => {
    const { AreaHeader } = await import('@/shell/area');
    render(<AreaHeader area={areaFor('resources')} locale="en" />);

    expect(screen.queryByTestId('counts')).toBeNull();
  });

  it('offers the same slot on a Settings page', async () => {
    const { SettingsPageHeader } = await import('@/shell/area');
    const { settingsPageFor } = await import('@/shell/routes');
    render(
      <SettingsPageHeader
        page={settingsPageFor('settings-members-roles')}
        locale="en"
        meta={<span data-testid="counts">4 people</span>}
      />,
    );

    expect(screen.getByTestId('counts')).toHaveTextContent('4 people');
  });

  it('leaves it out on a Settings page that has none', async () => {
    const { SettingsPageHeader } = await import('@/shell/area');
    const { settingsPageFor } = await import('@/shell/routes');
    render(
      <SettingsPageHeader
        page={settingsPageFor('settings-members-roles')}
        locale="en"
      />,
    );

    expect(screen.queryByTestId('counts')).toBeNull();
  });
});

describe('what the server reads off one request', () => {
  it('prefers the stored language over what the browser asked for', async () => {
    cookieJar.set(LOCALE_COOKIE, 'pt-BR');
    headerJar.set('accept-language', 'en-GB,en;q=0.9');
    const { requestLocale } = await import('@/shell/request');

    expect(await requestLocale()).toBe('pt-BR');
  });

  it('falls back to what the browser asked for, then to English', async () => {
    headerJar.set('accept-language', 'pt-BR,pt;q=0.9');
    const { requestLocale } = await import('@/shell/request');
    expect(await requestLocale()).toBe('pt-BR');

    headerJar.set('accept-language', 'fr-FR');
    expect(await requestLocale()).toBe('en');
  });

  it('reads the credential and the expiry, and answers nothing for neither', async () => {
    const { requestCredential, requestExpiry } = await import('@/shell/request');
    expect(await requestCredential()).toBeNull();
    expect(await requestExpiry()).toBeNull();

    cookieJar.set(SESSION_COOKIE, 'opaque');
    cookieJar.set(SESSION_EXPIRY_COOKIE, '2026-08-07T23:00:00Z');
    expect(await requestCredential()).toBe('opaque');
    expect(await requestExpiry()).toBe('2026-08-07T23:00:00Z');
  });

  it('treats an empty credential cookie as no credential', async () => {
    cookieJar.set(SESSION_COOKIE, '');
    const { requestCredential } = await import('@/shell/request');
    expect(await requestCredential()).toBeNull();
  });
});

describe('the not-found page', () => {
  it('renders inside the shell with a way back', async () => {
    const NotFound = (await import('@/app/(shell)/not-found')).default;
    render(await NotFound());

    expect(screen.getByTestId('not-found')).toBeInTheDocument();
    expect(screen.getByText(EN['notFound.title'])).toBeInTheDocument();
    expect(screen.getByTestId('way-back')).toHaveAttribute('href', '/');
  });

  it('names itself in the document title, like every other route', async () => {
    const { generateMetadata } = await import('@/app/(shell)/not-found');
    expect(await generateMetadata()).toMatchObject({
      title: `${EN['notFound.title']} · HAL9000`,
    });
  });
});

describe('the route error boundary', () => {
  it('shows the failure, offers a retry, and leaves the shell alone', async () => {
    const RouteError = (await import('@/app/(shell)/error')).default;
    const reset = vi.fn();
    render(
      <RouteError
        error={Object.assign(new Error('boom'), { digest: 'ab12' })}
        reset={reset}
      />,
    );

    expect(screen.getByTestId('route-error')).toBeInTheDocument();
    expect(screen.getByText(EN['error.title'])).toBeInTheDocument();
    expect(screen.getByRole('button', { name: EN['error.retry'] })).toBeInTheDocument();
  });

  it('renders the digest and never the exception itself', async () => {
    const RouteError = (await import('@/app/(shell)/error')).default;
    render(
      <RouteError
        error={Object.assign(new Error('postgres://user:secret@host/db'), {
          digest: 'ab12',
        })}
        reset={vi.fn()}
      />,
    );

    // The digest correlates the page with a line in the deployment's log and
    // carries nothing. Whatever the exception was holding stays off the screen.
    expect(screen.getByText('ab12')).toBeInTheDocument();
    expect(screen.queryByText(/secret/)).toBeNull();
  });
});

describe('the sign-in page', () => {
  it('says nothing about the deployment behind it', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({}) }));

    const page = screen.getByTestId('sign-in');
    // Not the name, not a count, not a version. Somebody who has not signed in
    // is not owed the fact that this deployment is called HAL9000.
    expect(page.textContent).not.toContain('HAL9000');
  });

  it('posts the credential in a body, never in the address', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({}) }));

    const form = screen.getByTestId('sign-in-form');
    expect(form).toHaveAttribute('method', 'post');
    expect(form).toHaveAttribute('action', '/api/session');
    // A query parameter is in the history, in the proxy's log, and in the
    // `Referer` of the next request.
    expect(form.getAttribute('action')).not.toContain('?');
  });

  it('never puts the password where another origin could read it', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({}) }));

    const password = screen.getByLabelText(EN['signIn.password']);
    expect(password).toHaveAttribute('type', 'password');
    expect(password).toHaveAttribute('name', 'password');

    // The username is not a secret and a password manager needs to see both to
    // offer either, so it is an ordinary text field with the standard token.
    const username = screen.getByLabelText(EN['signIn.username']);
    expect(username).toHaveAttribute('name', 'username');
    expect(username).toHaveAttribute('autocomplete', 'username');
  });

  it('says a credential was refused rather than showing the browser some JSON', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({ reason: 'rejected' }) }));

    expect(screen.getByTestId('sign-in-reason')).toHaveTextContent(
      EN['signIn.rejected'],
    );
  });

  it('distinguishes a deployment it could not reach from a credential it refused', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({ reason: 'unreachable' }) }));

    expect(screen.getByTestId('sign-in-reason')).toHaveTextContent(
      EN['signIn.unreachable'],
    );
  });

  it('carries the route to come back to, and refuses one that leaves the console', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    const { container } = render(
      await SignIn({ searchParams: Promise.resolve({ from: '/approvals' }) }),
    );
    expect(container.querySelector('input[name="returnTo"]')).toHaveValue('/approvals');

    const elsewhere = ['https:', '//elsewhere.invalid'].join('');
    const second = render(
      await SignIn({ searchParams: Promise.resolve({ from: elsewhere }) }),
    );
    expect(second.container.querySelector('input[name="returnTo"]')).toHaveValue('/');
  });

  it('explains an expiry rather than leaving somebody wondering', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({ reason: 'expired' }) }));
    expect(screen.getByTestId('sign-in-reason')).toHaveTextContent(
      EN['signIn.expired'],
    );
  });

  it('says nothing about a reason it was not given', async () => {
    const SignIn = (await import('@/app/sign-in/page')).default;
    render(await SignIn({ searchParams: Promise.resolve({ reason: 'nonsense' }) }));
    expect(screen.queryByTestId('sign-in-reason')).toBeNull();
  });
});
