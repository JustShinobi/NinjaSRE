import type { NextConfig } from 'next';

/**
 * The production build, and the two properties the gate asserts about it.
 *
 * `output: 'standalone'` produces a directory a deployment can run with the
 * pinned Node and nothing else installed — no package manager, no registry, no
 * install step behind the reverse proxy.
 *
 * `basePath` is read from the environment at build time so an operator can
 * serve the console somewhere other than the root of their proxy. It is empty
 * by default, which is the single-host compose case.
 *
 * There is deliberately no image, font or script host configured. Every asset
 * the console needs is bundled, and the end-to-end suite fails the build on any
 * request that leaves the deployment.
 */
const basePath = process.env.NINJASRE_CONSOLE_BASE_PATH ?? '';

/**
 * Where the nine routes the menu reorganisation folded into a tab now answer.
 *
 * Declarative, not a page file per old address: a redirect here is resolved
 * before a route file would even be looked up, so there is nothing under
 * `src/app/(shell)/` for the nine former areas any more — `routes.ts`'s own
 * manifest is still the one list of what a *page* is, and this is the one list
 * of what used to be a page and is not any more. A query string on the
 * incoming request that the destination does not already use is appended by
 * Next.js automatically, which is what carries a deep link such as
 * `/approvals/{id}` through as `?selected={id}` once the two remaining
 * call sites that used to build that address are themselves pointed at the
 * merged screen (`shell/load.ts`, `surfaces/screens/dashboard.tsx`).
 */
const FOLDED_AREAS: readonly { source: string; destination: string }[] = [
  { source: '/approvals', destination: '/decisions?tab=actions' },
  { source: '/approvals/:path*', destination: '/decisions?tab=actions' },
  { source: '/proposals', destination: '/decisions?tab=changes' },
  { source: '/memory', destination: '/knowledge?tab=learned' },
  { source: '/topology', destination: '/knowledge?tab=topology' },
  { source: '/detectors', destination: '/signals?tab=observation' },
  { source: '/data', destination: '/signals?tab=intake' },
  { source: '/audit', destination: '/administration?tab=audit' },
  // The Catalogue route's write half is what Integrations now is; its read
  // half moved to The agent's own Tools tab. A visitor arriving at the old
  // address is more often here to find or fix a credential than to browse
  // the tool list, so this is where the redirect lands.
  { source: '/catalogue', destination: '/integrations' },
  { source: '/team-context', destination: '/agent?tab=team' },
];

const nextConfig: NextConfig = {
  output: 'standalone',
  basePath,
  reactStrictMode: true,
  poweredByHeader: false,
  // The default loader rewrites an <Image> through a runtime optimiser. Serving
  // the bytes as they were built keeps the deployment free of a second process
  // and keeps every asset local, which is the property the network audit
  // asserts.
  images: { unoptimized: true },
  typescript: {
    // The build type-checks what it compiles; `make console-typecheck` runs tsc
    // over the whole tree, tests and configuration included. Neither is allowed
    // to pass on a type error.
    ignoreBuildErrors: false,
  },
  redirects() {
    return Promise.resolve(
      FOLDED_AREAS.map(({ source, destination }) => ({
        source,
        destination,
        // Temporary rather than permanent: pre-alpha, no users yet, and a
        // browser that cached a 308 across this reorganisation would still be
        // caching it the day the map moves again.
        permanent: false,
      })),
    );
  },
};

export default nextConfig;
