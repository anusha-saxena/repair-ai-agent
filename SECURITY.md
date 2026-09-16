# Demo security model

## Deliberate scope

Requests select one of three curated demo IDs. There is no upload, repository
URL, code-string, or executable-path input. IDs are looked up in a catalog built
from the read-only `demos/` directory at startup. Unknown IDs return 404 and any
POST body is rejected. Demo manifests are build-time code, not user input.
This removes the public API surface for submitting arbitrary code to execute.
AI-generated repairs still execute Python and need additional containment.

## Containment

The API runs as `appuser`. Its only sudo permission is a root-owned launcher
that accepts a validated UUID, checks its fixed job directory and metadata, and
runs a fixed CLI command. Its only other modes initialize the fixed firewall
and clean a UUID-named directory under the same fixed work root. It cannot accept shell commands or arbitrary paths.
The launcher uses Bubblewrap to mount application code and runtime libraries
read-only, expose only the selected job directory as writable, isolate process
IDs, drop capabilities, and run the CLI and pytest as `sandboxuser`.
Neither the SQLite directory nor other jobs are mounted into that sandbox.
The sandbox root is remounted read-only and further user namespaces are disabled.
The sandbox also sets no-new-privileges, so its visible sudo binary cannot
recover root privileges. Its temporary files live in its own job directory.

`subprocess.run` has a 90-second wall timeout. `preexec_fn` applies CPU,
address-space, process-count, core-dump, and per-file-size limits. On timeout,
the launcher kills its process group; the isolated PID namespace and
Bubblewrap parent-death handling terminate descendants. These defaults are
placeholders: 60 CPU seconds per process, 512 MiB address space per process,
and 32 processes for the sandbox OS user. Container memory and PID limits add
aggregate ceilings. A per-process CPU limit is not an aggregate CPU budget.

The supplied Compose deployment connects the API to an internal proxy network
and an ingress bridge for host port publishing. Before Uvicorn starts, a
container-wide firewall permits responses to inbound connections, root-only
DNS for resolving the internal proxy, and new connections to that proxy only.
The server fails closed if the firewall cannot be installed. Its sole outbound
route is a separate Squid proxy, which permits only CONNECT
to `api.anthropic.com:443`. Per-user IPv4 firewall rules allow `sandboxuser`
to connect only to that proxy; IPv6 is denied. Proxy addresses are resolved by
the launcher, so the sandbox needs no DNS access. Direct internet access and
connections back to the API are denied. TLS verification remains enabled.
The proxy publishes no port. Do not deploy only the API image on an unrestricted
network and claim these guarantees: the Compose network/proxy are required.

The API permits five submissions per IP per hour, persisted atomically in
SQLite, and serializes executions. Uvicorn does not trust forwarded headers.
CORS allows one explicit `FRONTEND_ORIGIN`; it is not an authentication system.
At a reverse proxy, configure trusted client IP forwarding deliberately, or
all visitors may share the proxy IP's allowance.

Responses contain public demo metadata, pass rates, classification, source
changes, and attempt counts. Subprocess logs, traces, test IDs containing
internal paths, and exceptions are never returned. Unexpected errors receive
a generic message; details stay in server logs. Generated results containing
known credentials or internal execution paths are rejected before storage.
No `.env` or VCS files are copied into the image. Keep API keys server-side.

## Retention and operational limits

Jobs expire based on UTC epoch `created_at`, never last access or file mtime.
The asyncio startup sweep runs before requests are accepted, then every hour.
Expired working directories, backups, reports, and SQLite rows are removed.
Expired results return 404 even between sweeps. Old orphan directories are
also removed; failed directory deletions are logged and retried without
forgetting their rows. A fixed UUID-only cleanup helper handles sandbox-owned
permissions that prevent the API user from deleting a directory. SQLite secure-delete overwrites deleted record content;
provider backups and container logs need their own retention policy.
Hourly sweeps mean physical deletion normally occurs between 24 and 25 hours
of age. This is application retention, not a promise of forensic erasure.
Rate-limit records last one hour. Interrupted background jobs become errors
on startup; this is a single API worker demo, not a durable distributed queue.

Bubblewrap needs Linux namespace/mount support. Compose adds SYS_ADMIN and
NET_ADMIN to the container's capability bounding set and relaxes its seccomp and system-path
profiles so the fixed privileged launcher can create namespaces and firewall
rules. The API and sandbox remain non-root, but this increases the impact of
a compromised launcher. Use a dedicated demo host; do not call this a boundary
for hostile arbitrary user code. Managed platforms that prohibit those
capabilities need a separate sandbox service, not a silent unsandboxed fallback.

## What Option B would require

This demo does not make arbitrary uploads safe, prevent kernel/container
escapes, prove an AI repair preserves intent, or stop distributed credit abuse.
A generated test can see the Anthropic key needed by the repair process;
stronger designs keep credentials in a separate broker and give test execution
no network. IP limits do not replace authenticated quotas or a spending cap.
For arbitrary repositories, add disposable VM or microVM workers, stricter
syscall/cgroup and disk quotas, no privileged launcher shared with the API,
separate credential handling, input/dependency policies, authenticated budgets,
and audited egress and artifact handling. Keep the demo-only API scope intact
until those controls exist.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Bubblewrap's security model](https://github.com/containers/bubblewrap#sandbox-security),
and [Docker internal networks](https://docs.docker.com/reference/compose-file/networks/#internal).
