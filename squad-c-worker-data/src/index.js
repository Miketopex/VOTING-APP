'use strict';
// CloudVote worker – entry point.
// Wires real Redis and PostgreSQL clients to the processing loop and starts
// the health server. Handles SIGTERM so `docker stop` never loses a vote
// that is being processed.

const { createClient } = require('redis');
const { Pool } = require('pg');

const { loadConfing } = require('./config');
const { createLogger } = require('./logger');
const { createProcessor } = require('./processor');
const { runLoop, sleep } = require('./loop');
const { createHealthServer } = require('./health');

async function waitForSchema(db, log) {
  // The vote service creates the tables on start-up; wait for them.
  for (let attempt = 1; ; attempt++) {
    try {
      await db.query('SELECT 1 FROM votes LIMIT 1');
      return;
    } catch (err) {
      log.warn('waiting_for_database', { attempt, error: String(err.message) });
      await sleep(Math.min(1000 * attempt, 5000));
    }
  }
}

async function main() {
  const config = loadConfig();
  const log = createLogger(config.logLevel);
  const state = { stopping: false, lastIteration: null, counts: {} };

  const redis = createClient({ url: config.redisUrl });
  redis.on('error', (err) => log.error('redis_error', { error: String(err.message) }));
  await redis.connect();
  // BRPOP blocks its connection, so it gets a dedicated one.
  const blocking = redis.duplicate();
  blocking.on('error', (err) => log.error('redis_error', { error: String(err.message) }));
  await blocking.connect();

  const db = new Pool({ connectionString: config.databaseUrl, max: 5, connectionTimeoutMillis: 5000 });
  db.on('error', (err) => log.error('postgres_pool_error', { error: String(err.message) }));

  const server = createHealthServer({ db, redis, state, config });
  server.listen(config.healthPort, () => log.info('health_server_listening', { port: config.healthPort }));

  await waitForSchema(db, log);

  const shutdown = (signal) => {
    if (state.stopping) return;
    log.info('shutdown_requested', { signal });
    state.stopping = true;
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  const processor = createProcessor({ db, redis, config, log });
  log.info('worker_started', { version: config.version, queue: config.queueKey });
  await runLoop({ blocking, redis, processor, config, state, log });

  server.close();
  await Promise.allSettled([blocking.quit(), redis.quit(), db.end()]);
  log.info('worker_stopped');
  process.exit(0);
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ level: 'ERROR', service: 'worker', message: 'fatal', error: String(err && err.stack) }) + '\n');
  process.exit(1);
});