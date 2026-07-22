(function (root, factory) {
    const helpers = factory();
    if (typeof module === 'object' && module.exports) {
        module.exports = helpers;
    }
    root.InvoiceUiHelpers = helpers;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    function stripNumericDecorations(value) {
        if (value === null || value === undefined || typeof value === 'boolean') return '';

        return String(value)
            .trim()
            .replace(/[₺$€£%]/g, '')
            .replace(/\b(TL|TRY|USD|DOLAR|EUR|EURO|GBP)\b/gi, '')
            .replace(/[\s\u00a0]/g, '');
    }

    function normalizeLocaleDecimal(value) {
        let text = stripNumericDecorations(value);
        if (!text) return null;

        let sign = '';
        if (text[0] === '+' || text[0] === '-') {
            sign = text[0] === '-' ? '-' : '';
            text = text.slice(1);
        }
        if (!text || !/^\d[\d.,]*$/.test(text)) return null;

        const dotCount = (text.match(/\./g) || []).length;
        const commaCount = (text.match(/,/g) || []).length;
        let integerPart;
        let fractionalPart = '';

        if (dotCount > 0 && commaCount > 0) {
            const decimalIndex = Math.max(text.lastIndexOf('.'), text.lastIndexOf(','));
            integerPart = text.slice(0, decimalIndex).replace(/[.,]/g, '');
            fractionalPart = text.slice(decimalIndex + 1);
            if (!integerPart || !fractionalPart || !/^\d+$/.test(fractionalPart)) return null;
        } else if (dotCount === 1 || commaCount === 1) {
            const separator = dotCount === 1 ? '.' : ',';
            [integerPart, fractionalPart] = text.split(separator);
            if (!integerPart || !fractionalPart) return null;
        } else if (dotCount > 1 || commaCount > 1) {
            const separator = dotCount > 1 ? '.' : ',';
            const escapedSeparator = separator === '.' ? '\\.' : ',';
            const groupingPattern = new RegExp(`^\\d{1,3}(?:${escapedSeparator}\\d{3})+$`);
            if (!groupingPattern.test(text)) return null;
            integerPart = text.split(separator).join('');
        } else {
            integerPart = text;
        }

        if (!/^\d+$/.test(integerPart) || (fractionalPart && !/^\d+$/.test(fractionalPart))) {
            return null;
        }

        const normalizedInteger = integerPart.replace(/^0+(?=\d)/, '') || '0';
        return `${sign}${normalizedInteger}${fractionalPart ? `.${fractionalPart}` : ''}`;
    }

    function parseLocaleNumber(value) {
        const normalized = normalizeLocaleDecimal(value);
        if (normalized === null) return null;
        const parsed = Number(normalized);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function decimalParts(value) {
        const normalized = normalizeLocaleDecimal(value);
        if (normalized === null) return null;
        const negative = normalized.startsWith('-');
        const unsigned = negative ? normalized.slice(1) : normalized;
        const [whole, fraction = ''] = unsigned.split('.');
        return {
            numerator: BigInt(`${whole}${fraction}` || '0') * (negative ? -1n : 1n),
            denominator: 10n ** BigInt(fraction.length),
            normalized,
        };
    }

    function divideRoundHalfUp(numerator, denominator) {
        if (denominator <= 0n) throw new Error('The denominator must be positive.');
        const negative = numerator < 0n;
        const absolute = negative ? -numerator : numerator;
        let quotient = absolute / denominator;
        const remainder = absolute % denominator;
        if (remainder * 2n >= denominator) quotient += 1n;
        return negative ? -quotient : quotient;
    }

    function decimalToScaledInteger(value, decimalPlaces) {
        const parsed = decimalParts(value);
        if (!parsed) return null;
        const multiplier = 10n ** BigInt(decimalPlaces);
        return divideRoundHalfUp(parsed.numerator * multiplier, parsed.denominator);
    }

    function formatRate(value) {
        const normalized = normalizeLocaleDecimal(value);
        if (normalized === null) return null;
        return normalized.includes('.')
            ? normalized.replace(/0+$/, '').replace(/\.$/, '')
            : normalized;
    }

    function calculateTaxBreakdown({ items, discountAmount, canonicalTaxAmount }) {
        if (!Array.isArray(items) || items.length === 0) {
            return { groups: [], totalTaxCents: '0' };
        }

        const lines = items.map(item => {
            const totalCents = decimalToScaledInteger(item && item.total_price, 2);
            const rate = decimalParts(item && item.tax_rate);
            const rateLabel = formatRate(item && item.tax_rate);
            if (totalCents === null || rate === null || rateLabel === null) return null;
            return { totalCents, rate, rateLabel };
        });
        if (lines.some(line => line === null)) {
            return { groups: [], totalTaxCents: '0' };
        }

        const subtotalCents = lines.reduce((sum, line) => sum + line.totalCents, 0n);
        const parsedDiscount = decimalToScaledInteger(discountAmount || '0', 2);
        const discountCents = parsedDiscount === null ? 0n : parsedDiscount;
        let allocatedDiscount = 0n;
        const groups = new Map();

        lines.forEach((line, index) => {
            let discountShare = 0n;
            if (subtotalCents > 0n && discountCents > 0n) {
                discountShare = index === lines.length - 1
                    ? discountCents - allocatedDiscount
                    : divideRoundHalfUp(discountCents * line.totalCents, subtotalCents);
                allocatedDiscount += discountShare;
            }

            const taxableCents = line.totalCents - discountShare;
            const taxCents = divideRoundHalfUp(
                taxableCents * line.rate.numerator,
                line.rate.denominator * 100n,
            );
            groups.set(line.rateLabel, (groups.get(line.rateLabel) || 0n) + taxCents);
        });

        const groupEntries = Array.from(groups, ([rate, taxCents]) => ({ rate, taxCents }));
        const computedTaxCents = groupEntries.reduce((sum, group) => sum + group.taxCents, 0n);
        const canonicalTaxCents = decimalToScaledInteger(canonicalTaxAmount, 2);
        const totalTaxCents = canonicalTaxCents === null ? computedTaxCents : canonicalTaxCents;

        // The backend's canonical KDV amount is authoritative. Reconcile only
        // the final displayed rate bucket so bucket values always add to it.
        if (groupEntries.length > 0 && totalTaxCents !== computedTaxCents) {
            groupEntries[groupEntries.length - 1].taxCents += totalTaxCents - computedTaxCents;
        }

        return {
            groups: groupEntries.map(group => ({
                rate: group.rate,
                taxCents: group.taxCents.toString(),
            })),
            totalTaxCents: totalTaxCents.toString(),
        };
    }

    function formatCentsTr(value) {
        let cents = BigInt(value);
        const negative = cents < 0n;
        if (negative) cents = -cents;
        const whole = (cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
        const fraction = (cents % 100n).toString().padStart(2, '0');
        return `${negative ? '-' : ''}${whole},${fraction}`;
    }

    async function fetchWithTimeout(fetchImpl, url, init, timeoutMs, parentSignal = null) {
        if (typeof fetchImpl !== 'function') {
            throw new TypeError('fetchImpl must be a function.');
        }

        const controller = new AbortController();
        let didTimeout = false;
        const abortFromParent = () => controller.abort();

        if (parentSignal) {
            if (parentSignal.aborted) {
                abortFromParent();
            } else {
                parentSignal.addEventListener('abort', abortFromParent, { once: true });
            }
        }

        const timeoutId = setTimeout(() => {
            didTimeout = true;
            controller.abort();
        }, timeoutMs);

        try {
            return await fetchImpl(url, { ...(init || {}), signal: controller.signal });
        } catch (error) {
            if (didTimeout && !(parentSignal && parentSignal.aborted)) {
                const timeoutError = new Error(`Request exceeded ${timeoutMs} ms.`);
                timeoutError.name = 'TimeoutError';
                timeoutError.cause = error;
                throw timeoutError;
            }
            throw error;
        } finally {
            clearTimeout(timeoutId);
            if (parentSignal) {
                parentSignal.removeEventListener('abort', abortFromParent);
            }
        }
    }

    return {
        calculateTaxBreakdown,
        decimalToScaledInteger,
        fetchWithTimeout,
        formatCentsTr,
        normalizeLocaleDecimal,
        parseLocaleNumber,
    };
}));
