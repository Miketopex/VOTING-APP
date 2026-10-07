'use strict';
// Tiny HTTP server (no framework) exposing the worker's health on :8080.
//   GET /health       -> 200 {"status":"ok",…} or 503 {"status":"degraded",…}
//   GET /health/live  -> 200 while the process runs (Docker HEALTHCHECK)

const http = require('node:http');

async function timed(fn) {
  const start = process.hrtime.bigint();
  try {
    await fn();
    return { status: 'ok', latency_ms: Number(process.hrtime.bigint() - start) / 1e6 };
  } catch (err) {
    return { status: 'error', error: err && (err.code || err.name || 'Error') };
  }
}

async function collectHealth({ db, redis, state, config }) {
  const [database, redisCheck] = await Promise.all([
    timed(() => db.query('SELECT 1')),
    timed(() => redis.ping()),
  ]);
  const loopAge = state.lastIteration ? (Date.now() - state.lastIteration) / 1000 : null;
  const loop = {
    status: loopAge !== null && loopAge <= config.staleSeconds ? 'ok' : 'error',
    last_iteration_age_s: loopAge === null ? null : Math.round(loopAge * 10) / 10,
  };
  const healthy = [database, redisCheck, loop].every((c) => c.status === 'ok');
  return {
    code: healthy ? 200 : 503,
    body: {
      status: healthy ? 'ok' : 'degraded',
      service: 'worker',
      version: config.version,
      uptime_seconds: Math.round(process.uptime()),
      processed: state.counts,
      checks: { database, redis: redisCheck, loop },
    },
  };
}

function createHealthServer(deps) {
  return http.createServer(async (req, res) => {
    const send = (code, body) => {
      res.writeHead(code, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method !== 'GET') return send(405, { error: 'method_not_allowed' });
    if (req.url === '/health/live') return send(200, { status: 'ok', service: 'worker' });
    if (req.url === '/health') {
      const { code, body } = await collectHealth(deps);
      return send(code, body);
    }
    return send(404, { error: 'not_found' });
  });
}

module.exports = { createHealthServer, collectHealth };