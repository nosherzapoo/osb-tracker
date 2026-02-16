/* ========== Comparative Context Panel ========== */

function renderComparative(container, comparativeData, liveNYData) {
    if (!comparativeData || !comparativeData.states) {
        container.innerHTML = '<p class="sidebar-note">Comparative data unavailable.</p>';
        return;
    }

    // Compute live NY figures from our data
    var nyState = null;
    var states = comparativeData.states.map(function(s) {
        var copy = JSON.parse(JSON.stringify(s));
        if (copy.abbreviation === 'NY' && liveNYData) {
            var nyCalc = computeNYLive(liveNYData);
            copy.data.monthlyHandle = nyCalc.monthlyHandle;
            copy.data.monthlyGGR = nyCalc.monthlyGGR;
            copy.data.monthlyTaxRevenue = nyCalc.monthlyTaxRevenue;
            nyState = copy;
        }
        return copy;
    });

    // Sort by monthly handle descending
    states.sort(function(a, b) {
        return (b.data.monthlyHandle || 0) - (a.data.monthlyHandle || 0);
    });

    // Find NY rank
    var nyRank = 0;
    for (var i = 0; i < states.length; i++) {
        if (states[i].abbreviation === 'NY') { nyRank = i + 1; break; }
    }

    var html = '';
    if (nyRank > 0) {
        html += '<div class="tax-card" style="margin-bottom:12px;text-align:center">' +
            '<div class="tax-label">NATIONAL RANKING BY HANDLE</div>' +
            '<div class="tax-value" style="color:var(--accent)">#' + nyRank + ' of ' + states.length + '</div>' +
        '</div>';
    }

    html += '<table class="comp-table">' +
        '<thead><tr><th>State</th><th>Handle/mo</th><th>Tax Rate</th></tr></thead>' +
        '<tbody>';

    states.forEach(function(s) {
        var isNY = s.abbreviation === 'NY';
        html += '<tr' + (isNY ? ' class="highlight"' : '') + '>' +
            '<td><span class="state-badge" style="background:' + (isNY ? 'var(--accent)' : 'var(--border)') + '">' +
                s.abbreviation + '</span></td>' +
            '<td>' + formatCompact(s.data.monthlyHandle) + '</td>' +
            '<td>' + (s.taxRate * 100).toFixed(0) + '%</td>' +
        '</tr>';
    });

    html += '</tbody></table>';
    html += '<p class="sidebar-note" style="margin-top:8px">Last updated: ' + comparativeData.lastUpdated +
        '. Other states are approximate figures from public reports.</p>';

    container.innerHTML = html;
}

function computeNYLive(handleData) {
    // Get the latest 4 weeks to approximate a month
    var sorted = handleData.slice().sort(function(a, b) {
        return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
    });

    var monthHandle = 0;
    var monthGGR = 0;
    var count = Math.min(4, sorted.length);
    for (var i = 0; i < count; i++) {
        var h = sorted[i]['Total'];
        if (h != null && !isNaN(h)) monthHandle += h;
    }

    return {
        monthlyHandle: monthHandle,
        monthlyGGR: null,
        monthlyTaxRevenue: null
    };
}
