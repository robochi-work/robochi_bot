/**
 * Telegram Mini App Lifecycle Manager v4
 * Nuclear option: detect ANY freeze and force full page reload.
 */
(function() {
    'use strict';
    var tg = window.Telegram && window.Telegram.WebApp;
    if (!tg) return;

    var lastBeat = Date.now();

    // Single strategy: if JS was frozen for ANY duration > 2 sec, reload.
    setInterval(function() {
        var now = Date.now();
        var gap = now - lastBeat;
        lastBeat = now;

        if (gap > 2500) {
            // JS was frozen — force full page reload
            window.location.reload();
        }
    }, 1000);

    // On visibility restore — reload immediately
    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible') {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 2500) {
                window.location.reload();
            }
        }
    });

    // Telegram activated — reload
    if (tg.isVersionAtLeast && tg.isVersionAtLeast('8.0')) {
        tg.onEvent('activated', function() {
            var gap = Date.now() - lastBeat;
            lastBeat = Date.now();
            if (gap > 2500) {
                window.location.reload();
            }
        });
    }

    // First touch/click after freeze — reload
    function onInteraction() {
        var gap = Date.now() - lastBeat;
        if (gap > 2500) {
            lastBeat = Date.now();
            window.location.reload();
        }
    }
    document.addEventListener('touchstart', onInteraction, { passive: true, capture: true });
    document.addEventListener('click', onInteraction, true);
})();
