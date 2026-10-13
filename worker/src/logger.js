'use strict';

const LEVELS = { debug: 10, info: 20, warn: 30, error: 40};

function createLogger(level = 'info', write = (line) => process.stdout.write(line + '\n')){
    const min = LEVELS[level] || LEVELS.info;

    const emit = (lvl, message, fields = {}) => {
        if (LEVELS[lvl] < min) return;
            write(JSON.stringify({
            time: new Date().toISOString().slice(0, 19) + 'Z',
            level: lvl.toUpperCase(),
            service: 'worker',
            message,
            ...fields,
        }))
    }

    return {
        debug: (m, f) => emit('debug', m, f),
        info: (m, f) => emit('info', m, f),
        warn: (m, f) => emit('warn', m, f),
        error: (m, f) => emit('error', m, f),
    };
};

module.exports = { createLogger};