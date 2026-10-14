'use strict';

class FakeRedis {
  constructor() {
    this.lists = new Map();
    this.values = new Map();
    this.down = false;
  }

  _check() {
    if (this.down) throw Object.assign(new Error('redis down'), { code: 'ECONNREFUSED' });
  }

  async ping() {
    this._check();
    return 'PONG';
  }

  async set(key, value) {
    this._check();
    this.values.set(key, String(value));
    return 'OK';
  }

  async get(key) {
    this._check();
    return this.values.has(key) ? this.values.get(key) : null;
  }

  async incr(key) {
    this._check();
    const n = parseInt(this.values.get(key) || '0', 10) + 1;
    this.values.set(key, String(n));
    return n;
  }

  async del(keys) {
    this._check();
    let n = 0;
    for (const k of [].concat(keys)) if (this.values.delete(k)) n++;
    return n;
  }

  async lPush(key, value) {
    this._check();
    const l = this.lists.get(key) || [];
    l.unshift(value);
    this.lists.set(key, l);
    return l.length;
  }

  async brPop(key) {
    this._check();
    const l = this.lists.get(key) || [];
    if (!l.length) return null;
    return { key, element: l.pop() };
  }

  list(key) {
    return this.lists.get(key) || [];
  }
}

class FakeDb {
  constructor() {
    this.votes = [];
    this.failWith = null;
  }

  async query(sql, params = []) {
    if (this.failWith) throw this.failWith;

    if (sql.trim() === 'SELECT 1') {
      return { rowCount: 1, rows: [{ '?column?': 1 }] };
    }

    if (sql.includes('INSERT INTO votes')) {
      const [pollId, optionId, userId, createdAt] = params;
      if (this.votes.some((v) => v.poll_id === pollId && v.user_id === userId)) {
        return { rowCount: 0, rows: [] };
      }
      const row = { id: this.votes.length + 1, poll_id: pollId, option_id: optionId, user_id: userId, created_at: createdAt };
      this.votes.push(row);
      return { rowCount: 1, rows: [{ id: row.id }] };
    }

    throw new Error('unexpected SQL in test: ' + sql);
  }
}

const silentLog = { debug() {}, info() {}, warn() {}, error() {} };

function testConfig(overrides = {}) {
  return {
    queueKey: 'votes',
    failedKey: 'votes:failed',
    heartbeatKey: 'worker:heartbeat',
    blockSeconds: 0,
    maxAttempts: 3,
    retryDelayMs: 0,
    staleSeconds: 30,
    version: 'test',
    ...overrides,
  };
}

module.exports = { FakeRedis, FakeDb, silentLog, testConfig };