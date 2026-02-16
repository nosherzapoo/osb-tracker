/* ========== Annotations Layer ========== */

function buildChartAnnotations(annotationsData, dateRange) {
    if (!annotationsData || !annotationsData.annotations) return {};

    var result = {};
    annotationsData.annotations.forEach(function(a) {
        if (a.type === 'point') {
            if (dateRange && !isDateInRange(a.date, dateRange)) return;
            result[a.id] = {
                type: 'line',
                xMin: a.date + 'T00:00:00',
                xMax: a.date + 'T00:00:00',
                borderColor: a.color || '#e74c3c',
                borderWidth: 1,
                borderDash: [4, 4],
                label: {
                    display: true,
                    content: a.label,
                    position: 'start',
                    backgroundColor: 'rgba(15,17,23,0.85)',
                    color: '#e4e6ed',
                    font: { size: 10 },
                    padding: 3
                }
            };
        } else if (a.type === 'range') {
            if (dateRange) {
                if (!isDateInRange(a.startDate, dateRange) && !isDateInRange(a.endDate, dateRange)) return;
            }
            result[a.id] = {
                type: 'box',
                xMin: a.startDate + 'T00:00:00',
                xMax: a.endDate + 'T00:00:00',
                backgroundColor: a.color || 'rgba(52, 152, 219, 0.1)',
                borderWidth: 0,
                label: {
                    display: true,
                    content: a.label,
                    position: { x: 'center', y: 'start' },
                    backgroundColor: 'transparent',
                    color: 'rgba(228,230,237,0.5)',
                    font: { size: 10 },
                    padding: 2
                }
            };
        }
    });
    return result;
}

function isDateInRange(dateStr, range) {
    if (!range.from && !range.to) return true;
    var d = dateStr;
    if (range.from && d < range.from) return false;
    if (range.to && d > range.to) return false;
    return true;
}
