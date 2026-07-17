'use strict';

const assert = require('node:assert/strict');
const {
    calculateTaxBreakdown,
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

console.log('ui_helpers.test.js: all assertions passed');
