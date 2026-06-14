/**
 * API Client - backend bilan muloqot
 */

class APIClient {
    constructor(baseURL = null) {
        // WebApp URL dan API URL ni aniqlash
        if (!baseURL) {
            const webappUrl = window.location.origin;
            // Production da alohida domen bo'lishi mumkin
            this.baseURL = webappUrl;
        } else {
            this.baseURL = baseURL;
        }

        this.token = localStorage.getItem('quiz_token') || null;
    }

    /**
     * Authorization header bilan request
     */
    async _request(method, endpoint, body = null, isFormData = false) {
        const url = `${this.baseURL}${endpoint}`;
        const headers = {};

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        let bodyToSend = body;
        if (body && !isFormData) {
            headers['Content-Type'] = 'application/json';
            bodyToSend = JSON.stringify(body);
        }

        try {
            const response = await fetch(url, {
                method,
                headers,
                body: bodyToSend,
            });

            // 401 da login ga qaytish
            if (response.status === 401) {
                this.token = null;
                localStorage.removeItem('quiz_token');
                throw new Error('Avtorizatsiya kerak');
            }

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `HTTP ${response.status}`);
            }

            return data;
        } catch (error) {
            console.error(`API ${method} ${endpoint} error:`, error);
            throw error;
        }
    }

    /**
     * Avtorizatsiya
     */
    async login(initData) {
        try {
            const data = await this._request('POST', '/api/auth/login', {
                initData,
                dev_mode: true,
                telegram_id: window.tgManager?.user?.id || 123456789,
                first_name: window.tgManager?.user?.first_name || 'Test',
                username: window.tgManager?.user?.username || 'testuser',
            });

            this.token = data.token;
            localStorage.setItem('quiz_token', this.token);
            localStorage.setItem('quiz_user', JSON.stringify(data.user));
            return data;
        } catch (e) {
            console.warn('Login failed, using offline mode:', e.message);
            // Offline rejim
            return this._offlineUser();
        }
    }

    _offlineUser() {
        const tgUser = window.tgManager?.user;
        return {
            token: 'offline-token',
            user: {
                id: 0,
                telegram_id: tgUser?.id || 0,
                first_name: tgUser?.first_name || 'User',
                username: tgUser?.username,
                language_code: tgUser?.language_code || 'uz',
                subscription_tier: 'free',
                tests_created: 0,
                tests_taken: 0,
            }
        };
    }

    /**
     * Foydalanuvchi ma'lumotlari
     */
    async getUser() {
        return this._request('GET', '/api/user');
    }

    /**
     * Fayl yuklash
     */
    async uploadFile(file, onProgress = null) {
        return new Promise((resolve, reject) => {
            const formData = new FormData();
            formData.append('file', file);

            const xhr = new XMLHttpRequest();
            const url = `${this.baseURL}/api/upload`;

            xhr.open('POST', url);
            if (this.token) {
                xhr.setRequestHeader('Authorization', `Bearer ${this.token}`);
            }

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable && onProgress) {
                    onProgress(e.loaded / e.total);
                }
            });

            xhr.addEventListener('load', () => {
                try {
                    const data = JSON.parse(xhr.responseText);
                    if (xhr.status >= 200 && xhr.status < 300) {
                        resolve(data);
                    } else {
                        reject(new Error(data.error || 'Upload failed'));
                    }
                } catch (e) {
                    reject(new Error('Parse error'));
                }
            });

            xhr.addEventListener('error', () => reject(new Error('Network error')));
            xhr.send(formData);
        });
    }

    /**
     * Test yaratish
     */
    async generateQuiz(params) {
        return this._request('POST', '/api/generate', params);
    }

    /**
     * Foydalanuvchi testlari
     */
    async getTests(page = 1) {
        return this._request('GET', `/api/tests?page=${page}`);
    }

    /**
     * Bitta test
     */
    async getTest(testId) {
        return this._request('GET', `/api/tests/${testId}`);
    }

    /**
     * Javoblarni yuborish
     */
    async submitTest(testId, answers, timeSpent) {
        return this._request('POST', `/api/tests/${testId}/submit`, {
            answers,
            time_spent: timeSpent,
        });
    }

    /**
     * Test share code
     */
    async shareTest(testId) {
        return this._request('POST', `/api/tests/${testId}/share`);
    }

    /**
     * Leaderboard
     */
    async getLeaderboard() {
        return this._request('GET', '/api/leaderboard');
    }

    /**
     * Trial boshlash
     */
    async startTrial() {
        return this._request('POST', '/api/trial');
    }
}

// Offline rejim uchun localStorage cache
class LocalCache {
    static set(key, value, ttlSeconds = null) {
        const item = {
            value,
            timestamp: Date.now(),
            ttl: ttlSeconds,
        };
        localStorage.setItem(`quiz_cache_${key}`, JSON.stringify(item));
    }

    static get(key) {
        try {
            const raw = localStorage.getItem(`quiz_cache_${key}`);
            if (!raw) return null;

            const item = JSON.parse(raw);
            if (item.ttl && Date.now() - item.timestamp > item.ttl * 1000) {
                localStorage.removeItem(`quiz_cache_${key}`);
                return null;
            }
            return item.value;
        } catch {
            return null;
        }
    }

    static remove(key) {
        localStorage.removeItem(`quiz_cache_${key}`);
    }
}

window.api = new APIClient();
window.LocalCache = LocalCache;
