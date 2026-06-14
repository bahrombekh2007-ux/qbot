/**
 * Telegram WebApp SDK wrapper
 * Hujjat: https://core.telegram.org/bots/webapps
 */

class TelegramManager {
    constructor() {
        this.tg = window.Telegram?.WebApp;
        this.isAvailable = !!this.tg;
        this.user = null;
        this.initData = '';
    }

    /**
     * Telegram WebApp ni ishga tushirish
     */
    init() {
        if (!this.isAvailable) {
            console.warn('Telegram WebApp SDK mavjud emas - development rejim');
            this.tg = this._createMockTg();
        }

        try {
            this.tg.ready();
            this.tg.expand();
        } catch (e) {
            console.error('TG init error:', e);
        }

        // InitData olish
        this.initData = this.tg.initData || '';
        this.user = this.tg.initDataUnsafe?.user || this._getMockUser();

        // Theme
        this.applyTheme();

        // MainButton ni sozlash
        this._setupMainButton();

        // BackButton
        this._setupBackButton();

        console.log('✅ Telegram WebApp initialized', this.user);
    }

    _createMockTg() {
        // Development uchun mock - Telegram'siz test qilish
        return {
            ready: () => {},
            expand: () => {},
            close: () => {
                if (window.confirm('WebApp yopilsinmi?')) {
                    window.close();
                }
            },
            initData: '',
            initDataUnsafe: { user: this._getMockUser() },
            colorScheme: 'dark',
            themeParams: {
                bg_color: '#0a0a0f',
                text_color: '#ffffff',
                hint_color: '#7c7c8a',
                link_color: '#7c3aed',
                button_color: '#7c3aed',
                button_text_color: '#ffffff',
            },
            MainButton: {
                text: '',
                show: () => {},
                hide: () => {},
                onClick: () => {},
                offClick: () => {},
                setText: function(t) { this.text = t; },
            },
            BackButton: {
                show: () => {},
                hide: () => {},
                onClick: () => {},
                offClick: () => {},
            },
            HapticFeedback: {
                impactOccurred: (style) => console.log('Haptic:', style),
                notificationOccurred: (type) => console.log('Notif:', type),
                selectionChanged: () => {},
            },
            showAlert: (msg) => alert(msg),
            showConfirm: (msg) => confirm(msg),
            showPopup: (params) => alert(params.title + '\n' + params.message),
            openLink: (url) => window.open(url, '_blank'),
            openTelegramLink: (url) => window.open(url, '_blank'),
            sendData: (data) => console.log('Send data:', data),
        };
    }

    _getMockUser() {
        return {
            id: 123456789,
            first_name: 'Test',
            last_name: 'User',
            username: 'testuser',
            language_code: 'uz',
            is_premium: true,
            photo_url: null,
        };
    }

    applyTheme() {
        try {
            const colorScheme = this.tg.colorScheme;
            document.documentElement.setAttribute('data-theme', colorScheme);
        } catch (e) {
            console.warn('Theme apply error:', e);
        }
    }

    _setupMainButton() {
        // MainButton listener keyinroq o'rnatiladi
    }

    _setupBackButton() {
        try {
            this.tg.BackButton.onClick(() => {
                // Default: app orqaga qaytadi
                if (window.app?.router) {
                    window.app.router.back();
                }
            });
        } catch (e) {
            console.warn('BackButton error:', e);
        }
    }

    showBackButton(show = true) {
        try {
            if (show) {
                this.tg.BackButton.show();
            } else {
                this.tg.BackButton.hide();
            }
        } catch (e) {}
    }

    /**
     * Haptic feedback
     */
    haptic(type = 'light') {
        try {
            const styles = {
                light: 'light',
                medium: 'medium',
                heavy: 'heavy',
                success: 'success',
                warning: 'warning',
                error: 'error',
            };
            const style = styles[type] || 'light';

            if (['success', 'warning', 'error'].includes(type)) {
                this.tg.HapticFeedback.notificationOccurred(style);
            } else {
                this.tg.HapticFeedback.impactOccurred(style);
            }
        } catch (e) {}
    }

    /**
     * Main button ni boshqarish
     */
    setMainButton(text, onClick) {
        try {
            this.tg.MainButton.setText(text);
            this.tg.MainButton.onClick(onClick);
            this.tg.MainButton.show();
        } catch (e) {}
    }

    hideMainButton() {
        try {
            this.tg.MainButton.hide();
        } catch (e) {}
    }

    showAlert(message) {
        try {
            this.tg.showAlert(message);
        } catch (e) {
            alert(message);
        }
    }

    showConfirm(message) {
        return new Promise((resolve) => {
            try {
                this.tg.showConfirm(message, resolve);
            } catch (e) {
                resolve(confirm(message));
            }
        });
    }

    openLink(url) {
        try {
            this.tg.openLink(url);
        } catch (e) {
            window.open(url, '_blank');
        }
    }

    sendData(data) {
        try {
            this.tg.sendData(JSON.stringify(data));
        } catch (e) {
            console.warn('Send data error:', e);
        }
    }

    close() {
        try {
            this.tg.close();
        } catch (e) {
            window.close();
        }
    }
}

// Global
window.tgManager = new TelegramManager();
