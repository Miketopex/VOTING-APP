# Voting Application Architecture

## 1. Overview

The Voting Application Ecosystem is a containerized web application deployed with Docker Compose. Its services communicate through the private Docker network `app-network`.

## 2. High-Level Architecture

```text
Internet / Client
       |
       v
     Nginx
    Port 80
       |
       v
 Vote Service
 Flask/Gunicorn
    Port 5000
    /       \
   v         v
PostgreSQL  Redis
  5432      6379
   ^
   |
Node.js Worker
 Background Jobs
    Port 8080
```

## 3. Core Services

### Nginx
Nginx is the public reverse proxy. It accepts HTTP traffic on port 80 and forwards application requests to `vote-service:5000`.

It also provides `/nginx-health`, structured JSON access logs, forwarded client headers, connection/read timeouts, and `server_tokens off`.

### Vote Service
The Flask/Gunicorn service is the main voting application and API. It handles authentication, polls, voting operations, database access, Redis access, and application health checks.

Source: `squad-b-vote-service/`

### Worker
The Node.js worker handles background processing and communicates with Redis and PostgreSQL.

Source: `squad-c-worker-data/`

### PostgreSQL
PostgreSQL provides persistent relational storage and uses the `postgres-data` Docker volume.

### Redis
Redis provides fast in-memory storage and queue-related functionality and uses the `redis-data` Docker volume.

## 4. Request Flow

A normal web request follows:

```text
Client -> Nginx -> Vote Service -> PostgreSQL / Redis
```

Background processing follows:

```text
Vote Service -> Redis -> Node.js Worker -> PostgreSQL
```

## 5. Networking

All application containers communicate through `app-network` and use Docker service names for internal communication.

Examples:
- Nginx -> `vote-service:5000`
- Vote Service -> PostgreSQL
- Vote Service -> Redis
- Worker -> PostgreSQL
- Worker -> Redis

PostgreSQL and Redis are intended for internal service communication rather than direct public access.

## 6. Health Monitoring

Nginx:
- `GET /nginx-health` checks Nginx independently of the application.

Vote Service:
- `/health/live` checks process liveness.
- `/health/ready` checks readiness and database connectivity.
- `/health` provides broader application health information.

Worker:
- Reports database and Redis connectivity, worker-loop freshness, uptime, and processing statistics.

## 7. Squad Responsibilities

- **Squad A — Infrastructure:** AWS infrastructure in `squad-a-infra/`.
- **Squad B — Vote Service:** Flask application and tests in `squad-b-vote-service/`.
- **Squad C — Worker & Data:** Node.js worker in `squad-c-worker-data/`.
- **Squad D — DevOps:** Deployment and Nginx configuration in `squad-d-devops/`.
- **Squad E — QA, Monitoring & Documentation:** QA, monitoring, architecture, security/compliance, and final documentation in `squad-e-qa-monitoring/`.

## 8. Documentation Maintenance

Review this document whenever a structural change is made, including changes to Docker Compose services, dependencies, ports, networks, volumes, AWS resources, reverse-proxy routing, health checks, or deployment architecture.

The contributor making a structural change should notify the documentation owner so the architecture map remains accurate.

## 9. Sources of Truth

Use these repository files when reviewing the architecture:
- `docker-compose.yml`
- `squad-d-devops/nginx/nginx.conf`
- `squad-a-infra/`
- `squad-b-vote-service/`
- `squad-c-worker-data/`
- `.github/workflows/`

Documentation should describe the implementation that currently exists in the repository, not planned features.
