/**
 * Telegram Mini App Lifecycle Manager v3
 * Last resort: reload page if JS was frozen too long.
 */
(function() {
    'use strict';
    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;

    var lastBeat = Date.now();
    var FREEZE_THRESHOLD = 3000;
    var RELOAD_THRESHOLD = 30000;

    // Heartbeat: detect JS freeze
    setInterval(function() {
        var now = Date.now();
        var gap = now - lastBeat;

        if (gap > RELOAD_THRESHOLD) {
            // Frozen for 30+ seconds — page is likely dead, reload
            lastBeat = now;
            window.location.reload();
            return;
        }

        if (gap > FREEZE_THRESHOLD) {
            // Short freeze — try soft recovery
            lastBeat = now;
            softRecover();
        }

        lastBeat = now;
    }, 1000);

    // Visibility change — immediate recovery
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            var gap = Date.now() - lastBeat;
            if (gap > RELOAD_THRESHOLD) {
                window.location.reload();
            } else if (gap > FREEZE_THRESHOLD) {
                softRecover();
            }
            lastBeat = Date.now();
        }
    });

    // Telegram activated event
    if (tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
        tg.onEvent('activated', function() {
            var gap = Date.now() - lastBeat;
            if (gap > RELOAD_THRESHOLD) {
                window.location.reload();
            } else if (gap > FREEZE_THRESHOLD) {
                softRecover();
            }
            lastBeat = Date.now();
        });
    }

    // First touch after freeze — recover immediately
    var touchRecovery = function() {
        var gap = Date.now() - lastBeat;
        if (gap > FREEZE_THRESHOLD) {
            if (gap > RELOAD_THRESHOLD) {
                window.location.reload();
            } else {
                softRecover();
            }
            lastBeat = Date.now();
        }
    };
    document.addEventListener('touchstart', touchRecovery, { passive: true, capture: true });
    document.addEventListener('click', touchRecovery, true);

    function softRecover() {
        // Re-expand
        try { if (!tg.isExpanded) tg.expand(); } catch(e) {}
        try { tg.disableVerticalSwipes(); } catch(e) {}

        // Force reflow on all interactive elements
        var body = document.body;
        body.style.pointerEvents = 'none';
        void body.offsetHeight;
        requestAnimationFrame(function() {
            body.style.pointerEvents = '';
            document.querySelectorAll('a, button, [onclick], input, select, textarea').forEach(function(el) {
                el.style.pointerEvents = 'none';
                void el.offsetHeight;
                el.style.pointerEvents = '';
            });
        });
    }
})();
