'use strict';

function databaseUrl(env) {
    if (env.DATABASE_URL) return env.DATABASE_URL;
    const user = env.POSTGRES_USER || 'voting';
    const password = encodeURIComponent(env.POSTGRES_PASSWORD || '');
    const host = env.POSTGRES_HOST || 'db';
    const port = env.POSTGRES_PORT || '5432';
    const db = env.POSTGRES_DB || 'voting';
    return `postgresql://${user}:${password}@${host}:${port}/${db}`;
}

function redisUrl(env) {
    if (env.REDIS_URL) return env.REDIS_URL;
    const host = env.REDIS_HOST || 'redis';
    const port = env.REDIS_PORT || '6379';
    const auth = env.REDIS_PASSWORD ? `:${encodeURIComponent(env.REDIS_PASSWORD)}@` : '';
    return `redis://${auth}${host}:${port}/0`;   
}

function loadConfig(env = process.env) {
    const queueKey = env.VOTE_QUEUE || 'votes';
    return {
        databaseUrl: databaseUrl(env),
        redisUrl: redisUrl(env),
        queueKey,
        failedKey: `${queueKey}:failed`,
        heartbeatKey: 'worker:heartbeat',
        healthPort: parseInt(env.HEALTH_PORT || '8080', 10),
        blockSeconds: parseInt(env.BLOCK_SECONDS || '5', 10),
        maxAttempts: parseInt(env.MAX_ATTEMPTS || '3', 10),
        retryDelayMs: parseInt(env.RETRY_DELAY_MS || '1000', 10),
        staleSeconds: parseInt(env.WORKER_STALE_SECONDS || '30', 10),
        version: env.APP_VERSION || 'dev',
        logLevel: (env.LOG_LEVEL || 'info').toLowerCase(),
    };
}

const keys = {
  results: (pollId) => `results:${pollId}`,
  pending: (pollId, userId) => `pending:${pollId}:${userId}`,
  stat: (name) => `stats:${name}`,
};

module.exports = { loadConfig, keys };

