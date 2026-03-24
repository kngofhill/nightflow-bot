console.log("showSchedule function exists:", typeof showSchedule);
console.log("showCaffeineCheck function exists:", typeof showCaffeineCheck);
console.log("setDayOff function exists:", typeof setDayOff);
const API_BASE = 'https://nightflow-bot-production.up.railway.app/api/v1';
const tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

const user = tg.initDataUnsafe?.user;
if (!user) {
    document.getElementById('content').innerHTML = '<div class="error">Error: Could not get user info.</div>';
} else {
    loadToday();
}

async function loadToday() {
    showLoading();
    try {
        const response = await fetch(`${API_BASE}/schedules/full?telegram_id=${user.id}`, {
            headers: {
                'Authorization': `Telegram ${tg.initData}`
            }
        });
        
        if (!response.ok) {
            if (response.status === 404) {
                showOnboarding();
                return;
            }
            throw new Error('Failed to fetch');
        }
        const data = await response.json();
        displayToday(data);
    } catch (error) {
        document.getElementById('content').innerHTML = '<div class="error">Error loading schedule. Pull to refresh.</div>';
        console.error(error);
    }
}

function showLoading() {
    document.getElementById('content').innerHTML = '<div class="loading">Loading...</div>';
}

function displayToday(schedule) {
    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    let html = `
        <div class="header">
            <h1>Nightflow</h1>
            <div class="time">${timeStr}</div>
        </div>
    `;
    
    if (schedule.shift_type === 'off') {
        html += `
            <div class="day-off">
                <div class="emoji">😴</div>
                <h2>Day Off</h2>
                <p>Rest and recharge today</p>
            </div>
        `;
    } else {
        // Determine next event
        const nextEvent = getNextEvent(schedule);
        
        html += `
            <div class="shift-badge ${schedule.shift_type}">
                ${schedule.shift_type.toUpperCase()} SHIFT
            </div>
            
            <div class="schedule-card">
                <div class="schedule-row">
                    <span class="label">Work</span>
                    <span class="value">${formatTime(schedule.work_start)} - ${formatTime(schedule.work_end)}</span>
                </div>
                <div class="schedule-row">
                    <span class="label">Sleep</span>
                    <span class="value">${formatTime(schedule.sleep_start)} - ${formatTime(schedule.sleep_end)}</span>
                </div>
            </div>
            
            <div class="next-event">
                <div class="next-label">NEXT</div>
                <div class="next-details">
                    <span class="next-emoji">${nextEvent.emoji}</span>
                    <span class="next-text">${nextEvent.text}</span>
                    <span class="next-time">${nextEvent.time}</span>
                </div>
            </div>
            
            <div class="timeline">
                <div class="timeline-item coffee">
                    <span class="timeline-emoji">☕</span>
                    <span class="timeline-time">${schedule.coffee_windows?.[0]?.time || '--:--'}</span>
                </div>
                <div class="timeline-item meal">
                    <span class="timeline-emoji">🍽️</span>
                    <span class="timeline-time">${schedule.meal_windows?.[0]?.time || '--:--'}</span>
                </div>
                <div class="timeline-item light">
                    <span class="timeline-emoji">💡</span>
                    <span class="timeline-time">${schedule.brightness_windows?.[0]?.time || '--:--'}</span>
                </div>
            </div>
        `;
    }
    
    // Add action buttons
    html += `
        <div class="actions">
            <button class="action-btn" onclick="showSchedule()">
                <span class="btn-emoji">📅</span>
                Full Schedule
            </button>
            <button class="action-btn" onclick="showCaffeineCheck()">
                <span class="btn-emoji">☕</span>
                Caffeine Check
            </button>
            <button class="action-btn" onclick="setDayOff()">
                <span class="btn-emoji">😴</span>
                Day Off
            </button>
        </div>
    `;
    
    document.getElementById('content').innerHTML = html;
}

function getNextEvent(schedule) {
    const now = new Date();
    const currentTime = now.getHours() * 60 + now.getMinutes();
    
    const events = [];
    
    // Collect all events
    if (schedule.coffee_windows) {
        schedule.coffee_windows.forEach(e => events.push({
            time: e.time,
            text: e.message || 'Coffee time',
            emoji: '☕',
            minutes: timeToMinutes(e.time)
        }));
    }
    if (schedule.meal_windows) {
        schedule.meal_windows.forEach(e => events.push({
            time: e.time,
            text: e.message || 'Meal time',
            emoji: '🍽️',
            minutes: timeToMinutes(e.time)
        }));
    }
    if (schedule.brightness_windows) {
        schedule.brightness_windows.forEach(e => events.push({
            time: e.time,
            text: e.message || 'Light reminder',
            emoji: '💡',
            minutes: timeToMinutes(e.time)
        }));
    }
    
    // Find next event
    events.sort((a, b) => a.minutes - b.minutes);
    const next = events.find(e => e.minutes > currentTime) || events[0];
    
    return next || { time: '--:--', text: 'No events', emoji: '⏰' };
}

function timeToMinutes(timeStr) {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

function formatTime(time) {
    return time || '--:--';
}

function showOnboarding() {
    document.getElementById('content').innerHTML = `
        <div class="onboarding">
            <h1>👋 Welcome to Nightflow</h1>
            <p>Let's optimize your shift schedule</p>
            <button class="primary-btn" onclick="startOnboarding()">Get Started</button>
        </div>
    `;
}

function startOnboarding() {
    document.getElementById('content').innerHTML = `
        <div class="onboarding">
            <h2>Choose your shift type</h2>
            <button class="option-btn" onclick="selectShiftType('constant')">
                <span class="option-emoji">🌙</span>
                Constant Schedule
                <span class="option-desc">Same hours every day</span>
            </button>
            <button class="option-btn" onclick="selectShiftType('rotating')">
                <span class="option-emoji">🔄</span>
                Rotating Schedule
                <span class="option-desc">Shifts change regularly</span>
            </button>
        </div>
    `;
}

function selectShiftType(type) {
    if (type === 'constant') {
        document.getElementById('content').innerHTML = `
            <div class="onboarding">
                <h2>Enter your work hours</h2>
                <p class="subtitle">Format: HH:MM-HH:MM (24h)</p>
                <input type="text" id="workHours" placeholder="22:00-06:00" class="time-input">
                <button class="primary-btn" onclick="saveConstantSchedule()">Save Schedule</button>
                <button class="secondary-btn" onclick="startOnboarding()">Back</button>
            </div>
        `;
    } else {
        alert('Rotating schedule coming soon!');
    }
}

async function saveConstantSchedule() {
    const workHours = document.getElementById('workHours').value;
    const [start, end] = workHours.split('-');
    
    if (!start || !end) {
        alert('Please use format: HH:MM-HH:MM');
        return;
    }
    
    showLoading();
    
    try {
        const response = await fetch(`${API_BASE}/schedules/constant?telegram_id=${user.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Telegram ${tg.initData}`
            },
            body: JSON.stringify({ 
                work_start: start.trim(), 
                work_end: end.trim() 
            })
        });
        
        if (response.ok) {
            loadToday();
        } else {
            alert('Error saving schedule. Please try again.');
        }
    } catch (error) {
        alert('Network error. Please try again.');
    }
}

async function showSchedule() {
    try {
        const response = await fetch(`${API_BASE}/schedules/full?telegram_id=${user.id}`, {
            headers: {
                'Authorization': `Telegram ${tg.initData}`
            }
        });
        
        if (!response.ok) {
            tg.showAlert(`Error: ${response.status}`);
            return;
        }
        
        const schedule = await response.json();
        
        // Build a clean message (no markdown, just plain text with emojis)
        let message = "📅 YOUR FULL SCHEDULE\n\n";
        message += "═══ SHIFT ═══\n";
        message += `${schedule.shift_type.toUpperCase()} SHIFT\n\n`;
        
        message += "═══ WORK ═══\n";
        message += `${formatTime(schedule.work_start)} → ${formatTime(schedule.work_end)}\n\n`;
        
        message += "═══ SLEEP ═══\n";
        message += `${formatTime(schedule.sleep_start)} → ${formatTime(schedule.sleep_end)}\n\n`;
        
        message += "☕ COFFEE TIMES\n";
        if (schedule.coffee_windows && schedule.coffee_windows.length > 0) {
            schedule.coffee_windows.forEach(w => {
                message += `• ${w.time}  ${w.message.replace('☕', '').trim()}\n`;
            });
        } else {
            message += "• No coffee times set\n";
        }
        
        message += "\n🍽️ MEAL TIMES\n";
        if (schedule.meal_windows && schedule.meal_windows.length > 0) {
            schedule.meal_windows.forEach(w => {
                message += `• ${w.time}  ${w.message.replace('🍽️', '').replace('🥗', '').replace('🍌', '').trim()}\n`;
            });
        } else {
            message += "• No meal times set\n";
        }
        
        message += "\n💡 LIGHT REMINDERS\n";
        if (schedule.brightness_windows && schedule.brightness_windows.length > 0) {
            schedule.brightness_windows.forEach(w => {
                message += `• ${w.time}  ${w.message.replace('☀️', '').replace('🌙', '').replace('📵', '').replace('🕶️', '').trim()}\n`;
            });
        } else {
            message += "• No light reminders set\n";
        }
        
        tg.showPopup({
            title: '📋 Full Schedule',
            message: message,
            buttons: [{type: 'ok', text: 'Got it'}]
        });
    } catch (error) {
        tg.showAlert(`Error: ${error.message}`);
        console.error(error);
    }
}

async function setDayOff() {
    tg.showPopup({
        title: 'Set Day Off',
        message: 'Set today as a day off? Notifications will be paused.',
        buttons: [
            {type: 'cancel', text: 'No'},
            {type: 'default', text: 'Yes'}
        ]
    }, async (buttonId) => {
        if (buttonId === 1) { // Yes button
            try {
                const response = await fetch(`${API_BASE}/schedules/dayoff?telegram_id=${user.id}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Telegram ${tg.initData}`
                    },
                    body: JSON.stringify({})
                });
                
                if (response.ok) {
                    tg.showAlert('✅ Day off set! No notifications today.');
                    loadToday(); // Refresh to show day off view
                } else {
                    tg.showAlert('Error setting day off');
                }
            } catch (error) {
                tg.showAlert('Network error');
                console.error(error);
            }
        }
    });
}

// Pull to refresh
let touchstartY = 0;
document.addEventListener('touchstart', e => {
    touchstartY = e.touches[0].screenY;
}, { passive: true });

document.addEventListener('touchend', e => {
    const touchendY = e.changedTouches[0].screenY;
    const diffY = touchendY - touchstartY;
    
    if (diffY > 100 && window.scrollY === 0) {
        loadToday();
    }
}, { passive: true });