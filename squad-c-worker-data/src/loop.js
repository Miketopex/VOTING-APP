'use strict';
// The main consume loop: block on the Redis queue, process one vote at a time,
// and refresh a heartbeat so the admin dashboard and /health can tell the
// worker is alive even when there are no votes.

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function runLoop({ blocking, redis, processor, config, state, log }) {
  log.info('worker_loop_started', { queue: config.queueKey });
  while (!state.stopping) {
    state.lastIteration = Date.now();
    try {
      await redis.set(config.heartbeatKey, String(Date.now()), { EX: 60 });
    } catch (err) {
      log.warn('heartbeat_failed', { error: String(err.message) });
    }

    let item;
    try {
      // BRPOP + the vote service's LPUSH = first in, first out
      item = await blocking.brPop(config.queueKey, config.blockSeconds);
    } catch (err) {
      if (state.stopping) break;
      log.error('queue_read_failed', { error: String(err.message) });
      await sleep(2000);
      continue;
    }
    if (!item) continue;

    let outcome;
    try {
      outcome = await processor.handle(item.element);
    } catch (err) {
      // e.g. Redis went away while handling – the vote is logged so it can be replayed
      outcome = 'error';
      log.error('vote_handling_crashed', { error: String(err.message), raw: item.element });
    }
    state.counts[outcome] = (state.counts[outcome] || 0) + 1;
    if (outcome === 'retry') await sleep(config.retryDelayMs);
  }
  log.info('worker_loop_stopped', { counts: state.counts });
}

module.exports = { runLoop, sleep };