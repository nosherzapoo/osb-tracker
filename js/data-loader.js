/* ========== Data Loading ========== */

function fetchCSV(url) {
    return new Promise(function(resolve, reject) {
        Papa.parse(url, {
            download: true,
            header: true,
            dynamicTyping: true,
            skipEmptyLines: true,
            complete: function(results) { resolve(results.data); },
            error: function(err) { reject(err); }
        });
    });
}

function fetchJSON(url) {
    return fetch(url).then(function(r) { return r.json(); });
}

function loadAllData() {
    return Promise.all([
        fetchCSV('data/handle.csv'),
        fetchCSV('data/ggr.csv'),
        fetchCSV('data/hold_pct.csv'),
        fetchCSV('data/yoy_handle.csv'),
        fetchCSV('data/yoy_ggr.csv'),
        fetchCSV('data/tax_revenue.csv'),
        fetchJSON('data/annotations.json'),
        fetchJSON('data/comparative_data.json')
    ]).then(function(results) {
        return {
            handle: results[0],
            ggr: results[1],
            holdPct: results[2],
            yoyHandle: results[3],
            yoyGgr: results[4],
            taxRevenue: results[5],
            annotations: results[6],
            comparative: results[7]
        };
    });
}
