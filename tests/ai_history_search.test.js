'use strict';

const assert = require('node:assert/strict');
const {
    buildFilterChipEntries,
    formatAmount,
    formatDate,
} = require('../ui/ai-history-search.js');

const chips = buildFilterChipEntries({
    customer: 'Örnek A.Ş.',
    invoice_date_from: '2026-07-01',
    min_amount_try: 50000,
    has_uyumsoft_document: false,
    sort_by: 'amount_try',
    sort_direction: 'desc',
    result_limit: 5,
});

assert.deepEqual(chips, [
    { label: 'Cari', value: 'Örnek A.Ş.' },
    { label: 'Fatura başlangıç', value: '2026-07-01' },
    { label: 'En az', value: '50.000 TL' },
    { label: 'Uyumsoft', value: 'Gönderilmemiş' },
    { label: 'Sıralama', value: 'Tutar · azalan' },
    { label: 'Sonuç sınırı', value: '5' },
]);

assert.deepEqual(buildFilterChipEntries(null), []);
assert.equal(formatAmount(56224.32), '56.224,32 TL');
assert.equal(formatAmount('not-a-number'), '-');
assert.equal(formatDate('2026-07-22T15:30:00'), '2026-07-22');
assert.equal(formatDate(null), '-');

console.log('ai_history_search.test.js: all assertions passed');
