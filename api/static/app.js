(function () {
    'use strict';

    const API_BASE =
        window.location.origin && window.location.origin !== 'null'
            ? `${window.location.origin}/api/v1`
            : 'https://nightflow-bot-production.up.railway.app/api/v1';

    const tg = window.Telegram.WebApp;
    tg.expand();
    tg.ready();
    tg.setHeaderColor('#12121a');
    tg.setBackgroundColor('#12121a');

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
            for (let m = 0; m < 60; m += 15) {
                out.push(`${pad2(h)}:${pad2(m)}`);
            }
        }
        return out;
    }

    const TIME_OPTS = timeOptions();

    function selectTimeHtml(name, value, id) {
        const v = value || '22:00';
        const opts = TIME_OPTS.map(
            (t) => `<option value="${t}"${t === v ? ' selected' : ''}>${t}</option>`
        ).join('');
        return `<select id="${id}" name="${name}" class="nf-select" aria-label="${name}">${opts}</select>`;
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

    function collectEvents(schedule) {
        const ev = [];
        const push = (time, label, icon) => {
            if (!time) return;
            ev.push({ time, label, icon, m: parseTimeToMinutes(time) });
        };

        const clean = (msg) =>
            String(msg || '')
                .replace(/\s+/g, ' ')
                .trim();

        (schedule.meal_windows || []).forEach((w) => {
            push(w.time, clean(w.message) || 'Meal', '🍽️');
        });
        (schedule.coffee_windows || []).forEach((w) => {
            push(w.time, clean(w.message) || 'Coffee', '☕');
        });
        (schedule.brightness_windows || []).forEach((w) => {
            push(w.time, clean(w.message) || 'Light', '💡');
        });

        ev.sort((a, b) => a.m - b.m);
        return ev;
    }

    function getNextEvent(schedule) {
        const raw = collectEvents(schedule);
        if (!raw.length) {
            return { line: 'No upcoming events', sub: '', icon: '⏰' };
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

    function openModal(html) {
        $modal.innerHTML = `
            <div class="modal-backdrop" data-close="1"></div>
            <div class="modal-sheet">${html}</div>`;
        $modal.classList.add('open');
        $modal.setAttribute('aria-hidden', 'false');
        $modal.querySelector('.modal-backdrop').addEventListener('click', closeModal);
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
        const showReport = !isOff && shouldShowReportCard(sched.work_start, sched.work_end);
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

            if (rotating) {
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

        body += `
                <div class="nf-bottom-nav">
                    <button type="button" class="nf-nav-btn" data-nav="dayoff"><span class="nf-nav-ico">😴</span>DAY OFF</button>
                    <button type="button" class="nf-nav-btn" data-nav="full"><span class="nf-nav-ico">📅</span>FULL</button>
                    <button type="button" class="nf-nav-btn" data-nav="weekly"><span class="nf-nav-ico">📊</span>WEEKLY</button>
                    <button type="button" class="nf-nav-btn" data-nav="settings"><span class="nf-nav-ico">⚙️</span>SETTINGS</button>
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
        const lines = events
            .map(
                (e) =>
                    `<li><span class="nf-list-time">${escapeHtml(e.time)}</span><span>${escapeHtml(e.icon)} ${escapeHtml(e.label)}</span></li>`
            )
            .join('');

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
                <ul class="nf-list">${lines}</ul>
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
            $root.querySelectorAll('.js-apply').forEach((b) => {
                b.addEventListener('click', () => {
                    tg.showAlert('Applied (demo). Connect API to persist.');
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

            $root.innerHTML = `
                <div class="nf-screen">
                    <div class="nf-topbar">
                        <button type="button" class="nf-back" id="bw">← BACK</button>
                        <h1>Weekly Report</h1>
                        <span></span>
                    </div>
                    <div class="nf-week-head">📅 ${escapeHtml(w.range || '')}</div>
                    <p class="nf-meter-label">ENERGY</p>
                    <div class="nf-energy-row">
                        ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                            .map((d, i) => `<span>${d}<br/>${w.energy?.[i] || '—'}</span>`)
                            .join('')}
                    </div>
                    <p class="nf-meter-label">COFFEE</p>
                    ${(
                        w.coffee || []
                    )
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="tiny">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div style="width:${c.pct}%"></div></div>
                        <div class="tiny">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                    <p class="nf-meter-label">MEALS</p>
                    ${(
                        w.meals || []
                    )
                        .map(
                            (c) => `
                    <div class="nf-meter-row">
                        <div class="tiny">${escapeHtml(c.label)}</div>
                        <div class="nf-meter"><div style="width:${c.pct}%"></div></div>
                        <div class="tiny">${c.pct}%</div>
                    </div>`
                        )
                        .join('')}
                    <p class="nf-meter-label">SLEEP</p>
                    <div class="nf-meter"><div style="width:${w.sleepPct || 0}%"></div></div>
                    <button type="button" class="nf-cta nf-cta-secondary" id="btn-sug">VIEW SUGGESTIONS</button>
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

    function renderSettings() {
        const sched = state.schedule;
        const s = state.settings;
        $root.innerHTML = `
            <div class="nf-screen">
                <div class="nf-topbar">
                    <button type="button" class="nf-back" id="bst">← BACK</button>
                    <h1>Settings</h1>
                    <span></span>
                </div>
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
                        <option>Asia/Tashkent</option>
                        <option>UTC</option>
                        <option>Europe/London</option>
                        <option>America/New_York</option>
                    </select>
                </div>
                <p class="nf-field-label">🔄 TRANSITION</p>
                <div class="nf-card">
                    ${toggleRow('Transition Reminders', 'transitionReminders', s.transitionReminders)}
                    <div class="nf-row" style="margin-top:8px;">
                        <span class="nf-muted">Lead time</span>
                        <select class="nf-select" id="lead-days">
                            <option value="1">1 day</option>
                            <option value="2">2 days</option>
                            <option value="3" selected>3 days</option>
                        </select>
                    </div>
                </div>
                <div class="nf-row-btns">
                    <button type="button" class="nf-cta" id="save-all">SAVE ALL</button>
                    <button type="button" class="nf-cta nf-cta-secondary" id="reset-def">RESET</button>
                </div>
            </div>`;

        document.getElementById('bst').onclick = back;
        document.getElementById('ed-ws').onclick = () => openEditWork();
        document.getElementById('ed-co').onclick = () => openEditCoffee();
        document.getElementById('ed-me').onclick = () =>
            tg.showAlert('Meal editor: connect PATCH schedule when API is ready.');
        document.getElementById('ed-li').onclick = () =>
            tg.showAlert('Light editor: connect PATCH schedule when API is ready.');
        document.getElementById('save-all').onclick = () =>
            tg.showAlert('Settings saved locally. Wire /api/v1/settings to persist.');
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

        $root.querySelectorAll('.nf-switch').forEach((sw) => {
            sw.addEventListener('click', () => {
                const k = sw.getAttribute('data-k');
                state.settings[k] = !state.settings[k];
                sw.classList.toggle('on', state.settings[k]);
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
            <p class="nf-sub">When you change work hours, meals, coffee, and light times will recalculate.</p>
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
                    method: 'POST',
                    json: payload,
                });
                if (!res.ok) throw new Error('x');
                await loadUserAndSchedule();
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
        const cw = sched.coffee_windows || [];
        const t0 = cw[0]?.time || '21:30';
        const t1 = cw[1]?.time || '01:30';
        openModal(`
            <div class="nf-topbar" style="margin-bottom:12px;">
                <button type="button" class="nf-back" id="mc-close">←</button>
                <h1 style="font-size:1rem;">Coffee</h1>
                <span></span>
            </div>
            <p class="nf-field-label">FIRST COFFEE</p>
            <div class="nf-card">Current: ${escapeHtml(t0)}<div style="margin-top:8px;">New ${selectTimeHtml('', t0, 'c0')}</div></div>
            <p class="nf-field-label">SECOND COFFEE</p>
            <div class="nf-card">Current: ${escapeHtml(t1)}<div style="margin-top:8px;">New ${selectTimeHtml('', t1, 'c1')}</div></div>
            <div class="nf-row-btns">
                <button type="button" class="nf-cta" id="mc-save">SAVE</button>
                <button type="button" class="nf-cta nf-cta-secondary" id="mc-can">CANCEL</button>
            </div>`);
        document.getElementById('mc-close').onclick = closeModal;
        document.getElementById('mc-can').onclick = closeModal;
        document.getElementById('mc-save').onclick = () => {
            closeModal();
            tg.showAlert('Coffee overrides need a PATCH endpoint; values not saved yet.');
        };
    }

    function renderSummary() {
        const sched = state.schedule || {};
        const d = new Date();
        const coffees = (sched.coffee_windows || []).slice(0, 2);
        const meals = (sched.meal_windows || []).slice(0, 6);

        const slider = (id, label, minL, maxL) => `
            <div class="nf-slider-block">
                <div class="nf-slider-label"><span>${escapeHtml(label)}</span></div>
                <input type="range" class="nf-range" min="1" max="4" value="2" data-k="${id}" />
                <div class="nf-scale"><span>${minL}</span><span>${maxL}</span></div>
            </div>`;

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
            </div>`;

        $root.innerHTML = html;
        document.getElementById('bsum').onclick = back;
        document.getElementById('btn-save-sum').onclick = async () => {
            const localDateStr = d.toISOString().slice(0, 10);

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

            const responses = { coffee, meals: mealResponses };

            try {
                await api('/summaries', {
                    method: 'POST',
                    json: {
                        telegram_id: user.id,
                        date: localDateStr,
                        energy,
                        sleep_quality,
                        responses,
                    },
                });
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
            if (ur.ok) state.userRow = await ur.json();
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
