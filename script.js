document.addEventListener('DOMContentLoaded', () => {
    // App Section Elements
    const reminderTextarea = document.getElementById('reminderText');
    const setReminderBtn = document.getElementById('setReminderBtn');
    const reminderMessageArea = document.getElementById('reminderMessageArea');
    const reminderList = document.getElementById('reminderList');
    const calendarEl = document.getElementById('calendar'); // Wadah FullCalendar

    let calendar; // Deklarasikan variabel untuk instance FullCalendar
    const DEFAULT_USER_ID = "default_user"; // ID pengguna default karena tidak ada login


    // --- Fungsi Jam Zona Waktu ---
    const timezoneOffsets = { // Offset dalam jam dari UTC
        "Lokal": (new Date().getTimezoneOffset() / -60), // Mendapatkan offset lokal dari UTC
        "WIB": 7, // UTC+7
        "WITA": 8, // UTC+8
        "WIT": 9  // UTC+9
    };

    function updateClocks() {
        const now = new Date(); // Waktu lokal komputer

        for (const tzLabel in timezoneOffsets) {
            const offset = timezoneOffsets[tzLabel];
            // Hitung UTC time: now.getTime() - (now.getTimezoneOffset() * 60000)
            // Kemudian tambahkan offset TZ target
            const targetTime = new Date(now.getTime() + (offset * 3600000) - (now.getTimezoneOffset() * 60000));
            
            const hours = targetTime.getHours().toString().padStart(2, '0');
            const minutes = targetTime.getMinutes().toString().padStart(2, '0');
            const seconds = targetTime.getSeconds().toString().padStart(2, '0');
            
            const clockElement = document.getElementById(`${tzLabel.toLowerCase()}Clock`);
            if (clockElement) { 
                clockElement.textContent = `${hours}:${minutes}:${seconds}`;
            }
        }
    }

    // Perbarui jam setiap detik
    setInterval(updateClocks, 1000);
    updateClocks(); // Panggil sekali saat start

    // --- Fungsi Utilitas ---
    function showMessage(messageAreaElement, message, type) {
        messageAreaElement.textContent = message;
        messageAreaElement.className = `message-area visible ${type}`; // Add visible and type class
        setTimeout(() => {
            messageAreaElement.classList.remove('visible');
        }, 5000);
    }

    // --- Inisialisasi FullCalendar ---
    function initializeCalendar(reminders) {
        if (calendar) { // Hancurkan instance kalender sebelumnya jika ada
            calendar.destroy();
        }

        const events = reminders.map(r => ({
            id: r.id,
            title: r.text,
            start: r.reminder_time, // FullCalendar bisa langsung pakai ISO string dari backend
            allDay: false, 
            display: 'auto', // Tampilkan sebagai event biasa
            backgroundColor: r.is_completed ? 'grey' : 'red', // Warna event di kalender
            borderColor: r.is_completed ? 'grey' : 'red',
            extendedProps: { // Data tambahan untuk diakses nanti
                repeatType: r.repeat_type,
                repeatInterval: r.repeat_interval,
                isCompleted: r.is_completed
            }
        }));

        calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth', 
            locale: 'id', // Set bahasa ke Indonesia
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
            },
            events: events, // Berikan event yang sudah kita siapkan
            eventDidMount: function(info) {
                if (info.event.extendedProps.isCompleted) {
                    info.el.style.backgroundColor = 'grey'; 
                    info.el.style.borderColor = 'grey';
                } else {
                    info.el.style.backgroundColor = 'red'; 
                    info.el.style.borderColor = 'red';
                }
            },
            eventClick: function(info) {
                const reminder = info.event.extendedProps;
                let repeatInfo = "";
                if (reminder.repeatType === 'yearly') {
                    repeatInfo = "(Setiap Tahun)";
                    if (reminder.repeatInterval > 1) {
                        repeatInfo = `(Setiap ${reminder.repeatInterval} Tahun)`;
                    }
                } else if (reminder.repeatType === 'monthly_interval') {
                    repeatInfo = `(Setiap ${reminder.repeatInterval} Bulan)`;
                }

                const completedStatus = reminder.isCompleted ? 'Sudah selesai.' : 'Belum selesai.';
                
                alert(`Pengingat: ${info.event.title}\nWaktu: ${info.event.start.toLocaleString('id-ID', { timeZoneName: 'short' })}\nPengulangan: ${repeatInfo || 'Tidak ada'}\nStatus: ${completedStatus}`);
            },
        });
        calendar.render();
    }

    // --- Fungsi Interaksi Backend ---
    async function sendRequest(url, method, body = null) {
        try {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
            };
            if (body) {
                options.body = JSON.stringify(body);
            }

            const response = await fetch(url, options);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || 'Terjadi kesalahan pada server.');
            }
            return data;
        } catch (error) {
            console.error('Request failed:', error);
            throw error; // Re-throw to be caught by caller
        }
    }

    function renderReminders(reminders) {
        reminderList.innerHTML = ''; 
        if (reminders.length === 0) {
            reminderList.innerHTML = '<li>Belum ada pengingat.</li>';
            return;
        }

        reminders.forEach(r => {
            const listItem = document.createElement('li');
            listItem.dataset.id = r.id; // Store reminder ID for actions
            if (r.is_completed) {
                listItem.classList.add('completed');
            }

            const reminderDetails = document.createElement('span');
            reminderDetails.classList.add('reminder-text');
            
            const reminderTime = r.reminder_time_display ? r.reminder_time_display : 'Waktu tidak diketahui';

            reminderDetails.innerHTML = `<strong>${r.text}</strong><br><small>${reminderTime} (${r.repeat_type !== 'none' ? r.repeat_type : 'Sekali'})</small>`;
            listItem.appendChild(reminderDetails);

            const actionsDiv = document.createElement('div');
            actionsDiv.classList.add('reminder-actions');

            if (!r.is_completed) {
                const completeBtn = document.createElement('button');
                completeBtn.textContent = 'Selesai';
                completeBtn.classList.add('complete-btn');
                completeBtn.addEventListener('click', async () => {
                    try {
                        await sendRequest(`/complete_reminder/${r.id}`, 'POST');
                        showMessage(reminderMessageArea, 'Pengingat ditandai selesai!', 'success');
                        loadReminders(); // Reload reminders
                    } catch (error) {
                        showMessage(reminderMessageArea, `Gagal menandai selesai: ${error.message}`, 'error');
                    }
                });
                actionsDiv.appendChild(completeBtn);
            }

            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = 'Hapus';
            deleteBtn.classList.add('delete-btn');
            deleteBtn.addEventListener('click', async () => {
                if (confirm('Anda yakin ingin menghapus pengingat ini?')) {
                    try {
                        await sendRequest(`/delete_reminder/${r.id}`, 'DELETE');
                        showMessage(reminderMessageArea, 'Pengingat berhasil dihapus!', 'success');
                        loadReminders(); // Reload reminders
                    } catch (error) {
                        showMessage(reminderMessageArea, `Gagal menghapus: ${error.message}`, 'error');
                    }
                }
            });
            actionsDiv.appendChild(deleteBtn);

            listItem.appendChild(actionsDiv);
            reminderList.appendChild(listItem);
        });
    }

    async function loadReminders() {
        reminderList.innerHTML = '<li>Memuat pengingat...</li>';
        calendarEl.innerHTML = '<p>Memuat kalender...</p>'; 
        try {
            const reminders = await sendRequest('/get_reminders', 'GET'); 
            renderReminders(reminders);
            initializeCalendar(reminders); // Inisialisasi kalender dengan data
            showMessage(reminderMessageArea, `Pengingat berhasil dimuat.`, 'success');
        } catch (error) {
            reminderList.innerHTML = `<li>Gagal memuat pengingat: ${error.message}</li>`;
            calendarEl.innerHTML = '<p>Gagal memuat kalender.</p>';
            showMessage(reminderMessageArea, `Gagal memuat pengingat. Cek koneksi server: ${error.message}`, 'error');
        }
    }

    // --- Event Listeners ---
    setReminderBtn.addEventListener('click', async () => {
        const text = reminderTextarea.value.trim();
        if (!text) {
            showMessage(reminderMessageArea, 'Teks pengingat tidak boleh kosong.', 'error');
            return;
        }

        try {
            const result = await sendRequest('/set_reminder', 'POST', { text, user_id: DEFAULT_USER_ID });
            showMessage(reminderMessageArea, result.message, 'success');
            reminderTextarea.value = ''; 
            loadReminders(); 
        } catch (error) {
            showMessage(reminderMessageArea, `Gagal mengatur pengingat: ${error.message}`, 'error');
        }
    });

    // Panggil saat halaman dimuat
    loadReminders();
});
