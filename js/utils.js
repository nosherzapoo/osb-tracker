/* ========== Utility Functions & Constants ========== */

var OPERATOR_COLORS = {
    'FanDuel':                '#1493ff',
    'DraftKings':             '#53d337',
    'BetMGM':                 '#c4a44a',
    'Caesars':                '#1b3c5d',
    'ESPN Bet':               '#d10000',
    'Fanatics':               '#00875a',
    'Bally Bet':              '#e5202e',
    'Resorts World Bet':      '#8b5cf6',
    'Rush Street Interactive': '#f59e0b',
    'Total':                  '#4f8ff7'
};

var TAB_CONFIG = {
    'handle':     { csv: 'handle',     label: 'Handle',          format: 'currency',   yAxis: 'currency'   },
    'ggr':        { csv: 'ggr',        label: 'GGR',             format: 'currency',   yAxis: 'currency'   },
    'hold':       { csv: 'hold_pct',   label: 'Hold %',          format: 'percent',    yAxis: 'percent'    },
    'yoy-handle': { csv: 'yoy_handle', label: 'YoY Handle Change', format: 'percent', yAxis: 'percent'    },
    'yoy-ggr':    { csv: 'yoy_ggr',    label: 'YoY GGR Change',   format: 'percent', yAxis: 'percent'    }
};

function formatCurrency(num) {
    if (num == null || isNaN(num)) return '—';
    var neg = num < 0;
    var abs = Math.abs(num);
    var str = abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return (neg ? '-$' : '$') + str;
}

function formatCompact(num) {
    if (num == null || isNaN(num)) return '—';
    var neg = num < 0;
    var abs = Math.abs(num);
    var suffix = '';
    if (abs >= 1e9) { abs = abs / 1e9; suffix = 'B'; }
    else if (abs >= 1e6) { abs = abs / 1e6; suffix = 'M'; }
    else if (abs >= 1e3) { abs = abs / 1e3; suffix = 'K'; }
    var str = abs.toFixed(abs >= 100 ? 0 : abs >= 10 ? 1 : 2);
    return (neg ? '-$' : '$') + str + suffix;
}

function formatPercent(num) {
    if (num == null || isNaN(num)) return '—';
    return (num * 100).toFixed(2) + '%';
}

function formatPercentSigned(num) {
    if (num == null || isNaN(num)) return '—';
    var val = (num * 100).toFixed(2);
    return (num >= 0 ? '+' : '') + val + '%';
}

function formatDate(dateStr) {
    if (!dateStr) return '—';
    var d = new Date(dateStr + 'T00:00:00');
    var mm = String(d.getMonth() + 1).padStart(2, '0');
    var dd = String(d.getDate()).padStart(2, '0');
    return mm + '/' + dd + '/' + d.getFullYear();
}

function getFormatter(type) {
    if (type === 'currency') return formatCurrency;
    if (type === 'percent') return formatPercent;
    return function(v) { return v == null ? '—' : String(v); };
}

function showToast(msg) {
    var el = document.getElementById('toast');
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(el._timer);
    el._timer = setTimeout(function() { el.classList.add('hidden'); }, 2500);
}
