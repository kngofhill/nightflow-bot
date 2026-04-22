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
        onboardingType: 'constant',
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
    };

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
        const label = name || 'Time';
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
            <h3 class="nf-tp-title">Set time</h3>
            <p class="nf-tp-sub">5-minute steps</p>
            <div class="nf-tp-cols">
                <div class="nf-tp-col">
                    <div class="nf-tp-lab">Hour</div>
                    <div class="nf-tp-scroll">${hBtns}</div>
                </div>
                <div class="nf-tp-mid">:</div>
                <div class="nf-tp-col">
                    <div class="nf-tp-lab">Min</div>
                    <div class="nf-tp-scroll" data-nf-tp-mcol="1">${mBtns}</div>
                </div>
            </div>
            <div class="nf-tp-preview" data-nf-tp-preview>${pad2(selH)}:${pad2(selM)}</div>
            <div class="nf-tp-actions">
                <button type="button" class="nf-cta nf-cta-secondary" data-nf-tp-cancel>Cancel</button>
                <button type="button" class="nf-cta" data-nf-tp-ok>Apply</button>
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
        return d.toLocaleDateString(undefined, {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });
    }

    function formatRangeDate(d1, d2) {
        const a = d1.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        const b = d2.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
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

    function parseTimeToMinutes(t) {
        if (!t || typeof t !== 'string') return 0;
        const [h, m] = t.split(':').map(Number);
        return (h || 0) * 60 + (m || 0);
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
            return { line: '⏰ Add your work hours', sub: 'Open Settings when you have Pro to edit', icon: '⏰' };
        }
        const now = new Date();
        const candidates = [];
        const add = (time, label, icon) => {
            if (!time) return;
            const at = nextOccurrenceAfterNow(time, now);
            if (at) {
                candidates.push({ at, label, icon, time: formatTime(time) });
            }
        };
        add(sched.work_start, 'Shift starts', '🌙');
        add(sched.work_end, 'Shift ends', '🏁');
        add(sched.sleep_start, 'Bedtime', '😴');
        add(sched.sleep_end, 'Wake', '☀️');
        if (!candidates.length) {
            return { line: '⏰ Next on your schedule', sub: '—', icon: '⏰' };
        }
        candidates.sort((a, b) => a.at - b.at);
        const next = candidates[0];
        const bestDelta = (next.at - now) / 60000;
        const h = Math.floor(Math.max(0, bestDelta) / 60);
        const m = Math.round(Math.max(0, bestDelta) % 60);
        const shortLabel = (next.label || '').split('.')[0];
        return {
            line: `${next.icon} ${shortLabel} · ${next.time}`,
            sub: `in ${h}h ${m}m`,
            icon: next.icon,
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
            const t = formatTime(time);
            const lab = clean(label) || 'Event';
            const k = `${t}|${icon}|${lab}`;
            if (seen.has(k)) return;
            seen.add(k);
            const m = parseTimeToMinutes(t);
            ev.push({
                time: t,
                label: lab,
                icon,
                kind: kind || 'other',
                m,
                sort: timeSortKeyForSchedule(t, schedule),
            });
        };

        if (schedule.work_start) {
            push(schedule.work_start, 'Shift starts', '🌙', 'work_start');
        }
        if (schedule.work_end) {
            push(schedule.work_end, 'Shift ends', '🏁', 'work_end');
        }
        if (schedule.sleep_start) {
            push(schedule.sleep_start, 'Bedtime', '😴', 'sleep_start');
        }
        if (schedule.sleep_end) {
            push(schedule.sleep_end, 'Wake', '☀️', 'sleep_end');
        }
        (schedule.meal_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || 'Meal', '🍽️', 'meal');
        });
        (schedule.coffee_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || 'Coffee', '☕', 'coffee');
        });
        (schedule.brightness_windows || []).forEach((w) => {
            push(w.time, (w && w.message) || 'Light', '💡', 'light');
        });

        ev.sort((a, b) => a.sort - b.sort);
        return ev;
    }

    function hasProEntitlement() {
        return !!(state.userRow && state.userRow.has_pro_entitlement);
    }

    function hasActivePaidPro() {
        return !!(state.userRow && state.userRow.active_paid_pro);
    }

    function formatProExpiresUser() {
        const s = state.userRow && state.userRow.pro_expires_at;
        if (!s) return '';
        try {
            const d = new Date(s);
            if (Number.isNaN(d.getTime())) return '';
            return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
        } catch (e) {
            return '';
        }
    }

    function getNextEvent(schedule) {
        if (!hasProEntitlement()) {
            return getNextCoreEvent(schedule);
        }
        const raw = collectEvents(schedule);
        if (!raw.length) {
            return { line: '⏰ No upcoming reminders', sub: 'Add times in Settings', icon: '⏰' };
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
        return {
            line: `${next.icon} ${shortLabel} · ${next.time}`,
            sub: `in ${h}h ${m}m`,
            icon: next.icon,
        };
    }

    function shiftTitle(st) {
        if (st === 'night') return '🌙 NIGHT SHIFT';
        if (st === 'day') return '☀️ DAY SHIFT';
        if (st === 'evening') return '🌆 EVENING SHIFT';
        return 'SHIFT';
    }

    function go(screen, pushStack) {
        const proOnly = ['full', 'suggestions', 'weekly', 'summary', 'transition'];
        if (proOnly.includes(screen) && !hasProEntitlement()) {
            tg.showAlert(
                'This area is part of Nightflow Pro. Use “Upgrade to Pro” on the home screen to unlock it.'
            );
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

    async function openProInvoice() {
        if (hasActivePaidPro()) {
            tg.showAlert(
                `You already have an active Pro subscription until ${
                    formatProExpiresUser() || 'the end of your current period'
                }. No need to subscribe again.`
            );
            return;
        }
        try {
            const res = await api('/subscription/invoice-link', { method: 'POST', json: {} });
            const data = await res.json().catch(() => ({}));
            if (res.status === 409) {
                tg.showAlert(
                    data.error ||
                        'You already have an active Pro subscription. No need to subscribe again.'
                );
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
                        tg.showAlert('Welcome to Nightflow Pro!');
                    }
                });
            } else {
                tg.openLink(url);
            }
        } catch (e) {
            console.warn(e);
            tg.showAlert('Open the bot chat and send /subscribe to pay with Stars.');
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
        $root.innerHTML = '<div class="nf-loading">Loading…</div>';
    }

    function renderOnboarding() {
        const type = state.onboardingType || 'constant';
        $root.innerHTML = `
            <div class="nf-screen nf-center" style="padding-top:24px;">
                <h1 class="nf-brand">🌙 NIGHTFLOW</h1>
                <p class="nf-tagline">"Your body's guide through the night"</p>
                <div class="nf-card nf-select-card">
                    <div class="nf-select-header">SELECT YOUR SCHEDULE TYPE</div>
                    <label class="nf-option">
                        <input type="radio" name="stype" value="constant" ${type === 'constant' ? 'checked' : ''}/>
                        <div class="nf-option-body">
                            <strong>PERMANENT NIGHT SHIFT</strong>
                            <span>Same hours every shift</span>
                        </div>
                    </label>
                    <label class="nf-option">
                        <input type="radio" name="stype" value="rotating" ${type === 'rotating' ? 'checked' : ''}/>
                        <div class="nf-option-body">
                            <strong>ROTATING SCHEDULE</strong>
                            <span>Shifts change in a pattern</span>
                        </div>
                    </label>
                </div>
                <button type="button" class="nf-cta" style="margin-top:20px;" id="btn-onb-continue">CONTINUE</button>
            </div>`;
        document.getElementById('btn-onb-continue').onclick = () => {
            const r = document.querySelector('input[name="stype"]:checked');
            state.onboardingType = r ? r.value : 'constant';
            go(state.onboardingType === 'constant' ? 'setup_perm' : 'setup_rot', false);
        };
    }

    function renderSetupPermanent() {
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btn-sp-back">← Back</button>
                    <h1>Set Up Permanent</h1>
                    <span class="nf-clock">${escapeHtml(nowClockStr())}</span>
                </div>
                <p class="nf-title">WORK HOURS</p>
                <div class="nf-card">
                    <div class="nf-row"><span>Start</span>${selectTimeHtml('work_start', '22:00', 'ws')}</div>
                    <div class="nf-row" style="margin-top:10px;"><span>End</span>${selectTimeHtml('work_end', '06:00', 'we')}</div>
                </div>
                <p class="nf-title">SLEEP HOURS</p>
                <div class="nf-card">
                    <div class="nf-row"><span>Start</span>${selectTimeHtml('sleep_start', '08:00', 'ss')}</div>
                    <div class="nf-row" style="margin-top:10px;"><span>End</span>${selectTimeHtml('sleep_end', '16:00', 'se')}</div>
                </div>
                <button type="button" class="nf-cta" id="btn-create-const">CREATE SCHEDULE</button>
            </div>`;
        document.getElementById('btn-sp-back').onclick = () => go('onboarding', false);
        initTimePickerButtons($root);
        document.getElementById('btn-create-const').onclick = async () => {
            const ws = document.getElementById('ws').value;
            const we = document.getElementById('we').value;
            const ss = document.getElementById('ss').value;
            const se = document.getElementById('se').value;
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
                    $root.innerHTML = `<div class="nf-error">${escapeHtml(err.error || 'Could not save')}</div>`;
                    return;
                }
                state.rotatingDemo = false;
                try {
                    localStorage.removeItem('nightflow_rotating_demo');
                } catch (e) {}
                await loadUserAndSchedule();
            } catch (e) {
                console.error(e);
                $root.innerHTML = '<div class="nf-error">Network error</div>';
            }
        };
    }

    const PATTERN_PRESETS = [
        { label: '2 nights, 2 days, 2 off', value: 'n2d2o2' },
        { label: '4 nights, 3 off', value: 'n4o3' },
        { label: 'Custom (demo)', value: 'custom' },
    ];

    function renderSetupRotating() {
        const today = new Date().toISOString().slice(0, 10);
        state.dayOffDate = state.dayOffDate || today;
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btn-sr-back">← Back</button>
                    <h1>Rotating Setup</h1>
                    <span class="nf-clock">${escapeHtml(nowClockStr())}</span>
                </div>
                <p class="nf-field-label">📅 START DATE</p>
                <div class="nf-card">
                    <input type="date" id="rot-start" class="nf-select" value="${today}" />
                </div>
                <p class="nf-field-label">📝 PATTERN</p>
                <div class="nf-card">
                    <select id="rot-pattern" class="nf-select">
                        ${PATTERN_PRESETS.map(
                            (p) => `<option value="${p.value}">${escapeHtml(p.label)}</option>`
                        ).join('')}
                    </select>
                </div>
                <p class="nf-field-label">⚙️ SHIFT HOURS</p>
                <div class="nf-card">
                    <div style="margin-bottom:12px;"><strong>🌙 NIGHT</strong></div>
                    <div class="nf-row"><span>Work</span>${selectTimeHtml('', '22:00', 'rn_ws')}${selectTimeHtml('', '06:00', 'rn_we')}</div>
                    <div class="nf-row" style="margin-top:8px;"><span>Sleep</span>${selectTimeHtml('', '08:00', 'rn_ss')}${selectTimeHtml('', '16:00', 'rn_se')}</div>
                    <hr style="border:none;border-top:1px solid var(--nf-border);margin:14px 0;" />
                    <div style="margin-bottom:12px;"><strong>☀️ DAY</strong></div>
                    <div class="nf-row"><span>Work</span>${selectTimeHtml('', '06:00', 'rd_ws')}${selectTimeHtml('', '14:00', 'rd_we')}</div>
                    <div class="nf-row" style="margin-top:8px;"><span>Sleep</span>${selectTimeHtml('', '22:00', 'rd_ss')}${selectTimeHtml('', '06:00', 'rd_se')}</div>
                    <hr style="border:none;border-top:1px solid var(--nf-border);margin:14px 0;" />
                    <div><strong>😴 OFF</strong><div class="nf-muted" style="margin-top:6px;">No schedule</div></div>
                </div>
                <button type="button" class="nf-cta" id="btn-create-rot">CREATE SCHEDULE</button>
                <p class="nf-sub nf-center">Rotating sync with the server is not available yet — demo mode will show the rotating dashboard.</p>
            </div>`;
        document.getElementById('btn-sr-back').onclick = () => go('onboarding', false);
        initTimePickerButtons($root);
        document.getElementById('btn-create-rot').onclick = async () => {
            renderLoading();
            const ws = document.getElementById('rn_ws').value;
            const we = document.getElementById('rn_we').value;
            const ss = document.getElementById('rn_ss').value;
            const se = document.getElementById('rn_se').value;
            try {
                await api('/users/me', {
                    method: 'POST',
                    json: {
                        telegram_id: user.id,
                        username: user.username || '',
                        first_name: user.first_name || '',
                        shift_type: 'rotating',
                    },
                });
                const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                    method: 'POST',
                    json: {
                        work_start: ws,
                        work_end: we,
                        sleep_start: ss,
                        sleep_end: se,
                    },
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    $root.innerHTML = `<div class="nf-error">${escapeHtml(err.error || 'Could not save')}</div>`;
                    return;
                }
                state.rotatingDemo = true;
                try {
                    localStorage.setItem('nightflow_rotating_demo', '1');
                } catch (e) {}
                await loadUserAndSchedule();
            } catch (e) {
                console.error(e);
                $root.innerHTML = '<div class="nf-error">Network error</div>';
            }
        };
    }

    function mockSuggestions() {
        return [
            {
                title: '☕ 01:30 COFFEE',
                body: 'Missed 4 times this week.',
                action: 'MOVE TO 01:00',
            },
            {
                title: '🍽️ 02:00 MEAL',
                body: 'Missed 5 times this week.',
                action: 'MOVE TO 01:30',
            },
            {
                title: '😴 SLEEP WINDOW',
                body: 'Deficit: 8 hours this week.',
                action: 'ADD 30 MINUTES',
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

    function weekTrendLabel(t) {
        if (t === 'up') {
            return '<div class="nf-trend nf-trend--up"><span class="nf-trend-ico">↑</span> Energy: stronger toward the end of the week</div>';
        }
        if (t === 'down') {
            return '<div class="nf-trend nf-trend--down"><span class="nf-trend-ico">↓</span> Energy: heavier than early in the week</div>';
        }
        if (t === 'steady') {
            return '<div class="nf-trend nf-trend--mid"><span class="nf-trend-ico">→</span> Energy: stable across the week</div>';
        }
        return '';
    }

    function mockTransition() {
        return {
            headline: 'In 2 days, you switch to Day Shift',
            blocks: [
                {
                    title: 'TOMORROW (Last Night)',
                    lines: ['Sleep: 08:00 – 12:00 (4h)', 'Awake: 12:00 – 22:00 (10h)'],
                },
                {
                    title: 'DAY AFTER (First Day)',
                    lines: ['Sleep: 22:00 – 06:00', 'Work: 06:00 – 14:00'],
                },
            ],
            caffeine: 'Stop by 16:00',
            light: 'Bright after waking, dim by 20:00',
        };
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
            hasProEntitlement() && !isOff && shouldShowReportCard(sched.work_start, sched.work_end);
        const next = isOff ? null : getNextEvent(sched);
        const rotating = isRotatingUi();

        let body = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <span style="width:3rem;"></span>
                    <h1>🌙 NIGHTFLOW</h1>
                    <span class="nf-clock">${escapeHtml(clock)}</span>
                </div>
                <div class="nf-card">
                    <div class="nf-card-label">Today</div>
                    <div class="nf-today-line">${escapeHtml(formatLongDate(today).toUpperCase())}</div>
                    ${rotating && !isOff ? `<div class="nf-today-sub">🌙 Night · Day 1 of 2</div>` : ''}
                </div>`;

        if (isOff) {
            body += `
                <div class="nf-card">
                    <div class="nf-shift-title off">DAY OFF</div>
                    <p class="nf-muted nf-center" style="margin:0;">No work scheduled today. Rest up.</p>
                </div>`;
        } else {
            const isFree = !hasProEntitlement();
            const paidPro = hasActivePaidPro();
            // TESTING ONLY — revert ?? fallback to 50 before production
            const stars = state.userRow?.pro_price_stars ?? 1;
            if (paidPro) {
                body += `<div class="nf-pro-active-banner" role="status">
                    <div class="nf-pro-active-title">Pro active</div>
                    <p class="nf-pro-active-sub">Paid through ${escapeHtml(
                        formatProExpiresUser() || '—'
                    )}</p>
                </div>`;
            } else if (isFree) {
                body += `<div class="nf-upgrade-hero" role="region" aria-label="Upgrade to Pro">
                    <div class="nf-upgrade-hero-title">Nightflow Pro</div>
                    <p class="nf-upgrade-hero-text">Get notifications, full schedule, weekly insights, and more.</p>
                    <p class="nf-upgrade-hero-price">${stars} Stars / 30 days</p>
                    <button type="button" class="nf-btn-pro" id="btn-dash-pro">Upgrade to Pro</button>
                </div>`;
            }
            body += `
                <div class="nf-card">
                    <div class="nf-shift-title ${escapeHtml(st)}">${shiftTitle(st)}</div>
                    <div class="nf-bar-row"><span class="nf-bar-label">Work</span><div style="flex:1;"><div class="nf-bar-times"><span>${escapeHtml(formatTime(sched.work_start))}</span><span>${escapeHtml(formatTime(sched.work_end))}</span></div><div class="nf-bar-track"></div></div></div>
                    <div class="nf-bar-row"><span class="nf-bar-label">Sleep</span><div style="flex:1;"><div class="nf-bar-times"><span>${escapeHtml(formatTime(sched.sleep_start))}</span><span>${escapeHtml(formatTime(sched.sleep_end))}</span></div><div class="nf-bar-track"></div></div></div>
                </div>
                <div class="nf-card nf-next-card">
                    <div class="nf-next-label">⏰ Next</div>
                    <div class="nf-next-main">${escapeHtml(next.line)}</div>
                    <div class="nf-next-sub">${escapeHtml(next.sub)}</div>
                </div>`;
            if (isFree) {
                body += `<div class="nf-free-timeline-hint">
                    <span class="nf-timeline-hint-ico" aria-hidden="true">✨</span>
                    <p>Upgrade to Pro to see your optimized coffee, meal, and light times.</p>
                </div>`;
            } else if (!paidPro) {
                body += `<p class="nf-trial-hint">You’re on a Pro trial. Subscribe with Stars in Settings to keep Pro after the trial.</p>`;
            }

            if (rotating && hasProEntitlement()) {
                body += `
                    <div class="nf-card nf-transition-card">
                        <div class="nf-card-label">Transition</div>
                        <div style="font-weight:600;">🔄 NIGHT → DAY in 2 days</div>
                        <button type="button" class="nf-cta nf-btn" id="btn-dash-trans">VIEW TRANSITION</button>
                    </div>`;
            }

            if (showReport) {
                body += `
                    <div class="nf-card nf-report-card">
                        <div class="nf-card-label">📝 REPORT YOUR DAY</div>
                        <button type="button" class="nf-cta" id="btn-dash-report">LOG END OF SHIFT</button>
                    </div>`;
            }
        }

        const navInner = hasProEntitlement()
            ? `
                    <button type="button" class="nf-nav-btn" data-nav="dayoff"><span class="nf-nav-ico">😴</span>DAY OFF</button>
                    <button type="button" class="nf-nav-btn" data-nav="full"><span class="nf-nav-ico">📅</span>FULL</button>
                    <button type="button" class="nf-nav-btn" data-nav="weekly"><span class="nf-nav-ico">📊</span>WEEKLY</button>
                    <button type="button" class="nf-nav-btn" data-nav="settings"><span class="nf-nav-ico">⚙️</span>SETTINGS</button>`
            : `
                    <button type="button" class="nf-nav-btn" data-nav="dayoff"><span class="nf-nav-ico">😴</span>DAY OFF</button>
                    <button type="button" class="nf-nav-btn" data-nav="settings"><span class="nf-nav-ico">⚙️</span>SETTINGS</button>`;
        const navClass = hasProEntitlement() ? 'nf-bottom-nav' : 'nf-bottom-nav nf-bottom-nav--free';
        body += `
                <div class="${navClass}">
                    ${navInner}
                </div>
            </div>`;

        $root.innerHTML = body;

        $root.querySelectorAll('[data-nav]').forEach((btn) => {
            btn.addEventListener('click', () => {
                const n = btn.getAttribute('data-nav');
                if (n === 'dayoff') go('dayoff', true);
                if (n === 'full') go('full', true);
                if (n === 'weekly') go('weekly', true);
                if (n === 'settings') go('settings', true);
            });
        });

        const proBtn = document.getElementById('btn-dash-pro');
        if (proBtn) proBtn.onclick = () => openProInvoice();

        const tr = document.getElementById('btn-dash-trans');
        if (tr) tr.onclick = () => go('transition', true);
        const rep = document.getElementById('btn-dash-report');
        if (rep) rep.onclick = () => go('summary', true);
    }

    function formatTime(t) {
        if (!t) return '--:--';
        if (typeof t === 'string') return t.slice(0, 5);
        return String(t);
    }

    function renderFullSchedule() {
        const sched = state.schedule;
        if (!sched || sched.shift_type === 'off') {
            $root.innerHTML = `
                <div class="nf-screen"><div class="nf-topbar">
                    <button type="button" class="nf-back" id="bf">← BACK</button>
                    <h1>Full Schedule</h1>
                    <span></span>
                </div><p class="nf-muted">No events today.</p></div>`;
            document.getElementById('bf').onclick = back;
            return;
        }

        const events = collectEvents(sched);
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
        const lines = events
            .map((e) => {
                const cls = kc(e.kind);
                return `<li class="nf-tl-item ${cls}">
                    <span class="nf-tl-dot" aria-hidden="true"></span>
                    <div class="nf-tl-body">
                        <span class="nf-tl-time">${escapeHtml(e.time)}</span>
                        <div class="nf-tl-line">
                            <span class="nf-tl-ico" aria-hidden="true">${escapeHtml(e.icon)}</span>
                            <span class="nf-tl-text">${escapeHtml(e.label)}</span>
                        </div>
                    </div>
                </li>`;
            })
            .join('');

        const hasWE =
            events.some((x) => x.kind === 'work_end') && events.some((x) => x.kind === 'sleep_start');
        const bridge =
            hasWE
                ? '<p class="nf-tl-bridge">Wind down from work into sleep — your recovery window is below.</p>'
                : '';

        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bf">← BACK</button>
                    <h1>Full Schedule</h1>
                    <span></span>
                </div>
                <p class="nf-muted" style="margin-top:0;">TODAY · ${escapeHtml(
                    new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                )} · ${escapeHtml((sched.shift_type || '').toUpperCase())}</p>
                ${bridge}
                <ul class="nf-tl nf-timeline">${lines}</ul>
                <p class="nf-muted nf-schedule-foot">Chronological order for your shift. Colors: work, sleep, coffee, meals, light.</p>
                <button type="button" class="nf-cta nf-cta-secondary" id="bfd">BACK TO DASHBOARD</button>
            </div>`;
        document.getElementById('bf').onclick = back;
        document.getElementById('bfd').onclick = back;
    }

    function renderSuggestions() {
        $root.innerHTML = '<div class="nf-loading">Loading...</div>';

        (async () => {
            let items = mockSuggestions();
            try {
                const res = await api(`/schedules/suggestions?telegram_id=${user.id}`);
                if (res.ok) {
                    const data = await res.json();
                    items = data.items || data.suggestions || data || items;
                }
            } catch (e) {
                console.warn('suggestions fetch failed', e);
            }

            if (!Array.isArray(items)) items = [];

            $root.innerHTML = `
                <div class="nf-screen">
                    <div class="nf-topbar">
                        <button type="button" class="nf-back" id="bsu">← BACK</button>
                        <h1>Suggestions</h1>
                        <span></span>
                    </div>
                    ${
                        items.length
                            ? items
                                  .map(
                                      (it) => `
                        <div class="nf-suggestion">
                            <h3>${escapeHtml(it.title)}</h3>
                            <p>${escapeHtml(it.body)}</p>
                            <p style="font-weight:600;">→ ${escapeHtml(it.action)}</p>
                            <div class="nf-row-btns">
                                <button type="button" class="nf-cta js-apply">APPLY</button>
                                <button type="button" class="nf-cta nf-cta-secondary js-adj">ADJUST IN SETTINGS</button>
                            </div>
                        </div>`
                                  )
                                  .join('')
                            : `<div class="nf-card nf-center"><div style="font-weight:600;">No suggestions this week.</div><div class="nf-muted" style="margin-top:6px;">Keep logging your day.</div></div>`
                    }
                    <button type="button" class="nf-cta nf-cta-secondary" id="bsub">BACK TO DASHBOARD</button>
                </div>`;

            document.getElementById('bsu').onclick = back;
            document.getElementById('bsub').onclick = back;
            $root.querySelectorAll('.js-adj').forEach((b) => {
                b.addEventListener('click', () => go('settings', true));
            });
            $root.querySelectorAll('.js-apply').forEach((b, i) => {
                b.addEventListener('click', async () => {
                    b.setAttribute('disabled', 'true');
                    try {
                        const res = await api(`/schedules/suggestions/apply?telegram_id=${user.id}`, {
                            method: 'POST',
                            json: { suggestion_index: i },
                        });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) {
                            tg.showAlert(
                                (data && data.error) || 'Could not apply this suggestion. Try again.'
                            );
                            b.removeAttribute('disabled');
                            return;
                        }
                        applyConstantRowToState(data);
                        const ok = await reloadScheduleFromApi();
                        if (!ok) console.warn('reload after suggestion apply');
                        tg.showAlert('Your schedule was updated.');
                        go('settings', true);
                    } catch (e) {
                        console.warn('apply suggestion', e);
                        tg.showAlert('Could not apply. Check your connection.');
                    }
                    b.removeAttribute('disabled');
                });
            });
        })();
    }

    function renderTransition() {
        const m = mockTransition();
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="btr">← BACK</button>
                    <h1>Night → Day</h1>
                    <span></span>
                </div>
                <p style="font-weight:600;">📅 ${escapeHtml(m.headline)}</p>
                <p class="nf-field-label">YOUR TRANSITION PLAN</p>
                ${m.blocks
                    .map(
                        (b) => `
                <div class="nf-card">
                    <div style="font-weight:700;margin-bottom:8px;">${escapeHtml(b.title)}</div>
                    ${b.lines.map((l) => `<div class="nf-muted">${escapeHtml(l)}</div>`).join('')}
                </div>`
                    )
                    .join('')}
                <p>☕ CAFFEINE: ${escapeHtml(m.caffeine)}</p>
                <p>💡 LIGHT: ${escapeHtml(m.light)}</p>
                <button type="button" class="nf-cta" id="btn-rem">SET REMINDERS</button>
            </div>`;
        document.getElementById('btr').onclick = back;
        document.getElementById('btn-rem').onclick = () =>
            tg.showAlert('Reminder scheduling hooks to the bot when live.');
    }

    function renderWeekly() {
        $root.innerHTML = '<div class="nf-loading">Loading...</div>';

        (async () => {
            let w = mockWeekly();
            try {
                const res = await api(`/reports/weekly?telegram_id=${user.id}`);
                if (res.ok) w = await res.json();
            } catch (e) {
                console.warn('weekly fetch failed', e);
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
            const dLogLabel = dLog === 1 ? 'day' : 'days';
            $root.innerHTML = `
                <div class="nf-screen nf-week-screen">
                    <div class="nf-topbar">
                        <button type="button" class="nf-back" id="bw">← BACK</button>
                        <h1>Weekly Report</h1>
                        <span></span>
                    </div>
                    <div class="nf-week-head">📅 ${escapeHtml(w.range || '')}</div>
                    ${weekTrendLabel(w.energy_trend)}
                    <div class="nf-card nf-week-hero">
                        <div class="nf-week-hero-row">
                            <div class="nf-donut nf-donut--mood" style="background:${moodBg};">
                                <div class="nf-donut-hole"></div>
                            </div>
                            <div class="nf-week-hero-copy">
                                <p class="nf-week-hero-title">Mood mix (logged days)</p>
                                <p class="nf-muted nf-week-hero-sub">${dLog} ${dLogLabel} with energy logs</p>
                                <ul class="nf-legend" aria-label="Energy distribution">
                                    <li><span class="nf-legend-swatch" style="background:#5c6bc0"></span> Drained</li>
                                    <li><span class="nf-legend-swatch" style="background:#90a4ae"></span> Low</li>
                                    <li><span class="nf-legend-swatch" style="background:#26a69a"></span> OK</li>
                                    <li><span class="nf-legend-swatch" style="background:#ffca28"></span> Great</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div class="nf-card" style="margin-bottom:12px;">
                        <p class="nf-meter-label" style="margin-top:0;">Daily energy</p>
                        <div class="nf-week-energy">
                        ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                            .map(
                                (d, i) =>
                                    `<div class="nf-week-day"><span class="nf-week-dow">${d}</span><span class="nf-week-emo" title="${d}">${
                                        w.energy?.[i] || '—'
                                    }</span></div>`
                            )
                            .join('')}
                        </div>
                    </div>
                    <div class="nf-week-habits">
                        <div class="nf-card nf-week-donut-card">
                            <p class="nf-meter-label" style="margin-top:0;">Coffee (avg)</p>
                            <div class="nf-donut nf-donut--ring" style="--p:${hCoffee};"><span class="nf-donut-pct">${hCoffee}%</span></div>
                            <p class="nf-muted tiny" style="text-align:center;">Adherence on scheduled coffee times</p>
                        </div>
                        <div class="nf-card nf-week-donut-card">
                            <p class="nf-meter-label" style="margin-top:0;">Meals (avg)</p>
                            <div class="nf-donut nf-donut--ring" style="--p:${hMeal};"><span class="nf-donut-pct">${hMeal}%</span></div>
                            <p class="nf-muted tiny" style="text-align:center;">Adherence on scheduled meal times</p>
                        </div>
                    </div>
                    <p class="nf-meter-label">Per-slot coffee</p>
                    ${(w.coffee || [])
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="tiny">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div class="nf-meter-fill" style="width:${c.pct}%"></div></div>
                        <div class="tiny">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                    <p class="nf-meter-label">Per-slot meals</p>
                    ${(w.meals || [])
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="tiny">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div class="nf-meter-fill" style="width:${c.pct}%"></div></div>
                        <div class="tiny">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                    <p class="nf-meter-label">Sleep quality (avg)</p>
                    <div class="nf-donut nf-donut--ring nf-donut--wide" style="--p:${sl};"><span class="nf-donut-pct">${sl}%</span></div>
                    <p class="nf-muted tiny" style="text-align:center;margin:0 0 8px;">From end-of-shift check-ins</p>
                    ${
                        hasData
                            ? ''
                            : '<p class="nf-muted" style="text-align:center;padding:4px 8px 12px;">Log end-of-shift check-ins to build your week-over-week trends here.</p>'
                    }
                    <button type="button" class="nf-cta nf-cta-secondary" id="btn-sug" style="margin-top:8px;">VIEW SUGGESTIONS</button>
                </div>`;

            document.getElementById('bw').onclick = back;
            document.getElementById('btn-sug').onclick = () => go('suggestions', true);
        })();
    }

    function renderDayOff() {
        const today = new Date().toISOString().slice(0, 10);
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bdof">← BACK</button>
                    <h1>Day Off</h1>
                    <span></span>
                </div>
                <div class="nf-emoji-big nf-center">😴</div>
                <h2 class="nf-center nf-title">DAY OFF MODE</h2>
                <p class="nf-center nf-muted">No notifications today.</p>
                <p class="nf-field-label">RESUME</p>
                <div class="nf-card nf-select-card">
                    <label class="nf-option">
                        <input type="radio" name="resume" value="tomorrow" checked />
                        <div class="nf-option-body"><strong>Tomorrow</strong></div>
                    </label>
                    <label class="nf-option">
                        <input type="radio" name="resume" value="date" />
                        <div class="nf-option-body"><strong>On date</strong></div>
                    </label>
                    <div style="padding:0 16px 12px;">
                        <input type="date" id="dof-date" class="nf-select" value="${today}" />
                    </div>
                    <label class="nf-option">
                        <input type="radio" name="resume" value="manual" />
                        <div class="nf-option-body"><strong>Manually (/resume)</strong></div>
                    </label>
                </div>
                <div class="nf-row-btns">
                    <button type="button" class="nf-cta" id="dof-confirm">CONFIRM</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="dof-keep">KEEP WORKING</button>
                </div>
                <button type="button" class="nf-cta nf-cta-secondary" id="dof-dash" style="margin-top:12px;">BACK TO DASHBOARD</button>
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
                tg.showAlert('Could not set day off');
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
            return new Date(iso).toLocaleDateString(undefined, {
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
            .map(
                (n) =>
                    `<option value="${n}"${String(n) === v ? ' selected' : ''}>${n} day${n > 1 ? 's' : ''}</option>`
            )
            .join('');
    }

    function renderSettingsReadOnly() {
        const sched = state.schedule;
        const tz = state.userRow?.timezone || 'Asia/Tashkent';
        $root.innerHTML = `
            <div class="nf-screen nf-free-settings">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bst">← BACK</button>
                    <h1>Settings</h1>
                    <span></span>
                </div>
                <p class="nf-free-settings-lead">Upgrade to Pro to customize your schedule.</p>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">📅 Work &amp; sleep</h3>
                    <div>WORK: ${escapeHtml(formatTime(sched?.work_start))} – ${escapeHtml(
            formatTime(sched?.work_end)
        )}</div>
                    <div style="margin-top:8px;">SLEEP: ${escapeHtml(
                        formatTime(sched?.sleep_start)
                    )} – ${escapeHtml(formatTime(sched?.sleep_end))}</div>
                </div>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">☕ · 🍽️ · 💡</h3>
                    <p class="nf-free-note">Coffee, meal, and light times are part of Pro — with smart reminders tuned to your shift.</p>
                </div>
                <div class="nf-card nf-free-readonly">
                    <h3 class="nf-free-h3">⏰ Notifications &amp; timezone</h3>
                    <p class="nf-free-note">Pro unlocks notification controls, weekly insights, and timezone changes.</p>
                    <p class="nf-free-tz" style="margin:10px 0 0 0;">Current timezone: <strong>${escapeHtml(
                        tz
                    )}</strong></p>
                </div>
                <button type="button" class="nf-btn-pro nf-btn-pro-wide" id="btn-settings-pro">Upgrade to Pro</button>
            </div>`;
        document.getElementById('bst').onclick = back;
        document.getElementById('btn-settings-pro').onclick = () => openProInvoice();
    }

    function renderSettings() {
        if (!hasProEntitlement()) {
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
        const stars = state.userRow?.pro_price_stars ?? 1;
        const paidNotice = paidPro
            ? `<p class="nf-billing-notice nf-billing-top">Pro (paid) through <strong>${escapeHtml(
                  formatProExpiresUser() || '—'
              )}</strong></p>`
            : '';
        const trialPayBlock =
            hasProEntitlement() && !paidPro
                ? `<div class="nf-card nf-card-cta">
                        <h3 class="nf-free-h3" style="margin:0 0 6px;">Keep Pro with Stars</h3>
                        <p class="nf-muted" style="font-size:0.86rem;margin:0 0 12px;">${stars} Stars / 30 days in Telegram. Extends Pro after your trial.</p>
                        <button type="button" class="nf-btn-pro nf-btn-pro-wide" id="btn-settings-stars">Pay with Stars</button>
                   </div>`
                : '';
        const billingBlock = canCancel
            ? `<div class="nf-card nf-billing-box">
                    <h3 class="nf-free-h3" style="margin:0 0 8px;">💳 Pro billing</h3>
                    <p class="nf-muted" style="margin:0 0 12px;font-size:0.86rem;">Recurring in Telegram. Cancel to stop future Star charges. You keep Pro until your current period ends.</p>
                    <button type="button" class="nf-cta-secondary nf-btn-cancel-sub" id="btn-cancel-sub">Cancel Subscription</button>
                </div>`
            : subCancelled && proExp
            ? `<p class="nf-billing-notice">Your subscription will not renew. You keep Pro access until <strong>${escapeHtml(
                  formatProExpiryDate(proExp)
              )}</strong>.</p>`
            : '';
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bst">← BACK</button>
                    <h1>Settings</h1>
                    <span></span>
                </div>
                ${paidNotice}
                ${trialPayBlock}
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>📅 WORK & SLEEP</h3>
                        <button type="button" class="nf-link" id="ed-ws">EDIT</button>
                    </div>
                    <div class="nf-card">
                        <div>WORK: ${escapeHtml(formatTime(sched?.work_start))} – ${escapeHtml(formatTime(sched?.work_end))}</div>
                        <div style="margin-top:6px;">SLEEP: ${escapeHtml(formatTime(sched?.sleep_start))} – ${escapeHtml(formatTime(sched?.sleep_end))}</div>
                    </div>
                </div>
                <div class="nf-card" style="margin:12px 0 0;">
                    <p class="nf-muted" style="font-size:0.86rem;margin:0 0 10px;line-height:1.45;">
                        <strong>What updates Telegram</strong> — The bot always reads your <strong>current saved</strong> times
                        and your notification toggles. Changing toggles only turns reminder <em>types</em> on or off, not
                        the clock times (those follow what is stored above).
                    </p>
                    <p class="nf-muted" style="font-size:0.86rem;margin:0 0 12px;line-height:1.45;">
                        Editing work &amp; sleep in <strong>EDIT</strong> updates <em>only</em> those four times; it
                        <strong>does not</strong> re-generate coffee, meal, or light slots — that is intentional. Use
                        the button below to run the Nightflow planner again on your <em>current</em> work &amp; sleep.
                    </p>
                    <button type="button" class="nf-cta" id="btn-rebuild-rec">↻ Rebuild recommended schedule</button>
                    <p class="nf-muted" style="font-size:0.8rem;margin:8px 0 0;">Replaces coffee, meal, and light
                        with a new recommendation. Uses the work &amp; sleep times shown in this screen.</p>
                </div>
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>☕ COFFEE TIMES</h3>
                        <button type="button" class="nf-link" id="ed-co">EDIT</button>
                    </div>
                    <div class="nf-card">${coffeeSummary(sched)}</div>
                </div>
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>🍽️ MEAL TIMES</h3>
                        <button type="button" class="nf-link" id="ed-me">EDIT</button>
                    </div>
                    <div class="nf-card">${mealSummary(sched)}</div>
                </div>
                <div class="nf-setting-block">
                    <div class="nf-setting-head">
                        <h3>💡 LIGHT REMINDERS</h3>
                        <button type="button" class="nf-link" id="ed-li">EDIT</button>
                    </div>
                    <div class="nf-card">${lightSummary(sched)}</div>
                </div>
                <p class="nf-field-label">⏰ NOTIFICATIONS</p>
                <div class="nf-card">
                    ${toggleRow('🔔 All Notifications', 'notifAll', s.notifAll)}
                    ${toggleRow('☕ Coffee Reminders', 'notifCoffee', s.notifCoffee)}
                    ${toggleRow('🍽️ Meal Reminders', 'notifMeal', s.notifMeal)}
                    ${toggleRow('💡 Light Reminders', 'notifLight', s.notifLight)}
                    ${toggleRow('😴 Sleep Reminders', 'notifSleep', s.notifSleep)}
                    ${toggleRow('📝 End of Shift Summary', 'notifSummary', s.notifSummary)}
                </div>
                <p class="nf-field-label">🌍 TIMEZONE</p>
                <div class="nf-card">
                    <select class="nf-select" id="tz-select">
                        ${timezoneOptionsHtml(tz)}
                    </select>
                </div>
                <p class="nf-field-label">🔄 TRANSITION</p>
                <div class="nf-card">
                    ${toggleRow('Transition Reminders', 'transitionReminders', s.transitionReminders)}
                    <div class="nf-row" style="margin-top:8px;">
                        <span class="nf-muted">Lead time</span>
                        <select class="nf-select" id="lead-days">
                            ${leadDaysOptionsHtml(s.transitionLeadDays)}
                        </select>
                    </div>
                </div>
                ${billingBlock}
                <div class="nf-row-btns">
                    <button type="button" class="nf-cta" id="save-all">SAVE ALL</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="reset-def">RESET</button>
                </div>
            </div>`;

        document.getElementById('bst').onclick = back;
        const btnStars = document.getElementById('btn-settings-stars');
        if (btnStars) btnStars.onclick = () => openProInvoice();
        document.getElementById('ed-ws').onclick = () => openEditWork();
        document.getElementById('ed-co').onclick = () => openEditCoffee();
        document.getElementById('ed-me').onclick = () => openEditMeals();
        document.getElementById('ed-li').onclick = () => openEditLight();
        const btnRe = document.getElementById('btn-rebuild-rec');
        if (btnRe) {
            btnRe.onclick = async () => {
                if (
                    !window.confirm(
                        'Replace coffee, meal, and light with a new recommendation based on your current work and sleep?'
                    )
                ) {
                    return;
                }
                renderLoading();
                try {
                    const res = await api(`/schedules/constant?telegram_id=${user.id}`, {
                        method: 'POST',
                        json: workSleepPayloadForRebuild(state.schedule),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        tg.showAlert(
                            (data && data.error) || 'Could not rebuild schedule. Check Pro and connection.'
                        );
                        state.screen = 'settings';
                        state.stack = ['dashboard'];
                        render();
                        return;
                    }
                    await loadUserAndSchedule();
                    state.screen = 'settings';
                    state.stack = ['dashboard'];
                    tg.showAlert('Recommended schedule updated — coffee, meal, and light times are refreshed.');
                    render();
                } catch (e) {
                    console.error(e);
                    tg.showAlert('Request failed');
                    state.screen = 'settings';
                    state.stack = ['dashboard'];
                    render();
                }
            };
        }
        const cancelSub = document.getElementById('btn-cancel-sub');
        if (cancelSub) {
            cancelSub.onclick = async () => {
                if (
                    !window.confirm(
                        'Stop automatic renewals? You keep Pro access until the end of your current period.'
                    )
                ) {
                    return;
                }
                try {
                    const res = await api(`/cancel-subscription?telegram_id=${user.id}`, {
                        method: 'POST',
                        json: {},
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) {
                        const parts = [
                            data.error,
                            data.explanation,
                            data.details,
                        ].filter(Boolean);
                        tg.showAlert(parts.length ? parts.join('\n\n') : 'Could not cancel subscription');
                        return;
                    }
                    if (data.user) {
                        state.userRow = { ...state.userRow, ...data.user };
                        applyUserSettingsFromUserRow(state.userRow);
                    } else {
                        const ur = await api(`/users/me?telegram_id=${user.id}`);
                        if (ur.ok) state.userRow = await ur.json();
                    }
                    tg.showAlert(data.message || 'Your subscription will not renew.');
                    render();
                } catch (e) {
                    console.error(e);
                    tg.showAlert('Request failed');
                }
            };
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
                tg.showAlert('Could not save settings');
                return;
            }
            state.userRow = row;
            applyUserSettingsFromUserRow(row);
            tg.showAlert('Settings saved successfully');
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
                    tg.showAlert('Could not save setting');
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
                    tg.showAlert('Could not save setting');
                    return;
                }
                state.userRow = row;
                applyUserSettingsFromUserRow(row);
            });
        });
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

    /** Work/sleep JSON for POST /schedules/constant (full recommit with optimization). */
    function workSleepPayloadForRebuild(sched) {
        const pick = (t, fallback) => {
            const s = formatTime(t);
            return s && s !== '--:--' ? s : fallback;
        };
        return {
            work_start: pick(sched?.work_start, '22:00'),
            work_end: pick(sched?.work_end, '06:00'),
            sleep_start: pick(sched?.sleep_start, '08:00'),
            sleep_end: pick(sched?.sleep_end, '16:00'),
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
                <h1 style="font-size:1rem;">Work & Sleep</h1>
                <span></span>
            </div>
            <p class="nf-field-label">🌙 WORK</p>
            <div class="nf-row"><span>Start</span>${selectTimeHtml('', ws, 'mw-s')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>End</span>${selectTimeHtml('', we, 'mw-e')}</div>
            <p class="nf-field-label">😴 SLEEP</p>
            <div class="nf-row"><span>Start</span>${selectTimeHtml('', ss, 'ms-s')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>End</span>${selectTimeHtml('', se, 'ms-e')}</div>
            <p class="nf-sub">Only work &amp; sleep are updated here. Coffee, meal, and light are <strong>not</strong> recalculated — use
                <strong>Settings → Rebuild recommended schedule</strong> to refresh those from your current work &amp; sleep.</p>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="m-save">SAVE</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="m-can">CANCEL</button>
            </div>`);
        document.getElementById('m-close').onclick = closeModal;
        document.getElementById('m-can').onclick = closeModal;
        document.getElementById('m-save').onclick = async () => {
            const payload = {
                work_start: document.getElementById('mw-s').value,
                work_end: document.getElementById('mw-e').value,
                sleep_start: document.getElementById('ms-s').value,
                sleep_end: document.getElementById('ms-e').value,
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
                    tg.showAlert(data.error || 'Could not save schedule');
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
                tg.showAlert('Could not save schedule');
                state.screen = 'settings';
                render();
            }
        };
    }

    function openEditCoffee() {
        const sched = state.schedule || {};
        let cw = [...(sched.coffee_windows || [])];
        const n = Math.max(2, cw.length);
        while (cw.length < n) {
            cw.push({
                time: '22:00',
                message: '☕ Coffee',
                type: cw.length ? 'mid_shift' : 'pre_work',
            });
        }
        const rows = cw
            .map((w, i) => {
                const t = w.time || '22:00';
                const label = i === 0 ? 'FIRST COFFEE' : i === 1 ? 'SECOND COFFEE' : `COFFEE ${i + 1}`;
                return `<p class="nf-field-label">${label}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || 'Coffee')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>Time</span>${selectTimeHtml('', t, `c-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mc-close">←</button>
                <h1 style="font-size:1rem;">Coffee</h1>
                <span></span>
            </div>
            ${rows}
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mc-save">SAVE</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mc-can">CANCEL</button>
            </div>`);
        document.getElementById('mc-close').onclick = closeModal;
        document.getElementById('mc-can').onclick = closeModal;
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
                    tg.showAlert(data.error || 'Could not save coffee times');
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after coffee save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert('Could not save coffee times');
            }
        };
    }

    function openEditMeals() {
        const sched = state.schedule || {};
        let mw = [...(sched.meal_windows || [])];
        const n = Math.max(1, mw.length);
        while (mw.length < n) {
            mw.push({ time: '12:00', message: '🍽️ Meal', type: 'mid_shift' });
        }
        const rows = mw
            .map((w, i) => {
                const t = w.time || '12:00';
                return `<p class="nf-field-label">MEAL ${i + 1}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || 'Meal')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>Time</span>${selectTimeHtml('', t, `m-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mm-close">←</button>
                <h1 style="font-size:1rem;">Meals</h1>
                <span></span>
            </div>
            ${rows}
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mm-save">SAVE</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mm-can">CANCEL</button>
            </div>`);
        document.getElementById('mm-close').onclick = closeModal;
        document.getElementById('mm-can').onclick = closeModal;
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
                    tg.showAlert(data.error || 'Could not save meal times');
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after meal save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert('Could not save meal times');
            }
        };
    }

    function openEditLight() {
        const sched = state.schedule || {};
        let bw = [...(sched.brightness_windows || [])];
        const n = Math.max(1, bw.length);
        while (bw.length < n) {
            bw.push({
                time: '21:00',
                message: '💡 Light reminder',
                type: 'dim',
                action: 'dim_lights',
            });
        }
        const rows = bw
            .map((w, i) => {
                const t = w.time || '21:00';
                return `<p class="nf-field-label">REMINDER ${i + 1}</p>
            <div class="nf-card"><div class="nf-muted tiny">${escapeHtml(w.message || 'Light')}</div>
            <div class="nf-row" style="margin-top:8px;"><span>Time</span>${selectTimeHtml('', t, `l-${i}`)}</div></div>`;
            })
            .join('');
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="ml-close">←</button>
                <h1 style="font-size:1rem;">Light reminders</h1>
                <span></span>
            </div>
            ${rows}
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="ml-save">SAVE</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="ml-can">CANCEL</button>
            </div>`);
        document.getElementById('ml-close').onclick = closeModal;
        document.getElementById('ml-can').onclick = closeModal;
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
                    tg.showAlert(data.error || 'Could not save light reminders');
                    return;
                }
                applyConstantRowToState(data);
                const ok = await reloadScheduleFromApi();
                if (!ok) console.warn('reloadScheduleFromApi after light save');
                closeModal();
                render();
            } catch (e) {
                tg.showAlert('Could not save light reminders');
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
            { v: 'lt15', l: '< 15 min' },
            { v: '15-30', l: '15-30 min' },
            { v: '30-60', l: '30-60 min' },
            { v: 'gt60', l: '> 60 min' },
        ];
        const roomOpts = [
            { v: 'dark', l: 'Dark' },
            { v: 'dim', l: 'Dim' },
            { v: 'light', l: 'Light' },
        ];
        const tempOpts = [
            { v: 'cool', l: 'Cool' },
            { v: 'comfortable', l: 'Comfortable' },
            { v: 'warm', l: 'Warm' },
        ];

        const html = `
<div class="nf-detailed-inner">
    <div class="nf-dl-header">
        <button type="button" class="nf-back" id="dl-close" aria-label="Close">←</button>
        <div>
            <h2 class="nf-dl-title">Detailed log</h2>
            <p class="nf-dl-sub">Optional · deeper check-in</p>
        </div>
    </div>
    <div class="nf-dl-scroll">
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">SLEEP</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Actual bed time</span>
                <div class="nf-dl-row">${selectTimeHtml('', '22:00', 'dl-bed')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Actual wake time</span>
                <div class="nf-dl-row">${selectTimeHtml('', '08:00', 'dl-wake')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Time to fall asleep</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-slat', latOpts, 'lt15')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Woke up during the night?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-night',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
                <div class="nf-dl-subfield" id="dl-night-count-wrap" style="display:none;">
                    <span class="nf-dl-label">Times woken</span>
                    <input type="number" class="nf-dl-num" id="dl-night-count" min="1" max="20" value="1" />
                </div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Room darkness</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-room', roomOpts, 'dark')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Temperature</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup('dl-temp', tempOpts, 'comfortable')}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">CAFFEINE</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Total cups today</span>
                <select class="nf-select" id="dl-cups" aria-label="Cups of caffeine">
                    <option value="0">0</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4+</option>
                </select>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Last coffee / caffeine time</span>
                <div class="nf-dl-row">${selectTimeHtml('', '14:00', 'dl-lastcaf')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Caffeine after 6pm?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-caf6',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">LIGHT & SCREENS</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Phone or tablet before bed?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-scr',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
                <div class="nf-dl-subfield" id="dl-screens-wrap" style="display:none;">
                    <span class="nf-dl-label">Minutes of screen time</span>
                    <input type="number" class="nf-dl-num" id="dl-screens-min" min="0" max="600" value="15" />
                </div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Bright light within 30 min of waking?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-bright',
                    [
                        { v: '1', l: 'Yes' },
                        { v: '0', l: 'No' },
                    ],
                    '1'
                )}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Dimmed lights ~2h before sleep?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-dim',
                    [
                        { v: '1', l: 'Yes' },
                        { v: '0', l: 'No' },
                    ],
                    '1'
                )}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">MEALS</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Time of last meal before sleep</span>
                <div class="nf-dl-row">${selectTimeHtml('', '20:00', 'dl-lastmeal')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Ate within 2h of bedtime?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-ate',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Hungry during sleep?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-hungry',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
            </div>
        </section>
        <section class="nf-dl-card">
            <h3 class="nf-dl-section-title">WORK & ENERGY</h3>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Most tired during shift at</span>
                <div class="nf-dl-row">${selectTimeHtml('', '03:00', 'dl-tired')}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Took breaks?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-breaks',
                    [
                        { v: '1', l: 'Yes' },
                        { v: '0', l: 'No' },
                    ],
                    '1'
                )}</div>
            </div>
            <div class="nf-dl-field">
                <span class="nf-dl-label">Unusual stress?</span>
                <div class="nf-dl-choice-wrap">${dlRadioGroup(
                    'dl-stress',
                    [
                        { v: '0', l: 'No' },
                        { v: '1', l: 'Yes' },
                    ],
                    '0'
                )}</div>
                <div class="nf-dl-subfield" id="dl-stress-wrap" style="display:none;">
                    <span class="nf-dl-label">Note (optional)</span>
                    <textarea class="nf-dl-note" id="dl-stress-note" maxlength="2000" placeholder="A few words..."></textarea>
                </div>
            </div>
        </section>
    </div>
    <div class="nf-dl-footer">
        <button type="button" class="nf-cta" id="dl-save">SAVE DETAILS</button>
        <button type="button" class="nf-cta nf-cta-secondary" id="dl-skip">SKIP</button>
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
                tg.showAlert('Detailed log saved.');
                closeModal();
                back();
            } catch (e) {
                console.error(e);
                tg.showAlert('Could not save. Try again.');
            }
        };
    }

    function renderSummary() {
        const sched = state.schedule || {};
        const d = new Date();
        const coffees = (sched.coffee_windows || []).slice(0, 2);
        const meals = (sched.meal_windows || []).slice(0, 6);
        const localDateStr = d.toISOString().slice(0, 10);

        const slider = (id, label, minL, maxL) => {
            const rid = `nf-r-${id.replace(/[^a-z0-9_-]/gi, '-')}`;
            return `
            <div class="nf-slider-block">
                <div class="nf-slider-label">
                    <span>${escapeHtml(label)}</span>
                    <output class="nf-range-val" for="${rid}">2</output>
                </div>
                <input type="range" class="nf-range" id="${rid}" min="1" max="4" value="2" step="1" data-k="${id}" />
                <div class="nf-scale" aria-hidden="true"><span>${minL}</span><span>${maxL}</span></div>
            </div>`;
        };

        let html = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bsum">← BACK</button>
                    <h1>End of Shift</h1>
                    <span></span>
                </div>
                <p class="nf-week-head">📅 ${escapeHtml(
                    d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
                )}</p>
                ${slider('energy', 'ENERGY', '😴', '⚡')}
        `;

        coffees.forEach((c, i) => {
            html += slider(
                `co-${i}`,
                `COFFEE (${escapeHtml(c.time)})`,
                '❌',
                '✅'
            );
        });
        meals.forEach((m, i) => {
            html += slider(
                `me-${i}`,
                `MEAL (${escapeHtml(m.time)})`,
                '❌',
                '✅'
            );
        });

        html += `
                ${slider('sleepq', 'SLEEP QUALITY', '😴', '😊')}
                <button type="button" class="nf-cta" id="btn-save-sum">SAVE SUMMARY</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="btn-tell-more" style="margin-top:10px;">TELL ME MORE</button>
            </div>`;

        $root.innerHTML = html;
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
                tg.showAlert('Could not save summary.');
                return;
            }

            tg.showAlert('Saved.');
            back();
        };
    }

    function render() {
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
        try {
            const ur = await api(`/users/me?telegram_id=${user.id}`);
            if (ur.ok) {
                state.userRow = await ur.json();
                applyUserSettingsFromUserRow(state.userRow);
            }
        } catch (e) {
            console.warn(e);
        }

        try {
            let res = await api(`/schedules/daily/today?telegram_id=${user.id}`);
            if (res.status === 404) {
                res = await api(`/schedules/full?telegram_id=${user.id}`);
            }
            if (!res.ok) {
                state.schedule = null;
                state.screen = 'onboarding';
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
            state.screen = 'onboarding';
            render();
            return;
        }

        try {
            if (localStorage.getItem('nightflow_rotating_demo') === '1') state.rotatingDemo = true;
        } catch (e) {}

        state.screen = 'dashboard';
        render();
    }

    async function boot() {
        if (!user) {
            $root.innerHTML =
                '<div class="nf-error">Could not read Telegram user. Open this app from Telegram.</div>';
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
