(function () {
    'use strict';

    const API_BASE =
        window.location.origin && window.location.origin !== 'null'
            ? `${window.location.origin}/api/v1`
            : 'https://nightflow-bot-production.up.railway.app/api/v1';

    const tg = window.Telegram.WebApp;
    tg.expand();
    tg.ready();

    function applyTgTheme() {
        const p = tg.themeParams || {};
        if (p.bg_color) {
            try {
                tg.setHeaderColor(p.bg_color);
                tg.setBackgroundColor(p.bg_color);
            } catch (e) {
                /* ignore */
            }
        } else {
            try {
                tg.setHeaderColor('#1c1c1e');
                tg.setBackgroundColor('#1c1c1e');
            } catch (e) {
                /* ignore */
            }
        }
        const r = document.documentElement;
        if (p.bg_color) {
            r.style.setProperty('--nf-app-bg', p.bg_color);
            r.style.setProperty('--nf-bg', p.bg_color);
        }
        if (p.secondary_bg_color) {
            r.style.setProperty('--nf-surface', p.secondary_bg_color);
            r.style.setProperty('--nf-card', p.secondary_bg_color);
        }
        if (p.text_color) r.style.setProperty('--nf-text', p.text_color);
        if (p.hint_color) r.style.setProperty('--nf-muted', p.hint_color);
        if (p.button_color) {
            r.style.setProperty('--nf-primary', p.button_color);
            r.style.setProperty('--nf-accent', p.button_color);
        }
        if (p.link_color) r.style.setProperty('--nf-link', p.link_color);
    }
    applyTgTheme();
    try {
        tg.onEvent('themeChanged', applyTgTheme);
    } catch (e) {
        /* not available in all runtimes */
    }

    const user = tg.initDataUnsafe?.user;

    const state = {
        screen: 'loading',
        stack: [],
        schedule: null,
        userRow: null,
        onboardingType: 'rotating',
        clockTimer: null,
        summary: {},
        settings: {
            notifAll: true,
            notifCoffee: true,
            notifMeal: true,
            notifLight: true,
            notifSleep: true,
            notifSummary: true,
            transitionReminders: true,
            transitionLeadDays: '3',
        },
        dayOffResume: 'tomorrow',
        dayOffDate: '',
        rotatingDemo: false,
        /** Active row from GET /schedules/rotating when user.shift_type === 'rotating' */
        rotatingPattern: null,
        /** true after "Switch to permanent" until a constant schedule exists (optional UI hint) */
        finishingConstantSetup: false,
        /** set when opening onboarding from settings — shows Back to settings */
        onboardingFromSettings: false,
        /** 1, 3, or 7 — full schedule range (Pro) */
        fullScheduleRange: 1,
        /** After "Adjust in settings" on a suggestion: open the right editor once */
        settingsFocus: null,
        /** Current suggestions list (for deep-link to settings) */
        suggestionItems: null,
    };

    try {
        const _r = localStorage.getItem('nf_full_range');
        if (_r === '1' || _r === '3' || _r === '7') state.fullScheduleRange = parseInt(_r, 10);
    } catch (e) {}

    const $root = document.getElementById('screen-root');
    const $modal = document.getElementById('modal-root');

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getLocale() {
        return 'en';
    }

    /** UI string. Functions in locales are called with extra args. */
    function t(k) {
        const L = window.NF_LOCALES;
        if (!L) return k;
        const loc = getLocale();
        const row = L[loc] || L.en;
        const pick = row && row[k] !== undefined && row[k] !== '' ? row[k] : L.en[k];
        const v = pick !== undefined ? pick : k;
        if (typeof v === 'function') {
            return v.apply(null, Array.prototype.slice.call(arguments, 1));
        }
        return v;
    }

    function syncDocumentLang() {
        try {
            document.documentElement.lang = 'en';
        } catch (e) {
            /* ignore */
        }
    }

    /** English-only app: never use the device locale for date strings (avoids e.g. Russian month names). */
    const NF_DATE_LOCALE = 'en-US';

    function localDateStrNow() {
        return new Date().toISOString().slice(0, 10);
    }
    function eosKey(suffix) {
        return `nf_eos_${suffix}_${localDateStrNow()}`;
    }
    function isEosIgnoredToday() {
        try {
            return localStorage.getItem(eosKey('ignore')) === '1';
        } catch (e) {
            return false;
        }
    }
    function isEosDoneToday() {
        try {
            return localStorage.getItem(eosKey('done')) === '1';
        } catch (e) {
            return false;
        }
    }
    function setEosDoneToday() {
        try {
            localStorage.setItem(eosKey('done'), '1');
        } catch (e) {}
    }
    function setEosIgnoreToday() {
        try {
            localStorage.setItem(eosKey('ignore'), '1');
        } catch (e) {}
    }
    function transCardKey() {
        return `nf_trans_hide_${localDateStrNow()}`;
    }
    function isTransCardHiddenToday() {
        try {
            return localStorage.getItem(transCardKey()) === '1';
        } catch (e) {
            return false;
        }
    }
    function setTransCardHiddenToday() {
        try {
            localStorage.setItem(transCardKey(), '1');
        } catch (e) {}
    }
    function suggestionFingerprint(it) {
        if (!it) return '';
        return [it.title, it.body, it.action].join('\u0001');
    }
    function getIgnoredSuggestionSet() {
        try {
            const a = JSON.parse(localStorage.getItem('nf_sug_ignored') || '[]');
            return new Set(Array.isArray(a) ? a : []);
        } catch (e) {
            return new Set();
        }
    }
    function ignoreSuggestionKey(key) {
        const s = getIgnoredSuggestionSet();
        s.add(key);
        const arr = [...s].slice(-80);
        try {
            localStorage.setItem('nf_sug_ignored', JSON.stringify(arr));
        } catch (e) {}
    }
    function settingsTargetFromApply(apply) {
        if (!apply || !apply.op) return null;
        const op = apply.op;
        if (op === 'extend_sleep') {
            if (isRotatingServer()) {
                const tpl = apply.template === 'day' ? 'day' : 'night';
                return { rotating: true, kind: 'sleep', template: tpl };
            }
            return { rotating: false, kind: 'work' };
        }
        const kind =
            op === 'shift_coffee' ? 'coffee' : op === 'shift_meal' ? 'meal' : op === 'shift_bright' ? 'light' : null;
        if (!kind) return null;
        if (isRotatingServer() && (apply.template === 'night' || apply.template === 'day')) {
            return { rotating: true, shift: apply.template, kind };
        }
        return { rotating: false, kind };
    }
    /** Open the right editor after navigating to Settings (see openSettingsFromSuggestion). */
    function consumeSettingsFocus() {
        const t = state.settingsFocus;
        if (!t) return;
        state.settingsFocus = null;
        setTimeout(() => {
            if (t.rotating) {
                if (t.kind === 'sleep') {
                    openEditRotatingTemplate(t.template === 'day' ? 'day' : 'night');
                    return;
                }
                if (t.shift && (t.kind === 'coffee' || t.kind === 'meal' || t.kind === 'light')) {
                    openEditRotatingWindows(t.shift, t.kind);
                    return;
                }
            } else {
                if (t.kind === 'work') {
                    openEditWork();
                    return;
                }
                if (t.kind === 'coffee') {
                    openEditCoffee();
                    return;
                }
                if (t.kind === 'meal') {
                    openEditMeals();
                    return;
                }
                if (t.kind === 'light') {
                    openEditLight();
                    return;
                }
            }
        }, 0);
    }
    function openSettingsFromSuggestion(apply) {
        const t = settingsTargetFromApply(apply);
        if (t) state.settingsFocus = t;
        go('settings', true);
    }

    function pad2(n) {
        return String(n).padStart(2, '0');
    }

    function timeOptions() {
        const out = [];
        for (let h = 0; h < 24; h++) {
            for (let m = 0; m < 60; m += 5) {
                out.push(`${pad2(h)}:${pad2(m)}`);
            }
        }
        return out;
    }

    const TIME_OPTS = timeOptions();

    function snapMinute(m) {
        return Math.min(55, Math.max(0, Math.round(m / 5) * 5));
    }

    function parseTimeParts(s) {
        if (!s || typeof s !== 'string') return { h: 22, m: 0 };
        const p = s.trim().split(':');
        const hh = Math.min(23, Math.max(0, parseInt(p[0], 10) || 0));
        const rawM = parseInt(p[1], 10);
        const mm = Number.isNaN(rawM) ? 0 : snapMinute(Math.min(59, Math.max(0, rawM)));
        return { h: hh, m: mm };
    }

    function timePickerField(name, value, id) {
        const v0 = (value && String(value).slice(0, 5)) || '22:00';
        const { h, m } = parseTimeParts(v0);
        const v = `${pad2(h)}:${pad2(m)}`;
        const label = name || t('stTimeL');
        return `<div class="nf-time-field">
            <input type="hidden" id="${id}" value="${v}" />
            <button type="button" class="nf-time-btn" data-nf-time-id="${id}" aria-label="${escapeHtml(
            String(label)
        )}">
                <span class="nf-time-btn-main">${escapeHtml(v)}</span>
                <span class="nf-time-btn-chev" aria-hidden="true">▾</span>
            </button>
        </div>`;
    }

    function selectTimeHtml(name, value, id) {
        return timePickerField(name, value, id);
    }

    function dismissTimePickerLayer(layer) {
        if (layer && layer.parentNode) {
            layer.remove();
        }
        const hasParentModal = $modal.querySelector('.modal-backdrop, .modal-sheet');
        const hasTimeLayer = $modal.querySelector('.nf-tp-layer');
        if (!hasParentModal && !hasTimeLayer) {
            $modal.classList.remove('open');
            $modal.setAttribute('aria-hidden', 'true');
        }
    }

    function openTimePickerModal(currentValue, onSet) {
        const p = parseTimeParts(currentValue);
        let selH = p.h;
        let selM = p.m;
        const minuteOpts = Array.from({ length: 12 }, (_, i) => i * 5);

        const hBtns = Array.from({ length: 24 }, (_, hr) => {
            const a = hr === selH ? ' is-active' : '';
            return `<button type="button" class="nf-tp-opt${a}" data-nf-h="${hr}">${pad2(hr)}</button>`;
        }).join('');
        const mBtns = minuteOpts
            .map((mm) => {
                const a = mm === selM ? ' is-active' : '';
                return `<button type="button" class="nf-tp-opt${a}" data-nf-m="${mm}">:${pad2(mm)}</button>`;
            })
            .join('');

        $modal.querySelectorAll('.nf-tp-layer').forEach((el) => el.remove());

        const inner = `<div class="nf-tp" data-nf-tp-root>
            <h3 class="nf-tp-title">${escapeHtml(t('tpTitle'))}</h3>
            <p class="nf-tp-sub">${escapeHtml(t('tpSub'))}</p>
            <div class="nf-tp-cols">
                <div class="nf-tp-col">
                    <div class="nf-tp-lab">${escapeHtml(t('tpH'))}</div>
                    <div class="nf-tp-scroll">${hBtns}</div>
                </div>
                <div class="nf-tp-mid">:</div>
                <div class="nf-tp-col">
                    <div class="nf-tp-lab">${escapeHtml(t('tpM'))}</div>
                    <div class="nf-tp-scroll" data-nf-tp-mcol="1">${mBtns}</div>
                </div>
            </div>
            <div class="nf-tp-preview" data-nf-tp-preview>${pad2(selH)}:${pad2(selM)}</div>
            <div class="nf-tp-actions">
                <button type="button" class="nf-cta nf-cta-secondary" data-nf-tp-cancel>${escapeHtml(
                    t('mdlCan')
                )}</button>
                <button type="button" class="nf-cta" data-nf-tp-ok>${escapeHtml(t('tpApply'))}</button>
            </div>
        </div>`;

        const layer = document.createElement('div');
        layer.className = 'nf-tp-layer';
        layer.setAttribute('role', 'dialog');
        layer.setAttribute('aria-modal', 'true');
        layer.innerHTML = `<div class="nf-tp-backdrop" data-nf-tp-backdrop></div>
            <div class="nf-tp-surface">${inner}</div>`;

        $modal.classList.add('open');
        $modal.setAttribute('aria-hidden', 'false');
        $modal.appendChild(layer);

        const box = layer.querySelector('[data-nf-tp-root]');
        if (!box) return;
        const preview = box.querySelector('[data-nf-tp-preview]');
        const okBtn = layer.querySelector('[data-nf-tp-ok]');
        const cancelBtn = layer.querySelector('[data-nf-tp-cancel]');
        const back = layer.querySelector('[data-nf-tp-backdrop]');
        if (!okBtn || !cancelBtn) return;

        box.querySelectorAll('.nf-tp-scroll .is-active').forEach((el) => {
            try {
                el.scrollIntoView({ block: 'center' });
            } catch (e) {
                /* ignore */
            }
        });

        function markActive() {
            box.querySelectorAll('[data-nf-h]').forEach((b) => {
                b.classList.toggle('is-active', parseInt(b.getAttribute('data-nf-h'), 10) === selH);
            });
            box.querySelectorAll('[data-nf-m]').forEach((b) => {
                b.classList.toggle('is-active', parseInt(b.getAttribute('data-nf-m'), 10) === selM);
            });
            if (preview) preview.textContent = `${pad2(selH)}:${pad2(selM)}`;
        }

        box.addEventListener('click', (e) => {
            const hb = e.target.closest('[data-nf-h]');
            const mb = e.target.closest('[data-nf-m]');
            if (hb) {
                selH = parseInt(hb.getAttribute('data-nf-h'), 10);
                markActive();
            }
            if (mb) {
                selM = parseInt(mb.getAttribute('data-nf-m'), 10);
                markActive();
            }
        });

        const finish = () => {
            onSet(`${pad2(selH)}:${pad2(selM)}`);
            dismissTimePickerLayer(layer);
        };
        const cancel = () => dismissTimePickerLayer(layer);

        okBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            finish();
        });
        cancelBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            cancel();
        });
        if (back) {
            back.addEventListener('click', (e) => {
                e.preventDefault();
                cancel();
            });
        }
    }

    function initTimePickerButtons(root) {
        if (!root) return;
        root.querySelectorAll('[data-nf-time-id]').forEach((btn) => {
            if (btn.getAttribute('data-nf-tp-bound') === '1') return;
            btn.setAttribute('data-nf-tp-bound', '1');
            btn.addEventListener('click', () => {
                const id = btn.getAttribute('data-nf-time-id');
                const input = document.getElementById(id);
                if (!input) return;
                openTimePickerModal(input.value, (next) => {
                    input.value = next;
                    const main = btn.querySelector('.nf-time-btn-main');
                    if (main) main.textContent = next;
                });
            });
        });
    }

    function nowClockStr() {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function formatLongDate(d) {
        return d.toLocaleDateString(NF_DATE_LOCALE, {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });
    }

    function formatRangeDate(d1, d2) {
        const a = d1.toLocaleDateString(NF_DATE_LOCALE, { month: 'short', day: 'numeric' });
        const b = d2.toLocaleDateString(NF_DATE_LOCALE, { month: 'short', day: 'numeric', year: 'numeric' });
        return `${a} – ${b}`;
    }

    function applyUserSettingsFromUserRow(row) {
        if (!row) return;
        let prefs = row.notification_prefs;
        if (typeof prefs === 'string') {
            try {
                prefs = JSON.parse(prefs);
            } catch (e) {
                prefs = {};
            }
        }
        if (!prefs || typeof prefs !== 'object') prefs = {};
        const def = (v, d) => (v === undefined || v === null ? d : !!v);
        state.settings.notifAll = row.notification_enabled !== false;
        state.settings.notifCoffee = def(prefs.notifCoffee, true);
        state.settings.notifMeal = def(prefs.notifMeal, true);
        state.settings.notifLight = def(prefs.notifLight, true);
        state.settings.notifSleep = def(prefs.notifSleep, true);
        state.settings.notifSummary = def(prefs.notifSummary, true);
        state.settings.transitionReminders = def(prefs.transitionReminders, true);
        const ld = prefs.transitionLeadDays ?? prefs.transition_lead_days;
        state.settings.transitionLeadDays = ld != null && ld !== '' ? String(ld) : '3';
    }

    async function patchUserMe(body) {
        try {
            const res = await api(`/users/me?telegram_id=${user.id}`, {
                method: 'PATCH',
                json: body,
            });
            if (!res.ok) return null;
            return await res.json();
        } catch (e) {
            console.warn('patchUserMe', e);
            return null;
        }
    }

    function applyConstantRowToState(row) {
        if (!row) return;
        if (!state.schedule) state.schedule = {};
        for (const k of ['work_start', 'work_end', 'sleep_start', 'sleep_end']) {
            if (row[k] !== undefined) state.schedule[k] = row[k];
        }
        for (const f of ['coffee_windows', 'meal_windows', 'brightness_windows']) {
            if (row[f] === undefined) continue;
            let v = row[f];
            if (typeof v === 'string') {
                try {
                    v = JSON.parse(v);
                } catch (e) {
                    v = [];
                }
            }
            state.schedule[f] = v;
        }
    }

    async function reloadScheduleFromApi() {
        try {
            let res = await api(`/schedules/daily/today?telegram_id=${user.id}`);
            if (res.status === 404) {
                res = await api(`/schedules/full?telegram_id=${user.id}`);
            }
            if (!res.ok) return false;
            state.schedule = await res.json();
            for (const f of ['coffee_windows', 'meal_windows', 'brightness_windows']) {
                if (typeof state.schedule[f] === 'string') {
                    try {
                        state.schedule[f] = JSON.parse(state.schedule[f]);
                    } catch (e) {
                        state.schedule[f] = [];
                    }
                }
            }
            return true;
        } catch (e) {
            console.warn('reloadScheduleFromApi', e);
            return false;
        }
    }

    async function api(path, options = {}) {
        const headers = {
            ...(options.headers || {}),
        };
        if (options.json != null) {
            headers['Content-Type'] = 'application/json';
        }
        if (tg.initData) {
            headers['Authorization'] = `Telegram ${tg.initData}`;
        }
        const res = await fetch(`${API_BASE}${path}`, {
            ...options,
            headers,
            body: options.json != null ? JSON.stringify(options.json) : options.body,
        });
        return res;
    }

    async function ensureUser() {
        if (!user) return;
        try {
            await api('/users/me', {
                method: 'POST',
                json: {
                    telegram_id: user.id,
                    username: user.username || '',
                    first_name: user.first_name || '',
                },
            });
        } catch (e) {
            console.warn('ensureUser', e);
        }
    }

    function isRotatingUi() {
        return state.userRow?.shift_type === 'rotating' || state.rotatingDemo === true;
    }

    function isRotatingServer() {
        return state.userRow?.shift_type === 'rotating';
    }

    function goToScheduleTypePicker() {
        state.onboardingFromSettings = true;
        const from = state.screen || 'dashboard';
        go('onboarding', from === 'onboarding' ? false : true);
    }

    function rotatingShiftsObj() {
        const sh = state.rotatingPattern && state.rotatingPattern.shifts;
        return sh && typeof sh === 'object' ? sh : {};
    }

    function patternHasDayWork() {
        const s = rotatingShiftsObj();
        const id = s.pattern_id || 'pitman_2_2_3';
        if (id === 'pat_4n4o') return false;
        if (id === 'block_rotation') {
            return (Number(s.block_days) || 0) > 0;
        }
        return true;
    }

    function parseTimeToMinutes(t) {
        if (!t || typeof t !== 'string') return 0;
        const [h, m] = t.split(':').map(Number);
        return (h || 0) * 60 + (m || 0);
    }

    /**
     * Work and sleep as half-open [start, end) minute ranges on a 24h loop.
     * Returns true if they share any time (e.g. work 0:00–8:00 vs sleep 6:00–14:00).
     */
    function timeRangeToSegments(startStr, endStr) {
        const a = parseTimeToMinutes(String(startStr || '00:00').slice(0, 5));
        const b = parseTimeToMinutes(String(endStr || '00:00').slice(0, 5));
        if (b > a) return [[a, b]];
        if (b < a) return [[a, 1440], [0, b]];
        return [[0, 1440]];
    }

    function segmentsOverlapHalfOpen(segmentsA, segmentsB) {
        for (const [a0, a1] of segmentsA) {
            for (const [b0, b1] of segmentsB) {
                if (a0 < b1 && b0 < a1) return true;
            }
        }
        return false;
    }

    /** @returns {string|null} User-facing error, or null if ok */
    function workSleepOverlapError(workStart, workEnd, sleepStart, sleepEnd) {
        const w = timeRangeToSegments(workStart, workEnd);
        const s = timeRangeToSegments(sleepStart, sleepEnd);
        if (segmentsOverlapHalfOpen(w, s)) {
            return t('wsOverlap');
        }
        return null;
    }

    function minutesUntilShiftEnd(workStart, workEnd) {
        if (!workStart || !workEnd) return -1;
        const now = new Date();
        const cur = now.getHours() * 60 + now.getMinutes();
        const ws = parseTimeToMinutes(workStart);
        const we = parseTimeToMinutes(workEnd);
        const overnight = we <= ws;

        let end = new Date(now);
        end.setSeconds(0, 0);
        end.setHours(Math.floor(we / 60), we % 60, 0, 0);

        if (overnight) {
            if (cur >= ws) {
                end.setDate(end.getDate() + 1);
            } else if (cur < we) {
                /* end is today */
            } else {
                return -1;
            }
        } else {
            if (cur >= we) return -1;
        }

        return (end - now) / 60000;
    }

    function shouldShowReportCard(workStart, workEnd) {
        const m = minutesUntilShiftEnd(workStart, workEnd);
        return m >= 0 && m <= 120;
    }

    /**
     * Next local Date when wall-clock time `HH:MM` is strictly after `fromDate`.
     */
    function nextOccurrenceAfterNow(hhmm, fromDate) {
        if (!hhmm) return null;
        const s = String(hhmm).slice(0, 5);
        const p = s.split(':');
        const H = Number(p[0]);
        const M = Number(p[1] || 0);
        if (Number.isNaN(H)) return null;
        const t = new Date(fromDate);
        t.setSeconds(0, 0);
        t.setMilliseconds(0);
        t.setHours(H, M, 0, 0);
        if (t.getTime() <= fromDate.getTime()) {
            t.setDate(t.getDate() + 1);
        }
        return t;
    }

    function getNextCoreEvent(sched) {
        if (!sched || !sched.work_start) {
            return {
                line: '⏰ ' + t('evAddW'),
                sub: t('evAddWS'),
                icon: '⏰',
                kindClass: 'other',
                kindLabel: t('evSetup'),
            };
        }
        const now = new Date();
        const candidates = [];
        const add = (time, key, icon, kc) => {
            if (!time) return;
            const at = nextOccurrenceAfterNow(time, now);
            if (at) {
                candidates.push({
                    at,
                    shortLabel: t(key),
                    icon,
                    time: formatTime(time),
                    kc: kc || 'work',
                });
            }
        };
        add(sched.work_start, 'evWs', '🌙', 'work');
        add(sched.work_end, 'evWe', '🏁', 'work');
        add(sched.sleep_start, 'evBed', '😴', 'sleep');
        add(sched.sleep_end, 'evWake', '☀️', 'sleep');
        if (!candidates.length) {
            return {
                line: '⏰ ' + t('evNSch'),
                sub: '—',
                icon: '⏰',
                kindClass: 'other',
                kindLabel: t('schedPage'),
            };
        }
        candidates.sort((a, b) => a.at - b.at);
        const next = candidates[0];
        const bestDelta = (next.at - now) / 60000;
        const h = Math.floor(Math.max(0, bestDelta) / 60);
        const mm = Math.round(Math.max(0, bestDelta) % 60);
        const shortLabel = (next.shortLabel || '').split('.')[0];
        const kl = next.kc === 'sleep' ? t('sleep') : t('work');
        return {
            line: `${kl} — ${next.icon} ${shortLabel} · ${next.time}`,
            sub: t('inHM', h, mm),
            icon: next.icon,
            kindClass: next.kc,
            kindLabel: kl,
        };
    }

    /** Order times for a night/overnight shift: after-midnight follows PM same \"day\". */
    function timeSortKeyForSchedule(timeStr, schedule) {
        const m = parseTimeToMinutes(timeStr);
        if (!schedule || schedule.work_start == null || schedule.work_end == null) {
            return m;
        }
        const ws = parseTimeToMinutes(schedule.work_start);
        const we = parseTimeToMinutes(schedule.work_end);
        if (we >= ws) {
            return m;
        }
        if (m >= ws) {
            return m;
        }
        if (m <= we) {
            return m + 24 * 60;
        }
        return m;
    }

    function collectEvents(schedule) {
        const ev = [];
        const seen = new Set();
        const clean = (msg) =>
            String(msg || '')
                .replace(/\s+/g, ' ')
                .trim();
        const push = (time, label, icon, kind) => {
            if (!time) return;
            const timeStr = formatTime(time);
            const lab = clean(label) || t('evTE');
            const k = `${timeStr}|${icon}|${lab}`;
            if (seen.has(k)) return;
            seen.add(k);
            const m = parseTimeToMinutes(timeStr);
            ev.push({
                time: timeStr,
                label: lab,
                icon,
                kind: kind || 'other',
                m,
                sort: timeSortKeyForSchedule(timeStr, schedule),
            });
        };

        if (schedule.work_start) {
            push(schedule.work_start, t('evWs') + ' · ' + t('work'), '🌙', 'work_start');
        }
        if (schedule.work_end) {
            push(schedule.work_end, t('evWe') + ' · ' + t('work'), '🏁', 'work_end');
        }
        if (schedule.sleep_start) {
            push(schedule.sleep_start, t('evBed') + ' · ' + t('sleep'), '😴', 'sleep_start');
        }
        if (schedule.sleep_end) {
            push(schedule.sleep_end, t('evWake') + ' · ' + t('sleep'), '☀️', 'sleep_end');
        }
        (schedule.meal_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || t('stMeal'), '🍽️', 'meal');
        });
        (schedule.coffee_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || t('stCoff'), '☕', 'coffee');
        });
        (schedule.brightness_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || t('stLight'), '💡', 'light');
        });

        ev.sort((a, b) => a.sort - b.sort);
        return ev;
    }

    function isHabitTimelineKind(k) {
        return k === 'coffee' || k === 'meal' || k === 'light' || k === 'other';
    }

    /**
     * Group events for the Plan timeline: same sort keys as collectEvents.
     * @returns {'shift'|'wind'|'rest'|'rem'}
     */
    function timelineEventPhase(e, sched) {
        const k = e.kind;
        if (k === 'work_start' || k === 'work_end') return 'shift';
        if (k === 'sleep_start' || k === 'sleep_end') return 'rest';
        if (isHabitTimelineKind(k)) {
            if (sched && sched.work_start && sched.work_end) {
                const wsK = timeSortKeyForSchedule(formatTime(sched.work_start), sched);
                const weK = timeSortKeyForSchedule(formatTime(sched.work_end), sched);
                if (e.sort >= wsK && e.sort <= weK) return 'shift';
            }
            if (sched && sched.work_end && sched.sleep_start) {
                const weK = timeSortKeyForSchedule(formatTime(sched.work_end), sched);
                const ssK = timeSortKeyForSchedule(formatTime(sched.sleep_start), sched);
                if (e.sort > weK && e.sort < ssK) return 'wind';
            }
            return 'rem';
        }
        return 'rem';
    }

    function timelinePhaseLabel(ph) {
        if (ph === 'shift') return t('tlPhaseShift');
        if (ph === 'wind') return t('tlPhaseWind');
        if (ph === 'rest') return t('tlPhaseRest');
        return t('tlPhaseRem');
    }

    function timelinePhaseIcon(ph) {
        if (ph === 'shift') return '💼';
        if (ph === 'wind') return '✨';
        if (ph === 'rest') return '😴';
        return '⏰';
    }

    function hasProEntitlement() {
        return !!(state.userRow && state.userRow.has_pro_entitlement);
    }

    function hasActivePaidPro() {
        return !!(state.userRow && state.userRow.active_paid_pro);
    }

    /** Pro period end for UI (date only, no time of day). */
    function formatProExpiresUser() {
        const s = state.userRow && state.userRow.pro_expires_at;
        if (!s) return '';
        try {
            const d = new Date(s);
            if (Number.isNaN(d.getTime())) return '';
            return d.toLocaleDateString(NF_DATE_LOCALE, { year: 'numeric', month: 'short', day: 'numeric' });
        } catch (e) {
            return '';
        }
    }

    function eventKindToCategory(kind) {
        if (kind === 'work_start' || kind === 'work_end') return 'work';
        if (kind === 'sleep_start' || kind === 'sleep_end') return 'sleep';
        if (kind === 'meal') return 'meal';
        if (kind === 'coffee') return 'coffee';
        if (kind === 'light') return 'light';
        return 'other';
    }

    function eventTypeTag(kind) {
        if (kind === 'work_start' || kind === 'work_end') return t('evTW');
        if (kind === 'sleep_start' || kind === 'sleep_end') return t('evTS');
        if (kind === 'meal') return t('evTM');
        if (kind === 'coffee') return t('evTC');
        if (kind === 'light') return t('evTL');
        return t('evTE');
    }

    function normalizeScheduleFields(row) {
        if (!row) return null;
        const o = { ...row };
        for (const f of ['coffee_windows', 'meal_windows', 'brightness_windows']) {
            if (typeof o[f] === 'string') {
                try {
                    o[f] = JSON.parse(o[f]);
                } catch (e) {
                    o[f] = [];
                }
            }
            if (!Array.isArray(o[f])) o[f] = [];
        }
        return o;
    }

    function getNextEvent(schedule) {
        if (!hasProEntitlement()) {
            return getNextCoreEvent(schedule);
        }
        const raw = collectEvents(schedule);
        if (!raw.length) {
            return {
                line: '⏰ ' + t('evNRem'),
                sub: t('evAddT'),
                icon: '⏰',
                kindClass: 'other',
                kindLabel: t('evRem'),
            };
        }
        const now = new Date();
        const cur = now.getHours() * 60 + now.getMinutes();
        let best = null;
        let bestDelta = Infinity;
        for (const e of raw) {
            let delta = e.m - cur;
            if (delta <= 0) delta += 24 * 60;
            if (delta > 0 && delta < bestDelta) {
                bestDelta = delta;
                best = e;
            }
        }
        const next = best || raw[0];
        const h = Math.floor(bestDelta / 60);
        const m = Math.round(bestDelta % 60);
        const shortLabel = (next.label || '').split('.')[0];
        const cat = eventKindToCategory(next.kind);
        const kLabel =
            cat === 'work'
                ? t('work')
                : cat === 'sleep'
                  ? t('sleep')
                  : cat === 'meal'
                    ? t('stMeal')
                    : cat === 'coffee'
                      ? t('stCoff')
                      : cat === 'light'
                        ? t('stLight')
                        : t('evTE');
        return {
            line: `${kLabel} — ${next.icon} ${shortLabel} · ${next.time}`,
            sub: t('inHM', h, m),
            icon: next.icon,
            kindClass: cat,
            kindLabel: kLabel,
        };
    }

    function shiftTitle(st) {
        if (st === 'night') return t('shiftNight');
        if (st === 'day') return t('shiftDay');
        if (st === 'evening') return t('shiftEve');
        return t('shiftDef');
    }

    function go(screen, pushStack) {
        const proOnly = ['full', 'suggestions', 'weekly', 'summary', 'transition'];
        if (proOnly.includes(screen) && !hasProEntitlement()) {
            tg.showAlert(t('proGateGo'));
            return;
        }
        if (pushStack) state.stack.push(state.screen);
        state.screen = screen;
        render();
    }

    function back() {
        const prev = state.stack.pop();
        if (prev) {
            state.screen = prev;
            render();
            return;
        }
        if (state.screen !== 'dashboard' && state.schedule) {
            state.screen = 'dashboard';
            render();
        }
    }

    /** Main tab pages (bottom bar). Does not use navigation stack. */
    const MAIN_TAB_SCREENS = new Set(['dashboard', 'full', 'weekly', 'suggestions', 'settings']);

    function goMainTab(screen) {
        if (!MAIN_TAB_SCREENS.has(screen)) return;
        if (['full', 'weekly', 'suggestions'].includes(screen) && !hasProEntitlement()) {
            tg.showAlert(t('proGate'));
            return;
        }
        state.stack = [];
        state.screen = screen;
        render();
    }

    function getMainTabBarHtml() {
        const s = state.screen;
        const mk = (screen, shortLabel, icon) => {
            const active = s === screen;
            return `<button type="button" class="nf-tab${active ? ' is-active' : ''}" data-main-tab="${screen}" aria-label="${escapeHtml(
                shortLabel
            )}" aria-current="${active ? 'true' : 'false'}">
                <span class="nf-tab-ico" aria-hidden="true">${icon}</span>
                <span class="nf-tab-lbl">${escapeHtml(shortLabel)}</span>
            </button>`;
        };
        if (hasProEntitlement()) {
            return `<nav class="nf-main-tabbar" role="tablist" aria-label="${escapeHtml(t('mainNav'))}">
                ${mk('dashboard', t('tabHome'), '🌙')}
                ${mk('full', t('tabSchedule'), '📅')}
                ${mk('weekly', t('tabWeek'), '📊')}
                ${mk('suggestions', t('tabIdeas'), '💡')}
                ${mk('settings', t('tabSettings'), '⚙️')}
            </nav>`;
        }
        return `<nav class="nf-main-tabbar nf-main-tabbar--free" role="tablist" aria-label="${escapeHtml(t('mainNav'))}">
            ${mk('dashboard', t('tabHome'), '🌙')}
            ${mk('settings', t('tabSettings'), '⚙️')}
        </nav>`;
    }

    function bindMainTabBar() {
        $root.querySelectorAll('[data-main-tab]').forEach((b) => {
            b.addEventListener('click', () => {
                goMainTab(b.getAttribute('data-main-tab'));
            });
        });
    }

    /** Top bar for tabbed screens: back only if something is on the stack (e.g. deep-linked from Ideas). */
    function topbarMainTabPage(title) {
        const hasBack = state.stack && state.stack.length > 0;
        if (hasBack) {
            return `<div class="nf-topbar"><button type="button" class="nf-back" id="mtb-back">←</button><h1>${escapeHtml(
                title
            )}</h1><span></span></div>`;
        }
        return `<div class="nf-topbar"><span class="nf-topbar-ghost" aria-hidden="true"></span><h1>${escapeHtml(
            title
        )}</h1><span></span></div>`;
    }

    function wireMainTabTopbar() {
        const b = document.getElementById('mtb-back');
        if (b) b.onclick = back;
    }

    async function openProInvoice() {
        if (hasActivePaidPro()) {
            tg.showAlert(
                `${t('proHasSub')} ${t('stProUntil')} ${formatProExpiresUser() || '—'}.`
            );
            return;
        }
        try {
            const res = await api('/subscription/invoice-link', { method: 'POST', json: {} });
            const data = await res.json().catch(() => ({}));
            if (res.status === 409) {
                tg.showAlert(data.error || t('proHasSub'));
                if (data.pro_expires_at && state.userRow) {
                    state.userRow = {
                        ...state.userRow,
                        pro_expires_at: data.pro_expires_at,
                        active_paid_pro: true,
                    };
                }
                render();
                return;
            }
            if (!res.ok) throw new Error('x');
            const url = data.url;
            if (!url) throw new Error('x');
            if (typeof tg.openInvoice === 'function') {
                tg.openInvoice(url, (st) => {
                    if (st === 'paid') {
                        loadUserAndSchedule();
                        tg.showAlert(t('proWelcome'));
                    }
                });
            } else {
                tg.openLink(url);
            }
        } catch (e) {
            console.warn(e);
            tg.showAlert(t('proOpenBot'));
        }
    }

    function openModal(html, opts) {
        opts = opts || {};
        const sheetClass = opts.sheetClass ? ` ${opts.sheetClass}` : '';
        $modal.innerHTML = `
            <div class="modal-backdrop" data-close="1"></div>
            <div class="modal-sheet${sheetClass}">${html}</div>`;
        $modal.classList.add('open');
        $modal.setAttribute('aria-hidden', 'false');
        if (opts.closeOnBackdrop !== false) {
            $modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
        }
        initTimePickerButtons($modal);
    }

    function closeModal() {
        $modal.classList.remove('open');
        $modal.setAttribute('aria-hidden', 'true');
        $modal.innerHTML = '';
    }

    function renderLoading() {
        $root.innerHTML = `<div class="nf-loading">${escapeHtml(t('loading'))}</div>`;
    }

    function renderOnboarding() {
        const type = state.onboardingType || 'rotating';
        const topFromSettings = state.onboardingFromSettings
            ? `<div class="nf-topbar" style="margin:0 0 12px;">
                <button type="button" class="nf-back" id="onb-back">← ${escapeHtml(t('back'))}</button>
                <h1 class="nf-onb-top-title">${escapeHtml(t('obChSch'))}</h1>
                <span></span>
            </div>`
            : '';
        $root.innerHTML = `
            <div class="nf-onb">
                <div class="nf-onb-glow" aria-hidden="true"></div>
                ${topFromSettings}
                <div class="nf-onb-hero">
                    <div class="nf-onb-moon" aria-hidden="true">🌙</div>
                    <h1 class="nf-onb-title">${escapeHtml(t('obBrand'))}</h1>
                    <p class="nf-onb-tagline">${escapeHtml(t('obTag'))}</p>
                </div>
                <p class="nf-onb-pick">${escapeHtml(t('obQ'))}</p>
                <div class="nf-select-card nf-onb-card" role="radiogroup" aria-label="${escapeHtml(t('stSchType'))}">
                    <div class="nf-onb-choices">
                        <label class="nf-choice-tile">
                            <input type="radio" name="stype" value="rotating" ${
                                type === 'rotating' ? 'checked' : ''
                            } />
                            <span class="nf-choice-ico" aria-hidden="true">🔁</span>
                            <div class="nf-choice-text">
                                <span class="nf-choice-title">${escapeHtml(t('obRot'))}</span>
                                <span class="nf-choice-sub">${escapeHtml(t('obRS'))}</span>
                            </div>
                        </label>
                        <label class="nf-choice-tile">
                            <input type="radio" name="stype" value="constant" ${
                                type === 'constant' ? 'checked' : ''
                            } />
                            <span class="nf-choice-ico" aria-hidden="true">⏱</span>
                            <div class="nf-choice-text">
                                <span class="nf-choice-title">${escapeHtml(t('obP'))}</span>
                                <span class="nf-choice-sub">${escapeHtml(t('obPS'))}</span>
                            </div>
                        </label>
                    </div>
                </div>
                <button type="button" class="nf-cta nf-onb-cta" id="btn-onb-continue">${escapeHtml(t('obCont'))}</button>
            </div>`;
        const bback = document.getElementById('onb-back');
        if (bback) {
            bback.onclick = () => {
                state.onboardingFromSettings = false;
                if (state.stack && state.stack.length) back();
                else go('settings', false);
            };
        }
        document.getElementById('btn-onb-continue').onclick = () => {
            const r = document.querySelector('input[name="stype"]:checked');
            state.onboardingType = r ? r.value : 'rotating';
            const fromSet = state.onboardingFromSettings;
            state.onboardingFromSettings = false;
            go(state.onboardingType === 'constant' ? 'setup_perm' : 'setup_rot', fromSet);
        };
    }

    function renderSetupPermanent() {
        const hint = state.finishingConstantSetup
            ? `<p class="nf-onb-hint">${escapeHtml(t('spH1'))}</p>`
            : `<div class="nf-setup-perm-hero">
                    <div class="nf-setup-perm-hero-ico" aria-hidden="true">⏱</div>
                    <div class="nf-setup-perm-hero-copy">
                        <h2 class="nf-setup-perm-hero-title">${escapeHtml(t('spH2'))}</h2>
                        <p class="nf-setup-perm-hero-sub">${escapeHtml(t('spH2s'))}</p>
                    </div>
                </div>`;
        $root.innerHTML = `
            <div class="nf-screen nf-setup-perm">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btn-sp-back">← ${escapeHtml(t('back'))}</button>
                    <h1>${escapeHtml(t('spT'))}</h1>
                    <span class="nf-clock">${escapeHtml(nowClockStr())}</span>
                </div>
                ${hint}
                <p class="nf-field-label nf-field-label--loose">${escapeHtml(t('stWS'))}</p>
                <p class="nf-muted nf-rot-pick-hint" style="margin-top:0;">${escapeHtml(t('spV'))}</p>
                <div class="nf-rot-tpl-stack nf-setup-perm-stack">
                    <div class="nf-rot-tpl-card nf-rot-tpl-card--night">
                        <div class="nf-rot-tpl-card__head">${escapeHtml(t('work'))}</div>
                        <p class="nf-rot-tpl-card__note">${escapeHtml(t('sWN'))}</p>
                        <div class="nf-rot-tpl-in">
                            <div class="nf-row"><span class="nf-rot-tpl-lab">${escapeHtml(t('sWS'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                                '',
                                '22:00',
                                'ws'
                            )}</span></div>
                            <div class="nf-row" style="margin-top:10px;"><span class="nf-rot-tpl-lab">${escapeHtml(
                                t('sWE')
                            )}</span><span class="nf-rot-tpl-pair">${selectTimeHtml('', '06:00', 'we')}</span></div>
                        </div>
                    </div>
                    <div class="nf-rot-tpl-card nf-rot-tpl-card--perm-sleep">
                        <div class="nf-rot-tpl-card__head">${escapeHtml(t('sleep'))}</div>
                        <p class="nf-rot-tpl-card__note">${escapeHtml(t('sSN'))}</p>
                        <div class="nf-rot-tpl-in">
                            <div class="nf-row"><span class="nf-rot-tpl-lab">${escapeHtml(t('sSS'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                                '',
                                '08:00',
                                'ss'
                            )}</span></div>
                            <div class="nf-row" style="margin-top:10px;"><span class="nf-rot-tpl-lab">${escapeHtml(
                                t('sSE')
                            )}</span><span class="nf-rot-tpl-pair">${selectTimeHtml('', '16:00', 'se')}</span></div>
                        </div>
                    </div>
                </div>
                <p class="nf-hint-validate">${escapeHtml(t('spV'))}</p>
                <button type="button" class="nf-cta" id="btn-create-const">${escapeHtml(t('spCr'))}</button>
                <p class="nf-sub nf-center" style="margin-top:4px;">${escapeHtml(t('spSF'))}</p>
            </div>`;
        document.getElementById('btn-sp-back').onclick = () => {
            state.finishingConstantSetup = false;
            if (state.stack && state.stack.length) back();
            else go('onboarding', false);
        };
        initTimePickerButtons($root);
        document.getElementById('btn-create-const').onclick = async () => {
            const ws = document.getElementById('ws').value;
            const we = document.getElementById('we').value;
            const ss = document.getElementById('ss').value;
            const se = document.getElementById('se').value;
            const overlap = workSleepOverlapError(ws, we, ss, se);
            if (overlap) {
                tg.showAlert(overlap);
                return;
            }
            renderLoading();
            try {
                await api('/users/me', {
                    method: 'POST',
                    json: {
                        telegram_id: user.id,
                        username: user.username || '',
                        first_name: user.first_name || '',
                        shift_type: 'constant',
                    },
                });
                const res = await api(
                    `/schedules/constant?telegram_id=${user.id}`,
                    {
                        method: 'POST',
                        json: {
                            work_start: ws,
                            work_end: we,
                            sleep_start: ss,
                            sleep_end: se,
                        },
                    }
                );
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    $root.innerHTML = `<div class="nf-error">${escapeHtml(
                        err.error || t('saveErrHtml')
                    )}</div>`;
                    return;
                }
                state.finishingConstantSetup = false;
                state.rotatingDemo = false;
                state.rotatingPattern = null;
                try {
                    localStorage.removeItem('nightflow_rotating_demo');
                } catch (e) {}
                await loadUserAndSchedule();
            } catch (e) {
                console.error(e);
                $root.innerHTML = `<div class="nf-error">${escapeHtml(t('netErrHtml'))}</div>`;
            }
        };
    }

    const PATTERN_PRESET_DEFS = [
        { value: 'pitman_2_2_3' },
        { value: 'block_rotation' },
        { value: 'pat_4n4o4d4o' },
        { value: 'pat_4n4o' },
    ];

    function patternPresetMeta(value) {
        const v = value == null ? '' : String(value);
        if (v === 'pitman_2_2_3') {
            return { value: v, icon: '🔀', title: t('patPitT'), sub: t('patPitS'), days: t('patPitD') };
        }
        if (v === 'block_rotation') {
            return { value: v, icon: '⬛', title: t('patBlkT'), sub: t('patBlkS'), days: t('patBlkD') };
        }
        if (v === 'pat_4n4o4d4o') {
            return { value: v, icon: '🔁', title: t('patN44T'), sub: t('patN44S'), days: t('patN44D') };
        }
        if (v === 'pat_4n4o4o' || v === 'pat_4n4o') {
            return { value: v, icon: '🌙', title: t('patN4oT'), sub: t('patN4oS'), days: t('patN4oD') };
        }
        if (v) {
            return { value: v, icon: '📅', title: v.replace(/_/g, ' '), sub: t('patFBS'), days: '' };
        }
        return { value: '', icon: '📅', title: t('patFBT'), sub: t('patFBS'), days: '' };
    }

    function patternMetaFromId(id) {
        return patternPresetMeta(id);
    }

    function formatPatternSlot(slot) {
        if (slot == null || slot === '') return '';
        const s = String(slot).toLowerCase();
        if (s === 'night') return t('stNt');
        if (s === 'day') return t('stDt');
        if (s === 'off') return t('offD');
        return s.charAt(0).toUpperCase() + s.slice(1);
    }

    function renderSetupRotating() {
        const today = new Date().toISOString().slice(0, 10);
        state.dayOffDate = state.dayOffDate || today;
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btn-sr-back">← ${escapeHtml(t('back'))}</button>
                    <h1>${escapeHtml(t('srT'))}</h1>
                    <span class="nf-clock">${escapeHtml(nowClockStr())}</span>
                </div>
                <p class="nf-field-label nf-field-label--loose">${escapeHtml(t('srAQ'))}</p>
                <div class="nf-card nf-card--inset">
                    <input type="date" id="rot-start" class="nf-select" value="${today}" />
                </div>
                <p class="nf-muted nf-rot-pick-hint nf-rot-anchor-hint">${escapeHtml(t('srAH'))}</p>
                <p class="nf-field-label nf-field-label--loose">${escapeHtml(t('srPR'))}</p>
                <p class="nf-muted nf-rot-pick-hint">${escapeHtml(t('srPH'))}</p>
                <div class="nf-pattern-grid" id="rot-pattern-grid" role="radiogroup" aria-label="${escapeHtml(t('srGA'))}">
                    ${PATTERN_PRESET_DEFS.map((d, i) => {
                        const p = patternPresetMeta(d.value);
                        return `
                    <label class="nf-pattern-card${i === 0 ? ' is-checked' : ''}">
                        <input type="radio" name="rot-pat" value="${escapeHtml(p.value)}"${
                            i === 0 ? ' checked' : ''
                        } />
                        <span class="nf-pattern-card__body">
                            <span class="nf-pattern-card__icon" aria-hidden="true">${escapeHtml(p.icon)}</span>
                            <span class="nf-pattern-card__title">${escapeHtml(p.title)}</span>
                            <span class="nf-pattern-card__days">${escapeHtml(p.days)}</span>
                            <span class="nf-pattern-card__sub">${escapeHtml(p.sub)}</span>
                        </span>
                    </label>`;
                    }).join('')}
                </div>
                <p class="nf-field-label" id="rot-block-label" style="display:none;">${escapeHtml(t('srBL'))}</p>
                <div class="nf-card nf-rot-block-card" id="rot-block-wrap" style="display:none;">
                    <p class="nf-rot-block-lead">${escapeHtml(t('srBRun'))}</p>
                    <div class="nf-rot-block-row">
                        <span class="nf-rot-block-lab">${escapeHtml(t('srBR'))}</span>
                        <input type="number" min="1" class="nf-rot-block-num" id="rot-bn" value="14" />
                    </div>
                    <div class="nf-rot-block-row">
                        <span class="nf-rot-block-lab">${escapeHtml(t('srDIR'))}</span>
                        <input type="number" min="0" class="nf-rot-block-num" id="rot-bd" value="14" />
                    </div>
                    <div class="nf-rot-block-row">
                        <span class="nf-rot-block-lab">${escapeHtml(t('srOIR'))}</span>
                        <input type="number" min="0" class="nf-rot-block-num" id="rot-bo" value="0" />
                    </div>
                </div>
                <p class="nf-field-label nf-field-label--loose">${escapeHtml(t('srWST'))}</p>
                <p class="nf-muted nf-rot-pick-hint" style="margin-top:-2px;">${escapeHtml(t('srWSH'))}</p>
                <div class="nf-rot-tpl-stack">
                    <div class="nf-rot-tpl-card nf-rot-tpl-card--night">
                        <div class="nf-rot-tpl-card__head">${escapeHtml(t('srNH'))}</div>
                        <p class="nf-rot-tpl-card__note">${escapeHtml(t('srNN'))}</p>
                    <div class="nf-rot-tpl-in">
                    <div class="nf-row"><span class="nf-rot-tpl-lab">${escapeHtml(t('work'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                        '',
                        '19:00',
                        'rn_ws'
                    )}${selectTimeHtml('', '07:00', 'rn_we')}</span></div>
                    <div class="nf-row" style="margin-top:8px;"><span class="nf-rot-tpl-lab">${escapeHtml(t('sleep'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                        '',
                        '08:00',
                        'rn_ss'
                    )}${selectTimeHtml('', '16:00', 'rn_se')}</span></div>
                    </div>
                    </div>
                    <hr class="rot-day-hr" style="border:none;border-top:1px solid var(--nf-border);margin:0;" />
                    <div class="nf-rot-tpl-card nf-rot-tpl-card--day rot-day-block">
                        <div class="nf-rot-tpl-card__head">${escapeHtml(t('srDH'))}</div>
                        <p class="nf-rot-tpl-card__note">${escapeHtml(t('srDN'))}</p>
                    <div class="nf-rot-tpl-in">
                    <div class="nf-row rot-day-block"><span class="nf-rot-tpl-lab">${escapeHtml(t('work'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                        '',
                        '07:00',
                        'rd_ws'
                    )}${selectTimeHtml('', '19:00', 'rd_we')}</span></div>
                    <div class="nf-row rot-day-block" style="margin-top:8px;"><span class="nf-rot-tpl-lab">${escapeHtml(t('sleep'))}</span><span class="nf-rot-tpl-pair">${selectTimeHtml(
                        '',
                        '22:00',
                        'rd_ss'
                    )}${selectTimeHtml('', '06:00', 'rd_se')}</span></div>
                    </div>
                    </div>
                    <p class="rot-4n4o-note nf-muted" style="display:none;margin:0 0 0;">${escapeHtml(t('sr4N'))}</p>
                <div class="nf-rot-tpl-card nf-rot-tpl-card--off">
                    <div class="nf-rot-tpl-card__head">${escapeHtml(t('srOH'))}</div>
                    <p class="nf-rot-tpl-card__note" style="margin:0;">${escapeHtml(t('srON'))}</p>
                </div>
                </div>
                <button type="button" class="nf-cta" id="btn-create-rot">${escapeHtml(t('srCF'))}</button>
                <p class="nf-hint-validate">${escapeHtml(t('srVH'))}</p>
                <p class="nf-sub nf-center">${escapeHtml(t('srSub'))}</p>
            </div>`;
        document.getElementById('btn-sr-back').onclick = () => {
            if (state.stack && state.stack.length) back();
            else go('onboarding', false);
        };
        initTimePickerButtons($root);
        function getSelectedRotPattern() {
            const r = $root.querySelector('input[name="rot-pat"]:checked');
            return r && r.value ? r.value : 'pitman_2_2_3';
        }
        const syncRotForm = () => {
            const v = getSelectedRotPattern();
            const block = v === 'block_rotation';
            const d4n4o = v === 'pat_4n4o';
            $root.querySelectorAll('.nf-pattern-card').forEach((lab) => {
                const inp = lab.querySelector('input[name="rot-pat"]');
                lab.classList.toggle('is-checked', inp && inp.checked);
            });
            const bw = document.getElementById('rot-block-wrap');
            const bl = document.getElementById('rot-block-label');
            if (bw) bw.style.display = block ? 'block' : 'none';
            if (bl) bl.style.display = block ? 'block' : 'none';
            $root.querySelectorAll('.rot-day-block').forEach((el) => {
                el.style.display = d4n4o ? 'none' : '';
            });
            const h = $root.querySelector('.rot-day-hr');
            if (h) h.style.display = d4n4o ? 'none' : '';
            const note = $root.querySelector('.rot-4n4o-note');
            if (note) note.style.display = d4n4o ? 'block' : 'none';
        };
        $root.querySelectorAll('input[name="rot-pat"]').forEach((inp) => {
            inp.addEventListener('change', syncRotForm);
        });
        syncRotForm();
        document.getElementById('btn-create-rot').onclick = async () => {
            const patternId = getSelectedRotPattern();
            const start = document.getElementById('rot-start').value;
            if (!start) {
                tg.showAlert(t('alPickDate'));
                return;
            }
            const nWs = document.getElementById('rn_ws').value;
            const nWe = document.getElementById('rn_we').value;
            const nSs = document.getElementById('rn_ss').value;
            const nSe = document.getElementById('rn_se').value;
            const oN = workSleepOverlapError(nWs, nWe, nSs, nSe);
            if (oN) {
                tg.showAlert(t('alNt') + ' ' + oN);
                return;
            }
            const body = {
                pattern_id: patternId,
                pattern_start_date: start,
                night: {
                    work_start: nWs,
                    work_end: nWe,
                    sleep_start: nSs,
                    sleep_end: nSe,
                },
            };
            if (patternId !== 'pat_4n4o') {
                const dWs = document.getElementById('rd_ws').value;
                const dWe = document.getElementById('rd_we').value;
                const dSs = document.getElementById('rd_ss').value;
                const dSe = document.getElementById('rd_se').value;
                const oD = workSleepOverlapError(dWs, dWe, dSs, dSe);
                if (oD) {
                    tg.showAlert(t('alDt') + ' ' + oD);
                    return;
                }
                body.day = {
                    work_start: dWs,
                    work_end: dWe,
                    sleep_start: dSs,
                    sleep_end: dSe,
                };
            }
            if (patternId === 'block_rotation') {
                body.block_nights = Math.max(1, parseInt(document.getElementById('rot-bn').value, 10) || 1);
                body.block_days = Math.max(0, parseInt(document.getElementById('rot-bd').value, 10) || 0);
                body.block_off = Math.max(0, parseInt(document.getElementById('rot-bo').value, 10) || 0);
            }
            renderLoading();
            try {
                const res = await api(`/schedules/rotating?telegram_id=${user.id}`, {
                    method: 'POST',
                    json: body,
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    $root.innerHTML = `<div class="nf-error">${escapeHtml(
                        err.error || t('errRotSave')
                    )}</div>`;
                    return;
                }
                state.rotatingDemo = false;
                try {
                    localStorage.removeItem('nightflow_rotating_demo');
                } catch (e) {}
                await loadUserAndSchedule();
            } catch (e) {
                console.error(e);
                $root.innerHTML = `<div class="nf-error">${escapeHtml(t('netErrHtml'))}</div>`;
            }
        };
    }

    function mockSuggestions() {
        return [
            {
                title: '🦆 OFFLINE: fake coffee with the moon penguins',
                body: "These are jokes — server didn't load. Real ideas need the API.",
                action: "Still not your data.",
                is_example: true,
                silly_example: true,
            },
        ];
    }

    function mockWeekly() {
        return {
            range: formatRangeDate(
                new Date(Date.now() - 6 * 86400000),
                new Date()
            ),
            energy: ['😴', '😐', '😊', '⚡', '⚡', '😊', '😐'],
            energy_trend: 'steady',
            energy_breakdown: { drained: 1, low: 1, ok: 2, great: 1, days_logged: 5 },
            habits: { avg_coffee_adherence_pct: 64, avg_meal_adherence_pct: 75 },
            coffee: [
                { label: '21:30', pct: 85 },
                { label: '01:30', pct: 42 },
            ],
            meals: [
                { label: '16:00', pct: 85 },
                { label: '20:30', pct: 85 },
                { label: '02:00', pct: 28 },
                { label: '06:00', pct: 85 },
            ],
            sleepPct: 62,
        };
    }

    function energyMoodDonutStyle(b) {
        const d = b || {};
        const p = [d.drained | 0, d.low | 0, d.ok | 0, d.great | 0];
        const t = p[0] + p[1] + p[2] + p[3];
        if (t < 1) {
            return 'var(--tg-theme-secondary-bg-color, #3a3a45)';
        }
        let a = 0;
        const cols = ['#5c6bc0', '#90a4ae', '#26a69a', '#ffca28'];
        const segs = [];
        p.forEach((n, i) => {
            if (n < 1) return;
            const pct = (n / t) * 100;
            const end = a + pct;
            segs.push(`${cols[i]} ${a}% ${end}%`);
            a = end;
        });
        return segs.length ? `conic-gradient(${segs.join(', ')})` : 'var(--tg-theme-secondary-bg-color, #3a3a45)';
    }

    function weekTrendLabel(tr) {
        const a = (cls, ico, msg) =>
            `<div class="nf-trend nf-trend--in-header ${cls}"><span class="nf-trend-ico" aria-hidden="true">${ico}</span> ${escapeHtml(
                msg
            )}</div>`;
        if (tr === 'up') return a('nf-trend--up', '↑', t('wkTrU'));
        if (tr === 'down') return a('nf-trend--down', '↓', t('wkTrD'));
        if (tr === 'steady') return a('nf-trend--mid', '→', t('wkTrM'));
        return '';
    }

    /** CSS tone class for weekly energy cell (emoji or placeholder). */
    function energyDayClass(emo) {
        if (emo == null) return 'nf-week-day--empty';
        const s = String(emo).trim();
        if (!s || s === '—') return 'nf-week-day--empty';
        if (/[😴💤🥱]/.test(s) || s.toLowerCase().includes('drain')) return 'nf-week-day--drained';
        if (/[😐😑😕🙁😟]/.test(s) || s.toLowerCase() === 'low') return 'nf-week-day--low';
        if (/[😊🙂😌]/.test(s) || s.toLowerCase() === 'ok') return 'nf-week-day--ok';
        if (/[⚡🚀💪🔥🤩😁]/.test(s) || s.toLowerCase() === 'great') return 'nf-week-day--great';
        return 'nf-week-day--ok';
    }

    function formatRecWindowList(arr) {
        if (!arr || !arr.length) {
            return `<p class="nf-rec-empty">${escapeHtml(t('recEmp'))}</p>`;
        }
        return arr
            .map(
                (w) => `
            <div class="nf-rec-slot">
                <div class="nf-rec-slot-time">${escapeHtml(formatTime(w.time))}</div>
                <div class="nf-rec-slot-msg">${escapeHtml((w && w.message) || '')}</div>
            </div>`
            )
            .join('');
    }

    function openOffDayRecommendations(sched) {
        const advice = sched.transition_advice
            ? `<div class="nf-rec-advice"><p class="nf-rec-advice-text">${escapeHtml(sched.transition_advice)}</p></div>`
            : '';
        openModal(
            `<div class="nf-rec-root">
                <div class="nf-rec-hero">
                    <div class="nf-rec-hero-moon" aria-hidden="true">🌙</div>
                    <h2 class="nf-rec-title">${escapeHtml(t('recTi'))}</h2>
                    <p class="nf-rec-sub">${escapeHtml(t('recSu'))}</p>
                </div>
                ${advice}
                <section class="nf-rec-section nf-rec-section--sleep">
                    <h3 class="nf-rec-sec-h"><span class="nf-rec-sec-ico" aria-hidden="true">😴</span> ${escapeHtml(
                        t('recSH')
                    )}</h3>
                    <div class="nf-rec-sleep-pill">
                        <span class="nf-rec-sleep-time">${escapeHtml(formatTime(sched.sleep_start))}</span>
                        <span class="nf-rec-sleep-sep">→</span>
                        <span class="nf-rec-sleep-time">${escapeHtml(formatTime(sched.sleep_end))}</span>
                    </div>
                    <p class="nf-rec-sec-note">${escapeHtml(t('recSN'))}</p>
                </section>
                <section class="nf-rec-section">
                    <h3 class="nf-rec-sec-h"><span class="nf-rec-sec-ico" aria-hidden="true">☕</span> ${escapeHtml(
                        t('recCH')
                    )}</h3>
                    <p class="nf-rec-sec-note">${escapeHtml(t('recCHs'))}</p>
                    <div class="nf-rec-slot-list">${formatRecWindowList(sched.coffee_windows)}</div>
                </section>
                <section class="nf-rec-section">
                    <h3 class="nf-rec-sec-h"><span class="nf-rec-sec-ico" aria-hidden="true">🍽</span> ${escapeHtml(
                        t('recEH')
                    )}</h3>
                    <p class="nf-rec-sec-note">${escapeHtml(t('recEHm'))}</p>
                    <div class="nf-rec-slot-list">${formatRecWindowList(sched.meal_windows)}</div>
                </section>
                <section class="nf-rec-section">
                    <h3 class="nf-rec-sec-h"><span class="nf-rec-sec-ico" aria-hidden="true">💡</span> ${escapeHtml(
                        t('recLH')
                    )}</h3>
                    <p class="nf-rec-sec-note">${escapeHtml(t('recLs'))}</p>
                    <div class="nf-rec-slot-list">${formatRecWindowList(sched.brightness_windows)}</div>
                </section>
                <button type="button" class="nf-cta nf-cta-secondary" id="nf-rec-done">${escapeHtml(t('recDo'))}</button>
            </div>`,
            { sheetClass: 'nf-rec-modal' }
        );
        const done = document.getElementById('nf-rec-done');
        if (done) done.onclick = closeModal;
    }

    function renderDashboard() {
        const sched = state.schedule;
        if (!sched) {
            renderOnboarding();
            return;
        }

        const clock = nowClockStr();
        const today = new Date();
        const isOff = sched.shift_type === 'off';
        const st = sched.shift_type || 'night';
        const showReport =
            hasProEntitlement() &&
            !isOff &&
            shouldShowReportCard(sched.work_start, sched.work_end) &&
            !isEosIgnoredToday() &&
            !isEosDoneToday();
        const next = isOff ? null : getNextEvent(sched);
        const rotating = isRotatingUi();

        let body = `
            <div class="nf-screen nf-screen--tabbed">
                <div class="nf-tabbar-body">
                <div class="nf-topbar">
                    <span class="nf-topbar-ghost" aria-hidden="true"></span>
                    <h1>🌙 ${escapeHtml(t('brand').toUpperCase())}</h1>
                    <span class="nf-clock">${escapeHtml(clock)}</span>
                </div>
                <div class="nf-home-quick">
                    <button type="button" class="nf-home-dayoff" id="btn-home-dayoff">
                        <span class="nf-home-dayoff-ico" aria-hidden="true">😴</span>
                        <span>${escapeHtml(t('markOff'))}</span>
                    </button>
                </div>
                <div class="nf-card">
                    <div class="nf-card-label">${escapeHtml(t('today'))}</div>
                    <div class="nf-today-line">${escapeHtml(formatLongDate(today).toUpperCase())}</div>
                    ${
                        rotating && (sched.pattern_slot || sched.pattern_id)
                            ? (() => {
                                  const pm = patternMetaFromId(sched.pattern_id);
                                  const sl = formatPatternSlot(sched.pattern_slot) || t('slotToday');
                                  return `<div class="nf-pattern-today" role="status">
        <span class="nf-pattern-today-ico" aria-hidden="true">${escapeHtml(pm.icon)}</span>
        <div class="nf-pattern-today-text">
            <div class="nf-pattern-today-slot">${escapeHtml(sl)}</div>
            <div class="nf-pattern-today-name">${escapeHtml(pm.title)}${
            pm.days ? ' · ' + escapeHtml(pm.days) : ''
        }</div>
        </div>
    </div>`;
                              })()
                            : ''
                    }
                </div>
                ${
                    !isOff && sched.transition_advice
                        ? `<p class="nf-sub" style="padding:0 12px 8px;margin:0;line-height:1.35;">${escapeHtml(
                              sched.transition_advice
                          )}</p>`
                        : ''
                }`;

        if (isOff) {
            const pmOff =
                rotating && (sched.pattern_id || sched.pattern_slot)
                    ? patternMetaFromId(sched.pattern_id)
                    : null;
            const slotLine =
                rotating && sched.pattern_slot
                    ? `${escapeHtml(formatPatternSlot(sched.pattern_slot))}${
                          pmOff ? ' · ' + escapeHtml(pmOff.title) : ''
                      }`
                    : '';
            const offLead = sched.transition_advice
                ? escapeHtml(sched.transition_advice)
                : escapeHtml(t('offDefLead'));
            body += `
                <div class="nf-card nf-off-card">
                    <div class="nf-shift-title off">${rotating ? escapeHtml(t('offRot')) : escapeHtml(t('offD'))}</div>
                    ${
                        slotLine
                            ? `<p class="nf-off-slot-line"><span class="nf-off-slot-ico" aria-hidden="true">${escapeHtml(
                                  pmOff ? pmOff.icon : '🌿'
                              )}</span><span>${slotLine}</span></p>`
                            : ''
                    }
                    <p class="nf-muted nf-off-lead">${offLead}</p>
                    <div class="nf-off-sleep-strip">
                        <span class="nf-off-sleep-k">${escapeHtml(t('sleep'))}</span>
                        <span class="nf-off-sleep-v">${escapeHtml(formatTime(sched.sleep_start))} – ${escapeHtml(
                formatTime(sched.sleep_end)
            )}</span>
                    </div>
                    <button type="button" class="nf-cta" id="btn-off-rec">${escapeHtml(t('offRec'))}</button>
                </div>`;
        } else {
            const isFree = !hasProEntitlement();
            const paidPro = hasActivePaidPro();
            // TESTING ONLY — revert ?? fallback to 50 before production
            const stars = state.userRow?.pro_price_stars ?? 88;
            if (!paidPro && isFree) {
                body += `<div class="nf-upgrade-hero" role="region" aria-label="${escapeHtml(t('proAppName'))}">
                    <div class="nf-upgrade-hero-title">${escapeHtml(t('proHeroTitle'))}</div>
                    <p class="nf-upgrade-hero-text">${escapeHtml(t('proBannerBody'))}</p>
                    <p class="nf-upgrade-hero-price">${escapeHtml(t('proBannerPrice', stars))}</p>
                    <button type="button" class="nf-btn-pro" id="btn-dash-pro">${escapeHtml(t('proBannerBtn'))}</button>
                </div>`;
            }
            body += `
                <div class="nf-card">
                    <div class="nf-shift-title ${escapeHtml(st)}">${shiftTitle(st)}</div>
                    <div class="nf-bar-row"><span class="nf-bar-label">${escapeHtml(t('work'))}</span><div style="flex:1;"><div class="nf-bar-times"><span>${escapeHtml(formatTime(sched.work_start))}</span><span>${escapeHtml(formatTime(sched.work_end))}</span></div><div class="nf-bar-track"></div></div></div>
                    <div class="nf-bar-row"><span class="nf-bar-label">${escapeHtml(t('sleep'))}</span><div style="flex:1;"><div class="nf-bar-times"><span>${escapeHtml(formatTime(sched.sleep_start))}</span><span>${escapeHtml(formatTime(sched.sleep_end))}</span></div><div class="nf-bar-track"></div></div></div>
                </div>
                <div class="nf-card nf-next-card nf-next-card--${escapeHtml(
                    (next && next.kindClass) || 'other'
                )}">
                    <div class="nf-next-label"><span class="nf-next-chip">${escapeHtml(
                        (next && next.kindLabel) || t('nextLabel')
                    )}</span> ${escapeHtml(t('nextAfter'))}</div>
                    <div class="nf-next-main">${escapeHtml(next ? next.line : '')}</div>
                    <div class="nf-next-sub">${escapeHtml(next ? next.sub : '')}</div>
                </div>`;
            if (isFree) {
                body += `<div class="nf-free-timeline-hint">
                    <span class="nf-timeline-hint-ico" aria-hidden="true">✨</span>
                    <p>${escapeHtml(t('freeTimeline'))}</p>
                </div>`;
            } else if (!paidPro) {
                body += `<p class="nf-trial-hint">${escapeHtml(t('trialHint'))}</p>`;
            }

            if (rotating && hasProEntitlement() && !isTransCardHiddenToday()) {
                body += `
                    <div class="nf-card nf-transition-card">
                        <div class="nf-trans-head">
                            <span class="nf-trans-ico" aria-hidden="true">🔄</span>
                            <div>
                                <p class="nf-trans-title">${escapeHtml(t('transCardT'))}</p>
                                <p class="nf-trans-text">${escapeHtml(t('transCardD'))}</p>
                            </div>
                        </div>
                        <div class="nf-trans-actions">
                        <button type="button" class="nf-cta nf-btn" id="btn-dash-trans">${escapeHtml(t('transView'))}</button>
                        <button type="button" class="nf-trans-skip" id="btn-trans-card-hide">${escapeHtml(t('transHide'))}</button>
                        </div>
                    </div>`;
            }

            if (showReport) {
                body += `
                    <div class="nf-card nf-eos-prompt" role="region" aria-label="${escapeHtml(t('eosTitle'))}">
                        <div class="nf-eos-prompt__row">
                            <div class="nf-eos-prompt__icon" aria-hidden="true">🌙</div>
                            <div class="nf-eos-prompt__copy">
                                <p class="nf-eos-prompt__kicker">${escapeHtml(t('eosKicker'))}</p>
                                <p class="nf-eos-prompt__title">${escapeHtml(t('eosTitle'))}</p>
                                <p class="nf-eos-prompt__sub">${escapeHtml(t('eosSub'))}</p>
                            </div>
                        </div>
                        <button type="button" class="nf-cta" id="btn-dash-report">${escapeHtml(t('eosCta'))}</button>
                        <button type="button" class="nf-eos-skip" id="btn-dash-report-ignore">${escapeHtml(t('eosSkip'))}</button>
                    </div>`;
            }
        }

        body += `</div>
                ${getMainTabBarHtml()}
            </div>`;

        $root.innerHTML = body;

        bindMainTabBar();
        const homeDay = document.getElementById('btn-home-dayoff');
        if (homeDay) {
            homeDay.onclick = () => go('dayoff', true);
        }

        const proBtn = document.getElementById('btn-dash-pro');
        if (proBtn) proBtn.onclick = () => openProInvoice();

        const offRec = document.getElementById('btn-off-rec');
        if (offRec) offRec.onclick = () => openOffDayRecommendations(sched);
        const repIgn = document.getElementById('btn-dash-report-ignore');
        if (repIgn) {
            repIgn.onclick = () => {
                setEosIgnoreToday();
                renderDashboard();
            };
        }

        const tr = document.getElementById('btn-dash-trans');
        if (tr) tr.onclick = () => go('transition', true);
        const trH = document.getElementById('btn-trans-card-hide');
        if (trH) {
            trH.onclick = () => {
                setTransCardHiddenToday();
                renderDashboard();
            };
        }
        const rep = document.getElementById('btn-dash-report');
        if (rep) rep.onclick = () => go('summary', true);
    }

    function formatTime(t) {
        if (!t) return '--:--';
        if (typeof t === 'string') return t.slice(0, 5);
        return String(t);
    }

    function buildTimelineListHtml(sched, opts) {
        const s = normalizeScheduleFields(sched) || sched;
        const events = collectEvents(s);
        const kc = (k) =>
            ({
                work_start: 'nf-tl--wstart',
                work_end: 'nf-tl--wend',
                sleep_start: 'nf-tl--sleepin',
                sleep_end: 'nf-tl--wake',
                coffee: 'nf-tl--coffee',
                meal: 'nf-tl--meal',
                light: 'nf-tl--light',
                other: 'nf-tl--other',
            }[k] || 'nf-tl--other');
        const oneRow = (e) => {
            const cls = kc(e.kind);
            const tag = eventTypeTag(e.kind);
            return `<li class="nf-tl-item ${cls}">
                    <span class="nf-tl-dot" aria-hidden="true"></span>
                    <div class="nf-tl-body">
                        <span class="nf-tl-time">${escapeHtml(e.time)}</span>
                        <div class="nf-tl-line">
                            <span class="nf-tl-kind">${escapeHtml(tag)}</span>
                            <span class="nf-tl-ico" aria-hidden="true">${escapeHtml(e.icon)}</span>
                            <span class="nf-tl-text">${escapeHtml(e.label)}</span>
                        </div>
                    </div>
                </li>`;
        };
        if (!events.length) return '';
        const grouped = !opts || opts.group !== false;
        if (grouped && s) {
            const phaseSet = new Set(events.map((e) => timelineEventPhase(e, s)));
            if (phaseSet.size >= 2) {
                const parts = [];
                let last = null;
                for (const e of events) {
                    const p = timelineEventPhase(e, s);
                    if (p !== last) {
                        const rawLab = timelinePhaseLabel(p);
                        const lab = escapeHtml(rawLab);
                        const ico = escapeHtml(timelinePhaseIcon(p));
                        const attrLab = String(rawLab).replace(/&/g, '&amp;').replace(/"/g, '&quot;');
                        parts.push(
                            `<li class="nf-tl-section" role="group" aria-label="${attrLab}">
                                <div class="nf-tl-section-label">
                                    <span class="nf-tl-section-ico" aria-hidden="true">${ico}</span>
                                    <span class="nf-tl-section-txt">${lab}</span>
                                </div>
                            </li>`
                        );
                        last = p;
                    }
                    parts.push(oneRow(e));
                }
                return parts.join('');
            }
        }
        return events.map((e) => oneRow(e)).join('');
    }

    function daySectionHtml(dayRow, isMulti) {
        const sched = normalizeScheduleFields(dayRow) || dayRow;
        if (!sched || sched.shift_type === 'off') {
            const dlabel = sched && sched.date ? String(sched.date) : '';
            const dPretty = dlabel
                ? new Date(dlabel + 'T12:00:00').toLocaleDateString(NF_DATE_LOCALE, {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                  })
                : new Date().toLocaleDateString(NF_DATE_LOCALE, {
                      weekday: 'short',
                      month: 'short',
                      day: 'numeric',
                  });
            return `<div class="nf-day-block">
                <p class="nf-day-head">${escapeHtml(dPretty)} · <strong>${escapeHtml(t('plOFF'))}</strong></p>
                <p class="nf-muted" style="margin:4px 0 0;">${
                    sched && sched.transition_advice ? escapeHtml(sched.transition_advice) : escapeHtml(t('plRest'))
                }</p>
            </div>`;
        }

        const dStr = sched.date
            ? new Date(String(sched.date) + 'T12:00:00').toLocaleDateString(NF_DATE_LOCALE, {
                  weekday: 'short',
                  month: 'short',
                  day: 'numeric',
              })
            : new Date().toLocaleDateString(NF_DATE_LOCALE, { month: 'short', day: 'numeric' });
        const stu = (sched.shift_type || '').toUpperCase();
        const trBadge =
            sched.is_transition_day === true
                ? `<span class="nf-tr-pill" title="${escapeHtml(t('plTRt'))}">${escapeHtml(t('plTR'))}</span> `
                : '';
        const evs = collectEvents(sched);
        const hasBridge =
            evs.some((x) => x.kind === 'work_end') && evs.some((x) => x.kind === 'sleep_start');
        const lines = buildTimelineListHtml(sched);
        const bridge = hasBridge ? `<p class="nf-tl-bridge">${escapeHtml(t('plBridge'))}</p>` : '';
        const advice = sched.transition_advice
            ? `<p class="nf-day-advice nf-muted">${escapeHtml(sched.transition_advice)}</p>`
            : '';
        const locked = sched.reminders_locked
            ? `<p class="nf-day-locked">${escapeHtml(String(sched.reminders_locked))}</p>`
            : '';
        const well =
            !sched.is_transition_day && Array.isArray(sched.wellness_suggestions) && sched.wellness_suggestions.length
                ? `<div class="nf-wellness-hint">
                    <div class="nf-card-label" style="margin:0 0 6px;">${escapeHtml(t('plTipH'))}</div>
                    ${sched.wellness_suggestions
                        .map(
                            (x) => `<p class="nf-muted" style="margin:0 0 4px 0;">${escapeHtml(x)}</p>`
                        )
                        .join('')}
                </div>`
                : '';
        return `<div class="nf-day-block">
            <p class="nf-day-head">${trBadge}${escapeHtml(dStr)} · <strong>${escapeHtml(stu)}</strong></p>
            ${
                isMulti && (sched.pattern_id || sched.pattern_slot)
                    ? `<p class="nf-day-meta nf-day-meta--pat">${
                          [
                              formatPatternSlot(sched.pattern_slot) ? escapeHtml(formatPatternSlot(sched.pattern_slot)) : '',
                              sched.pattern_id ? escapeHtml(patternMetaFromId(sched.pattern_id).title) : '',
                          ]
                              .filter(Boolean)
                              .join(' · ') || '—'
                      }</p>`
                    : ''
            }
            ${advice}
            ${locked}
            ${well}
            ${bridge}
            <ul class="nf-tl nf-timeline">${lines}</ul>
        </div>`;
    }

    function renderFullSchedule() {
        $root.innerHTML = `<div class="nf-loading">${escapeHtml(t('loadFull'))}</div>`;

        (async () => {
            const n = hasProEntitlement() ? (state.fullScheduleRange || 1) : 1;
            let days = [];
            let trRem = true;
            let trLead = '3';

            if (hasProEntitlement()) {
                try {
                    const res = await api(
                        `/schedules/preview?days=${n}&telegram_id=${encodeURIComponent(user.id)}`
                    );
                    if (res.ok) {
                        const data = await res.json();
                        days = data.days || [];
                        if (data.transitionReminders != null) trRem = Boolean(data.transitionReminders);
                        if (data.transitionLeadDays != null) trLead = String(data.transitionLeadDays);
                    }
                } catch (e) {
                    console.warn('schedule preview', e);
                }
            }

            if (!days.length) {
                const s = normalizeScheduleFields(state.schedule);
                if (s && s.shift_type && s.shift_type !== 'off') {
                    if (!s.date) {
                        try {
                            s.date = new Date().toISOString().slice(0, 10);
                        } catch (e) {}
                    }
                    days = [s];
                } else {
                    $root.innerHTML = `<div class="nf-screen nf-screen--tabbed"><div class="nf-tabbar-body">
                    ${topbarMainTabPage(t('schedPage'))}
                    <p class="nf-muted" style="padding:0 4px 12px;">${escapeHtml(t('fsNoEv'))}</p>
                </div>${getMainTabBarHtml()}</div>`;
                    bindMainTabBar();
                    wireMainTabTopbar();
                    return;
                }
            }

            const multi = hasProEntitlement() && n > 1;
            const rangeBlock = hasProEntitlement()
                ? `<div class="nf-full-range" role="group" aria-label="${escapeHtml(t('schedPage'))}">
                    <span class="nf-full-range-lab">${escapeHtml(t('fsLab'))}</span>
                    <button type="button" class="nf-chip-range${
                        n === 1 ? ' is-active' : ''
                    }" data-range="1" aria-pressed="${n === 1}">${escapeHtml(t('fsD1'))}</button>
                    <button type="button" class="nf-chip-range${
                        n === 3 ? ' is-active' : ''
                    }" data-range="3" aria-pressed="${n === 3}">${escapeHtml(t('fsD3'))}</button>
                    <button type="button" class="nf-chip-range${
                        n === 7 ? ' is-active' : ''
                    }" data-range="7" aria-pressed="${n === 7}">${escapeHtml(t('fsD7'))}</button>
                </div>`
                : '';
            const foot =
                isRotatingUi() && hasProEntitlement()
                    ? `<p class="nf-muted nf-schedule-foot" style="margin-top:8px;">${escapeHtml(
                          t('plTF', trRem, trLead)
                      )}</p>`
                    : `<p class="nf-muted nf-schedule-foot" style="margin-top:8px;">${escapeHtml(t('plFoot'))}</p>`;

            const dayBlocks = (days || [])
                .map((d) => daySectionHtml(d, multi))
                .join('');

            $root.innerHTML = `
            <div class="nf-screen nf-screen--tabbed">
                <div class="nf-tabbar-body">
                ${topbarMainTabPage(t('schedPage'))}
                ${rangeBlock}
                <div class="nf-full-days">${dayBlocks}</div>
                ${foot}
                </div>
                ${getMainTabBarHtml()}
            </div>`;

            bindMainTabBar();
            wireMainTabTopbar();
            if (hasProEntitlement()) {
                $root.querySelectorAll('.nf-chip-range').forEach((b) => {
                    b.addEventListener('click', () => {
                        const r = Number(b.getAttribute('data-range'));
                        if (r === 1 || r === 3 || r === 7) {
                            state.fullScheduleRange = r;
                            try {
                                localStorage.setItem('nf_full_range', String(r));
                            } catch (e) {}
                            render();
                        }
                    });
                });
            }
        })();
    }

    function renderSuggestions() {
        $root.innerHTML = `<div class="nf-loading">${escapeHtml(t('loadFull'))}</div>`;

        (async () => {
            let items = mockSuggestions();
            let sugMode = 'examples';
            try {
                const res = await api(`/schedules/suggestions?telegram_id=${user.id}`);
                if (res.ok) {
                    const data = await res.json();
                    const raw = data.items || data.suggestions;
                    if (Array.isArray(raw) && raw.length) {
                        const realOnly = raw.filter((x) => x && !x.is_example);
                        items = realOnly.length > 0 ? realOnly : raw;
                        sugMode = data.suggestions_mode || (items[0] && items[0].is_example ? 'examples' : 'live');
                    } else {
                        items = Array.isArray(raw) && raw.length === 0 ? [] : items;
                    }
                }
            } catch (e) {
                console.warn('suggestions fetch failed', e);
            }

            if (!Array.isArray(items)) items = [];
            state.suggestionItems = items;

            const ignored = getIgnoredSuggestionSet();
            const visible = items
                .map((it, origIdx) => ({ it, origIdx }))
                .filter(({ it }) => it && !ignored.has(suggestionFingerprint(it)));

            const hasApplicable = visible.some(({ it: x }) => x && !x.is_example);
            const leadIdeas = sugMode === 'examples' ? t('sugMockLead') : t('sugL');
            const sugRows = visible.length
                ? visible
                      .map(({ it, origIdx }) => {
                          if (it && it.is_example) {
                              return `<div class="nf-suggestion nf-suggestion--example" data-sug-idx="${origIdx}">
                            <div class="nf-sug-body">
                            <div class="nf-sug-mock-hdr">
                            <span class="nf-sug-example-pill">${escapeHtml(t('sugEx'))}</span>
                            <span class="nf-sug-mock-warn">${escapeHtml(t('sugMockSub'))}</span>
                            </div>
                            <h3>${escapeHtml(it.title)}</h3>
                            <p>${escapeHtml(it.body)}</p>
                            <p class="nf-sug-action nf-muted">${escapeHtml(it.action)}</p>
                            </div>
                        </div>`;
                          }
                          return `<div class="nf-suggestion nf-suggestion-selectable" data-sug-idx="${origIdx}">
                            <label class="nf-sug-check">
                                <input type="checkbox" class="nf-sug-cb" value="${origIdx}" />
                                <span class="nf-sug-check-ui" aria-hidden="true"></span>
                            </label>
                            <div class="nf-sug-body">
                            <h3>${escapeHtml(it.title)}</h3>
                            <p>${escapeHtml(it.body)}</p>
                            <p class="nf-sug-action">→ ${escapeHtml(it.action)}</p>
                            <div class="nf-sug-actions">
                                <button type="button" class="nf-btn-sug-ignore js-sug-ignore" data-fp="${escapeHtml(
                                    suggestionFingerprint(it)
                                )}">${escapeHtml(t('sugIg'))}</button>
                                <button type="button" class="nf-btn-sug-settings js-sug-adj" data-orig-idx="${origIdx}">${escapeHtml(
                              t('sugAdj')
                          )}</button>
                            </div>
                            </div>
                        </div>`;
                      })
                      .join('')
                : `<div class="nf-card nf-center"><div style="font-weight:600;">${escapeHtml(
                      t('sugEm')
                  )}</div><div class="nf-muted" style="margin-top:6px;">${escapeHtml(t('sugEm2'))}</div></div>`;

            $root.innerHTML = `
                <div class="nf-screen nf-sug-screen nf-screen--tabbed">
                    <div class="nf-tabbar-body">
                    ${topbarMainTabPage(t('ideasPage'))}
                    <p class="nf-sug-lead">${escapeHtml(leadIdeas)}</p>
                    ${sugRows}
                    ${
                        visible.length && hasApplicable
                            ? `<div class="nf-sug-apply-bar">
                        <button type="button" class="nf-cta" id="btn-sug-apply" disabled>${escapeHtml(
                            t('sugAp')
                        )}</button>
                    </div>`
                            : ''
                    }
                    </div>
                    ${getMainTabBarHtml()}
                </div>`;

            wireMainTabTopbar();
            bindMainTabBar();

            const applyBtn = document.getElementById('btn-sug-apply');
            const syncApplyEnabled = () => {
                if (!applyBtn) return;
                const n = $root.querySelectorAll('.nf-sug-cb:checked').length;
                applyBtn.disabled = n < 1;
                applyBtn.textContent = n < 1 ? t('sugAp') : t('sugApN', n);
            };
            $root.querySelectorAll('.nf-sug-cb').forEach((cb) => {
                cb.addEventListener('change', syncApplyEnabled);
            });
            syncApplyEnabled();

            $root.querySelectorAll('.js-sug-ignore').forEach((b) => {
                b.addEventListener('click', () => {
                    const fp = b.getAttribute('data-fp');
                    if (fp) ignoreSuggestionKey(fp);
                    renderSuggestions();
                });
            });
            $root.querySelectorAll('.js-sug-adj').forEach((b) => {
                b.addEventListener('click', () => {
                    const i = parseInt(b.getAttribute('data-orig-idx') || '', 10);
                    const it = Array.isArray(state.suggestionItems) ? state.suggestionItems[i] : null;
                    if (it && it.apply) openSettingsFromSuggestion(it.apply);
                    else go('settings', true);
                });
            });

            if (applyBtn) {
                applyBtn.addEventListener('click', async () => {
                    const selected = [...$root.querySelectorAll('.nf-sug-cb:checked')]
                        .map((cb) => parseInt(cb.value, 10))
                        .filter((n) => !Number.isNaN(n));
                    if (selected.length < 1) return;
                    applyBtn.setAttribute('disabled', 'true');
                    try {
                        const res = await api(`/schedules/suggestions/apply?telegram_id=${user.id}`, {
                            method: 'POST',
                            json: { suggestion_indices: selected },
                        });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) {
                            tg.showAlert((data && data.error) || t('errApply'));
                            applyBtn.removeAttribute('disabled');
                            return;
                        }
                        if (data && data.rotating) {
                            const ok = await reloadScheduleFromApi();
                            if (!ok) console.warn('reload after suggestion apply (rotating)');
                        } else {
                            if (data && data.work_start !== undefined) applyConstantRowToState(data);
                            const ok = await reloadScheduleFromApi();
                            if (!ok) console.warn('reload after suggestion apply');
                        }
                        tg.showAlert(
                            (data && data.applied) === 1
                                ? t('sugUp1')
                                : t('sugUp', (data && data.applied) || selected.length)
                        );
                        renderSuggestions();
                    } catch (e) {
                        console.warn('apply suggestions', e);
                        tg.showAlert(t('errApplyNet'));
                    }
                    applyBtn.removeAttribute('disabled');
                });
            }
        })();
    }

    function renderTransition() {
        const m = {
            headline: t('trH'),
            blocks: [
                {
                    title: t('trB1'),
                    lines: [t('trL1a'), t('trL1b')],
                },
                {
                    title: t('trB2'),
                    lines: [t('trL2a'), t('trL2b')],
                },
            ],
            caffeine: t('trCaf'),
            light: t('trLgt'),
        };
        $root.innerHTML = `
            <div class="nf-screen nf-screen--tabbed nf-trans-page">
                <div class="nf-tabbar-body">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btr">← ${escapeHtml(t('back'))}</button>
                    <h1>${escapeHtml(t('trT'))}</h1>
                    <span></span>
                </div>
                <div class="nf-trans-hero">
                    <h2>${escapeHtml(t('trHero'))}</h2>
                    <p>${escapeHtml(t('trHeroSub'))}</p>
                    <p style="margin-top:10px;font-size:0.88rem;opacity:0.95;">📅 ${escapeHtml(m.headline)}</p>
                </div>
                <p class="nf-field-label" style="margin:0 0 8px;">${escapeHtml(t('trP'))}</p>
                <div class="nf-trans-grid">
                ${m.blocks
                    .map(
                        (b) => `
                <div class="nf-trans-tile">
                    <h3>${escapeHtml(b.title)}</h3>
                    ${b.lines.map((l) => `<p>${escapeHtml(l)}</p>`).join('')}
                </div>`
                    )
                    .join('')}
                </div>
                <div class="nf-card" style="margin-bottom:12px;">
                    <p style="margin:0 0 6px;font-weight:600;">☕ ${escapeHtml(t('trCa'))}</p>
                    <p class="nf-muted" style="margin:0;">${escapeHtml(m.caffeine)}</p>
                    <p style="margin:10px 0 6px;font-weight:600;">💡 ${escapeHtml(t('trLi'))}</p>
                    <p class="nf-muted" style="margin:0;">${escapeHtml(m.light)}</p>
                </div>
                <button type="button" class="nf-cta" id="btn-rem">${escapeHtml(t('trSetR'))}</button>
                <button type="button" class="nf-cta-secondary" id="btn-tr-dismiss" style="margin-top:10px;">${escapeHtml(
                    t('trDismiss')
                )}</button>
                </div>
                ${getMainTabBarHtml()}
            </div>`;
        document.getElementById('btr').onclick = back;
        document.getElementById('btn-rem').onclick = () => {
            goMainTab('settings');
        };
        const dsm = document.getElementById('btn-tr-dismiss');
        if (dsm) {
            dsm.onclick = () => {
                setTransCardHiddenToday();
                back();
            };
        }
        bindMainTabBar();
    }

    function renderWeekly() {
        $root.innerHTML = `<div class="nf-loading">${escapeHtml(t('loadFull'))}</div>`;

        (async () => {
            let w = mockWeekly();
            let wellness = [];
            try {
                const res = await api(`/reports/weekly?telegram_id=${user.id}`);
                if (res.ok) w = await res.json();
            } catch (e) {
                console.warn('weekly fetch failed', e);
            }
            if (hasProEntitlement()) {
                try {
                    const pr = await api(
                        `/schedules/preview?days=7&telegram_id=${encodeURIComponent(user.id)}`
                    );
                    if (pr.ok) {
                        const pd = await pr.json();
                        const seen = new Set();
                        (pd.days || []).forEach((d) => {
                            (d.wellness_suggestions || []).forEach((s) => {
                                if (s && !seen.has(s)) {
                                    seen.add(s);
                                    wellness.push(s);
                                }
                            });
                        });
                    }
                } catch (e) {
                    console.warn('weekly wellness preview', e);
                }
            }

            const hasData =
                (w.energy && w.energy.some((x) => x && x !== '—')) ||
                (w.coffee && w.coffee.length) ||
                (w.meals && w.meals.length) ||
                (w.sleepPct | 0) > 0;
            const eb = w.energy_breakdown || {};
            const habits = w.habits || {};
            const moodBg = energyMoodDonutStyle(eb);
            const hCoffee = habits.avg_coffee_adherence_pct | 0;
            const hMeal = habits.avg_meal_adherence_pct | 0;
            const sl = w.sleepPct | 0;
            const dLog = (eb.days_logged | 0) || 0;
            const dLogLabel = dLog === 1 ? t('wkD1') : t('wkDN');
            const chk = w.checkin;
            const wkChkLine =
                chk && chk.summary_line
                    ? `<div class="nf-card" style="margin-bottom:12px;">
                        <p class="nf-week-kicker">${escapeHtml(t('wkChkH'))}</p>
                        <p class="nf-checkin-brief">${escapeHtml(chk.summary_line)}</p>
                    </div>`
                    : '';
            $root.innerHTML = `
                <div class="nf-screen nf-week-screen nf-screen--tabbed">
                    <div class="nf-tabbar-body">
                    ${topbarMainTabPage(t('weekTitle'))}
                    <div class="nf-card nf-week-header-card">
                        <p class="nf-week-kicker">${escapeHtml(t('wkKicker'))}</p>
                        <p class="nf-week-lead">${escapeHtml(t('wkRLead'))}</p>
                        <div class="nf-week-date-pill" role="text">
                            <span class="nf-week-range-ico" aria-hidden="true">📅</span>
                            <span class="nf-week-date-pill-txt">${escapeHtml(w.range || '')}</span>
                        </div>
                        ${weekTrendLabel(w.energy_trend)}
                    </div>
                    ${wkChkLine}
                    <section class="nf-week-block nf-week-block--mood" aria-label="${escapeHtml(t('wkMoodH'))}">
                        <h2 class="nf-week-block-title">${escapeHtml(t('wkMoodH'))}</h2>
                        <p class="nf-week-block-desc">${escapeHtml(t('wkMoodB'))}</p>
                    <div class="nf-card nf-week-hero nf-week-mood-card">
                        <div class="nf-week-hero-row">
                            <div class="nf-donut nf-donut--mood" style="background:${moodBg};" role="img" aria-label="${escapeHtml(
                t('wkEgy')
            )}">
                                <div class="nf-donut-hole"></div>
                            </div>
                            <div class="nf-week-hero-copy">
                                <p class="nf-week-hero-stat"><span class="nf-week-hero-stat-n">${dLog}</span> ${dLogLabel} ${escapeHtml(
                t('wkDLog')
            )}</p>
                                <ul class="nf-legend" aria-label="${escapeHtml(t('wkMoodH'))}">
                                    <li><span class="nf-legend-swatch" style="background:#5c6bc0"></span> ${escapeHtml(t('wkLegD'))}</li>
                                    <li><span class="nf-legend-swatch" style="background:#90a4ae"></span> ${escapeHtml(t('wkLegL'))}</li>
                                    <li><span class="nf-legend-swatch" style="background:#26a69a"></span> ${escapeHtml(t('wkLegO'))}</li>
                                    <li><span class="nf-legend-swatch" style="background:#ffca28"></span> ${escapeHtml(t('wkLegG'))}</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    </section>
                    <div class="nf-card nf-week-daily-wrap">
                        <p class="nf-week-section-h">${escapeHtml(t('wkByDay'))}</p>
                        <p class="nf-week-section-sub">${escapeHtml(t('wkByDayB'))}</p>
                        <div class="nf-week-energy">
                        ${[0, 1, 2, 3, 4, 5, 6]
                            .map(
                                (i) => {
                                    const d = t('wkD' + i);
                                    return `<div class="nf-week-day ${energyDayClass(
                                        w.energy ? w.energy[i] : '—'
                                    )}"><span class="nf-week-dow">${d}</span><span class="nf-week-emo" title="${escapeHtml(
                                        d
                                    )}">${w.energy?.[i] || '—'}</span></div>`;
                                }
                            )
                            .join('')}
                        </div>
                    </div>
                    <section class="nf-week-block" aria-label="${escapeHtml(t('wkHab2'))}">
                        <h2 class="nf-week-block-title">${escapeHtml(t('wkHab2'))}</h2>
                        <p class="nf-week-block-desc">${escapeHtml(t('wkHab2B'))}</p>
                        <div class="nf-week-snap-grid">
                        <div class="nf-week-snap-tile">
                            <span class="nf-week-snap-ico" aria-hidden="true">☕</span>
                            <p class="nf-week-snap-kicker">${escapeHtml(t('wkCoff2'))}</p>
                            <div class="nf-donut nf-donut--ring nf-donut--snap nf-donut--coffee-ring" style="--p:${hCoffee}%;" role="img" aria-label="${escapeHtml(
                t('wkCoff2')
            )} ${hCoffee}%">
                                <span class="nf-donut-pct nf-donut-pct--snap">${hCoffee}%</span>
                            </div>
                            <p class="nf-week-snap-hint">${escapeHtml(t('wkAdh'))}</p>
                        </div>
                        <div class="nf-week-snap-tile">
                            <span class="nf-week-snap-ico" aria-hidden="true">🍽</span>
                            <p class="nf-week-snap-kicker">${escapeHtml(t('wkMeal2'))}</p>
                            <div class="nf-donut nf-donut--ring nf-donut--snap nf-donut--meal-ring" style="--p:${hMeal}%;" role="img" aria-label="${escapeHtml(
                t('wkMeal2')
            )} ${hMeal}%">
                                <span class="nf-donut-pct nf-donut-pct--snap">${hMeal}%</span>
                            </div>
                            <p class="nf-week-snap-hint">${escapeHtml(t('wkAdh'))}</p>
                        </div>
                        <div class="nf-week-snap-tile">
                            <span class="nf-week-snap-ico" aria-hidden="true">🌙</span>
                            <p class="nf-week-snap-kicker">${escapeHtml(t('wkSl2'))}</p>
                            <div class="nf-donut nf-donut--ring nf-donut--snap nf-donut--sleep-ring" style="--p:${sl}%;" role="img" aria-label="${escapeHtml(
                t('wkSl2')
            )} ${sl}%">
                                <span class="nf-donut-pct nf-donut-pct--snap">${sl}%</span>
                            </div>
                            <p class="nf-week-snap-hint">${escapeHtml(t('wkFrLog'))}</p>
                        </div>
                    </div>
                    </section>
                    <div class="nf-card nf-week-bars">
                        <p class="nf-week-section-h">${escapeHtml(t('wkBySlot2'))}</p>
                        <p class="nf-week-section-sub">${escapeHtml(t('wkBySlot2B'))}</p>
                        <div class="nf-week-bars-block nf-week-bars-block--coffee">
                            <p class="nf-week-bars-block-title">☕ ${escapeHtml(t('wkCoff2'))}</p>
                    ${(w.coffee || [])
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="nf-week-slot-lab">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div class="nf-meter-fill nf-meter-fill--coffee" style="width:${c.pct}%"></div></div>
                        <div class="nf-week-slot-pct">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                        ${
                            !(w.coffee && w.coffee.length)
                                ? `<p class="nf-muted tiny nf-week-empty">${escapeHtml(t('wkNoBar'))}</p>`
                                : ''
                        }
                        </div>
                        <div class="nf-week-bars-block nf-week-bars-block--meals">
                            <p class="nf-week-bars-block-title">🍽 ${escapeHtml(t('wkMeal2'))}</p>
                    ${(w.meals || [])
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="nf-week-slot-lab">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div class="nf-meter-fill nf-meter-fill--meal" style="width:${c.pct}%"></div></div>
                        <div class="nf-week-slot-pct">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                        ${
                            !(w.meals && w.meals.length)
                                ? `<p class="nf-muted tiny nf-week-empty">${escapeHtml(t('wkNoBar'))}</p>`
                                : ''
                        }
                        </div>
                    </div>
                    ${
                        hasData
                            ? ''
                            : `<p class="nf-week-nudge nf-muted">${escapeHtml(t('wkNudge2'))}</p>`
                    }
                    ${
                        wellness.length
                            ? `<div class="nf-card nf-week-wellness">
                        <p class="nf-week-wellness-title">${escapeHtml(t('wkWTitle'))}</p>
                        <p class="nf-week-wellness-lead">${escapeHtml(t('wkWLead'))}</p>
                        <ul class="nf-week-wellness-list">
                        ${wellness.map((s) => `<li>${escapeHtml(s)}</li>`).join('')}
                        </ul>
                    </div>`
                            : ''
                    }
                </div>
                ${getMainTabBarHtml()}
                </div>`;

            wireMainTabTopbar();
            bindMainTabBar();
        })();
    }

    function renderDayOff() {
        const today = new Date().toISOString().slice(0, 10);
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bdof">← ${escapeHtml(t('back'))}</button>
                    <h1>${escapeHtml(t('dofT'))}</h1>
                    <span></span>
                </div>
                <div class="nf-emoji-big nf-center">😴</div>
                <h2 class="nf-center nf-title">${escapeHtml(t('dofM'))}</h2>
                <p class="nf-center nf-muted">${escapeHtml(t('dofNN'))}</p>
                <p class="nf-field-label">${escapeHtml(t('dofR'))}</p>
                <div class="nf-card nf-select-card">
                    <label class="nf-option">
                        <input type="radio" name="resume" value="tomorrow" checked />
                        <div class="nf-option-body"><strong>${escapeHtml(t('dofTmr'))}</strong></div>
                    </label>
                    <label class="nf-option">
                        <input type="radio" name="resume" value="date" />
                        <div class="nf-option-body"><strong>${escapeHtml(t('dofDt'))}</strong></div>
                    </label>
                    <div style="padding:0 16px 12px;">
                        <input type="date" id="dof-date" class="nf-select" value="${today}" />
                    </div>
                    <label class="nf-option">
                        <input type="radio" name="resume" value="manual" />
                        <div class="nf-option-body"><strong>${escapeHtml(t('dofMan'))}</strong></div>
                    </label>
                </div>
                <div class="nf-row-btns">
                    <button type="button" class="nf-cta" id="dof-confirm">${escapeHtml(t('dofC'))}</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="dof-keep">${escapeHtml(t('dofK'))}</button>
                </div>
                <button type="button" class="nf-cta nf-cta-secondary" id="dof-dash" style="margin-top:12px;">${escapeHtml(
                    t('dofBD')
                )}</button>
            </div>`;
        document.getElementById('bdof').onclick = back;
        document.getElementById('dof-dash').onclick = back;
        document.getElementById('dof-keep').onclick = back;
        document.getElementById('dof-confirm').onclick = async () => {
            renderLoading();
            try {
                const res = await api(`/schedules/dayoff?telegram_id=${user.id}`, {
                    method: 'POST',
                    json: {},
                });
                if (!res.ok) throw new Error('bad');
                await loadUserAndSchedule();
            } catch (e) {
                tg.showAlert(t('errSaveG'));
                render();
            }
        };
    }

    const DEFAULT_TZ_LIST = ['Asia/Tashkent', 'UTC', 'Europe/London', 'America/New_York'];

    function timezoneOptionsHtml(selected) {
        const s = selected || 'Asia/Tashkent';
        const list = [...DEFAULT_TZ_LIST];
        if (!list.includes(s)) list.unshift(s);
        return list.map((z) => `<option value="${escapeHtml(z)}"${z === s ? ' selected' : ''}>${escapeHtml(z)}</option>`).join('');
    }

    function formatProExpiryDate(iso) {
        if (!iso) return '';
        try {
            return new Date(iso).toLocaleDateString(NF_DATE_LOCALE, {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                year: 'numeric',
            });
        } catch (e) {
            return String(iso);
        }
    }

    function leadDaysOptionsHtml(val) {
        const v = String(val || '3');
        return [1, 2, 3]
            .map((n) => `<option value="${n}"${String(n) === v ? ' selected' : ''}>${n}d</option>`)
            .join('');
    }

    function renderSettingsReadOnly() {
        const sched = state.schedule;
        const tz = state.userRow?.timezone || 'Asia/Tashkent';
        $root.innerHTML = `
            <div class="nf-screen nf-screen--tabbed nf-free-settings">
                <div class="nf-tabbar-body">
                ${topbarMainTabPage(t('stTitle'))}
                <p class="nf-free-settings-lead">${escapeHtml(t('stFreeL'))}</p>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">📅 ${escapeHtml(t('stFreeWS'))}</h3>
                    <div>${escapeHtml(t('work'))}: ${escapeHtml(formatTime(sched?.work_start))} – ${escapeHtml(
            formatTime(sched?.work_end)
        )}</div>
                    <div style="margin-top:8px;">${escapeHtml(t('sleep'))}: ${escapeHtml(
                        formatTime(sched?.sleep_start)
                    )} – ${escapeHtml(formatTime(sched?.sleep_end))}</div>
                </div>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">☕ · 🍽 · 💡</h3>
                    <p class="nf-free-note">${escapeHtml(t('stFreeCM'))}</p>
                </div>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">⏰ ${escapeHtml(t('stNotif'))} · ${escapeHtml(t('stTZ'))}</h3>
                    <p class="nf-free-note">${escapeHtml(t('stFreeN'))}</p>
                    <p class="nf-free-tz" style="margin:10px 0 0 0;">${escapeHtml(t('stTZ'))}: <strong>${escapeHtml(
                        tz
                    )}</strong></p>
                </div>
                <button type="button" class="nf-btn-pro nf-btn-pro-wide" id="btn-settings-pro">${escapeHtml(
                    t('proBannerBtn')
                )}</button>
                </div>
                ${getMainTabBarHtml()}
            </div>`;
        wireMainTabTopbar();
        bindMainTabBar();
        document.getElementById('btn-settings-pro').onclick = () => openProInvoice();
    }

    function renderSettings() {
        if (!hasProEntitlement()) {
            state.settingsFocus = null;
            renderSettingsReadOnly();
            return;
        }
        const sched = state.schedule;
        const s = state.settings;
        const tz = state.userRow?.timezone || 'Asia/Tashkent';
        const canCancel = state.userRow?.can_cancel_star_subscription === true;
        const subCancelled = state.userRow?.subscription_cancelled === true;
        const proExp = state.userRow?.pro_expires_at;
        const paidPro = hasActivePaidPro();
        const stars = state.userRow?.pro_price_stars ?? 88;
        const paidNotice = paidPro
            ? `<div class="nf-pro-status-compact" role="status">
                    <span class="nf-pro-status-ico" aria-hidden="true">✓</span>
                    <div class="nf-pro-status-txt">
                        <span class="nf-pro-status-title">${escapeHtml(t('stActive'))}</span>
                        <span class="nf-pro-status-sub">${escapeHtml(t('stProUntil'))} <strong>${escapeHtml(
                            formatProExpiresUser() || '—'
                        )}</strong></span>
                    </div>
                </div>`
            : '';
        const trialPayBlock =
            hasProEntitlement() && !paidPro
                ? `<div class="nf-card nf-card-cta">
                        <h3 class="nf-free-h3" style="margin:0 0 6px;">${escapeHtml(t('stKeep'))}</h3>
                        <p class="nf-muted" style="font-size:0.86rem;margin:0 0 12px;">${escapeHtml(
                            t('stKeepD', stars)
                        )}</p>
                        <button type="button" class="nf-btn-pro nf-btn-pro-wide" id="btn-settings-stars">${escapeHtml(
                            t('stPayStars')
                        )}</button>
                   </div>`
                : '';
        const billingBlock = canCancel
            ? `<div class="nf-card nf-billing-box">
                    <h3 class="nf-free-h3" style="margin:0 0 8px;">💳 ${escapeHtml(t('stBill'))}</h3>
                    <p class="nf-muted" style="margin:0;font-size:0.86rem;line-height:1.45;">${escapeHtml(
                        t('stBillH')
                    )}</p>
                </div>`
            : subCancelled && proExp
            ? `<p class="nf-billing-notice">${escapeHtml(t('stNorenew'))} <strong>${escapeHtml(
                  formatProExpiryDate(proExp)
              )}</strong>.</p>`
            : '';
        const rsX = rotatingShiftsObj();
        const rotPatMeta = patternMetaFromId(rsX.pattern_id);
        const nX = rsX.night || {};
        const dX = rsX.day || {};
        const wsnX = (tm) => escapeHtml(formatTime(tm) || '—');
        const pStart = state.rotatingPattern?.pattern_start_date;
        let pStartNice = '—';
        if (pStart) {
            try {
                pStartNice = new Date(String(pStart) + 'T12:00:00').toLocaleDateString(NF_DATE_LOCALE, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                });
            } catch (e) {
                pStartNice = String(pStart);
            }
        }
        const workSleepBlock = isRotatingServer()
            ? `<div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>🌙 ${escapeHtml(t('stNt'))} · ${escapeHtml(t('stTpl'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-rot-n">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">
                        <div>${escapeHtml(t('work'))}: ${wsnX(nX.work_start)} – ${wsnX(nX.work_end)}</div>
                        <div style="margin-top:6px;">${escapeHtml(t('sleep'))}: ${wsnX(nX.sleep_start)} – ${wsnX(
                  nX.sleep_end
              )}</div>
                    </div>
                </div>
                ${
                    patternHasDayWork()
                        ? `<div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>☀️ ${escapeHtml(t('stDt'))} · ${escapeHtml(t('stTpl'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-rot-d">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">
                        <div>${escapeHtml(t('work'))}: ${wsnX(dX.work_start)} – ${wsnX(dX.work_end)}</div>
                        <div style="margin-top:6px;">${escapeHtml(t('sleep'))}: ${wsnX(dX.sleep_start)} – ${wsnX(
                  dX.sleep_end
              )}</div>
                    </div>
                </div>`
                        : `<p class="nf-muted" style="padding:0 2px 8px;">${escapeHtml(t('stDayHid'))}</p>`
                }
                <div class="nf-card nf-card-pattern-info">
                    <div class="nf-pattern-info-head">
                        <span class="nf-pattern-info-ico" aria-hidden="true">${escapeHtml(rotPatMeta.icon)}</span>
                        <div>
                            <div class="nf-pattern-info-title">${escapeHtml(rotPatMeta.title)}</div>
                            <p class="nf-pattern-info-sub">${escapeHtml(rotPatMeta.sub)}</p>
                        </div>
                    </div>
                    <div class="nf-pattern-info-stats">
                        <div class="nf-pattern-stat">
                            <span class="nf-pattern-stat-l">${escapeHtml(t('stCycle'))}</span>
                            <span class="nf-pattern-stat-v">${escapeHtml(rotPatMeta.days || '—')}</span>
                        </div>
                        <div class="nf-pattern-stat">
                            <span class="nf-pattern-stat-l">${escapeHtml(t('stAnchor'))}</span>
                            <span class="nf-pattern-stat-v">${escapeHtml(pStartNice)}</span>
                        </div>
                    </div>
                    <p class="nf-pattern-info-anchor-hint">${escapeHtml(t('stAnchorH'))}</p>
                </div>`
            : `<div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>📅 ${escapeHtml(t('stWS'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-ws">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">
                        <div>${escapeHtml(t('work'))}: ${escapeHtml(formatTime(sched?.work_start))} – ${escapeHtml(
                  formatTime(sched?.work_end)
              )}</div>
                        <div style="margin-top:6px;">${escapeHtml(t('sleep'))}: ${escapeHtml(
                  formatTime(sched?.sleep_start)
              )} – ${escapeHtml(formatTime(sched?.sleep_end))}</div>
                    </div>
                </div>`;
        const planWindowsBlock = isRotatingServer()
            ? `<div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>${escapeHtml(t('stRemTpl'))} · ${escapeHtml(t('stTpl'))}</h3>
                    </div>
                    <p class="nf-muted" style="font-size:0.84rem;margin:0 0 10px;line-height:1.4;">${escapeHtml(
                        t('stRemL')
                    )}</p>
                    <div class="nf-card">
                        <div class="nf-rot-win-head">🌙 ${escapeHtml(t('stNt'))}</div>
                        <div class="nf-rot-win-row">
                            <span class="nf-rot-win-k">☕ ${escapeHtml(t('stCoff'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-n-co">${escapeHtml(t('stEdit'))}</button>
                        </div>
                        <div class="nf-rot-win-row">
                            <span class="nf-rot-win-k">🍽 ${escapeHtml(t('stMeal'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-n-me">${escapeHtml(t('stEdit'))}</button>
                        </div>
                        <div class="nf-rot-win-row" style="margin-bottom:0;">
                            <span class="nf-rot-win-k">💡 ${escapeHtml(t('stLight'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-n-li">${escapeHtml(t('stEdit'))}</button>
                        </div>
                    </div>
                    ${
                        patternHasDayWork()
                            ? `<div class="nf-card" style="margin-top:10px;">
                        <div class="nf-rot-win-head">☀️ ${escapeHtml(t('stDt'))}</div>
                        <div class="nf-rot-win-row">
                            <span class="nf-rot-win-k">☕ ${escapeHtml(t('stCoff'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-d-co">${escapeHtml(t('stEdit'))}</button>
                        </div>
                        <div class="nf-rot-win-row">
                            <span class="nf-rot-win-k">🍽 ${escapeHtml(t('stMeal'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-d-me">${escapeHtml(t('stEdit'))}</button>
                        </div>
                        <div class="nf-rot-win-row" style="margin-bottom:0;">
                            <span class="nf-rot-win-k">💡 ${escapeHtml(t('stLight'))}</span>
                            <button type="button" class="nf-btn-edit" id="er-d-li">${escapeHtml(t('stEdit'))}</button>
                        </div>
                    </div>`
                            : ''
                    }
                    <div class="nf-card" style="margin-top:10px;">
                        <div class="nf-muted" style="margin-bottom:6px;">${escapeHtml(t('stPrvC'))}</div>
                        <div><span class="nf-evt-coffee">☕</span> ${coffeeSummary(sched)}</div>
                        <div style="margin-top:6px;"><span class="nf-evt-meal">🍽</span> ${mealSummary(sched)}</div>
                        <div style="margin-top:6px;"><span class="nf-evt-light">💡</span> ${lightSummary(sched)}</div>
                    </div>
                </div>`
            : `<div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>☕ ${escapeHtml(t('stCoff'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-co">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">${coffeeSummary(sched)}</div>
                </div>
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>🍽 ${escapeHtml(t('stMeal'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-me">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">${mealSummary(sched)}</div>
                </div>
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>💡 ${escapeHtml(t('stLight'))}</h3>
                        <button type="button" class="nf-btn-edit" id="ed-li">${escapeHtml(t('stEdit'))}</button>
                    </div>
                    <div class="nf-card">${lightSummary(sched)}</div>
                </div>`;
        const showScheduleTypeCard =
            (!isRotatingServer() && (state.userRow?.shift_type === 'constant' || !state.userRow?.shift_type)) ||
            isRotatingServer();
        const scheduleTypeCard = showScheduleTypeCard
            ? `<div class="nf-card nf-settings-action-card nf-card-schedule-type">
                        <h3 class="nf-free-h3" style="margin:0 0 8px;">${escapeHtml(t('stSchType'))}</h3>
                        <p class="nf-muted" style="font-size:0.86rem;margin:0 0 10px;line-height:1.4;">${escapeHtml(
                            t('stSchTypeH')
                        )}</p>
                        <button type="button" class="nf-btn-schedule-type" id="btn-change-schedule-type">${escapeHtml(
                            t('stSchTypeBtn')
                        )}</button>
                   </div>`
            : '';
        $root.innerHTML = `
            <div class="nf-screen nf-screen--tabbed">
                <div class="nf-tabbar-body">
                ${topbarMainTabPage(t('stTitle'))}
                ${paidNotice}
                ${trialPayBlock}
                ${workSleepBlock}
                ${planWindowsBlock}
                ${scheduleTypeCard}
                <p class="nf-field-label">⏰ ${escapeHtml(t('stNotif'))}</p>
                <div class="nf-card">
                    ${toggleRow('🔔 ' + t('stTAll'), 'notifAll', s.notifAll)}
                    ${toggleRow('☕ ' + t('stTC'), 'notifCoffee', s.notifCoffee)}
                    ${toggleRow('🍽 ' + t('stTM'), 'notifMeal', s.notifMeal)}
                    ${toggleRow('💡 ' + t('stTL'), 'notifLight', s.notifLight)}
                    ${toggleRow('😴 ' + t('stTS'), 'notifSleep', s.notifSleep)}
                    ${toggleRow('📝 ' + t('stTEos'), 'notifSummary', s.notifSummary)}
                </div>
                <p class="nf-field-label">🌍 ${escapeHtml(t('stTZ'))}</p>
                <div class="nf-card">
                    <select class="nf-select" id="tz-select">
                        ${timezoneOptionsHtml(tz)}
                    </select>
                </div>
                <p class="nf-field-label">🔄 ${escapeHtml(t('stTrans'))}</p>
                <div class="nf-card">
                    ${toggleRow(t('stTRot'), 'transitionReminders', s.transitionReminders)}
                    <div class="nf-row" style="margin-top:8px;">
                        <span class="nf-muted">${escapeHtml(t('stLead'))}</span>
                        <select class="nf-select" id="lead-days">
                            ${leadDaysOptionsHtml(s.transitionLeadDays)}
                        </select>
                    </div>
                </div>
                ${billingBlock}
                <div class="nf-row-btns">
                    <button type="button" class="nf-cta" id="save-all">${escapeHtml(t('stSave'))}</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="reset-def">${escapeHtml(t('stReset'))}</button>
                </div>
                </div>
                ${getMainTabBarHtml()}
            </div>`;

        wireMainTabTopbar();
        bindMainTabBar();
        const btnStars = document.getElementById('btn-settings-stars');
        if (btnStars) btnStars.onclick = () => openProInvoice();
        const btnSchedType = document.getElementById('btn-change-schedule-type');
        if (btnSchedType) {
            btnSchedType.onclick = () => goToScheduleTypePicker();
        }
        if (isRotatingServer()) {
            const ern = document.getElementById('ed-rot-n');
            if (ern) ern.onclick = () => openEditRotatingTemplate('night');
            const erd = document.getElementById('ed-rot-d');
            if (erd) erd.onclick = () => openEditRotatingTemplate('day');
            const bindRw = (id, shift, kind) => {
                const el = document.getElementById(id);
                if (el) el.onclick = () => openEditRotatingWindows(shift, kind);
            };
            bindRw('er-n-co', 'night', 'coffee');
            bindRw('er-n-me', 'night', 'meal');
            bindRw('er-n-li', 'night', 'light');
            bindRw('er-d-co', 'day', 'coffee');
            bindRw('er-d-me', 'day', 'meal');
            bindRw('er-d-li', 'day', 'light');
        } else {
            const o = document.getElementById('ed-ws');
            if (o) o.onclick = () => openEditWork();
            const oc = document.getElementById('ed-co');
            if (oc) oc.onclick = () => openEditCoffee();
            const om = document.getElementById('ed-me');
            if (om) om.onclick = () => openEditMeals();
            const ol = document.getElementById('ed-li');
            if (ol) ol.onclick = () => openEditLight();
        }
        document.getElementById('save-all').onclick = async () => {
            const tzSel = document.getElementById('tz-select');
            const leadSel = document.getElementById('lead-days');
            if (leadSel) state.settings.transitionLeadDays = leadSel.value;
            const row = await patchUserMe({
                timezone: tzSel ? tzSel.value : tz,
                notification_enabled: state.settings.notifAll,
                notification_prefs: {
                    notifCoffee: state.settings.notifCoffee,
                    notifMeal: state.settings.notifMeal,
                    notifLight: state.settings.notifLight,
                    notifSleep: state.settings.notifSleep,
                    notifSummary: state.settings.notifSummary,
                    transitionReminders: state.settings.transitionReminders,
                    transitionLeadDays: state.settings.transitionLeadDays,
                },
            });
            if (!row) {
                tg.showAlert(t('errSaveSt'));
                return;
            }
            state.userRow = row;
            applyUserSettingsFromUserRow(row);
            tg.showAlert(t('msgSaved'));
            render();
        };
        document.getElementById('reset-def').onclick = () => {
            state.settings = {
                notifAll: true,
                notifCoffee: true,
                notifMeal: true,
                notifLight: true,
                notifSleep: true,
                notifSummary: true,
                transitionReminders: true,
                transitionLeadDays: '3',
            };
            render();
        };

        const leadEl = document.getElementById('lead-days');
        if (leadEl) {
            leadEl.onchange = async () => {
                state.settings.transitionLeadDays = leadEl.value;
                const row = await patchUserMe({ transition_lead_days: leadEl.value });
                if (!row) {
                    tg.showAlert(t('errSaveG'));
                    render();
                    return;
                }
                state.userRow = row;
                applyUserSettingsFromUserRow(row);
            };
        }

        $root.querySelectorAll('.nf-switch').forEach((sw) => {
            sw.addEventListener('click', async () => {
                const k = sw.getAttribute('data-k');
                const prev = state.settings[k];
                const next = !prev;
                state.settings[k] = next;
                sw.classList.toggle('on', next);
                const body =
                    k === 'notifAll'
                        ? { notification_enabled: next }
                        : k === 'transitionReminders'
                          ? { transition_reminders: next }
                          : { notification_prefs: { [k]: next } };
                const row = await patchUserMe(body);
                if (!row) {
                    state.settings[k] = prev;
                    sw.classList.toggle('on', prev);
                    tg.showAlert(t('errSaveG'));
                    return;
                }
                state.userRow = row;
                applyUserSettingsFromUserRow(row);
            });
        });
        consumeSettingsFocus();
    }

    function toggleRow(label, key, on) {
        return `
            <div class="nf-toggle-row">
                <span>${escapeHtml(label)}</span>
                <button type="button" class="nf-switch ${on ? 'on' : ''}" data-k="${escapeHtml(key)}" aria-pressed="${on}"></button>
            </div>`;
    }

    function coffeeSummary(sched) {
        const cw = sched?.coffee_windows || [];
        return cw.map((w) => w.time).join(' · ') || '—';
    }

    function mealSummary(sched) {
        const mw = sched?.meal_windows || [];
        return mw.map((w) => w.time).join(' · ') || '—';
    }

    function lightSummary(sched) {
        const bw = sched?.brightness_windows || [];
        return bw.map((w) => w.time).join(' · ') || '—';
    }

    function openEditRotatingWindows(shift, kind, prefill) {
        if (!isRotatingServer() || !state.rotatingPattern) {
            tg.showAlert(t('alRotL'));
            return;
        }
        if (shift === 'day' && !patternHasDayWork()) {
            tg.showAlert(t('alPatNoDay'));
            return;
        }
        const sh = { ...rotatingShiftsObj() };
        const sec = { ...(sh[shift] || {}) };
        const key =
            kind === 'coffee' ? 'coffee_windows' : kind === 'meal' ? 'meal_windows' : 'brightness_windows';
        let arr = Array.isArray(prefill)
            ? [...prefill]
            : Array.isArray(sec[key])
              ? [...sec[key]]
              : [];
        const labelFor = (i) => {
            if (kind === 'coffee') {
                if (i === 0) return t('mdlCoff1');
                if (i === 1) return t('mdlCoff2');
                return t('mdlCoffI', i + 1);
            }
            if (kind === 'meal') return t('mdlMealI', i + 1);
            return t('mdlRemI', i);
        };
        const n = Math.max(kind === 'meal' ? 1 : 2, arr.length);
        while (arr.length < n) {
            const def = {
                time: '12:00',
                message:
                    kind === 'coffee'
                        ? '☕ ' + t('stCoff')
                        : kind === 'meal'
                          ? '🍽 ' + t('stMeal')
                          : '💡 ' + t('stLight'),
                type: 'custom',
            };
            arr.push(def);
        }
        const shLabel = shift === 'night' ? t('stNt') : t('stDt');
        const kindL = kind === 'coffee' ? t('stCoff') : kind === 'meal' ? t('stMeal') : t('stLight');
        const title = (shift === 'night' ? '🌙 ' : '☀️ ') + shLabel + ' · ' + kindL;
        const rows = arr
            .map((w, i) => {
                const tm = w.time || '12:00';
                const lab = labelFor(i);
                return `<p class="nf-field-label">${escapeHtml(lab)}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || '')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(t('stTimeL'))}</span>${selectTimeHtml(
                    '',
                    tm,
                    `rw-${i}`
                )}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mrw-close">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(title)}</h1>
                <span></span>
            </div>
            ${rows}
            <button type="button" class="nf-cta-secondary nf-btn-add-slot" id="mrw-add">+ ${escapeHtml(t('mdlAN'))}</button>
            <p class="nf-sub">${escapeHtml(t('mdlMrot', shLabel))}</p>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mrw-save">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mrw-can">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('mrw-close').onclick = closeModal;
        document.getElementById('mrw-can').onclick = closeModal;
        const addBtn = document.getElementById('mrw-add');
        if (addBtn) {
            addBtn.onclick = () => {
                const next = arr.map((w, i) => ({
                    ...w,
                    time: (document.getElementById(`rw-${i}`) || {}).value || w.time || '12:00',
                }));
                next.push({
                    time: '12:00',
                    message:
                        kind === 'coffee'
                            ? '☕ ' + t('stCoff')
                            : kind === 'meal'
                              ? '🍽 ' + t('stMeal')
                              : '💡 ' + t('stLight'),
                    type: 'custom',
                });
                closeModal();
                openEditRotatingWindows(shift, kind, next);
            };
        }
        document.getElementById('mrw-save').onclick = async () => {
            const next = arr.map((w, i) => ({
                ...w,
                time: document.getElementById(`rw-${i}`).value,
            }));
            const nextSec = { ...sec, [key]: next };
            const payload = { [shift]: nextSec };
            closeModal();
            renderLoading();
            try {
                const res = await api(`/schedules/rotating?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: payload,
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    state.screen = 'settings';
                    render();
                    return;
                }
                state.rotatingPattern = data;
                await loadUserAndSchedule();
                state.screen = 'settings';
                state.stack = ['dashboard'];
                render();
            } catch (e) {
                console.error(e);
                tg.showAlert(t('errNet'));
                state.screen = 'settings';
                render();
            }
        };
    }

    function openEditRotatingTemplate(which) {
        if (!isRotatingServer() || !state.rotatingPattern) {
            tg.showAlert(t('alRotL'));
            return;
        }
        const sh = { ...rotatingShiftsObj() };
        const sec = which === 'day' ? sh.day || {} : sh.night || {};
        const ws = formatTime(sec.work_start) || (which === 'day' ? '07:00' : '19:00');
        const we = formatTime(sec.work_end) || (which === 'day' ? '19:00' : '07:00');
        const ss = formatTime(sec.sleep_start) || (which === 'day' ? '22:00' : '08:00');
        const se = formatTime(sec.sleep_end) || (which === 'day' ? '06:00' : '16:00');
        const whichLabel = which === 'day' ? t('stDt') : t('stNt');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="m-close-rt">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(t('mdlRt', whichLabel))}</h1>
                <span></span>
            </div>
            <p class="nf-field-label">🌙 ${escapeHtml(t('work'))}</p>
            <div class="nf-row"><span>${escapeHtml(t('sWS'))}</span>${selectTimeHtml('', ws, 'rt-ws')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(t('sWE'))}</span>${selectTimeHtml(
                '',
                we,
                'rt-we'
            )}</div>
            <p class="nf-field-label">😴 ${escapeHtml(t('sleep'))}</p>
            <div class="nf-row"><span>${escapeHtml(t('sSS'))}</span>${selectTimeHtml('', ss, 'rt-ss')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(t('sSE'))}</span>${selectTimeHtml(
                '',
                se,
                'rt-se'
            )}</div>
            <p class="nf-sub">${escapeHtml(t('mdlMws2'))}</p>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="m-savert">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="m-canrt">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('m-close-rt').onclick = closeModal;
        document.getElementById('m-canrt').onclick = closeModal;
        document.getElementById('m-savert').onclick = async () => {
            const wss = document.getElementById('rt-ws').value;
            const wse = document.getElementById('rt-we').value;
            const sss = document.getElementById('rt-ss').value;
            const sse = document.getElementById('rt-se').value;
            const o = workSleepOverlapError(wss, wse, sss, sse);
            if (o) {
                tg.showAlert(o);
                return;
            }
            const payload = {
                [which === 'day' ? 'day' : 'night']: {
                    work_start: wss,
                    work_end: wse,
                    sleep_start: sss,
                    sleep_end: sse,
                },
            };
            closeModal();
            renderLoading();
            try {
                const res = await api(`/schedules/rotating?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: payload,
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    state.screen = 'settings';
                    render();
                    return;
                }
                state.rotatingPattern = data;
                await loadUserAndSchedule();
                state.screen = 'settings';
                state.stack = ['dashboard'];
                render();
            } catch (e) {
                console.error(e);
                tg.showAlert(t('errNet'));
                state.screen = 'settings';
                render();
            }
        };
    }

    function openEditWork() {
        const sched = state.schedule || {};
        const ws = formatTime(sched.work_start) || '22:00';
        const we = formatTime(sched.work_end) || '06:00';
        const ss = formatTime(sched.sleep_start) || '08:00';
        const se = formatTime(sched.sleep_end) || '16:00';
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="m-close">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(t('mdlTws'))}</h1>
                <span></span>
            </div>
            <p class="nf-field-label">🌙 ${escapeHtml(t('work'))}</p>
            <div class="nf-row"><span>${escapeHtml(t('sWS'))}</span>${selectTimeHtml('', ws, 'mw-s')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(t('sWE'))}</span>${selectTimeHtml(
                '',
                we,
                'mw-e'
            )}</div>
            <p class="nf-field-label">😴 ${escapeHtml(t('sleep'))}</p>
            <div class="nf-row"><span>${escapeHtml(t('sSS'))}</span>${selectTimeHtml('', ss, 'ms-s')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(t('sSE'))}</span>${selectTimeHtml(
                '',
                se,
                'ms-e'
            )}</div>
            <p class="nf-sub">${escapeHtml(t('mdlMws'))}</p>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="m-save">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="m-can">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('m-close').onclick = closeModal;
        document.getElementById('m-can').onclick = closeModal;
        document.getElementById('m-save').onclick = async () => {
            const wss = document.getElementById('mw-s').value;
            const wse = document.getElementById('mw-e').value;
            const sss = document.getElementById('ms-s').value;
            const sse = document.getElementById('ms-e').value;
            const o = workSleepOverlapError(wss, wse, sss, sse);
            if (o) {
                tg.showAlert(o);
                return;
            }
            const payload = {
                work_start: wss,
                work_end: wse,
                sleep_start: sss,
                sleep_end: sse,
            };
            closeModal();
            renderLoading();
            try {
                const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: payload,
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    state.screen = 'settings';
                    render();
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after work/sleep save');
                state.screen = 'settings';
                state.stack = ['dashboard'];
                render();
            } catch (e) {
                tg.showAlert(t('errSaveSt'));
                state.screen = 'settings';
                render();
            }
        };
    }

    function openEditCoffee(prefill) {
        const sched = state.schedule || {};
        let cw = Array.isArray(prefill) ? [...prefill] : [...(sched.coffee_windows || [])];
        const n = Math.max(2, cw.length);
        while (cw.length < n) {
            cw.push({
                time: '22:00',
                message: '☕ ' + t('stCoff'),
                type: cw.length ? 'mid_shift' : 'pre_work',
            });
        }
        const coffLab = (i) => (i === 0 ? t('mdlCoff1') : i === 1 ? t('mdlCoff2') : t('mdlCoffI', i + 1));
        const rows = cw
            .map((w, i) => {
                const tm = w.time || '22:00';
                return `<p class="nf-field-label">${escapeHtml(coffLab(i))}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || t('stCoff'))}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(
                t('stTimeL')
            )}</span>${selectTimeHtml('', tm, `c-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mc-close">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(t('stCoff'))}</h1>
                <span></span>
            </div>
            ${rows}
            <button type="button" class="nf-cta-secondary nf-btn-add-slot" id="mc-add">+ ${escapeHtml(t('mdlAN'))}</button>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mc-save">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mc-can">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('mc-close').onclick = closeModal;
        document.getElementById('mc-can').onclick = closeModal;
        const addCoffee = document.getElementById('mc-add');
        if (addCoffee) {
            addCoffee.onclick = () => {
                const next = cw.map((w, i) => ({
                    ...w,
                    time: (document.getElementById(`c-${i}`) || {}).value || w.time || '22:00',
                }));
                next.push({ time: '12:00', message: '☕ ' + t('stCoff'), type: 'mid_shift' });
                closeModal();
                openEditCoffee(next);
            };
        }
        document.getElementById('mc-save').onclick = async () => {
            const next = cw.map((w, i) => ({
                ...w,
                time: document.getElementById(`c-${i}`).value,
            }));
            try {
                const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: { coffee_windows: next },
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after coffee save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert(t('errSaveSt'));
            }
        };
    }

    function openEditMeals(prefill) {
        const sched = state.schedule || {};
        let mw = Array.isArray(prefill) ? [...prefill] : [...(sched.meal_windows || [])];
        const n = Math.max(1, mw.length);
        while (mw.length < n) {
            mw.push({ time: '12:00', message: '🍽 ' + t('stMeal'), type: 'mid_shift' });
        }
        const rows = mw
            .map((w, i) => {
                const tm = w.time || '12:00';
                return `<p class="nf-field-label">${escapeHtml(t('mdlMealI', i + 1))}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || t('stMeal'))}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(
                t('stTimeL')
            )}</span>${selectTimeHtml('', tm, `m-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mm-close">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(t('stMeal'))}</h1>
                <span></span>
            </div>
            ${rows}
            <button type="button" class="nf-cta-secondary nf-btn-add-slot" id="mm-add">+ ${escapeHtml(t('mdlAN'))}</button>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mm-save">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mm-can">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('mm-close').onclick = closeModal;
        document.getElementById('mm-can').onclick = closeModal;
        const addMeal = document.getElementById('mm-add');
        if (addMeal) {
            addMeal.onclick = () => {
                const next = mw.map((w, i) => ({
                    ...w,
                    time: (document.getElementById(`m-${i}`) || {}).value || w.time || '12:00',
                }));
                next.push({ time: '12:00', message: '🍽 ' + t('stMeal'), type: 'mid_shift' });
                closeModal();
                openEditMeals(next);
            };
        }
        document.getElementById('mm-save').onclick = async () => {
            const next = mw.map((w, i) => ({
                ...w,
                time: document.getElementById(`m-${i}`).value,
            }));
            try {
                const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: { meal_windows: next },
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after meal save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert(t('errSaveSt'));
            }
        };
    }

    function openEditLight(prefill) {
        const sched = state.schedule || {};
        let bw = Array.isArray(prefill) ? [...prefill] : [...(sched.brightness_windows || [])];
        const n = Math.max(1, bw.length);
        while (bw.length < n) {
            bw.push({
                time: '21:00',
                message: '💡 ' + t('stLight'),
                type: 'dim',
                action: 'dim_lights',
            });
        }
        const rows = bw
            .map((w, i) => {
                const tm = w.time || '21:00';
                return `<p class="nf-field-label">${escapeHtml(t('mdlRemI', i))}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || t('stLight'))}</div>
            <div class="nf-row" style="margin-top:8px;"><span>${escapeHtml(
                t('stTimeL')
            )}</span>${selectTimeHtml('', tm, `l-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="ml-close">←</button>
                <h1 style="font-size:1rem;">${escapeHtml(t('mdlLig'))}</h1>
                <span></span>
            </div>
            ${rows}
            <button type="button" class="nf-cta-secondary nf-btn-add-slot" id="ml-add">+ ${escapeHtml(t('mdlAN'))}</button>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="ml-save">${escapeHtml(t('stSave'))}</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="ml-can">${escapeHtml(t('mdlCan'))}</button>
            </div>`);
        document.getElementById('ml-close').onclick = closeModal;
        document.getElementById('ml-can').onclick = closeModal;
        const addLight = document.getElementById('ml-add');
        if (addLight) {
            addLight.onclick = () => {
                const next = bw.map((w, i) => ({
                    ...w,
                    time: (document.getElementById(`l-${i}`) || {}).value || w.time || '21:00',
                }));
                next.push({
                    time: '22:00',
                    message: '💡 ' + t('stLight'),
                    type: 'dim',
                    action: 'dim_lights',
                });
                closeModal();
                openEditLight(next);
            };
        }
        document.getElementById('ml-save').onclick = async () => {
            const next = bw.map((w, i) => ({
                ...w,
                time: document.getElementById(`l-${i}`).value,
            }));
            try {
                const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                    method: 'PATCH',
                    json: { brightness_windows: next },
                });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) {
                    tg.showAlert(data.error || t('errSaveSt'));
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after light save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert(t('errSaveSt'));
            }
        };
    }

    function summaryCheckInPayload(localDateStr, coffees, meals) {
        const getVal = (k) => {
            const el = $root.querySelector(`input[data-k="${k}"]`);
            return el ? Number(el.value) : null;
        };
        const energy = getVal('energy');
        const sleep_quality = getVal('sleepq');
        const coffee = coffees.map((c, i) => ({
            time: c.time,
            rating: getVal(`co-${i}`),
        }));
        const mealResponses = meals.map((m, i) => ({
            time: m.time,
            rating: getVal(`me-${i}`),
        }));
        return {
            telegram_id: user.id,
            date: localDateStr,
            energy,
            sleep_quality,
            responses: { coffee, meals: mealResponses },
        };
    }

    function dlRadioGroup(name, options, selected) {
        return options
            .map(
                (o) =>
                    `<label class="nf-dl-choice"><input type="radio" name="${name}" value="${o.v}"${o.v === selected ? ' checked' : ''}/><span>${escapeHtml(o.l)}</span></label>`
            )
            .join('');
    }

    function openDetailedLog(localDateStr, coffees, meals) {
        const latOpts = [
            { v: 'lt15', l: t('dlLa0') },
            { v: '15-30', l: t('dlLa1') },
            { v: '30-60', l: t('dlLa2') },
            { v: 'gt60', l: t('dlLa3') },
        ];
        const roomOpts = [
            { v: 'dark', l: t('dlRo0') },
            { v: 'dim', l: t('dlRo1') },
            { v: 'light', l: t('dlRo2') },
        ];
        const tempOpts = [
            { v: 'cool', l: t('dlTe0') },
            { v: 'comfortable', l: t('dlTe1') },
            { v: 'warm', l: t('dlTe2') },
        ];
        const ynN = () => [
            { v: '0', l: t('no') },
            { v: '1', l: t('yes') },
        ];
        const ynY = () => [
            { v: '1', l: t('yes') },
            { v: '0', l: t('no') },
        ];

        const html = `
<div class="nf-detailed-inner">
    <div class="nf-dl-header">
        <button type="button" class="nf-back" id="dl-close" aria-label="${escapeHtml(t('mdlCan'))}">←</button>
        <div>
            <h2 class="nf-dl-title">${escapeHtml(t('dlT'))}</h2>
            <p class="nf-dl-sub">${escapeHtml(t('dlS'))}</p>
        </div>
    </div>
    <div class="nf-dl-scroll">
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">${escapeHtml(t('dlSleep'))}</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlBed'))}</span>
                <div class="nf-dl-row">${selectTimeHtml('', '22:00', 'dl-bed')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlWake'))}</span>
                <div class="nf-dl-row">${selectTimeHtml('', '08:00', 'dl-wake')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlFall'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-slat', latOpts, 'lt15')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlNight'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-night', ynN(), '0')}</div>
                <div class="nf-dl-subfield" id="dl-night-count-wrap" style="display:none;">
                    <span class="nf-dl-label">${escapeHtml(t('dlNW'))}</span>
                    <input type="number" class="nf-dl-num" id="dl-night-count" min="1" max="20" value="1" />
                </div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlRoom'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-room', roomOpts, 'dark')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlTemp'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-temp', tempOpts, 'comfortable')}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">${escapeHtml(t('dlCaf'))}</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlCups'))}</span>
                <select class="nf-select" id="dl-cups" aria-label="${escapeHtml(t('dlCups'))}">
                    <option value="0">0</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4+</option>
                </select>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlLastC'))}</span>
                <div class="nf-dl-row">${selectTimeHtml('', '14:00', 'dl-lastcaf')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlC6'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-caf6', ynN(), '0')}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">${escapeHtml(t('dlLS'))}</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlScr'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-scr', ynN(), '0')}</div>
                <div class="nf-dl-subfield" id="dl-screens-wrap" style="display:none;">
                    <span class="nf-dl-label">${escapeHtml(t('dlScrM'))}</span>
                    <input type="number" class="nf-dl-num" id="dl-screens-min" min="0" max="600" value="15" />
                </div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlBright'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-bright', ynY(), '1')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlDim'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-dim', ynY(), '1')}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">${escapeHtml(t('dlMeal'))}</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlLastM'))}</span>
                <div class="nf-dl-row">${selectTimeHtml('', '20:00', 'dl-lastmeal')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlAte'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-ate', ynN(), '0')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlHung'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-hungry', ynN(), '0')}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">${escapeHtml(t('dlWE'))}</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlTired'))}</span>
                <div class="nf-dl-row">${selectTimeHtml('', '03:00', 'dl-tired')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlBreak'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-breaks', ynY(), '1')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">${escapeHtml(t('dlStress'))}</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-stress', ynN(), '0')}</div>
                <div class="nf-dl-subfield" id="dl-stress-wrap" style="display:none;">
                    <span class="nf-dl-label">${escapeHtml(t('dlStN'))}</span>
                    <textarea class="nf-dl-note" id="dl-stress-note" maxlength="2000" placeholder="${escapeHtml(
                        t('dlStP')
                    )}"></textarea>
                </div>
            </div>
        </section>
    </div>
    <div class="nf-dl-footer">
        <button type="button" class="nf-cta" id="dl-save">${escapeHtml(t('dlSD'))}</button>
        <button type="button" class="nf-cta nf-cta-secondary" id="dl-skip">${escapeHtml(t('dlSk'))}</button>
    </div>
</div>`;

        openModal(html, { sheetClass: 'nf-detailed-sheet', closeOnBackdrop: false });

        const sheet = $modal.querySelector('.modal-sheet');
        const q = (sel) => sheet.querySelector(sel);
        const syncNight = () => {
            const on = q('input[name="dl-night"][value="1"]')?.checked;
            const w = q('#dl-night-count-wrap');
            if (w) w.style.display = on ? 'block' : 'none';
        };
        const syncScr = () => {
            const on = q('input[name="dl-scr"][value="1"]')?.checked;
            const w = q('#dl-screens-wrap');
            if (w) w.style.display = on ? 'block' : 'none';
        };
        const syncStress = () => {
            const on = q('input[name="dl-stress"][value="1"]')?.checked;
            const w = q('#dl-stress-wrap');
            if (w) w.style.display = on ? 'block' : 'none';
        };
        sheet.querySelectorAll('input[name="dl-night"]').forEach((r) => r.addEventListener('change', syncNight));
        sheet.querySelectorAll('input[name="dl-scr"]').forEach((r) => r.addEventListener('change', syncScr));
        sheet.querySelectorAll('input[name="dl-stress"]').forEach((r) => r.addEventListener('change', syncStress));
        syncNight();
        syncScr();
        syncStress();

        const closeD = () => closeModal();
        q('#dl-close').onclick = closeD;
        q('#dl-skip').onclick = closeD;

        q('#dl-save').onclick = async () => {
            const checked = (name) => q(`input[name="${name}"]:checked`)?.value;
            const nightYes = checked('dl-night') === '1';
            const nightWakings = nightYes ? Math.max(1, parseInt(q('#dl-night-count')?.value || '1', 10) || 1) : 0;
            const scrYes = checked('dl-scr') === '1';
            const scrMin = scrYes ? Math.max(0, parseInt(q('#dl-screens-min')?.value || '0', 10) || 0) : null;
            const stressYes = checked('dl-stress') === '1';
            const cups = Math.min(4, Math.max(0, parseInt(q('#dl-cups')?.value || '0', 10) || 0));
            const payload = {
                telegram_id: user.id,
                date: localDateStr,
                bed_time: q('#dl-bed')?.value || null,
                wake_time: q('#dl-wake')?.value || null,
                sleep_latency: checked('dl-slat'),
                night_wakings: nightWakings,
                room_darkness: checked('dl-room'),
                temperature: checked('dl-temp'),
                caffeine_cups: cups,
                last_caffeine_time: q('#dl-lastcaf')?.value || null,
                caffeine_after_6pm: checked('dl-caf6') === '1',
                screens_before_bed: scrYes,
                screens_minutes: scrMin,
                bright_light_morning: checked('dl-bright') === '1',
                dim_lights_before_sleep: checked('dl-dim') === '1',
                last_meal_time: q('#dl-lastmeal')?.value || null,
                ate_near_bedtime: checked('dl-ate') === '1',
                hungry_during_sleep: checked('dl-hungry') === '1',
                tired_at: q('#dl-tired')?.value || null,
                took_breaks: checked('dl-breaks') === '1',
                stress: stressYes,
                stress_note: stressYes ? (q('#dl-stress-note')?.value || '').trim() || null : null,
            };
            try {
                const r1 = await api('/summaries', { method: 'POST', json: summaryCheckInPayload(localDateStr, coffees, meals) });
                if (!r1.ok) throw new Error('sum');
                const r2 = await api('/summaries/detailed', { method: 'POST', json: payload });
                if (!r2.ok) throw new Error('det');
                tg.showAlert(t('alDL'));
                closeModal();
                back();
            } catch (e) {
                console.error(e);
                tg.showAlert(t('alDLE'));
            }
        };
    }

    function renderSummary() {
        const sched = state.schedule || {};
        const d = new Date();
        const coffees = (sched.coffee_windows || []).slice(0, 2);
        const meals = (sched.meal_windows || []).slice(0, 6);
        const localDateStr = d.toISOString().slice(0, 10);
        const hasHabitSlots = coffees.length > 0 || meals.length > 0;

        const slider = (id, label, minL, maxL) => {
            const rid = `nf-r-${id.replace(/[^a-z0-9_-]/gi, '-')}`;
            return `
            <div class="nf-slider-block nf-summary-slider">
                <div class="nf-slider-label">
                    <span class="nf-slider-title">${label}</span>
                    <output class="nf-range-val" for="${rid}">2</output>
                </div>
                <input type="range" class="nf-range" id="${rid}" min="1" max="4" value="2" step="1" data-k="${id}" />
                <div class="nf-range-ticks" aria-hidden="true"><span>1</span><span>2</span><span>3</span><span>4</span></div>
                <div class="nf-scale" aria-hidden="true"><span>${minL}</span><span>${maxL}</span></div>
            </div>`;
        };

        const dateLong = d.toLocaleDateString(NF_DATE_LOCALE, {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });

        let body = '';
        body += `<header class="nf-checkin-hero" aria-label="${escapeHtml(t('chkinTitle'))}">
            <h2 class="nf-checkin-hero__title">${escapeHtml(t('chkinHero'))}</h2>
            <p class="nf-checkin-hero__date"><span class="nf-checkin-hero__date-ico" aria-hidden="true">📅</span> ${escapeHtml(
                dateLong
            )}</p>
        </header>`;

        body += `<div class="nf-card nf-checkin-card">
            <div class="nf-checkin-step">
                <span class="nf-checkin-step__num" aria-hidden="true">1</span>
                <div class="nf-checkin-step__main">
                    <h3 class="nf-checkin-step__h">${escapeHtml(t('chkinS1h'))}</h3>
                    <p class="nf-checkin-step__hint">${escapeHtml(t('chkinS1x'))}</p>
                    <p class="nf-checkin-legend" aria-label="">
                        <span class="nf-checkin-legend__item">${escapeHtml(t('chkinLeg'))}</span>
                    </p>
                    ${slider('energy', escapeHtml(t('chkinEnergyRow')), '😫', '⚡')}
                    ${slider('sleepq', escapeHtml(t('chkinSleepRow')), '😫', '😊')}
                </div>
            </div>
        </div>`;

        if (hasHabitSlots) {
            let habitBlock = `<div class="nf-card nf-checkin-card nf-checkin-card--habit">
            <div class="nf-checkin-step">
                <span class="nf-checkin-step__num" aria-hidden="true">2</span>
                <div class="nf-checkin-step__main">
                    <h3 class="nf-checkin-step__h">${escapeHtml(t('chkinS2h'))}</h3>
                    <p class="nf-checkin-step__hint">${escapeHtml(t('chkinS2x'))}</p>`;
            if (coffees.length) {
                habitBlock += `<p class="nf-checkin-subh">☕ ${escapeHtml(t('chkinCof'))}</p>`;
                coffees.forEach((c, i) => {
                    const lab = escapeHtml(t('chkinPlanned', formatTime(c.time)));
                    habitBlock += slider(
                        `co-${i}`,
                        lab,
                        escapeHtml(t('chkinScaleL')),
                        escapeHtml(t('chkinScaleR'))
                    );
                });
            }
            if (meals.length) {
                habitBlock += `<p class="nf-checkin-subh nf-checkin-subh--meals">🍽 ${escapeHtml(t('chkinMeal'))}</p>`;
                meals.forEach((m, i) => {
                    const lab = escapeHtml(t('chkinPlanned', formatTime(m.time)));
                    habitBlock += slider(
                        `me-${i}`,
                        lab,
                        escapeHtml(t('chkinScaleL')),
                        escapeHtml(t('chkinScaleR'))
                    );
                });
            }
            habitBlock += `</div></div></div>`;
            body += habitBlock;
        } else {
            body += `<p class="nf-checkin-note nf-muted" role="note">${escapeHtml(t('chkinNoSlots'))}</p>`;
        }

        $root.innerHTML = `
            <div class="nf-screen nf-summary-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bsum">←</button>
                    <h1>${escapeHtml(t('chkinTitle'))}</h1>
                    <span></span>
                </div>
                <div class="nf-summary-body nf-summary-body--checkin">
                ${body}
                </div>
                <div class="nf-summary-actions">
                    <button type="button" class="nf-cta" id="btn-save-sum">${escapeHtml(t('chkinSave'))}</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="btn-tell-more">${escapeHtml(t('chkinDetail'))}</button>
                </div>
            </div>`;
        $root.querySelectorAll('input.nf-range').forEach((el) => {
            const id = el.getAttribute('id');
            const out = $root.querySelector(`output[for="${id}"]`);
            const sync = () => {
                if (out) out.textContent = el.value;
            };
            el.addEventListener('input', sync);
            el.addEventListener('change', sync);
            sync();
        });
        document.getElementById('bsum').onclick = back;
        document.getElementById('btn-tell-more').onclick = () => openDetailedLog(localDateStr, coffees, meals);
        document.getElementById('btn-save-sum').onclick = async () => {
            try {
                const res = await api('/summaries', {
                    method: 'POST',
                    json: summaryCheckInPayload(localDateStr, coffees, meals),
                });
                if (!res.ok) throw new Error('x');
            } catch (e) {
                console.error(e);
                tg.showAlert(t('errSave'));
                return;
            }

            setEosDoneToday();
            tg.showAlert(t('msgSaved'));
            back();
        };
    }

    function render() {
        syncDocumentLang();
        if (state.clockTimer) clearInterval(state.clockTimer);
        switch (state.screen) {
            case 'loading':
                renderLoading();
                break;
            case 'onboarding':
                renderOnboarding();
                break;
            case 'setup_perm':
                renderSetupPermanent();
                break;
            case 'setup_rot':
                renderSetupRotating();
                break;
            case 'dashboard':
                renderDashboard();
                state.clockTimer = setInterval(() => {
                    if (state.screen === 'dashboard') renderDashboard();
                }, 60000);
                break;
            case 'full':
                renderFullSchedule();
                break;
            case 'suggestions':
                renderSuggestions();
                break;
            case 'weekly':
                renderWeekly();
                break;
            case 'transition':
                renderTransition();
                break;
            case 'dayoff':
                renderDayOff();
                break;
            case 'settings':
                renderSettings();
                break;
            case 'summary':
                renderSummary();
                break;
            default:
                renderLoading();
        }
    }

    async function loadUserAndSchedule() {
        state.stack = [];
        state.rotatingPattern = null;
        try {
            const ur = await api(`/users/me?telegram_id=${user.id}`);
            if (ur.ok) {
                state.userRow = await ur.json();
                applyUserSettingsFromUserRow(state.userRow);
                syncDocumentLang();
            }
        } catch (e) {
            console.warn(e);
        }
        if (isRotatingServer()) {
            try {
                const rp = await api(`/schedules/rotating?telegram_id=${user.id}`);
                if (rp.ok) state.rotatingPattern = await rp.json();
            } catch (e) {
                console.warn('rotating pattern', e);
            }
        }

        try {
            let res = await api(`/schedules/daily/today?telegram_id=${user.id}`);
            if (res.status === 404) {
                res = await api(`/schedules/full?telegram_id=${user.id}`);
            }
            if (!res.ok) {
                state.schedule = null;
                const st = state.userRow && state.userRow.shift_type;
                if (st === 'constant') {
                    state.finishingConstantSetup = true;
                    state.screen = 'setup_perm';
                } else {
                    state.screen = 'onboarding';
                }
                render();
                return;
            }
            state.schedule = await res.json();
            for (const f of ['coffee_windows', 'meal_windows', 'brightness_windows']) {
                if (typeof state.schedule[f] === 'string') {
                    try {
                        state.schedule[f] = JSON.parse(state.schedule[f]);
                    } catch (e) {
                        state.schedule[f] = [];
                    }
                }
            }
        } catch (e) {
            state.schedule = null;
            const st2 = state.userRow && state.userRow.shift_type;
            if (st2 === 'constant') {
                state.finishingConstantSetup = true;
                state.screen = 'setup_perm';
            } else {
                state.screen = 'onboarding';
            }
            render();
            return;
        }

        state.finishingConstantSetup = false;

        try {
            if (localStorage.getItem('nightflow_rotating_demo') === '1') state.rotatingDemo = true;
        } catch (e) {}

        state.screen = 'dashboard';
        render();
    }

    async function boot() {
        if (!user) {
            $root.innerHTML = `<div class="nf-error">${escapeHtml(t('errBoot'))}</div>`;
            return;
        }
        renderLoading();
        await ensureUser();
        await loadUserAndSchedule();
    }

    boot();

    let touchstartY = 0;
    document.addEventListener(
        'touchstart',
        (e) => {
            touchstartY = e.touches[0].screenY;
        },
        { passive: true }
    );
    document.addEventListener(
        'touchend',
        (e) => {
            const touchendY = e.changedTouches[0].screenY;
            if (touchendY - touchstartY > 100 && window.scrollY === 0) {
                loadUserAndSchedule();
            }
        },
        { passive: true }
    );
})();
