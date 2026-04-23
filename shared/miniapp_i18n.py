"""
Localized strings for the Telegram mini app + API payloads (en / ru / uz).
Thread ui_language (or "en") into builders that return user-visible text.
"""

from __future__ import annotations

from typing import Any, Dict

STRS: Dict[str, Dict[str, str]] = {
    "calc_coffee_pre": {
        "en": "☕ Pre-shift coffee. Perfect timing to start alert.",
        "ru": "☕ Кофе до смены. Хорошее время, чтобы взбодриться.",
        "uz": "☕ Smenadan oldin qahva. Uyg‘onish uchun qulay vaqt.",
    },
    "calc_coffee_mid": {
        "en": "☕ Mid-shift boost. You're halfway there.",
        "ru": "☕ Середина смены. Половина пути — держитесь.",
        "uz": "☕ Smena o‘rtasi. Yarmiga keldiniz.",
    },
    "calc_meal_pre": {
        "en": "🍽️ Pre-shift meal. Protein + complex carbs for steady energy.",
        "ru": "🍽️ Еда до смены. Белок и «медленные» углеводы — ровная энергия.",
        "uz": "🍽️ Smenadan oldin ovqat. Oqsil + murakkab uglevodlar — barqaror energiya.",
    },
    "calc_meal_mid": {
        "en": "🥗 Mid-shift fuel. Avoid heavy/greasy food.",
        "ru": "🥗 Еда в середине смены. Избегайте тяжёлого и жирного.",
        "uz": "🥗 Smena o‘rtasida. Og‘ir va yog‘li dan saqlaning.",
    },
    "calc_meal_post": {
        "en": "🍌 Post-shift snack. Light before sleep. Banana is perfect.",
        "ru": "🍌 Перекус после смены. Лёгкое — перед сном; банан — отлично.",
        "uz": "🍌 Smenadan keyin. Yengil atıştiruv — uyqu oldidan; banan mos.",
    },
    "calc_bright": {
        "en": "☀️ Bright light time. Tell your brain: wake up!",
        "ru": "☀️ Яркий свет. Скажите мозгу: пора бодрствовать!",
        "uz": "☀️ Yorug‘lik vaqti. Miya uchun signal: uyg‘oq bo‘l!",
    },
    "calc_dim": {
        "en": "🌙 Time to dim lights. Tell your brain: sleep is coming.",
        "ru": "🌙 Приглушите свет. Мозгу: скоро сон.",
        "uz": "🌙 Yorug‘likni pasaytiring. Uyqu yaqinligini bildirib qo‘ying.",
    },
    "calc_screens": {
        "en": "📵 30 min until sleep. Put devices away. Read a book.",
        "ru": "📵 30 мин до сна. Уберите устройства. Книга — лучше.",
        "uz": "📵 Uyquga ~30 daq. Qurilmalarni olib qo‘ying. Kitob yaxshiroq.",
    },
    "calc_commute": {
        "en": "🕶️ On the way home? Wear sunglasses. Blue light blockers help.",
        "ru": "🕶️ Дорога домой? Солнечные очки и блок «синего» помогут.",
        "uz": "🕶️ Uyga yo‘l? Quyosh ko‘zoynagi va ko‘k nur bloklari yordam beradi.",
    },
    "rest_coffee1": {
        "en": "☕ First coffee — after you’re truly awake. Skip if you’re still groggy.",
        "ru": "☕ Первый кофе — когда реально проснулись. Не пейте, если клонит в сон.",
        "uz": "☕ Birinchi qahva — uyg‘onganingizga ishonch bo‘lganda. Charchoq bo‘lsa — o‘tkazing.",
    },
    "rest_coffee2": {
        "en": "☕ Optional second cup — keep before your wind-down window.",
        "ru": "☕ Второй (по желанию) — до «заминки» перед сном.",
        "uz": "☕ Ixtiyoriy ikkinchi piyola — tushdan oldin sokinlashishdan avval.",
    },
    "rest_meal1": {
        "en": "🍽 Main meal — steady protein; lighter than a heavy “celebration” dinner.",
        "ru": "🍽 Основной приём: белок, без слишком тяжёлого праздничного ужина.",
        "uz": "🍽 Asosiy ovqat — barqaror oqsil; bayramdagi haddan oshiq og‘ir emas.",
    },
    "rest_meal2": {
        "en": "🥗 Mid-awake fuel — avoid your heaviest meal within 3h of bed.",
        "ru": "🥗 В середине бодрствования — не самый тяжёлый приём за 3 ч до сна.",
        "uz": "🥗 Uyg‘oqlik o‘rtasida — uxlashdan 3 s oldin eng og‘ir taom bo‘lmasin.",
    },
    "rest_meal3": {
        "en": "🍽 Earlier dinner — finish eating a few hours before lying down.",
        "ru": "🍽 Пораньше ужин — закончить за пару часов до сна.",
        "uz": "🍽 Kechroq emas, balki erta kechki — yotishdan bir necha soat oldin tugating.",
    },
    "rest_bl_bright": {
        "en": "☀️ Bright light soon after waking — anchors your clock for the day.",
        "ru": "☀️ Яркий свет вскоре после подъёма — якорь суток.",
        "uz": "☀️ Uyg‘ongach tez yoritish — kun ritmini mustahkamlaydi.",
    },
    "rest_bl_dim": {
        "en": "🌙 Start dimming lights — tells your brain sleep is coming.",
        "ru": "🌙 Смягчайте свет — сигнал мозгу, что пора ко сну.",
        "uz": "🌙 Yoritishni sekin pasaytiring — uyqu yaqin.",
    },
    "rest_bl_ns": {
        "en": "📵 Wind-down — softer screens and lower light before bed.",
        "ru": "📵 «Заминка» — тише экраны, меньше света перед сном.",
        "uz": "📵 Tushdan oldin — yumshoq ekran va pastroq yoritish.",
    },
    "well_coffee": {
        "en": "Coffee very close to bedtime can fragment sleep — consider an earlier last cup on rest days.",
        "ru": "Кофе вплотную ко сну может ломать сон — в выходной попробуйте последний пораньше.",
        "uz": "Qahva uxlashga juda yaqin bo‘lsa uyqu bo‘linadi — dam kunida so‘nggisini erta iching.",
    },
    "well_meal": {
        "en": "Heavy eating right before bed can feel uncomfortable — a lighter last meal may help on regular days.",
        "ru": "Плотно прямо перед сном — тяжело; в обычные дни легче в последний приём.",
        "uz": "Uxlashdan oldin o‘t ovqat noqulay; oddiy kunlarda so‘nggi taom yengil bo‘lsin.",
    },
    "well_bright": {
        "en": "Very bright light minutes before you lie down can delay melatonin — this is a gentle heads-up, not a rule change.",
        "ru": "Слишком яркий свет сразу перед сном сдвигает мелатонин — мягкое замечание, не правило.",
        "uz": "Yotishdan oldin juda yorug‘lik melatoninni kechiktiradi — e’tibor, qoidaga o‘tkazish emas.",
    },
    "reminders_locked": {
        "en": "Transition day: coffee / meal / light follow the system plan so sleep timing stays consistent.",
        "ru": "Переходный день: кофе, еда и свет по системе — так стабильнее сон.",
        "uz": "O‘tish kuni: qahva/taom/yoritish tizim bo‘yicha — uyqu vaqti barqarorroq bo‘ladi.",
    },
    "rot_pit_night_to_day": {
        "en": "Night → day: short 4h sleep (08:00–12:00), then stay awake until ~22:00 before day block.",
        "ru": "Ночь → день: короткий сон 4 ч (08:00–12:00), потом бодрствовать до ~22:00 до дневного блока.",
        "uz": "Tun → kun: 4 s qisqa uyqu (08:00–12:00), keyin ~22:00 gacha uyg‘oq — kunduzgi blokkacha.",
    },
    "rot_block_end_night": {
        "en": "End of night block: short 4h sleep, then stay awake until first day-sleep (≈22:00).",
        "ru": "Конец ночного блока: короткий 4-ч сон, до первого дневного сна (≈22:00) бодрствовать.",
        "uz": "Tun bloki oxiri: 4 s uyqu, keyin birinchi kunduz uyqusiga (≈22:00) qadar uyg‘oq.",
    },
    "rot_pit_day_to_night": {
        "en": "Day → night: take a 4h nap 14:00–18:00 before the first night of the new cycle.",
        "ru": "День → ночь: 4 ч (14:00–18:00) до первой ночи цикла.",
        "uz": "Kun → tun: siklning birinchi tuni oldidan 4 s uyqu 14:00–18:00.",
    },
    "rot_block_end_day": {
        "en": "End of day block: 4h nap 14:00–18:00, then first night of night block.",
        "ru": "Конец дневного блока: 4 ч 14:00–18:00, потом первая ночь ночного блока.",
        "uz": "Kun bloki oxiri: 14:00–18:00 da 4 s uyqu, keyin tun bloki tuni.",
    },
    "rot_off_default": {
        "en": "Off day — sleep aligned with your upcoming work block.",
        "ru": "Выходной — сон под будущий рабочий блок.",
        "uz": "Dam — uyqu kelayotgan ish smenasiga mos.",
    },
    "rot_pat4_off_before_day": {
        "en": "Off before day run — use day sleep (22:00–06:00).",
        "ru": "Выходной перед дневным «прогоном» — сон 22:00–06:00.",
        "uz": "Kun seriyasi oldidan dam — kun uyqu 22:00–06:00.",
    },
    "rot_pat4_off_before_night": {
        "en": "Off before night run — use night sleep (08:00–16:00).",
        "ru": "Выходной перед ночным «прогоном» — сон 08:00–16:00.",
        "uz": "Tun seriyasi oldidan dam — tun uyqu 08:00–16:00.",
    },
    "rot_pat4_last_off": {
        "en": "Last off day before night: 4h nap, then first night.",
        "ru": "Последний выходной перед ночами: 4 ч сон, первая ночь.",
        "uz": "Tunlardan oldingi oxirgi dam: 4 s uyqu, keyin tun.",
    },
    "rot_pat4n4o_off": {
        "en": "Off day — use night rest sleep (08:00–16:00).",
        "ru": "Выходной — ночной «отдыхо-сон» 08:00–16:00.",
        "uz": "Dam — tunda dam olish uxlashi 08:00–16:00.",
    },
    "rot_pat4n4o_last": {
        "en": "Last off day: 4h nap 14:00–18:00, bright light ~20:00, then first night block.",
        "ru": "Последний выходной: 4 ч 14:00–18:00, яркий свет ~20:00, дальше первый ночной блок.",
        "uz": "Oxirgi dam: 4 s 14:00–18:00, yoritish ~20:00, keyin birinchi tun bloki.",
    },
    "rot_bright_20": {
        "en": "Bright light ~20:00 to boost alertness before the night block.",
        "ru": "Яркий свет ~20:00 — бодрость перед ночным блоком.",
        "uz": "Yoritish ~20:00 — tun bloki oldidan uyg‘oq turishga.",
    },
    "rot_block_off": {
        "en": "Off day — night-style rest; next work block is nights.",
        "ru": "Выходной — ночной отдых; дальше ночной блок.",
        "uz": "Dam — tungi dam olish; keyingi smena tun.",
    },
    "in_tpl_night": {
        "en": "🌙 Night · ",
        "ru": "🌙 Ночь · ",
        "uz": "🌙 Tun · ",
    },
    "in_tpl_day": {
        "en": "☀️ Day · ",
        "ru": "☀️ День · ",
        "uz": "☀️ Kun · ",
    },
    "in_coffee_t": {
        "en": "☕{tlabel}Coffee may be too close to sleep",
        "ru": "☕{tlabel}Кофе слишком близко ко сну",
        "uz": "☕{tlabel}Qahva uxlashga juda yaqin",
    },
    "in_coffee_b": {
        "en": "Last cup at {ts} is within 5h of bedtime on this template — that can break rest for some people.",
        "ru": "Последняя чашка в {ts} в пределах 5 ч до сна в этом шаблоне — кому-то мешает отдыху.",
        "uz": "So‘nggi piyola {ts} — shu shablon bo‘yicha uxlashga 5 s ichida, ba’zilar uchun qiyin bo‘ladi.",
    },
    "in_coffee_a": {
        "en": "Nudge to {to_t} (or edit in Settings).",
        "ru": "Сдвиньте к {to_t} (или в настройках).",
        "uz": "{to_t} ga siljitish (yoki sozlamalarda).",
    },
    "in_meal_t": {
        "en": "🍽{tlabel}Meal may be too close to sleep",
        "ru": "🍽{tlabel}Еда слишком близко ко сну",
        "uz": "🍽{tlabel}Ovqat uxlashga juda yaqin",
    },
    "in_meal_b": {
        "en": "Eating at {ts} is within 3h of bed — a lighter/earlier last meal on this pattern may help.",
        "ru": "Приём в {ts} в пределах 3 ч до сна — легче/раньше последний приём в этом графике поможет.",
        "uz": "{ts}da ovqat yotishga 3 s ichida — yengil/erta oxirgi ovqat yaxshiroq bo‘ladi.",
    },
    "in_meal_a": {
        "en": "Nudge to {to_t} (or edit in Settings).",
        "ru": "Сдвиньте к {to_t} (или в настройках).",
        "uz": "{to_t} ga siljitish (yoki sozlamalarda).",
    },
    "in_bright_t": {
        "en": "💡{tlabel}Light may be too close to bed",
        "ru": "💡{tlabel}Свет слишком близко ко сну",
        "uz": "💡{tlabel}Yoritish yotishga juda yaqin",
    },
    "in_bright_b": {
        "en": "Brightness at {ts} is right before you lie down — a dimmer cue earlier helps your eyes and melatonin.",
        "ru": "Яркость в {ts} прямо перед сном — мягче светом раньше — легче засыпать.",
        "uz": "Yoritish {ts} yotishdan oldin — biroz erta pasaytirib qo‘yish foydali bo‘ladi.",
    },
    "in_bright_a": {
        "en": "Nudge to {to_t} (or edit in Settings).",
        "ru": "Сдвиньте к {to_t} (или в настройках).",
        "uz": "{to_t} ga siljitish (yoki sozlamalarda).",
    },
    "sug_lab_night": {
        "en": "🌙 NIGHT",
        "ru": "🌙 НОЧЬ",
        "uz": "🌙 TUN",
    },
    "sug_lab_day": {
        "en": "☀️ DAY",
        "ru": "☀️ ДЕНЬ",
        "uz": "☀️ KUN",
    },
    "sug_slot_night": {
        "en": "night",
        "ru": "ночных",
        "uz": "tun",
    },
    "sug_slot_day": {
        "en": "day",
        "ru": "дневных",
        "uz": "kunduzgi",
    },
    "sug_rot_coff_t": {
        "en": "☕ {lab} · {t} coffee",
        "ru": "☕ {lab} · {t} кофе",
        "uz": "☕ {lab} · {t} qahva",
    },
    "sug_rot_coff_b": {
        "en": "Weak log on {n} of your {templ} shift days this week.",
        "ru": "Слабые отметки: {n} {templ} сменных дня на этой неделе.",
        "uz": "Zaif jurnal: bu hafta {templ} smenada {n} kun.",
    },
    "sug_rot_coff_a": {
        "en": "Move to {t} on the {tpl} template",
        "ru": "Перенести на {t} в шаблоне {tpl}",
        "uz": "{tpl} shablonda {t} ga o‘tkazish",
    },
    "sug_rot_meal_t": {
        "en": "🍽 {lab} · {t} meal",
        "ru": "🍽 {lab} · {t} приём пищи",
        "uz": "🍽 {lab} · {t} ovqat",
    },
    "sug_rot_meal_b": {
        "en": "Weak log on {n} of your {templ} shift days this week.",
        "ru": "Слабые отметки: {n} {templ} сменных дня на этой неделе.",
        "uz": "Zaif jurnal: bu hafta {templ} smenada {n} kun.",
    },
    "sug_rot_meal_a": {
        "en": "Move to {t} on the {tpl} template",
        "ru": "Перенести на {t} в шаблоне {tpl}",
        "uz": "{tpl} shablonda {t} ga o‘tkazish",
    },
    "sug_rot_sleep_t": {
        "en": "😴 {lab} · SLEEP",
        "ru": "😴 {lab} · СОН",
        "uz": "😴 {lab} · UYQU",
    },
    "sug_rot_sleep_b": {
        "en": "Sleep quality was low on your {templ} shift days recently.",
        "ru": "Сон слабый в ваши {templ} сменные дни за последний период.",
        "uz": "Yaqinda {templ} smena kunlaringizda uyqu sifati past.",
    },
    "sug_rot_sleep_a": {
        "en": "Add 30 minutes (earlier to bed) on the {tpl} template",
        "ru": "Добавьте 30 минут (раньше в постель) в шаблоне {tpl}",
        "uz": "{tpl} shablonida 30 daq qo‘shing (ertaroq yotish)",
    },
    "sug_templ_night": {
        "en": "night",
        "ru": "ночь",
        "uz": "tun",
    },
    "sug_templ_day": {
        "en": "day",
        "ru": "день",
        "uz": "kun",
    },
    "sug_const_coff_t": {
        "en": "☕ {t} coffee",
        "ru": "☕ {t} кофе",
        "uz": "☕ {t} qahva",
    },
    "sug_const_coff_b": {
        "en": "Log looked weak {n} times in the days after your last schedule change.",
        "ru": "Слабые отметки {n} раз в днях после последнего изменения графика.",
        "uz": "Oxirgi jadval o‘zgarishidan keyingi kunlarda {n} marta zaif ro‘yxatga olingan.",
    },
    "sug_const_coff_a": {
        "en": "Move to {t}",
        "ru": "Перенести на {t}",
        "uz": "{t} ga o‘tkazish",
    },
    "sug_const_meal_t": {
        "en": "🍽 {t} meal",
        "ru": "🍽 {t} приём пищи",
        "uz": "🍽 {t} ovqat",
    },
    "sug_const_meal_b": {
        "en": "Log looked weak {n} times in the days after your last schedule change.",
        "ru": "Слабые отметки {n} раз в днях после последнего изменения графика.",
        "uz": "Oxirgi jadval o‘zgarishidan keyingi kunlarda {n} marta zaif ro‘yxatga olingan.",
    },
    "sug_const_meal_a": {
        "en": "Move to {t}",
        "ru": "Перенести на {t}",
        "uz": "{t} ga o‘tkazish",
    },
    "sug_const_sleep_t": {
        "en": "😴 SLEEP",
        "ru": "😴 СОН",
        "uz": "😴 UYQU",
    },
    "sug_const_sleep_b": {
        "en": "Sleep quality was low in the days since your last schedule change.",
        "ru": "С сильным изменением графика сон в последние дни был слабым.",
        "uz": "Jadval o‘zgarishidan keyin uyqu sifati past bo‘lgan.",
    },
    "sug_const_sleep_a": {
        "en": "Add 30 minutes (earlier to bed)",
        "ru": "Добавьте 30 минут (раньше в постель)",
        "uz": "30 daq qo‘shing (ertaroq yotish)",
    },
    "api_dayoff_ok": {
        "en": "Day off saved.",
        "ru": "Выходной сохранён.",
        "uz": "Dam muvaffaqiyatli saqlandi.",
    },
    "caff_closed": {
        "en": "🚫 **Caffeine window closed!**\n\nWithin 6 hours of sleep. Sleep at {t} (in {h}h {m}m). Caffeine now may cost sleep quality.",
        "ru": "🚫 **Окно кофена закрылось!**\n\nВ пределах 6 ч до сна. Сон в {t} (через {h}ч {m}м). Сейчас кофе мешает сну.",
        "uz": "🚫 **Kofein oynasi yopildi!**\n\nUxlashga 6 soat qoldi. Uyqu {t} (yana {h}s {m}daq). Hozir qahva sifatga xalaqit beradi.",
    },
    "caff_open": {
        "en": "✅ **Caffeine OK!**\n\n{h}h {m}m left before the 6h window before sleep. Last call: {cutoff}.",
        "ru": "✅ **Кофе можно!**\n\nОсталось {h}ч {m}м до «6 ч до сна». Последняя нормальная порция: {cutoff}.",
        "uz": "✅ **Qahva bo‘ladi!**\n\n6 soatli uyqu oynasigacha: {h}s {m}daq. Optimal so‘nggi vaqt: {cutoff}.",
    },
    "caff_err_no_sched": {
        "en": "No schedule. Set it up in Settings first.",
        "ru": "Нет графика. Сначала настройте в настройках.",
        "uz": "Jadval yo‘q. Avval sozlamalarda yarating.",
    },
    "caff_err_no_sleep": {
        "en": "Sleep time not set in the schedule.",
        "ru": "В графике не задано время сна.",
        "uz": "Jadvalda uyqu vaqti yo‘q.",
    },
    "err_no_apply": {
        "en": "No action for this item.",
        "ru": "Нет действия для этого пункта.",
        "uz": "Bu element uchun amal yo‘q.",
    },
    "err_invalid_time": {
        "en": "Invalid time.",
        "ru": "Неверное время.",
        "uz": "Noto‘g‘ri vaqt.",
    },
    "err_no_rot": {
        "en": "No active rotating pattern.",
        "ru": "Нет активного сменного шаблона.",
        "uz": "Faol aylantiriladigan andoza yo‘q.",
    },
    "err_set_sleep": {
        "en": "Set sleep times in Settings for this template first.",
        "ru": "Сначала задайте сон в настройках для этого шаблона.",
        "uz": "Avval shu shablon uchun sozlamalarda uyqu vaqtini kiriting.",
    },
    "err_invalid_delta": {
        "en": "Invalid time adjustment.",
        "ru": "Неверный сдвиг.",
        "uz": "Noto‘g‘ri surish.",
    },
    "err_invalid_window": {
        "en": "Invalid reminder window.",
        "ru": "Неверный слот напоминаний.",
        "uz": "Eslatma sloti noto‘g‘ri.",
    },
    "err_not_found_templ": {
        "en": "Not found in this template.",
        "ru": "В этом шаблоне не найдено.",
        "uz": "Bu shablonda topilmadi.",
    },
    "err_slot_limit": {
        "en": "Limit reached for this type.",
        "ru": "Достигнут лимит по этому типу.",
        "uz": "Shu tur bo‘yicha chekka yetdingiz.",
    },
    "err_constant_nf": {
        "en": "No constant schedule found.",
        "ru": "Постоянный график не найден.",
        "uz": "Doimiy jadval topilmadi.",
    },
    "tr_adv_head": {
        "en": "🔄 **Shift change prep**",
        "ru": "🔄 **Подготовка к смене**",
        "uz": "🔄 **Smena o‘tishiga tayyorlov**",
    },
    "tr_adv_line": {
        "en": "From {o1}-{o2} to {n1}-{n2}",
        "ru": "С {o1}–{o2} на {n1}–{n2}",
        "uz": "{o1}–{o2} dan {n1}–{n2} gacha",
    },
    "tr_adv_late_h": {
        "en": "New start is {h:.1f} hours later.",
        "ru": "Новое начало на {h:.1f} ч позже.",
        "uz": "Yangi boshlanish {h:.1f} s kechroq.",
    },
    "tr_adv_small": {
        "en": "Small change — go to bed a bit later each night.",
        "ru": "Небольшой сдвиг — чуть-чуть ложитесь позже.",
        "uz": "Kichik o‘zgarish — kechqurun biroz uzoqroq yoting.",
    },
    "tr_adv_medium": {
        "en": "Medium shift. Try: nap 3–4h before the first new shift, then 4–5h sleep after work.",
        "ru": "Средний сдвиг. Попробуйте: 3–4 ч сна до первой смены, затем 4–5 ч после смены.",
        "uz": "O‘rtacha. Sinab ko‘ring: yangi smenadan oldin 3–4 s uyqu, smenadan keyin 4–5 s.",
    },
    "tr_adv_large": {
        "en": "Big change — a few days to adjust: Day1 +2h awake, Day2 +4h, Day3 full schedule.",
        "ru": "Большой сдвиг — в несколько дней: 1й +2ч бодр., 2й +4ч, 3й — полный график.",
        "uz": "Katta o‘zgarish — 1-kun uyg‘oq +2s, 2-kun +4s, 3-to‘liq jadval.",
    },
    "tr_adv_early_h": {
        "en": "New start is {h:.1f} hours earlier.",
        "ru": "Новое начало на {h:.1f} ч раньше.",
        "uz": "Yangi boshlanish {h:.1f} s ertaroq.",
    },
    "tr_adv_early_s": {
        "en": "Early shift: bed earlier, bright light at wake, no caffeine 6h before the new sleep time.",
        "ru": "Ранний старт: раньше отбой, яркий свет при подъёме, без кофе за 6 ч до нового сна.",
        "uz": "Erta: ertaroq yotish, uyg‘onganda yoritish, yangi uxlash oldidan 6 s qahvasiz.",
    },
    "tr_adv_foot": {
        "en": "Daily transition reminders are on.",
        "ru": "Напоминания о переходе включены.",
        "uz": "Kunlik o‘tish eslatmalari yoqilgan.",
    },
}


def norm_lang(raw: Any) -> str:
    if raw is None or raw is False:
        return "en"
    s = str(raw).strip().lower()[:2]
    return s if s in ("en", "ru", "uz") else "en"


def mt(key: str, lang: str, **kwargs) -> str:
    lang = norm_lang(lang)
    rec = STRS.get(key) or {}
    s = rec.get(lang) or rec.get("en") or key
    if not kwargs:
        return s
    try:
        return s.format(**kwargs)
    except (KeyError, ValueError):
        return s
