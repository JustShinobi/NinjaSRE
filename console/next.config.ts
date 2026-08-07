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
};

export default nextConfig;
