/* ========== PDF Report Generator ========== */

function generatePDF(allData, currentTab, selectedOperators) {
    showToast('Generating PDF report...');

    // Use jsPDF
    var doc = new jspdf.jsPDF('p', 'mm', 'a4');
    var pageW = 210;
    var margin = 15;
    var contentW = pageW - 2 * margin;
    var y = 20;

    // ---- Page 1: Title + KPIs ----
    doc.setFontSize(20);
    doc.setTextColor(30, 30, 40);
    doc.text('NY Mobile Sports Betting', margin, y);
    y += 8;
    doc.setFontSize(14);
    doc.setTextColor(100, 100, 120);
    doc.text('Weekly Report', margin, y);
    y += 6;
    doc.setFontSize(9);
    doc.text('Generated: ' + new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }), margin, y);
    y += 10;

    // KPI summary
    doc.setDrawColor(200, 200, 210);
    doc.setLineWidth(0.3);
    doc.line(margin, y, pageW - margin, y);
    y += 8;

    var latestWeek = getLatestWeek(allData.handle);
    var prevWeek = getPrevWeek(allData.handle);
    var latestGGR = getLatestWeek(allData.ggr);

    if (latestWeek) {
        var kpis = [
            { label: 'Week Ending', value: formatDate(latestWeek['Week Ending']) },
            { label: 'Total Handle', value: formatCurrency(latestWeek['Total']) },
            { label: 'Total GGR', value: formatCurrency(latestGGR ? latestGGR['Total'] : null) },
            { label: 'WoW Handle Change', value: prevWeek ? formatPercentSigned((latestWeek['Total'] - prevWeek['Total']) / Math.abs(prevWeek['Total'])) : 'N/A' }
        ];

        doc.setFontSize(10);
        var colW = contentW / kpis.length;
        kpis.forEach(function(kpi, i) {
            var x = margin + i * colW;
            doc.setTextColor(120, 120, 140);
            doc.text(kpi.label, x, y);
            doc.setTextColor(30, 30, 40);
            doc.setFontSize(12);
            doc.text(kpi.value, x, y + 6);
            doc.setFontSize(10);
        });
        y += 18;
    }

    // Operator breakdown table
    doc.setDrawColor(200, 200, 210);
    doc.line(margin, y, pageW - margin, y);
    y += 6;
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 40);
    doc.text('Operator Breakdown — Latest Week', margin, y);
    y += 6;

    if (latestWeek) {
        var ops = Object.keys(latestWeek).filter(function(k) {
            return k !== 'Week Ending' && k !== 'Total';
        }).sort();

        // Table header
        doc.setFontSize(8);
        doc.setTextColor(100, 100, 120);
        doc.text('Operator', margin, y);
        doc.text('Handle', margin + 60, y);
        doc.text('GGR', margin + 105, y);
        doc.text('Market Share', margin + 140, y);
        y += 1;
        doc.line(margin, y, pageW - margin, y);
        y += 4;

        var totalHandle = latestWeek['Total'] || 1;
        doc.setTextColor(30, 30, 40);
        ops.forEach(function(op) {
            var h = latestWeek[op];
            var g = latestGGR ? latestGGR[op] : null;
            if (h == null && g == null) return;
            var share = (h != null && totalHandle > 0) ? ((h / totalHandle) * 100).toFixed(1) + '%' : '—';

            doc.text(op, margin, y);
            doc.text(h != null ? formatCurrency(h) : '—', margin + 60, y);
            doc.text(g != null ? formatCurrency(g) : '—', margin + 105, y);
            doc.text(share, margin + 140, y);
            y += 5;

            if (y > 270) { doc.addPage(); y = 20; }
        });

        // Total row
        y += 1;
        doc.line(margin, y, pageW - margin, y);
        y += 4;
        doc.setFontSize(9);
        doc.text('Total', margin, y, { renderingMode: 'fill' });
        doc.text(formatCurrency(latestWeek['Total']), margin + 60, y);
        doc.text(latestGGR ? formatCurrency(latestGGR['Total']) : '—', margin + 105, y);
        doc.text('100%', margin + 140, y);
    }

    // ---- Page 2: Recent trends table ----
    doc.addPage();
    y = 20;
    doc.setFontSize(11);
    doc.setTextColor(30, 30, 40);
    doc.text('Weekly Handle Trends — Last 12 Weeks', margin, y);
    y += 6;

    doc.setFontSize(8);
    doc.setTextColor(100, 100, 120);
    doc.text('Week Ending', margin, y);
    doc.text('Total Handle', margin + 40, y);
    doc.text('Total GGR', margin + 85, y);
    doc.text('Hold %', margin + 125, y);
    doc.text('YoY Handle', margin + 150, y);
    y += 1;
    doc.line(margin, y, pageW - margin, y);
    y += 4;

    var sorted = allData.handle.slice().sort(function(a, b) {
        return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
    });
    var last12 = sorted.slice(0, 12);
    doc.setTextColor(30, 30, 40);

    last12.forEach(function(row) {
        var we = row['Week Ending'];
        var ggrRow = findRow(allData.ggr, we);
        var holdRow = findRow(allData.holdPct, we);
        var yoyRow = findRow(allData.yoyHandle, we);

        doc.text(formatDate(we), margin, y);
        doc.text(formatCurrency(row['Total']), margin + 40, y);
        doc.text(ggrRow ? formatCurrency(ggrRow['Total']) : '—', margin + 85, y);
        doc.text(holdRow ? formatPercent(holdRow['Total']) : '—', margin + 125, y);
        doc.text(yoyRow && yoyRow['Total'] != null ? formatPercentSigned(yoyRow['Total']) : '—', margin + 150, y);
        y += 5;
    });

    // Footer on each page
    var pages = doc.internal.getNumberOfPages();
    for (var p = 1; p <= pages; p++) {
        doc.setPage(p);
        doc.setFontSize(7);
        doc.setTextColor(150, 150, 160);
        doc.text('NY Sports Betting Tracker — gaming.ny.gov', margin, 290);
        doc.text('Page ' + p + ' of ' + pages, pageW - margin - 20, 290);
    }

    doc.save('ny-sports-betting-report-' + new Date().toISOString().slice(0, 10) + '.pdf');
    showToast('PDF report downloaded');
}

function getLatestWeek(data) {
    if (!data || data.length === 0) return null;
    var sorted = data.slice().sort(function(a, b) {
        return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
    });
    return sorted[0];
}

function getPrevWeek(data) {
    if (!data || data.length < 2) return null;
    var sorted = data.slice().sort(function(a, b) {
        return a['Week Ending'] > b['Week Ending'] ? -1 : 1;
    });
    return sorted[1];
}

function findRow(data, weekEnding) {
    for (var i = 0; i < data.length; i++) {
        if (data[i]['Week Ending'] === weekEnding) return data[i];
    }
    return null;
}
