/* ========== Permalink / Share State ========== */

function decodeState() {
    var params = new URLSearchParams(window.location.search);
    return {
        tab: params.get('tab') || 'handle',
        dateFrom: params.get('from') || null,
        dateTo: params.get('to') || null,
        operators: params.get('ops') ? params.get('ops').split(',') : null
    };
}

function encodeState(state) {
    var params = new URLSearchParams();
    if (state.tab && state.tab !== 'handle') params.set('tab', state.tab);
    if (state.dateFrom) params.set('from', state.dateFrom);
    if (state.dateTo) params.set('to', state.dateTo);
    if (state.operators && state.operators.length > 0) {
        params.set('ops', state.operators.join(','));
    }
    var str = params.toString();
    return str ? '?' + str : window.location.pathname;
}

function pushState(state) {
    var url = encodeState(state);
    window.history.replaceState(null, '', url);
}

function copyPermalink(state) {
    var url = window.location.origin + window.location.pathname + encodeState(state);
    if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(function() {
            showToast('Link copied to clipboard');
        });
    } else {
        showToast('Could not copy link');
    }
}
