/**
 * Where the palette asks its question.
 *
 * Its own module so the courier's route file and the browser client can share
 * one string without the client importing a server route — the same separation
 * `VERIFY_ENDPOINT` keeps, and for the same reason: a path written twice is a
 * path that gets renamed once.
 */
export const SEARCH_ENDPOINT = '/api/search';
