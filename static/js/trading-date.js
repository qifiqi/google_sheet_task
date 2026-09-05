(function (root) {
    'use strict';

    function cloneLocalDate(value) {
        const source = value instanceof Date ? value : new Date();
        return new Date(source.getFullYear(), source.getMonth(), source.getDate());
    }

    function previousWeekday(referenceDate) {
        const date = cloneLocalDate(referenceDate);
        date.setDate(date.getDate() - 1);
        while (date.getDay() === 0 || date.getDay() === 6) {
            date.setDate(date.getDate() - 1);
        }
        return date;
    }

    function formatDate(date) {
        const localDate = cloneLocalDate(date);
        const month = String(localDate.getMonth() + 1).padStart(2, '0');
        const day = String(localDate.getDate()).padStart(2, '0');
        return `${localDate.getFullYear()}-${month}-${day}`;
    }

    function defaultDateRange(years, referenceDate) {
        const end = previousWeekday(referenceDate);
        const start = cloneLocalDate(end);
        start.setFullYear(start.getFullYear() - years);
        while (start.getDay() === 0 || start.getDay() === 6) {
            start.setDate(start.getDate() - 1);
        }
        return { start, end };
    }

    root.TradingDate = Object.freeze({
        previousWeekday,
        formatDate,
        defaultDateRange,
    });
}(typeof window === 'undefined' ? globalThis : window));
