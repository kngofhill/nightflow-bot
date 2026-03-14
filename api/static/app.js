const API_BASE = 'nightflow-bot-production.up.railway.app'; // Replace with your Railway URL

const tg = window.Telegram.WebApp;
tg.expand();

const user = tg.initDataUnsafe?.user;
if (!user) {
    document.getElementById('content').innerText = 'Error: Could not get user info.';
} else {
    loadToday();
}

async function loadToday() {
    try {
        const response = await fetch(`${API_BASE}/schedules/daily/today?telegram_id=${user.id}`, {
            headers: {
                'Authorization': `Telegram ${tg.initData}`
            }
        });
        if (!response.ok) {
            if (response.status === 404) {
                // No schedule – show onboarding
                showOnboarding();
                return;
            }
            throw new Error('Failed to fetch');
        }
        const data = await response.json();
        displayToday(data);
    } catch (error) {
        document.getElementById('content').innerText = 'Error loading schedule.';
        console.error(error);
    }
}

function displayToday(schedule) {
    let html = '';
    if (schedule.shift_type === 'off') {
        html = '<p>Today is a day off. Rest well!</p>';
    } else {
        html = `
            <p><strong>Shift:</strong> ${schedule.shift_type}</p>
            <p><strong>Work:</strong> ${schedule.work_start || '--'} – ${schedule.work_end || '--'}</p>
            <p><strong>Sleep:</strong> ${schedule.sleep_start || '--'} – ${schedule.sleep_end || '--'}</p>
            <p><strong>Coffee:</strong> ${schedule.coffee_windows?.map(c => c.time).join(', ') || '—'}</p>
            <p><strong>Meals:</strong> ${schedule.meal_windows?.map(m => m.time).join(', ') || '—'}</p>
        `;
    }
    document.getElementById('content').innerHTML = html;
    document.getElementById('refresh').style.display = 'block';
}

function showOnboarding() {
    document.getElementById('content').innerHTML = `
        <h2>Welcome! Let's set up your schedule.</h2>
        <p>Choose your shift type:</p>
        <button onclick="setShiftType('constant')">Constant Schedule</button>
        <button onclick="setShiftType('rotating')">Rotating Schedule</button>
    `;
}

window.setShiftType = async function(type) {
    // Save shift type to user
    await fetch(`${API_BASE}/users/me`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Telegram ${tg.initData}`
        },
        body: JSON.stringify({
            telegram_id: user.id,
            first_name: user.first_name,
            username: user.username,
            shift_type: type
        })
    });
    if (type === 'constant') {
        // Ask for work hours
        document.getElementById('content').innerHTML = `
            <h2>Enter your typical work hours</h2>
            <p>Format: HH:MM-HH:MM (e.g., 22:00-06:00)</p>
            <input type="text" id="workHours" placeholder="22:00-06:00">
            <button onclick="saveConstantSchedule()">Save</button>
        `;
    } else {
        // Rotating – for now just a placeholder
        alert('Rotating schedule setup coming soon!');
    }
}

window.saveConstantSchedule = async function() {
    const workHours = document.getElementById('workHours').value;
    const [start, end] = workHours.split('-');
    if (!start || !end) {
        alert('Invalid format');
        return;
    }
    const response = await fetch(`${API_BASE}/schedules/constant?telegram_id=${user.id}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Telegram ${tg.initData}`
        },
        body: JSON.stringify({ work_start: start, work_end: end })
    });
    if (response.ok) {
        loadToday(); // go back to dashboard
    } else {
        alert('Error saving schedule');
    }
}

document.getElementById('refresh').addEventListener('click', loadToday);