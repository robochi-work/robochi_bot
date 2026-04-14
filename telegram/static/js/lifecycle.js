/**
 * Telegram Mini App Lifecycle Manager v5
 * Fix: deduplicate reload triggers + 350ms delay to avoid ERR_CONNECTION_ABORTED.
 * Multiple events (visibilitychange, activated, touchstart) can fire in rapid
 * succession on resume — without deduplication each one calls reload(), and the
 * second reload aborts the first mid-handshake, producing ERR_CONNECTION_ABORTED.
 */
(function() {
    'use strict';
    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;

    // ── Single-instance guard ──────────────────────────────────
    // When a new Mini App window opens, it tells previous ones to close.
    try {
        var channel = new BroadcastChannel('robochi_webapp');
        // Notify any already-open instance to close
        channel.postMessage({ type: 'new_instance', ts: Date.now() });
        // If another instance opens after us — we close
        channel.addEventListener('message', function(e) {
            if (e.data && e.data.type === 'new_instance' && e.data.ts > Date.now() - 500) {
                try { tg.close(); } catch(_) {}
            }
        });
    } catch(_) {
        // BroadcastChannel not supported — skip
    }

    var lastBeat = Date.now();
    var reloadTimer = null;

    function scheduleReload() {
        if (reloadTimer !== null) return;  // already scheduled — ignore duplicate
        reloadTimer = setTimeout(function() {
            window.location.reload();
        }, 350);  // 350ms: let Telegram network layer stabilise before reload
    }

    // Heartbeat: detect JS freeze (tab was backgrounded by OS)
    setInterval(function() {
        var now = Date.now();
        var gap = now - lastBeat;
        lastBeat = now;
        if (gap > 2500) {
            scheduleReload();
        }
    }, 1000);

    // Visibility restore
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 2500) {
                scheduleReload();
            }
        }
    });

    // Telegram activated event (v8.0+)
    if (tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
        tg.onEvent('activated', function() {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 2500) {
                scheduleReload();
            }
        });
    }

    // First interaction after freeze
    function onInteraction() {
        var gap = Date.now() - lastBeat;
        if (gap > 2500) {
            lastBeat = Date.now();
            scheduleReload();
        }
    }
    document.addEventListener('touchstart', onInteraction, { passive: true, capture: true });
    document.addEventListener('click', onInteraction, true);
})();
