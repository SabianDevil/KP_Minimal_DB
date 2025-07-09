// Function to generate a unique ID (UUID v4 like)
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Get or create user_id
let userId = localStorage.getItem('user_id');
if (!userId) {
    userId = generateUUID();
    localStorage.setItem('user_id', userId);
    console.log('New User ID generated:', userId);
    alert('Selamat datang! Ini adalah pengenal unik Anda. Jaga baik-baik agar jadwal Anda tidak hilang:\n\n' + userId);
} else {
    console.log('Existing User ID:', userId);
}

document.addEventListener('DOMContentLoaded', function() {
    const reminderInput = document.getElementById('reminderInput');
    const addReminderBtn = document.getElementById('addReminderBtn');
    const reminderListDiv = document.getElementById('reminderList');

    const calendarGrid = document.getElementById('calendarGrid');
    const currentMonthYearSpan = document.getElementById('currentMonthYear');
    const prevMonthBtn = document.getElementById('prevMonthBtn');
    const nextMonthBtn = document.getElementById('nextMonthBtn');
    const selectedDateRemindersDiv = document.getElementById('selectedDateReminders');
    const realtimeClockDiv = document.getElementById('realtimeClock'); 

    let currentMonth = new Date().getMonth();
    let currentYear = new Date().getFullYear();
    let selectedCalendarDate = null; 

    // --- Helper Functions ---
    const getMonthName = (monthIndex) => {
        const monthNames = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                            "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
        return monthNames[monthIndex];
    };

    // Fungsi untuk memperbarui jam dan tanggal realtime
    function updateRealtimeClock() {
        const now = new Date();
        const optionsDate = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const optionsTime = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };

        const formattedDate = now.toLocaleDateString('id-ID', optionsDate);
        const formattedTime = now.toLocaleTimeString('id-ID', optionsTime);

        realtimeClockDiv.textContent = `${formattedDate}, ${formattedTime} WIB`; 
    }

    // --- Core Reminder List Functions ---
    async function fetchReminders() {
        reminderListDiv.innerHTML = '<p class="loading">Memuat pengingat...</p>';
        try {
            const response = await fetch(`/get_reminders?user_id=${userId}`);
            const reminders = await response.json();

            if (response.status !== 200 && reminders.success === false) {
                 reminderListDiv.innerHTML = `<p class="error">Gagal memuat pengingat: ${reminders.message}</p>`;
                 return;
            }

            reminderListDiv.innerHTML = ''; 

            if (reminders.length === 0) {
                reminderListDiv.innerHTML = '<p class="no-reminders">Belum ada pengingat terjadwal.</p>';
                return;
            }

            reminders.forEach(r => {
                const reminderItem = createReminderDisplayElement(r); // Gunakan fungsi baru
                reminderListDiv.appendChild(reminderItem);
            });
        } catch (error) {
            console.error('Error fetching reminders:', error);
            reminderListDiv.innerHTML = '<p class="error">Gagal memuat pengingat. Silakan coba lagi.</p>';
        }
    }

    // Fungsi untuk membuat elemen tampilan pengingat dengan detail
    function createReminderDisplayElement(r, isCalendarDetail = false) {
        const reminderItem = document.createElement('div');
        reminderItem.className = 'reminder-item';
        if (r.notified) {
            reminderItem.classList.add('notified');
        }

        const mainContent = document.createElement('div');
        mainContent.className = 'reminder-main-content';

        const reminderText = document.createElement('span');
        reminderText.textContent = `${isCalendarDetail ? new Date(r.datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : r.formatted_datetime} - ${r.event} ${r.repeat_type !== 'none' ? '(Berulang)' : ''} ${isCalendarDetail ? `(${r.notified_status})` : ''}`;
        mainContent.appendChild(reminderText);

        const deleteButton = document.createElement('button');
        deleteButton.className = 'delete-btn';
        deleteButton.textContent = 'Hapus';
        deleteButton.onclick = (e) => {
            e.stopPropagation(); // Mencegah toggle detail saat klik hapus
            deleteReminder(r.id);
        };
        mainContent.appendChild(deleteButton);
        reminderItem.appendChild(mainContent);

        // --- Bagian Detail ---
        const detailContent = document.createElement('div');
        detailContent.className = 'reminder-detail-content';
        
        let detailsHtml = '';
        // Iterasi melalui metadata untuk menampilkan semua key-value pair
        if (r.metadata && typeof r.metadata === 'object') {
            for (const key in r.metadata) {
                if (r.metadata.hasOwnProperty(key) && r.metadata[key]) {
                    const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()); // Format key (e.g., "favorite_meals" -> "Favorite Meals")
                    detailsHtml += `<p><strong>${formattedKey}:</strong> ${r.metadata[key]}</p>`;
                }
            }
        }

        if (detailsHtml) {
            detailContent.innerHTML = detailsHtml;
            detailContent.style.display = 'none'; // Sembunyikan default
            reminderItem.appendChild(detailContent);

            const toggleBtn = document.createElement('div');
            toggleBtn.className = 'reminder-toggle-btn';
            toggleBtn.textContent = 'Lihat Detail ▼';
            toggleBtn.onclick = () => {
                if (detailContent.style.display === 'none') {
                    detailContent.style.display = 'block';
                    toggleBtn.textContent = 'Sembunyikan Detail ▲';
                } else {
                    detailContent.style.display = 'none';
                    toggleBtn.textContent = 'Lihat Detail ▼';
                }
            };
            mainContent.appendChild(toggleBtn); 
        }

        return reminderItem;
    }


    addReminderBtn.addEventListener('click', async function() {
        const fullNoteText = reminderInput.value.trim();
        if (!fullNoteText) {
            alert('Catatan pengingat tidak boleh kosong!');
            return;
        }

        try {
            // Mengirim seluruh teks ke endpoint baru
            const response = await fetch('/add_multiple_reminders', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ full_note_text: fullNoteText, user_id: userId }) 
            });

            const result = await response.json();
            if (result.success) {
                alert(result.message);
                reminderInput.value = '';
                fetchReminders(); 
                renderCalendar(currentMonth, currentYear); 
                if (selectedCalendarDate) {
                    showRemindersForSelectedDate(selectedCalendarDate); 
                }
            } else {
                alert('Gagal menambah pengingat: ' + result.message);
            }
        } catch (error) {
            console.error('Error adding reminder:', error);
            alert('Terjadi kesalahan saat menambahkan pengingat.');
        }
    });

    async function deleteReminder(id) {
        if (!confirm('Apakah Anda yakin ingin menghapus pengingat ini?')) {
            return;
        }
        try {
            const response = await fetch(`/delete_reminder/${id}?user_id=${userId}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (result.success) {
                alert(result.message);
                fetchReminders(); 
                renderCalendar(currentMonth, currentYear); 
                if (selectedCalendarDate) {
                    showRemindersForSelectedDate(selectedCalendarDate); 
                }
            } else {
                alert('Gagal menghapus pengingat: ' + result.message);
            }
        } catch (error) {
            console.error('Error deleting reminder:', error);
            alert('Terjadi kesalahan saat menghapus pengingat.');
        }
    }

    // --- Calendar Functions ---
    async function renderCalendar(month, year) {
        calendarGrid.innerHTML = ''; 
        currentMonthYearSpan.textContent = `${getMonthName(month)} ${year}`;

        const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
        dayNames.forEach(dayName => {
            const header = document.createElement('div');
            header.className = 'day-header';
            header.textContent = dayName;
            calendarGrid.appendChild(header);
        });

        const firstDayOfMonth = new Date(year, month, 1);
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startDay = firstDayOfMonth.getDay(); 

        let monthlyReminders = [];
        try {
            const response = await fetch(`/get_reminders_for_month?year=${year}&month=${month + 1}&user_id=${userId}`);
            if (response.status !== 200) {
                console.error('Failed to fetch monthly reminders. Status:', response.status);
                return;
            }
            monthlyReminders = await response.json();
        } catch (error) {
            console.error('Error fetching monthly reminders:', error);
        }

        for (let i = 0; i < startDay; i++) {
            const emptyDay = document.createElement('div');
            emptyDay.className = 'calendar-day empty-day';
            calendarGrid.appendChild(emptyDay);
        }

        for (let day = 1; day <= daysInMonth; day++) {
            const dayElement = document.createElement('div');
            dayElement.className = 'calendar-day';
            dayElement.dataset.date = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
            dayElement.onclick = () => selectCalendarDay(dayElement);

            const dayNumberSpan = document.createElement('span');
            dayNumberSpan.className = 'day-number';
            dayNumberSpan.textContent = day;
            dayElement.appendChild(dayNumberSpan);

            const remindersOnThisDay = monthlyReminders.filter(r => {
                return r.date === dayElement.dataset.date;
            });

            if (remindersOnThisDay.length > 0) {
                const marker = document.createElement('div');
                marker.className = 'reminder-marker';
                if (remindersOnThisDay.length > 1) {
                    marker.classList.add('multi');
                }
                dayElement.appendChild(marker);
            }
            
            if (selectedCalendarDate && dayElement.dataset.date === selectedCalendarDate) {
                dayElement.classList.add('selected');
            }

            calendarGrid.appendChild(dayElement);
        }
    }

    function selectCalendarDay(dayElement) {
        const previouslySelected = document.querySelector('.calendar-day.selected');
        if (previouslySelected) {
            previouslySelected.classList.remove('selected');
        }

        dayElement.classList.add('selected');
        selectedCalendarDate = dayElement.dataset.date;

        showRemindersForSelectedDate(selectedCalendarDate);
    }

    async function showRemindersForSelectedDate(dateString) {
        selectedDateRemindersDiv.innerHTML = '<p class="loading">Memuat pengingat...</p>';
        try {
            const response = await fetch(`/get_reminders?user_id=${userId}`); 
            const allReminders = await response.json();

            if (response.status !== 200 && allReminders.success === false) {
                 selectedDateRemindersDiv.innerHTML = `<p class="error">Gagal memuat pengingat: ${allReminders.message}</p>`;
                 return;
            }

            const remindersOnThisDate = allReminders.filter(r => {
                const reminderDate = new Date(r.datetime).toISOString().slice(0, 10); 
                return reminderDate === dateString;
            });

            selectedDateRemindersDiv.innerHTML = '';

            if (remindersOnThisDate.length === 0) {
                selectedDateRemindersDiv.innerHTML = `<p class="no-reminders">Tidak ada jadwal pada ${dateString}.</p>`;
                return;
            }

            remindersOnThisDate.sort((a, b) => {
                const timeA = new Date(a.datetime).getTime();
                const timeB = new Date(b.datetime).getTime();
                return timeA - timeB;
            });

            remindersOnThisDate.forEach(r => {
                const reminderItem = createReminderDisplayElement(r, true); 
                selectedDateRemindersDiv.appendChild(reminderItem);
            });

        } catch (error) {
            console.error('Error fetching reminders for selected date:', error);
            selectedDateRemindersDiv.innerHTML = '<p class="error">Gagal memuat jadwal untuk tanggal ini.</p>';
        }
    }


    // --- Navigation Buttons ---
    prevMonthBtn.addEventListener('click', () => {
        currentMonth--;
        if (currentMonth < 0) {
            currentMonth = 11;
            currentYear--;
        }
        selectedCalendarDate = null; 
        renderCalendar(currentMonth, currentYear);
        selectedDateRemindersDiv.innerHTML = '<p class="no-selection">Pilih tanggal di kalender untuk melihat jadwal.</p>';
    });

    nextMonthBtn.addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 11) {
            currentMonth = 0;
            currentYear++;
        }
        selectedCalendarDate = null; 
        renderCalendar(currentMonth, currentYear);
        selectedDateRemindersDiv.innerHTML = '<p class="no-selection">Pilih tanggal di kalender untuk melihat jadwal.</p>';
    });

    // --- Initialization ---
    updateRealtimeClock(); 
    setInterval(updateRealtimeClock, 1000); 

    fetchReminders(); 
    renderCalendar(currentMonth, currentYear); 

    setInterval(() => {
        fetchReminders();
        renderCalendar(currentMonth, currentYear);
        if (selectedCalendarDate) {
            showRemindersForSelectedDate(selectedCalendarDate);
        }
    }, 10000); 
});
