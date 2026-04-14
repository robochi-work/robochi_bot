/**
 * Telegram Mini App Lifecycle Manager v6
 * - Single-instance guard via BroadcastChannel
 * - Reload with retry on resume from background
 */
(function() {
    'use strict';
    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;

    // ── Single-instance guard ──────────────────────────────────
    try {
        var channel = new BroadcastChannel('robochi_webapp');
        channel.postMessage({ type: 'new_instance', ts: Date.now() });
        channel.addEventListener('message', function(e) {
            if (e.data && e.data.type === 'new_instance' && e.data.ts > Date.now() - 500) {
                try { tg.close(); } catch(_) {}
            }
        });
    } catch(_) {}

    // ── Reload with retry ──────────────────────────────────────
    var lastBeat = Date.now();
    var reloadTimer = null;
    var retryCount = 0;
    var MAX_RETRIES = 3;

    function scheduleReload() {
        if (reloadTimer !== null) return;
        var delay = 500 + (retryCount * 500); // 500ms, 1000ms, 1500ms
        reloadTimer = setTimeout(function() {
            reloadTimer = null;
            retryCount++;
            if (retryCount > MAX_RETRIES) {
                // After max retries, show tap-to-reload hint
                document.body.style.opacity = '0.5';
                document.body.addEventListener('click', function() {
                    window.location.reload();
                }, { once: true });
                return;
            }
            window.location.reload();
        }, delay);
    }

    // Heartbeat: detect JS freeze (tab was backgrounded by OS)
    setInterval(function() {
        var now = Date.now();
        var gap = now - lastBeat;
        lastBeat = now;
        if (gap > 3000) {
            scheduleReload();
        }
    }, 1000);

    // Visibility restore
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 3000) {
                scheduleReload();
            }
        }
    });

    // Telegram activated event (v8.0+)
    if (tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
        tg.onEvent('activated', function() {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 3000) {
                scheduleReload();
            }
        });
    }
})();
