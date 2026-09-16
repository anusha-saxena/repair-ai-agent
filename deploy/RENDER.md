# Render deployment assessment

The existing Dockerfile is not a complete Render deployment. It relies on runtime
settings in `compose.yaml`, including `SYS_ADMIN`, `NET_ADMIN`, namespace policy
changes, and a separate Anthropic-only proxy. The API intentionally refuses to
start if its firewall cannot be installed. Do not bypass that startup check or
run AI-generated patches directly in the API container to get a deployment working.

Render supports building Dockerfiles, but its published Docker and Blueprint
documentation does not confirm support for these runtime permissions. Confirm
them with Render before deploying the current sandbox there:

- https://render.com/docs/docker
- https://render.com/docs/blueprint-spec

## Free tier limitations

Render Free is available on demand, rather than continuously running. It sleeps
after 15 minutes without incoming traffic and takes about a minute to wake up.
Local files, including SQLite jobs and submission limits, disappear on sleep,
restart, or redeployment. Free web services cannot attach persistent disks.
The free instance has 512 MB RAM and 0.1 CPU; this is below the current Compose
container's 768 MB memory limit. The repeated pytest runs need benchmarking on
any target host before promising that the existing 90-second job timeout fits.
Anthropic usage is billed separately from hosting.

Sources: https://render.com/docs/free and https://render.com/docs/compute-plans

## Preparation already supported

`api.serve` accepts `PORT` (default `8000`) and binds to `0.0.0.0` with one worker.
This only addresses HTTP port configuration; it does not make the sandbox
compatible with Render.

Once a compatible backend exists, set `ANTHROPIC_API_KEY` only on that backend
and `FRONTEND_ORIGIN` to the exact Vercel frontend origin. Set Vercel's
`VITE_API_URL` to the public HTTPS backend origin and rebuild the frontend.
Never put the Anthropic key in a frontend variable.

## Architecture needed if runtime permissions are unavailable

Render can host an API that delegates repairs to a separate sandbox worker.
That is a future implementation, not the current `api.runner`: it presently
calls a local privileged helper. A remote worker needs authenticated requests,
fixed demo IDs, job progress/results, bounded execution, and cleanup. Persistent
job and rate-limit storage also needs a design that survives Render restarts.
The worker must run on a host or sandbox service that supports the isolation
requirements, with its own hosting costs and credentials.

No `render.yaml` is supplied yet because a single free Docker web service would
not reproduce the current execution boundaries. The existing Linux Compose
deployment remains the supported way to run the complete backend.
