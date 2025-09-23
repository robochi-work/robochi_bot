class TelegramAppHelper {
    constructor(webApp) {
        this.webApp = webApp;
        this.webApp.expand();
    }

    setHeaderColorFromVar(varName) {
        const root = document.documentElement;
        const color = getComputedStyle(root).getPropertyValue(varName).trim();

        if (color) {
            this.webApp.setHeaderColor(color);
        }
    }
}

function applyTelegramTheme() {
    const root = document.documentElement;
    root.classList.remove('light', 'dark');
    root.classList.add(Telegram.WebApp.colorScheme);
}

window.addEventListener('DOMContentLoaded', () => {
    const webApp = window.Telegram?.WebApp;

    if (!webApp) {
        console.warn("Telegram.WebApp not found");
        return;
    }
    webApp.disableVerticalSwipes();

    const tgHelper = new TelegramAppHelper(webApp);
    tgHelper.setHeaderColorFromVar('--main_purple');

    applyTelegramTheme();
    Telegram.WebApp.onEvent('themeChanged', applyTelegramTheme);

});
function sendTelegramWebData(url) {
    const initData = Telegram.WebView.initParams.tgWebAppData;
    const encodedInitData = encodeURIComponent(initData);
    const currentParams = new URLSearchParams(window.location.search);
    const nextPath = currentParams.get('next') || '/';
    window.location.href = `${url}?init_data=${encodedInitData || ''}&next=${nextPath}`;
};

document.addEventListener('alpine:init', () => {
    const tg = window.Telegram.WebApp;
    tg.ready();

    const photoUrl = tg.initDataUnsafe.user?.photo_url ?? null;
    if (!photoUrl) {
      console.warn('photo_url отсутствует — ничего не отправляем');
      return;
    }

    const csrfToken = getCookie('csrftoken');
    fetch('/api/users/me/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ photo: photoUrl })
    })
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      console.log('✅ photo успешно отправлено на /api/users/me/');
    })
    .catch(err => {
      console.error('❌ Ошибка при отправке photo на /api/users/me/:', err);
    });
  });