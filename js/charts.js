/* ========== Chart.js Chart Management ========== */

var _mainChart = null;

function createMainChart(canvasId) {
    var ctx = document.getElementById(canvasId).getContext('2d');
    _mainChart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [] },
        options: getDefaultChartOptions('currency'),
        plugins: [Chart.registry.getPlugin('annotation')]
    });
    return _mainChart;
}

function updateChart(chart, data, tab, operators, dateRange, annotationsData, showAnnotations) {
    if (!chart || !data || data.length === 0) return;

    var config = TAB_CONFIG[tab];
    var fmt = config.yAxis;

    // Filter by date range
    var filtered = filterByDate(data, dateRange);

    // Sort chronologically for chart (oldest first)
    filtered = filtered.slice().sort(function(a, b) {
        return a['Week Ending'] < b['Week Ending'] ? -1 : 1;
    });

    var labels = filtered.map(function(row) {
        return new Date(row['Week Ending'] + 'T00:00:00');
    });

    // Build datasets
    var datasets = [];
    operators.forEach(function(op) {
        var isTotal = op === 'Total';
        var color = OPERATOR_COLORS[op] || '#888';
        datasets.push({
            label: op,
            data: filtered.map(function(row) {
                var v = row[op];
                return (v != null && !isNaN(v)) ? v : null;
            }),
            borderColor: color,
            backgroundColor: color + '20',
            borderWidth: isTotal ? 2.5 : 1.5,
            borderDash: isTotal ? [6, 3] : [],
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.1,
            spanGaps: false,
            order: isTotal ? 0 : 1
        });
    });

    // Annotations
    var annotationConfig = {};
    if (showAnnotations && annotationsData) {
        annotationConfig = buildChartAnnotations(annotationsData, dateRange);
    }

    chart.data.labels = labels;
    chart.data.datasets = datasets;
    chart.options = getDefaultChartOptions(fmt);
    chart.options.plugins.annotation = { annotations: annotationConfig };
    chart.update('none');
}

function getDefaultChartOptions(fmt) {
    var isCurrency = fmt === 'currency';
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
            x: {
                type: 'time',
                time: { unit: 'month', displayFormats: { month: 'MMM yyyy' } },
                grid: { color: 'rgba(42,46,59,0.5)' },
                ticks: { color: '#8b8fa3', maxRotation: 0, autoSkipPadding: 20 }
            },
            y: {
                grid: { color: 'rgba(42,46,59,0.5)' },
                ticks: {
                    color: '#8b8fa3',
                    callback: function(value) {
                        if (isCurrency) return formatCompact(value);
                        return formatPercent(value);
                    }
                }
            }
        },
        plugins: {
            legend: {
                display: true,
                position: 'top',
                labels: {
                    color: '#8b8fa3',
                    boxWidth: 12,
                    padding: 10,
                    font: { size: 11 },
                    usePointStyle: true
                }
            },
            tooltip: {
                backgroundColor: 'rgba(26,29,39,0.95)',
                titleColor: '#e4e6ed',
                bodyColor: '#e4e6ed',
                borderColor: '#2a2e3b',
                borderWidth: 1,
                padding: 10,
                callbacks: {
                    label: function(ctx) {
                        var val = ctx.parsed.y;
                        if (val == null) return ctx.dataset.label + ': —';
                        var formatted = isCurrency ? formatCurrency(val) : formatPercent(val);
                        return ctx.dataset.label + ': ' + formatted;
                    }
                }
            },
            annotation: { annotations: {} }
        }
    };
}

function filterByDate(data, dateRange) {
    if (!dateRange || (!dateRange.from && !dateRange.to)) return data;
    return data.filter(function(row) {
        var d = row['Week Ending'];
        if (dateRange.from && d < dateRange.from) return false;
        if (dateRange.to && d > dateRange.to) return false;
        return true;
    });
}

function createMarketShareChart(canvas, handleData) {
    // Use latest week's data
    var sorted = handleData.slice().sort(function(a, b) {
        return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
    });
    var latest = sorted[0];
    if (!latest) return null;

    var labels = [];
    var values = [];
    var colors = [];
    var ops = Object.keys(latest).filter(function(k) {
        return k !== 'Week Ending' && k !== 'Total';
    }).sort();

    ops.forEach(function(op) {
        var v = latest[op];
        if (v != null && !isNaN(v) && v > 0) {
            labels.push(op);
            values.push(v);
            colors.push(OPERATOR_COLORS[op] || '#888');
        }
    });

    return new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderColor: '#1a1d27',
                borderWidth: 2
            }]
        },
        options: {
            responsive: false,
            animation: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#e4e6ed', font: { size: 10 }, padding: 6, boxWidth: 10 }
                },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            var total = ctx.dataset.data.reduce(function(a, b) { return a + b; }, 0);
                            var pct = ((ctx.parsed / total) * 100).toFixed(1);
                            return ctx.label + ': ' + formatCompact(ctx.parsed) + ' (' + pct + '%)';
                        }
                    }
                }
            }
        }
    });
}
