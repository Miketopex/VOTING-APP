# CloudVote

A voting application, built as four services behind a reverse proxy so that casting a
vote and counting it are separate jobs. A vote is accepted in milliseconds and put on a
queue; a worker drains the queue into PostgreSQL. The site stays responsive under a
burst, and no vote is lost if the database is briefly slow.

```
            ┌────────┐      ┌──────────────┐      ┌───────────┐
  browser → │ nginx  │ ───→ │ vote service │ ───→ │   redis   │  queue + results cache
            └────────┘      │   (Flask)    │ ←─── └───────────┘
                            └──────┬───────┘            ↑ ↓
                                   │                ┌───┴────────┐
                                   └──────────────→ │   worker   │  drains the queue
                                        reads       │  (Node.js) │
                                   ┌───────────┐ ←──┴────────────┘
                                   │ postgres  │   writes the vote
                                   └───────────┘
```

Full detail, including the failure behaviour of each component, is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

Directories are named after what they run, because the tooling reads these paths —
compose builds from `vote/` and `worker/`, CI runs in them, Terraform needs its `.tf`
files in one directory. Who owns what is in [`.github/CODEOWNERS`](.github/CODEOWNERS),
which GitHub acts on by requesting the right reviewer on every pull request.

| Path | What it is | Squad |
|---|---|---|
| `vote/` | Flask application, templates and its test suite | B |
| `worker/` | Node.js queue worker, health server, DB backup scripts | C |
| `nginx/` | Reverse proxy configuration and TLS certificates | D |
| `scripts/` | Deploy, rollback, EC2 bootstrap, env fetch | D |
| `infra/terraform/` | AWS infrastructure | A |
| `qa/` | End-to-end test and the monitoring probe | E |
| `docs/` | Architecture and operational documentation | E |
| `.github/workflows/` | CI and CD | D |

## Running it locally

You need Docker with the Compose plugin. Nothing else — no Python or Node on your
machine.

```bash
git clone https://github.com/Miketopex/VOTING-APP.git
cd VOTING-APP

cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"   # paste into .env
# also set POSTGRES_PASSWORD and ADMIN_PASSWORD in .env

docker compose up --build
```

Then open **http://localhost**. If something already uses port 80, set `HTTP_PORT=8080`
in `.env` and open http://localhost:8080 instead.

A demo poll is seeded on first start, and the admin account named in `.env` is created
if it does not exist. Register a user, vote, and watch the result appear once the worker
picks it up.

To stop, and to throw away the database and queue with it:

```bash
docker compose down -v
```

## Running the tests

The vote service and the worker each have their own suite; the end-to-end test drives a
real vote through the whole stack. CI runs all three.

```bash
# vote service — 42 tests, no database needed (sqlite + an in-memory Redis stand-in)
docker run --rm -v "$PWD/vote":/w -w /w -e SECRET_KEY=test python:3.12-slim \
  bash -c "pip install -q -r requirements-dev.txt && flake8 . && pytest -q"

# worker — 9 tests
docker run --rm -v "$PWD/worker":/w -w /w node:20-slim \
  bash -c "npm ci --silent && node --test"

# end to end — builds the stack, registers, votes, waits for the worker, reads it back
HTTP_PORT=8080 bash qa/e2e.sh
```

## Checking a running deployment

```bash
bash qa/health-check.sh                     # localhost
bash qa/health-check.sh http://<ec2-host>   # a deployment
```

It exits `0` healthy, `1` degraded, `2` down, so it can be used directly from cron or an
alert rule.

| Endpoint | Answers |
|---|---|
| `/nginx-health` | Is the proxy up? Does not touch the app. |
| `/health/live` | Is the app process alive? No dependencies, so a restart policy never kills the app because the database is down. |
| `/health/ready` | Should traffic come here? `503` when PostgreSQL is gone. |
| `/health` | The full picture — database, Redis, worker heartbeat. |

## How a deploy happens

1. A pull request runs CI: lint, both unit suites, then the end-to-end test.
2. On merge to `main`, CD builds the `vote` and `worker` images, tags them with the
   commit SHA and pushes them to Docker Hub.
3. It copies `docker-compose.yml`, `docker-compose.prod.yml`, the scripts and the nginx
   config to EC2, then runs `scripts/deploy.sh`.
4. `deploy.sh` pulls the new images, starts them, and polls `/health` for two minutes.
   If it never goes healthy it restores the previous tag from `.deployed_tag` and exits
   non-zero.

`docker-compose.yml` on its own **builds** from source, which is what you want on a
laptop. `docker-compose.prod.yml` replaces those builds with the pushed images, which is
what makes the rollback in step 4 possible — there has to be an image tag for it to
change.

Required repository secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `EC2_HOST`,
`EC2_USER`, `EC2_SSH_KEY`.

## Configuration

Everything is environment variables; `.env.example` documents each one. Two have no
default on purpose:

- `SECRET_KEY` — Flask signs session cookies with it. A shared default would let anyone
  forge an admin session, so Compose refuses to start without it.
- `POSTGRES_PASSWORD` — used by the database, the vote service and the worker.

In production these come from AWS SSM Parameter Store under `/cloudvote/prod/`;
`scripts/fetch-env.sh` writes them to `.env` on the instance at deploy time.
