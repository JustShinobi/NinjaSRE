import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { applyTheme, storeTheme, THEME_STORAGE_KEY } from '@/design/theme';
import { SESSION_COOKIE, SESSION_EXPIRY_COOKIE } from '@/session/cookies';
import { useBrowserLocale, useChosenTheme, useNow } from '@/shell/browser';
import { EmptyStateLink } from '@/shell/empty-link';

/**
 * The credential's whole journey, and the three values only a browser has.
 *
 * The credential arrives in a body, is offered to the API origin, and becomes an
 * HTTP-only cookie. Every assertion here is about a place it must *not* be: not
 * in the redirect, not in a readable cookie, not in the response body, and not
 * replayed by the redirect's method.
 */

// jsdom normalises the loopback address in a URL, so the console's own
// origin is written the way the request ends up carrying it.
const CONSOLE_ORIGIN = 'http://localhost:8423';

function signInRequest(fields: Readonly<Record<string, string>>): NextRequest {
  const body = new FormData();
  for (const [name, value] of Object.entries(fields)) {
    body.set(name, value);
  }
  return new NextRequest(`${CONSOLE_ORIGIN}/api/session`, { method: 'POST', body });
}

function accepting(status: number): typeof fetch {
  return vi.fn(() => Promise.resolve(new Response('{}', { status })));
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://127.0.0.1:8424');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

describe('exchanging a credential for a session', () => {
  it('offers the credential to the API origin, never to the console origin', async () => {
    const fetching = accepting(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/session/route');

    await POST(signInRequest({ credential: 'tok_live', returnTo: '/approvals' }));

    const [url, init] = (fetching as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0] as [string, RequestInit];
    expect(url).toBe('http://127.0.0.1:8424/auth/me');
    expect(new Headers(init.headers).get('authorization')).toBe('Bearer tok_live');
  });

  it('keeps the credential where no component can read it', async () => {
    vi.stubGlobal('fetch', accepting(200));
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'tok_live' }));
    const session = answer.cookies.get(SESSION_COOKIE);

    expect(session?.value).toBe('tok_live');
    // HTTP-only is the structural half: `document.cookie` cannot see it however
    // hard a component tries, so no bug in a component can leak one.
    expect(session?.httpOnly).toBe(true);
    expect(session?.sameSite).toBe('strict');
  });

  it('puts the credential in no address and no body', async () => {
    vi.stubGlobal('fetch', accepting(200));
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'tok_live' }));

    expect(answer.headers.get('location')).not.toContain('tok_live');
    expect(await answer.text()).not.toContain('tok_live');
  });

  it('redirects with a method that cannot replay the credential', async () => {
    vi.stubGlobal('fetch', accepting(200));
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'tok_live' }));

    // 303, so the browser follows with a GET. A 307 replays the POST, and the
    // body of that POST is the credential.
    expect(answer.status).toBe(303);
  });

  it('publishes only the expiry to the browser, and only the expiry', async () => {
    vi.stubGlobal('fetch', accepting(200));
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'tok_live' }));
    const expiry = answer.cookies.get(SESSION_EXPIRY_COOKIE);

    expect(expiry?.httpOnly).toBe(false);
    expect(expiry?.value).not.toContain('tok_live');
    expect(Number.isNaN(new Date(expiry?.value ?? '').getTime())).toBe(false);
  });

  it('comes back to where the viewer was, and refuses to leave the console', async () => {
    vi.stubGlobal('fetch', accepting(200));
    const { POST } = await import('@/app/api/session/route');

    const kept = await POST(signInRequest({ credential: 'x', returnTo: '/audit' }));
    expect(kept.headers.get('location')).toBe(`${CONSOLE_ORIGIN}/audit`);

    const elsewhere = ['https:', '//elsewhere.invalid/steal'].join('');
    const refused = await POST(signInRequest({ credential: 'x', returnTo: elsewhere }));
    expect(refused.headers.get('location')).toBe(`${CONSOLE_ORIGIN}/`);
  });

  it('sets no session at all when the API does not accept the credential', async () => {
    vi.stubGlobal('fetch', accepting(401));
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'wrong' }));

    expect(answer.status).toBe(401);
    expect(answer.cookies.get(SESSION_COOKIE)?.value).toBe('');
  });

  it('refuses an empty credential without asking the API about it', async () => {
    const fetching = accepting(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: '   ' }));

    expect(answer.status).toBe(400);
    expect(fetching).not.toHaveBeenCalled();
  });

  it('distinguishes a deployment it cannot reach from a credential it rejected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('network'))),
    );
    const { POST } = await import('@/app/api/session/route');

    const answer = await POST(signInRequest({ credential: 'tok_live' }));

    // Otherwise somebody retypes a token that was right all along.
    expect(answer.status).toBe(502);
  });

  it('clears both cookies when the session is ended deliberately', async () => {
    const { DELETE } = await import('@/app/api/session/route');
    const answer = DELETE();

    expect(answer.cookies.get(SESSION_COOKIE)?.value).toBe('');
    expect(answer.cookies.get(SESSION_EXPIRY_COOKIE)?.value).toBe('');
  });
});

describe('the values only a browser has', () => {
  function Probe(): React.ReactNode {
    const now = useNow();
    const theme = useChosenTheme();
    const locale = useBrowserLocale();
    return (
      <span data-testid="probe" data-theme={theme ?? 'system'} data-locale={locale}>
        {now === null ? 'no clock' : 'a clock'}
      </span>
    );
  }

  it('reads the clock, the chosen theme and the locale', () => {
    render(<Probe />);
    const probe = screen.getByTestId('probe');

    expect(probe).toHaveTextContent('a clock');
    expect(probe).toHaveAttribute('data-theme', 'system');
    expect(probe).toHaveAttribute('data-locale', 'en');
  });

  it('follows a theme chosen while the page is open', () => {
    render(<Probe />);
    act(() => {
      storeTheme('dark');
    });

    expect(screen.getByTestId('probe')).toHaveAttribute('data-theme', 'dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    act(() => {
      storeTheme(null);
    });
    expect(screen.getByTestId('probe')).toHaveAttribute('data-theme', 'system');
    applyTheme(null);
  });

  it('reads the locale a viewer chose', () => {
    document.cookie = 'ninjasre_locale=pt-BR';
    render(<Probe />);
    expect(screen.getByTestId('probe')).toHaveAttribute('data-locale', 'pt-BR');
    document.cookie = 'ninjasre_locale=; max-age=0';
  });
});

describe('the way back from a page that does not exist', () => {
  it('is a real link as well as a control', async () => {
    const assign = vi.fn();
    vi.stubGlobal('location', { assign });

    render(
      <EmptyStateLink
        heading="There is no such page"
        body="The address does not name an area of this console."
        actionLabel="Go to the overview"
        href="/"
      />,
    );

    expect(screen.getByTestId('way-back')).toHaveAttribute('href', '/');
    await userEvent.click(screen.getByRole('button', { name: 'Go to the overview' }));
    expect(assign).toHaveBeenCalledWith('/');
  });
});
