# NinjaSRE on Proxmox VE

One command, run on a Proxmox node as root, that creates an LXC container and
installs NinjaSRE **directly into it** — PostgreSQL under the guest's own init,
the platform's three processes under systemd or OpenRC. No container runtime,
no images.

```sh
git clone <this repository> /root/NinjaSRE
cd /root/NinjaSRE/deploy/proxmox
./ninjasre-lxc.sh --distro debian --ip dhcp \
    --llm-provider ollama --llm-base-url http://192.0.2.10:11434
```

One model provider is the whole minimum viable configuration and the platform
will not start without one. Give it here, put it in `--env-file`, or leave it
out: provisioning then installs everything, stops before starting the services,
and prints the two lines to add and the one command to re-run.

An LXC container is already the isolation boundary. Nesting a second runtime
inside it would add an image build, a daemon and a storage driver to something
that needs none of them, so the guest gets three services, one configuration
file and one database — all of them things an operator can read with the tools
they already know.

What that costs is the graph extension, which neither distribution packages and
which is therefore compiled during provisioning. That is the one slow step, and
it is why the container is given more memory than the running platform needs.

## What it does, in order

1. **Preflight.** Root, a real node, a storage that accepts container root
   filesystems, a bridge that exists, enough free memory, a free container ID,
   a template. `--check-only` stops here; `--dry-run` prints every command.
2. **Create.** `pct create`, unprivileged, with `nesting=1,keyctl=1`.
3. **Install the system.** [`guest/install-system.sh`](guest/install-system.sh):
   PostgreSQL 18, the vector extension, the graph extension compiled from its
   published release artefact after a checksum check, the pinned CPython the
   project targets, and the service account. This is the only file that knows a
   package manager.
4. **Ship the source.** `git archive` of the working tree by default, so the
   repository's own ignore rules decide what travels — no virtualenv, no
   `node_modules`, no stray environment file.
5. **Install the platform.** [`guest/bring-up.sh`](guest/bring-up.sh): a virtual
   environment, the role and database, both extensions, the generated secrets,
   the migrations, the three service units, and a wait on `/health/ready`.

Steps 3 and 5 are separately re-runnable inside the guest, and step 5 keeps any
configuration it finds. That is what makes "set the provider and run it again" a
real instruction rather than a reprovision.

## Choosing the distribution

Both work, and every dependency was verified on both rather than assumed. The
table below is measured, not quoted from documentation.

| | Debian 13 | Alpine 3.23 |
|---|---|---|
| Python 3.14.7 | fetched by `uv` (glibc build) | fetched by `uv` (musl build) |
| Provisioning time | ~9 min | ~11 min (musl builds a few wheels) |
| Python dependencies | install and import ✅ | install and import ✅ (musl wheels) |
| PostgreSQL 18.4 | PGDG repository (`trixie-pgdg`) | `postgresql18`, in community |
| Vector extension 0.8.6 | `postgresql-18-pgvector` | compiled from source |
| Graph extension 1.8.0 | **compiled from source** | **compiled from source** |
| Init | systemd | OpenRC |
| Shell in template | bash | busybox ash |
| Template size | ~124 MB | ~3 MB |

Four things follow from it, and each one is a decision this flow makes for you:

- **PostgreSQL is pinned to 18 on both**, the current stable major. The graph
  extension is built against one major version's server headers and loads into
  no other, so the major and the artefact URL are one decision in two places and
  a contract test holds them together. Debian 13 ships 17, so the flow adds the
  PostgreSQL project's own repository rather than taking the distribution's.

- **The graph extension is checked before it is compiled.** It arrives as the
  upstream's published release tarball, not a clone of a branch, and its
  SHA-256 is verified first — what is being built becomes a shared library the
  database server loads into its own process.
- **Neither distribution packages the graph extension.** It is cloned at a
  pinned tag and compiled against the server that was just installed. It builds
  cleanly against musl as well as glibc — the only Alpine-specific requirement
  is `perl`, which is not in the base template and whose absence fails the build
  two minutes in with a message naming only a Makefile line. It is installed up
  front for that reason.
- **Both distributions run the same vector version.** Alpine does package the
  extension for this major, but at 0.8.1 against PGDG's 0.8.6. Recall is a
  property of a pgvector version, so Alpine compiles 0.8.6 from source rather
  than let search results depend on which guest the deployment landed in.
- **Every guest script is `/bin/sh`.** The Alpine template has no bash. A
  bashism is a script that works on the distribution its author tested and
  fails on the other one, so the contract test asserts the shebang and parses
  both under `sh -n`.

**Pick Debian** if you want the shorter provisioning run, journald, and a guest
that behaves like every other Debian machine you administer. **Pick Alpine** for
roughly a third of the disk and a noticeably smaller idle footprint, on a node
whose memory is already spoken for.

### The interpreter is fetched, not taken from the distribution

Alpine 3.23 packages Python 3.12 and Debian 13 packages 3.13. Taking either
would mean the container images and the native install ran different
interpreters, and a bug that appears on only one of them is a bug nobody
reproduces. So `install-system.sh` fetches the version in `.python-version`
through `uv`, which has a standalone build for musl as well as for glibc, and
records the path for the second half of the flow to use.

`uv` itself is pinned and checksummed for all four target triples: a
checksummed extension sitting behind an unverified downloader is not a verified
build. `uv` then verifies the interpreter it downloads in turn.

### The database role is a superuser, and that is not new

The platform runs `LOAD 'age'` on each connection before it will use the graph,
and PostgreSQL grants that statement to superusers only. A bare library name can
never satisfy the `$libdir/plugins` exception, and `shared_preload_libraries`
does not change the rule — both were tried. So the role this flow creates is
made a superuser, and a deployment whose role is not one comes up reporting
`extension age is unavailable` while `pg_extension` plainly lists it.

This is parity rather than a relaxation: in the published container deployment
the account the platform connects as is that cluster's superuser and always has
been. A native install simply makes it visible. Removing the need is an
application change — the graph bootstrap would have to treat an already-loaded
library as loaded instead of requiring the statement to succeed — not something
provisioning can do.

## What ends up in the guest

```
/opt/ninjasre/src          the source tree that was shipped in
/opt/ninjasre/python       the pinned CPython, fetched rather than packaged
/opt/ninjasre/python-path  which interpreter the services run, in one line
/opt/ninjasre/venv         the virtual environment the services run from
/etc/ninjasre/ninjasre.env the configuration, including the generated secrets
/var/lib/ninjasre          the state directory, the only path the services write
/var/log/ninjasre          OpenRC's service logs (Debian uses the journal)
```

Three services, matching the topology the platform declares for itself:

| Service | Port | Bound to |
|---|---|---|
| `ninjasre-app` | 8420 | `--bind-address`, `0.0.0.0` by default |
| `ninjasre-console` | 8421 | `--bind-address`, `0.0.0.0` by default |
| `ninjasre-proxy` | 8422 | loopback, always |

The credential proxy is a separate process rather than a thread of the
application for the same reason it is a separate container in the Compose
profiles: it is the only one holding a credential, so it gets its own account
boundary and its own service to stop. Its port is not an operator choice.

**They are started in that order, and the order matters.** The application and
the console are the same ASGI programme on two ports, and each runs the
platform's boot sequence — which creates the first administrator, among other
things. Started together they race it and the loser exits on a duplicate key.
The Compose profiles say the same thing with `depends_on`; provisioning waits
for the application to report ready before it starts the console.

```sh
# Debian
systemctl status ninjasre-app
journalctl -u ninjasre-app -f

# Alpine
rc-service ninjasre-app status
tail -f /var/log/ninjasre/app.log
```

## Options

`--help` is authoritative. The ones that matter most:

```
--distro debian|alpine     Guest distribution. Default: debian
--profile NAME             dev | homelab | standard | enterprise. Default: homelab
--vmid N                   Default: the cluster's next free ID
--storage NAME             Must accept content 'rootdir'. Default: local-lvm
--ip dhcp|CIDR             Default: dhcp. A static address needs --gateway
--bridge NAME / --vlan TAG Default: vmbr0, untagged
--memory MIB / --cores N   Default: 6144 / 4
--bind-address ADDR        What app and console bind to. Default: 0.0.0.0
--env-file PATH            An environment file to seed with: a provider key, an endpoint
--node NAME                Provision on another node of the cluster, over SSH
--config PATH              Keep the settings in a file instead (see the example)
--check-only / --dry-run   Preflight only / print every command
--no-start                 Install the system but not the platform
--force                    Destroy an existing container with this ID first
```

Settings can live in a file instead — copy
[`ninjasre-lxc.conf.example`](ninjasre-lxc.conf.example) and pass `--config`.
Flags still win over the file.

### The default profile is `homelab`

It is the only profile that declares a resource ceiling — 4 GiB and 2 CPUs. The
container is given 6 GiB by default because compiling the graph extension
against PostgreSQL, not the running platform, is the peak. Lower it afterwards
with `pct set <vmid> --memory 4608` once provisioning has finished.

## Two nodes

`pct create` is local to a node, so provisioning the other half of a cluster
means running the script there. `--node NAME` does that for you: it bundles the
source, copies itself and the bundle over SSH, and re-runs remotely with the
same arguments.

```sh
./ninjasre-lxc.sh --node pve01 --distro alpine --ip dhcp
```

What a two-node cluster does **not** buy you here, and it is better to know
before the first outage:

- **Migration needs shared storage.** A container on `local-lvm` or any other
  node-local storage cannot be live-migrated; the disk has to move, which means
  an offline migration and a copy. If migration matters, put `--storage` on
  something both nodes see.
- **Two nodes cannot form a quorum on their own.** Losing either leaves the
  survivor inquorate and read-only for cluster configuration unless a QDevice
  or a third vote is in place. This affects Proxmox's management plane, not a
  container that is already running.
- **Running it on both nodes gives you two deployments**, with two databases and
  two encryption keys. Two nodes are useful here for *placement* — moving the
  deployment off a node you want to reboot — not for high availability. High
  availability is the Helm chart's job.

## After it finishes

The script prints the container ID, its address, and the console URL. The
generated secrets are in the guest's configuration file:

```sh
pct exec <vmid> -- cat /etc/ninjasre/ninjasre.env
```

**Back up `NINJASRE_DATABASE_ENCRYPTION_KEY` somewhere other than your database
dumps.** It is generated during provisioning because the platform deliberately
never generates one, and it is the only thing that can read what it wrote. A
re-run keeps the configuration file it finds, precisely so a second attempt
cannot mint a new key over stored credentials.

The first administrator's token is *not* in that file. The application mints one
at first start and prints it once — `journalctl -u ninjasre-app` on Debian,
`/var/log/ninjasre/app.log` on Alpine.

## When it fails

| Symptom | Cause |
|---|---|
| `the graph extension did not build` | The last 25 lines of the build log are printed with it. On Alpine this is almost always a missing build dependency; the installer's package list is the place to fix it. |
| `no model provider is configured` | Not a failure. Everything is installed; add the provider to the guest's configuration file and re-run `/opt/ninjasre/bin/bring-up.sh`. |
| `extension age is unavailable` in the health output | The database role is not a superuser. See the section above — the platform's `LOAD` requires it. |
| `PostgreSQL did not accept a connection within 60s` | On Alpine, the cluster was initialised but the service did not come up: `pct exec <vmid> -- rc-service postgresql status`. |
| `the installed platform package cannot be imported` | The virtual environment did not get the package. `PYTHONPATH` is set deliberately — the platform's package directory shares its name with a standard library module, and the standard library wins without it. |
| `container has no network after 60s` | Wrong bridge, a VLAN tag the bridge does not carry, or a static address with no route to its gateway. |
| `the application was not ready within 180s` | The last 40 log lines are printed with the failure. Most often a required setting the seeded environment file did not carry. |
| Build killed partway through | The guest ran out of memory compiling the extension. Raise `--memory`. |

## Verified against

Developed and run against a two-node Proxmox VE 9.2 cluster on kernel 7.0, with
the `debian-13-standard` and `alpine-3.23-default` templates from `pveam`.

Both distributions were provisioned from an empty container to a running
deployment on the current stable stack — **PostgreSQL 18.4, Apache AGE 1.8.0,
pgvector 0.8.6** — with eight migrations applied to an empty schema, all three
services under their init system, and `/health/ready` reporting
`store_state: healthy` with no degradation. The graph extension compiled from
its release artefact on both, against musl as well as glibc.

No node addresses, cluster names or storage layouts from that environment are
recorded here; the script discovers all of them at runtime and the preflight
fails with a specific message when one is missing.
