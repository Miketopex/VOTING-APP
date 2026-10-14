'use strict';

const { keys } = require('./config');

const INSERT_VOTE = `
  INSERT INTO votes (poll_id, option_id, user_id, created_at)
  VALUES ($1, $2, $3, $4)
  ON CONFLICT (poll_id, user_id) DO NOTHING
  RETURNING id`;

const PERMANENT_PG_ERRORS = new Set([
  '23503', // foreign_key_violation
  '22P02', // invalid_text_representation
  '23502', // not_null_violation
]);

function utcTimestamp(date = new Date()) {
  return date.toISOString().slice(0, 19).replace('T', ' ');
}

function parseMessage(raw) {
  let msg;
  try {
    msg = JSON.parse(raw);
  } catch {
    return { error: 'invalid_json' };
  }

  for (const field of ['poll_id', 'option_id', 'user_id']) {
    if (!Number.isInteger(msg[field]) || msg[field] <= 0) {
      return { error: `invalid_${field}` };
    }
  }
  msg.attempts = Number.isInteger(msg.attempts) ? msg.attempts : 0;
  return { msg };
}

function createProcessor({ db, redis, config, log }) {
  async function deadLetter(raw, reason, extra = {}) {
    await redis.lPush(config.failedKey, JSON.stringify({
      raw,
      reason,
      failed_at: utcTimestamp(),
      ...extra,
    }));
    await redis.incr(keys.stat('votes_failed'));
    log.error('vote_failed', { reason, ...extra });
    return 'failed';
  }

  async function handle(raw) {
    const { msg, error } = parseMessage(raw);
    if (error) return deadLetter(raw, error);

    const ctx = { poll_id: msg.poll_id, user_id: msg.user_id };
    const started = Date.now();

    try {
      const res = await db.query(INSERT_VOTE, [msg.poll_id, msg.option_id, msg.user_id, utcTimestamp()]);
      let outcome;

      if (res.rowCount === 0) {
        outcome = 'duplicate';
        await redis.incr(keys.stat('votes_duplicate'));
        log.warn('vote_duplicate_ignored', ctx);
      } else {
        outcome = 'stored';
        await redis.incr(keys.stat('votes_processed'));
        log.info('vote_stored', { ...ctx, vote_id: res.rows[0].id, duration_ms: Date.now() - started });
      }

      await redis.del([keys.results(msg.poll_id), keys.pending(msg.poll_id, msg.user_id)]);
      return outcome;

    } catch (err) {
      if (err && PERMANENT_PG_ERRORS.has(err.code)) {
        return deadLetter(raw, `db_${err.code}`, ctx);
      }

      msg.attempts = (msg.attempts || 0) + 1;
      if (msg.attempts >= config.maxAttempts) {
        return deadLetter(JSON.stringify(msg), 'max_attempts', { ...ctx, error: String(err && err.message) });
      }

      await redis.lPush(config.queueKey, JSON.stringify(msg));
      log.warn('vote_retry_scheduled', { ...ctx, attempts: msg.attempts, error: String(err && err.message) });
      return 'retry';
    }
  }

  return { handle };
}

module.exports = { createProcessor, parseMessage, utcTimestamp, INSERT_VOTE };