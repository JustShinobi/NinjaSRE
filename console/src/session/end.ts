import { SESSION_ENDPOINT } from './cookies';

/**
 * End the session on the server.
 *
 * Navigating to the sign-in with the cookie still set is not signing out; it is
 * closing a tab. The next person at that keyboard types the address and is
 * inside, and the operator who pressed the button believes they are not.
 *
 * A failure here is swallowed on purpose. The viewer is leaving either way, and
 * refusing to take them to the sign-in because the sign-out request failed
 * leaves them staring at a console they have already decided to abandon. The
 * cookie's own lifetime is the backstop, and the API refuses the token the
 * moment it is revoked at the source.
 */
export async function endSession(): Promise<void> {
  try {
    await fetch(SESSION_ENDPOINT, { method: 'DELETE', cache: 'no-store' });
  } catch {
    // Leaving anyway. See above.
  }
}
