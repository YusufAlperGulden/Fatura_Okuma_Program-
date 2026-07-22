'use strict';

const assert = require('node:assert/strict');
const {
    calculateTaxBreakdown,
    fetchWithTimeout,
    parseLocaleNumber,
} = require('../ui/helpers.js');

// A single decimal separator is always decimal, even with three or more digits.
assert.equal(parseLocaleNumber('0,125'), 0.125);
assert.equal(parseLocaleNumber('1,2340'), 1.234);
assert.equal(parseLocaleNumber('12.345'), 12.345);

// Repeated separators are accepted only as valid thousands grouping.
assert.equal(parseLocaleNumber('1.234.567'), 1234567);
assert.equal(parseLocaleNumber('1,234,567'), 1234567);
assert.equal(parseLocaleNumber('1.234.567,89 TL'), 1234567.89);
assert.equal(parseLocaleNumber('1,234,567.89 USD'), 1234567.89);
assert.equal(parseLocaleNumber('12,34,56'), null);
assert.equal(parseLocaleNumber('abc'), null);

// KDV is rounded per line with ROUND_HALF_UP semantics and discount cents are
// distributed deterministically. The displayed total must equal the canonical
// document KDV rather than a raw floating-point group sum.
const breakdown = calculateTaxBreakdown({
    items: [
        { total_price: '0,03', tax_rate: '20' },
        { total_price: '0,03', tax_rate: '20' },
        { total_price: '99,94', tax_rate: '10' },
    ],
    discountAmount: '0,01',
    canonicalTaxAmount: '10,01',
});

assert.deepEqual(breakdown.groups, [
    { rate: '20', taxCents: '2' },
    { rate: '10', taxCents: '999' },
]);
assert.equal(breakdown.totalTaxCents, '1001');

function waitForAbort(_url, { signal }) {
    return new Promise((resolve, reject) => {
        const rejectWithAbort = () => {
            const error = new Error('aborted');
            error.name = 'AbortError';
            reject(error);
        };
        if (signal.aborted) {
            rejectWithAbort();
            return;
        }
        signal.addEventListener('abort', rejectWithAbort, { once: true });
    });
}

async function runTimeoutAssertions() {
    const reusableBatchController = new AbortController();
    await assert.rejects(
        fetchWithTimeout(
            waitForAbort,
            '/upload',
            { method: 'POST' },
            5,
            reusableBatchController.signal,
        ),
        error => error.name === 'TimeoutError',
    );
    assert.equal(reusableBatchController.signal.aborted, false);

    const nextResponse = await fetchWithTimeout(
        async () => ({ ok: true }),
        '/upload',
        { method: 'POST' },
        50,
        reusableBatchController.signal,
    );
    assert.equal(nextResponse.ok, true);

    const canceledBatchController = new AbortController();
    const canceledRequest = fetchWithTimeout(
        waitForAbort,
        '/upload',
        { method: 'POST' },
        1000,
        canceledBatchController.signal,
    );
    canceledBatchController.abort();
    await assert.rejects(canceledRequest, error => error.name === 'AbortError');
}

runTimeoutAssertions()
    .then(() => console.log('ui_helpers.test.js: all assertions passed'))
    .catch(error => {
        console.error(error);
        process.exitCode = 1;
    });
