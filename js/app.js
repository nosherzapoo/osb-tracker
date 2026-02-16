/* ========== Main Application ========== */

(function() {
    'use strict';

    // --- State ---
    var currentTab = 'handle';
    var selectedOperators = [];   // empty = all
    var dateRange = { from: null, to: null };
    var allData = null;
    var chart = null;
    var operatorList = [];
    var showAnnotations = true;
    var soloIndex = -1;  // for j/k cycling

    // --- Init ---
    async function init() {
        document.getElementById('main').innerHTML =
            '<div class="loading-spinner">Loading data...</div>';

        try {
            allData = await loadAllData();
        } catch (e) {
            document.getElementById('main').innerHTML =
                '<div class="loading-spinner">Failed to load data. Run the Python scraper first to generate CSV files.</div>';
            console.error(e);
            return;
        }

        // Restore main HTML
        document.getElementById('main').innerHTML =
            '<section id="kpi-cards"></section>' +
            '<section id="chart-area"><canvas id="main-chart"></canvas></section>' +
            '<section id="table-area"><table id="detail-table"></table></section>';

        // Extract operator names from CSV headers
        var sampleRow = allData.handle[0];
        operatorList = Object.keys(sampleRow).filter(function(k) {
            return k !== 'Week Ending' && k !== 'Total';
        }).sort();

        // Apply saved state from URL
        var saved = decodeState();
        currentTab = saved.tab || 'handle';
        dateRange.from = saved.dateFrom;
        dateRange.to = saved.dateTo;
        if (saved.operators) {
            selectedOperators = saved.operators;
        }

        // Build UI
        buildOperatorToggles();
        setActiveTab(currentTab);
        updateDateInputs();
        renderLastUpdated();

        // Create chart
        chart = createMainChart('main-chart');

        // Sidebar
        renderComparative(
            document.getElementById('comparative-content'),
            allData.comparative,
            allData.handle
        );
        var taxKPIs = computeTaxKPIs(allData.taxRevenue);
        renderTaxSidebar(document.getElementById('tax-content'), taxKPIs);

        // Event listeners
        setupTabListeners();
        setupFilterListeners();
        setupKeyboardShortcuts();
        setupSidebarToggles();
        setupModalListeners();
        setupAnnotationToggle();

        document.getElementById('btn-export').addEventListener('click', exportCurrentView);
        document.getElementById('btn-pdf').addEventListener('click', function() {
            generatePDF(allData, currentTab, getActiveOperators());
        });
        document.getElementById('btn-share').addEventListener('click', function() {
            copyPermalink({
                tab: currentTab,
                dateFrom: dateRange.from,
                dateTo: dateRange.to,
                operators: selectedOperators.length > 0 ? selectedOperators : null
            });
        });

        // Initial render
        render();
    }

    // --- Render ---
    function render() {
        var tabData = getDataForTab(currentTab);
        var ops = getActiveOperators();
        renderKPICards(tabData, ops);
        updateChart(chart, tabData, currentTab, ops, dateRange, allData.annotations, showAnnotations);
        renderTable(tabData, ops);
        pushState({
            tab: currentTab,
            dateFrom: dateRange.from,
            dateTo: dateRange.to,
            operators: selectedOperators.length > 0 ? selectedOperators : null
        });
    }

    function getDataForTab(tab) {
        var map = {
            'handle': allData.handle,
            'ggr': allData.ggr,
            'hold': allData.holdPct,
            'yoy-handle': allData.yoyHandle,
            'yoy-ggr': allData.yoyGgr
        };
        return map[tab] || allData.handle;
    }

    function getActiveOperators() {
        if (selectedOperators.length === 0) {
            return operatorList.concat(['Total']);
        }
        return selectedOperators;
    }

    // --- KPI Cards ---
    function renderKPICards(tabData, ops) {
        var container = document.getElementById('kpi-cards');
        if (!tabData || tabData.length === 0) { container.innerHTML = ''; return; }

        var config = TAB_CONFIG[currentTab];
        var fmt = getFormatter(config.format);

        // Sort descending
        var sorted = tabData.slice().sort(function(a, b) {
            return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
        });

        var latest = sorted[0];
        var prev = sorted.length > 1 ? sorted[1] : null;

        // Determine which column to show in KPIs
        var col = ops.length === 1 ? ops[0] : 'Total';

        var latestVal = latest[col];
        var prevVal = prev ? prev[col] : null;
        var wow = (latestVal != null && prevVal != null && prevVal !== 0)
            ? (latestVal - prevVal) / Math.abs(prevVal) : null;

        // Latest handle and GGR regardless of tab
        var latestHandle = allData.handle.slice().sort(function(a, b) {
            return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
        })[0];
        var latestGGR = allData.ggr.slice().sort(function(a, b) {
            return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
        })[0];

        var cards = [
            {
                label: 'Latest ' + config.label,
                value: fmt(latestVal),
                change: wow
            },
            {
                label: 'Handle (Latest)',
                value: formatCompact(latestHandle ? latestHandle[col] : null),
                change: null
            },
            {
                label: 'GGR (Latest)',
                value: formatCompact(latestGGR ? latestGGR[col] : null),
                change: null
            }
        ];

        // Tax revenue card
        var taxKPIs = computeTaxKPIs(allData.taxRevenue);
        cards.push({
            label: 'Est. Tax YTD',
            value: formatCompact(taxKPIs.ytdTotal),
            change: taxKPIs.ytdChange
        });

        var html = '';
        cards.forEach(function(c) {
            var changeHtml = '';
            if (c.change != null) {
                var cls = c.change >= 0 ? 'positive' : 'negative';
                changeHtml = '<div class="kpi-change ' + cls + '">' + formatPercentSigned(c.change) + ' WoW</div>';
            }
            html += '<div class="kpi-card">' +
                '<div class="kpi-label">' + c.label + '</div>' +
                '<div class="kpi-value">' + c.value + '</div>' +
                changeHtml +
            '</div>';
        });

        container.innerHTML = html;
    }

    // --- Data Table ---
    function renderTable(tabData, ops) {
        var table = document.getElementById('detail-table');
        if (!tabData || tabData.length === 0) { table.innerHTML = ''; return; }

        var config = TAB_CONFIG[currentTab];
        var fmt = getFormatter(config.format);

        var filtered = filterByDate(tabData, dateRange);

        // Already sorted descending from CSV
        var columns = ['Week Ending'].concat(ops);

        var html = '<thead><tr>';
        columns.forEach(function(col) {
            html += '<th>' + col + '</th>';
        });
        html += '</tr></thead><tbody>';

        var maxRows = Math.min(filtered.length, 200);
        for (var i = 0; i < maxRows; i++) {
            var row = filtered[i];
            html += '<tr>';
            columns.forEach(function(col) {
                if (col === 'Week Ending') {
                    html += '<td>' + formatDate(row[col]) + '</td>';
                } else {
                    var v = row[col];
                    var cls = '';
                    if (config.format === 'percent' && v != null) {
                        cls = v >= 0 ? 'td-positive' : 'td-negative';
                    }
                    html += '<td class="' + cls + '">' + fmt(v) + '</td>';
                }
            });
            html += '</tr>';
        }

        if (filtered.length > maxRows) {
            html += '<tr><td colspan="' + columns.length + '" style="text-align:center;color:var(--text-muted)">' +
                '... ' + (filtered.length - maxRows) + ' more rows (export CSV for full data)</td></tr>';
        }

        html += '</tbody>';
        table.innerHTML = html;
    }

    // --- Operator Toggles ---
    function buildOperatorToggles() {
        var container = document.getElementById('operator-toggles');
        var allOps = operatorList.concat(['Total']);

        var html = '<button class="op-toggle active" data-op="all">All</button>';
        allOps.forEach(function(op) {
            var color = OPERATOR_COLORS[op] || '#888';
            var isActive = selectedOperators.length === 0 || selectedOperators.indexOf(op) !== -1;
            html += '<button class="op-toggle' + (isActive && selectedOperators.length > 0 ? ' active' : '') +
                '" data-op="' + op + '" style="' +
                (isActive && selectedOperators.length > 0 ? 'background:' + color + ';border-color:' + color : '') +
                '">' + op + '</button>';
        });
        container.innerHTML = html;

        container.addEventListener('click', function(e) {
            var btn = e.target.closest('.op-toggle');
            if (!btn) return;
            var op = btn.dataset.op;

            if (op === 'all') {
                selectedOperators = [];
                soloIndex = -1;
            } else {
                var idx = selectedOperators.indexOf(op);
                if (idx !== -1) {
                    selectedOperators.splice(idx, 1);
                } else {
                    selectedOperators.push(op);
                }
            }
            updateOperatorToggleUI();
            render();
        });
    }

    function updateOperatorToggleUI() {
        var container = document.getElementById('operator-toggles');
        var buttons = container.querySelectorAll('.op-toggle');
        var allActive = selectedOperators.length === 0;

        buttons.forEach(function(btn) {
            var op = btn.dataset.op;
            if (op === 'all') {
                btn.classList.toggle('active', allActive);
                return;
            }
            var isActive = allActive || selectedOperators.indexOf(op) !== -1;
            btn.classList.toggle('active', isActive);
            var color = OPERATOR_COLORS[op] || '#888';
            btn.style.background = isActive && !allActive ? color : '';
            btn.style.borderColor = isActive && !allActive ? color : '';
        });
    }

    // --- Tabs ---
    function setActiveTab(tab) {
        document.querySelectorAll('#tab-bar .tab').forEach(function(btn) {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });
        currentTab = tab;
    }

    function setupTabListeners() {
        document.getElementById('tab-bar').addEventListener('click', function(e) {
            var btn = e.target.closest('.tab');
            if (!btn) return;
            switchTab(btn.dataset.tab);
        });
    }

    function switchTab(tab) {
        if (!TAB_CONFIG[tab]) return;
        setActiveTab(tab);
        render();
    }

    // --- Filters ---
    function setupFilterListeners() {
        document.getElementById('date-from').addEventListener('change', function() {
            dateRange.from = this.value || null;
            render();
        });
        document.getElementById('date-to').addEventListener('change', function() {
            dateRange.to = this.value || null;
            render();
        });
    }

    function updateDateInputs() {
        if (dateRange.from) document.getElementById('date-from').value = dateRange.from;
        if (dateRange.to) document.getElementById('date-to').value = dateRange.to;
    }

    function setupAnnotationToggle() {
        document.getElementById('toggle-annotations').addEventListener('change', function() {
            showAnnotations = this.checked;
            render();
        });
    }

    // --- Last Updated ---
    function renderLastUpdated() {
        var sorted = allData.handle.slice().sort(function(a, b) {
            return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
        });
        var latest = sorted[0];
        if (latest) {
            document.getElementById('last-updated').textContent =
                'Latest data: week ending ' + formatDate(latest['Week Ending']);
        }
    }

    // --- Export ---
    function exportCurrentView() {
        var tabData = getDataForTab(currentTab);
        var ops = getActiveOperators();
        var filtered = filterByDate(tabData, dateRange);

        // Build export data
        var columns = ['Week Ending'].concat(ops);
        var rows = filtered.map(function(row) {
            var out = {};
            columns.forEach(function(col) { out[col] = row[col]; });
            return out;
        });

        var csv = Papa.unparse(rows);
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = 'ny-sports-betting-' + currentTab + '-' + new Date().toISOString().slice(0, 10) + '.csv';
        a.click();
        URL.revokeObjectURL(url);
        showToast('CSV exported');
    }

    // --- Keyboard Shortcuts ---
    function setupKeyboardShortcuts() {
        document.addEventListener('keydown', function(e) {
            var tag = e.target.tagName;
            if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

            var tabs = ['handle', 'ggr', 'hold', 'yoy-handle', 'yoy-ggr'];

            switch (e.key) {
                case '1': switchTab(tabs[0]); break;
                case '2': switchTab(tabs[1]); break;
                case '3': switchTab(tabs[2]); break;
                case '4': switchTab(tabs[3]); break;
                case '5': switchTab(tabs[4]); break;
                case 'j': cycleOperator(1); break;
                case 'k': cycleOperator(-1); break;
                case 'a':
                    selectedOperators = [];
                    soloIndex = -1;
                    updateOperatorToggleUI();
                    render();
                    break;
                case 'e': exportCurrentView(); break;
                case 'r': e.preventDefault(); location.reload(); break;
                case '?':
                    document.getElementById('keyboard-modal').classList.toggle('hidden');
                    break;
                case 'Escape':
                    document.getElementById('keyboard-modal').classList.add('hidden');
                    break;
            }
        });
    }

    function cycleOperator(direction) {
        var allOps = operatorList.concat(['Total']);

        if (selectedOperators.length !== 1) {
            soloIndex = direction === 1 ? 0 : allOps.length - 1;
        } else {
            var current = allOps.indexOf(selectedOperators[0]);
            soloIndex = current + direction;
            if (soloIndex < 0) soloIndex = allOps.length - 1;
            if (soloIndex >= allOps.length) soloIndex = 0;
        }

        selectedOperators = [allOps[soloIndex]];
        updateOperatorToggleUI();
        render();
    }

    // --- Sidebar ---
    function setupSidebarToggles() {
        document.querySelectorAll('.sidebar-heading').forEach(function(heading) {
            heading.addEventListener('click', function() {
                var targetId = this.dataset.toggle;
                if (!targetId) return;
                var target = document.getElementById(targetId);
                if (target) {
                    target.classList.toggle('hidden');
                    this.classList.toggle('collapsed');
                }
            });
        });
    }

    // --- Modal ---
    function setupModalListeners() {
        document.getElementById('close-modal').addEventListener('click', function() {
            document.getElementById('keyboard-modal').classList.add('hidden');
        });
        document.getElementById('keyboard-modal').addEventListener('click', function(e) {
            if (e.target === this) this.classList.add('hidden');
        });
    }

    // --- Start ---
    init();
})();
