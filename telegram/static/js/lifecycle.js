/**
 * Telegram Mini App Lifecycle Manager v8
 * - Touch-based freeze detection (most reliable signal)
 * - Ping server before reload (avoid ERR_CONNECTION_ABORTED)
 * - Single-instance guard via BroadcastChannel
 */
(function() {
    'use strict';

    // ── Single-instance guard ──────────────────────────────────
    var tg = window.Telegram && window.Telegram.WebApp;
    try {
        var channel = new BroadcastChannel('robochi_webapp');
        channel.postMessage({ type: 'new_instance', ts: Date.now() });
        channel.addEventListener('message', function(e) {
            if (e.data && e.data.type === 'new_instance' && e.data.ts > Date.now() - 500) {
                try { if (tg) tg.close(); } catch(_) {}
            }
        });
    } catch(_) {}

    // ── State ──────────────────────────────────────────────────
    var lastBeat = Date.now();
    var recovering = false;
    var STALE_MS = 3000;

    // ── Heartbeat ──────────────────────────────────────────────
    setInterval(function() { lastBeat = Date.now(); }, 1000);

    // ── Overlay ────────────────────────────────────────────────
    function showOverlay() {
        if (document.getElementById('lifecycle-overlay')) return;
        var div = document.createElement('div');
        div.id = 'lifecycle-overlay';
        div.style.cssText = 'position:fixed;inset:0;z-index:99999;'
            + 'display:flex;align-items:center;justify-content:center;'
            + 'background:var(--bg-color,#fff);color:var(--text-color,#000);'
            + 'font-size:18px;';
        div.textContent = '\u0417\u0430\u0432\u0430\u043D\u0442\u0430\u0436\u0435\u043D\u043D\u044F...';
        document.body.appendChild(div);
    }

    function hideOverlay() {
        var el = document.getElementById('lifecycle-overlay');
        if (el) el.remove();
    }

    // ── Ping then reload ───────────────────────────────────────
    function pingAndReload(attempt) {
        if (!recovering) return;
        attempt = attempt || 1;
        var MAX = 6;

        showOverlay();

        fetch(window.location.href, { method: 'HEAD', cache: 'no-store' })
            .then(function(r) {
                if (r.ok || r.status === 302 || r.status === 301) {
                    window.location.reload();
                } else {
                    throw new Error('status ' + r.status);
                }
            })
            .catch(function() {
                if (attempt >= MAX) {
                    hideOverlay();
                    recovering = false;
                    window.location.reload();
                    return;
                }
                var delay = Math.min(1000 * attempt, 4000);
                setTimeout(function() { pingAndReload(attempt + 1); }, delay);
            });
    }

    function onResume() {
        var gap = Date.now() - lastBeat;
        lastBeat = Date.now();
        if (gap > STALE_MS && !recovering) {
            recovering = true;
            setTimeout(function() { pingAndReload(1); }, 600);
        }
    }

    // ── Touch detection (most reliable!) ───────────────────────
    // When user touches screen after returning from background,
    // this fires EVEN if visibilitychange/focus/heartbeat didn't.
    document.addEventListener('touchstart', function() {
        var gap = Date.now() - lastBeat;
        if (gap > STALE_MS) {
            onResume();
        }
    }, { passive: true, capture: true });

    // ── Browser events ─────────────────────────────────────────
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') onResume();
    });
    window.addEventListener('focus', function() { onResume(); });
    window.addEventListener('pageshow', function() { onResume(); });

    // ── Telegram SDK events ────────────────────────────────────
    if (tg && tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
        tg.onEvent('activated', function() { onResume(); });
    }
})();
