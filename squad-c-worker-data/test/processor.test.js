'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const { createProcessor, parseMessage, utcTimestamp } = require('../src/processor');
const { FakeRedis, FakeDb, silentLog, testConfig } = require('../test-support/fakes');

function setup(configOverrides) {
  const redis = new FakeRedis();
  const db = new FakeDb();
  const config = testConfig(configOverrides);
  const processor = createProcessor({ db, redis, config, log: silentLog });
  return { redis, db, config, processor };
}

const vote = (extra = {}) => JSON.stringify({ poll_id: 1, option_id: 2, user_id: 3, request_id: 'r1', ...extra });

test('stores a valid vote, counts it and invalidates the cache', async () => {
  const { redis, db, processor } = setup();
  await redis.set('results:1', '{"cached":true}');
  await redis.set('pending:1:3', '1');

  assert.equal(await processor.handle(vote()), 'stored');
  assert.equal(db.votes.length, 1);
  assert.deepEqual([db.votes[0].poll_id, db.votes[0].option_id, db.votes[0].user_id], [1, 2, 3]);
  assert.equal(await redis.get('stats:votes_processed'), '1');
  assert.equal(await redis.get('results:1'), null, 'results cache must be cleared');
  assert.equal(await redis.get('pending:1:3'), null, 'pending flag must be cleared');
});

test('a second vote by the same user is ignored (one vote per user)', async () => {
  const { db, redis, processor } = setup();
  await processor.handle(vote());
  assert.equal(await processor.handle(vote({ option_id: 4 })), 'duplicate');
  assert.equal(db.votes.length, 1);
  assert.equal(db.votes[0].option_id, 2, 'first vote wins');
  assert.equal(await redis.get('stats:votes_duplicate'), '1');
});

test('invalid JSON goes to the dead-letter queue', async () => {
  const { redis, processor } = setup();
  assert.equal(await processor.handle('not json'), 'failed');
  const failed = JSON.parse(redis.list('votes:failed')[0]);
  assert.equal(failed.reason, 'invalid_json');
  assert.equal(await redis.get('stats:votes_failed'), '1');
});

test('missing or invalid ids go to the dead-letter queue', async () => {
  const { redis, processor, db } = setup();
  assert.equal(await processor.handle(JSON.stringify({ poll_id: 1, option_id: 'x', user_id: 3 })), 'failed');
  assert.equal(await processor.handle(JSON.stringify({ poll_id: -1, option_id: 2, user_id: 3 })), 'failed');
  assert.equal(redis.list('votes:failed').length, 2);
  assert.equal(db.votes.length, 0);
});

test('a transient database error re-queues the vote with attempts+1', async () => {
  const { redis, db, processor } = setup();
  db.failWith = Object.assign(new Error('connection terminated'), { code: '57P01' });
  assert.equal(await processor.handle(vote()), 'retry');
  const requeued = JSON.parse(redis.list('votes')[0]);
  assert.equal(requeued.attempts, 1);

  db.failWith = null;
  assert.equal(await processor.handle(redis.list('votes').pop()), 'stored');
});

test('gives up after maxAttempts and dead-letters the vote', async () => {
  const { redis, db, processor } = setup({ maxAttempts: 2 });
  db.failWith = new Error('db unavailable');
  assert.equal(await processor.handle(vote()), 'retry');
  assert.equal(await processor.handle(redis.list('votes').pop()), 'failed');
  const failed = JSON.parse(redis.list('votes:failed')[0]);
  assert.equal(failed.reason, 'max_attempts');
});

test('a permanent database error (foreign key) is not retried', async () => {
  const { redis, db, processor } = setup();
  db.failWith = Object.assign(new Error('violates foreign key'), { code: '23503' });
  assert.equal(await processor.handle(vote()), 'failed');
  assert.equal(redis.list('votes').length, 0);
  assert.equal(JSON.parse(redis.list('votes:failed')[0]).reason, 'db_23503');
});

test('parseMessage defaults attempts to 0', () => {
  assert.equal(parseMessage(vote()).msg.attempts, 0);
});

test('utcTimestamp uses the "YYYY-MM-DD HH:MM:SS" format', () => {
  assert.equal(utcTimestamp(new Date('2026-09-29T19:05:07.123Z')), '2026-09-29 19:05:07');
});