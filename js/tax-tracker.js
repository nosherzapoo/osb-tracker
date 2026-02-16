/* ========== Tax Revenue Tracker ========== */

function computeTaxKPIs(taxData) {
    var now = new Date();
    var currentYear = now.getFullYear();

    // All-time total
    var allTimeTotal = 0;
    taxData.forEach(function(row) {
        var v = row['Total'];
        if (v != null && !isNaN(v)) allTimeTotal += v;
    });

    // YTD current year
    var ytdTotal = 0;
    taxData.forEach(function(row) {
        var d = new Date(row['Week Ending'] + 'T00:00:00');
        if (d.getFullYear() === currentYear) {
            var v = row['Total'];
            if (v != null && !isNaN(v)) ytdTotal += v;
        }
    });

    // Prior year same period
    var priorYear = currentYear - 1;
    var dayOfYear = getDayOfYear(now);
    var priorYtdTotal = 0;
    taxData.forEach(function(row) {
        var d = new Date(row['Week Ending'] + 'T00:00:00');
        if (d.getFullYear() === priorYear && getDayOfYear(d) <= dayOfYear) {
            var v = row['Total'];
            if (v != null && !isNaN(v)) priorYtdTotal += v;
        }
    });

    var ytdChange = priorYtdTotal !== 0 ? (ytdTotal - priorYtdTotal) / Math.abs(priorYtdTotal) : null;

    return {
        allTimeTotal: allTimeTotal,
        ytdTotal: ytdTotal,
        priorYtdTotal: priorYtdTotal,
        ytdChange: ytdChange
    };
}

function getDayOfYear(d) {
    var start = new Date(d.getFullYear(), 0, 0);
    var diff = d - start;
    return Math.floor(diff / 86400000);
}

function renderTaxSidebar(container, kpis) {
    var changeClass = kpis.ytdChange != null ? (kpis.ytdChange >= 0 ? 'positive' : 'negative') : '';
    var changeText = kpis.ytdChange != null ? formatPercentSigned(kpis.ytdChange) + ' vs prior year' : '';

    container.innerHTML =
        '<div class="tax-card">' +
            '<div class="tax-label">ALL-TIME EST. TAX REVENUE</div>' +
            '<div class="tax-value">' + formatCompact(kpis.allTimeTotal) + '</div>' +
            '<div class="tax-sub">Since Jan 2022</div>' +
        '</div>' +
        '<div class="tax-card">' +
            '<div class="tax-label">YTD ' + new Date().getFullYear() + ' TAX REVENUE</div>' +
            '<div class="tax-value">' + formatCompact(kpis.ytdTotal) + '</div>' +
            (changeText ? '<div class="tax-sub kpi-change ' + changeClass + '">' + changeText + '</div>' : '') +
        '</div>' +
        '<div class="tax-card">' +
            '<div class="tax-label">TAX RATE</div>' +
            '<div class="tax-value">51%</div>' +
            '<div class="tax-sub">Highest in the nation</div>' +
        '</div>';
}
