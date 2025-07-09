document.addEventListener('DOMContentLoaded', function() {
    const reminderInput = document.getElementById('reminderInput');
    const addReminderBtn = document.getElementById('addReminderBtn');
    const reminderListDiv = document.getElementById('reminderList');

    const calendarGrid = document.getElementById('calendarGrid');
    const currentMonthYearSpan = document.getElementById('currentMonthYear');
    const prevMonthBtn = document.getElementById('prevMonthBtn');
    const nextMonthBtn = document.getElementById('nextMonthBtn');
    const selectedDateRemindersDiv = document.getElementById('selectedDateReminders');

    let currentMonth = new Date().getMonth();
    let currentYear = new Date().getFullYear();
    let selectedCalendarDate = null; // To store the currently selected date in the calendar

    // --- Helper Functions ---
    const getMonthName = (monthIndex) => {
        const monthNames = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                            "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
        return monthNames[monthIndex];
    };

    const getDayName = (dayIndex) => {
        const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
        return dayNames[dayIndex];
    };

    // --- Core Reminder List Functions ---
    async function fetchReminders() {
        reminderListDiv.innerHTML = '<p class="loading">Memuat pengingat...</p>';
        try {
            const response = await fetch('/get_reminders');
            const reminders = await response.json();

            reminderListDiv.innerHTML = ''; // Clear previous content

            if (reminders.length === 0) {
                reminderListDiv.innerHTML = '<p class="no-reminders">Belum ada pengingat terjadwal.</p>';
                return;
            }

            reminders.forEach(r => {
                const reminderItem = document.createElement('div');
                reminderItem.className = 'reminder-item';
                if (r.notified) {
                    reminderItem.classList.add('notified');
                }

                const reminderText = document.createElement('span');
                reminderText.textContent = `${r.formatted_datetime} - ${r.event} ${r.repeat_type !== 'none' ? '(Berulang)' : ''}`;
                
                const deleteButton = document.createElement('button');
                deleteButton.className = 'delete-btn';
                deleteButton.textContent = 'Hapus';
                deleteButton.onclick = () => deleteReminder(r.id);

                reminderItem.appendChild(reminderText);
                reminderItem.appendChild(deleteButton);
                reminderListDiv.appendChild(reminderItem);
            });
        } catch (error) {
            console.error('Error fetching reminders:', error);
            reminderListDiv.innerHTML = '<p class="error">Gagal memuat pengingat. Silakan coba lagi.</p>';
        }
    }

    addReminderBtn.addEventListener('click', async function() {
        const note = reminderInput.value.trim();
        if (!note) {
            alert('Catatan pengingat tidak boleh kosong!');
            return;
        }

        try {
            const response = await fetch('/add_reminder', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ note: note })
            });

            const result = await response.json();
            if (result.success) {
                alert(result.message);
                reminderInput.value = '';
                fetchReminders(); // Refresh general list
                renderCalendar(currentMonth, currentYear); // Refresh calendar
                if (selectedCalendarDate) {
                    showRemindersForSelectedDate(selectedCalendarDate); // Refresh selected date's reminders
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
            const response = await fetch(`/delete_reminder/${id}`, {
                method: 'DELETE'
            });
            const result = await response.json();
            if (result.success) {
                alert(result.message);
                fetchReminders(); // Refresh general list
                renderCalendar(currentMonth, currentYear); // Refresh calendar
                if (selectedCalendarDate) {
                    showRemindersForSelectedDate(selectedCalendarDate); // Refresh selected date's reminders
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
        calendarGrid.innerHTML = ''; // Clear previous calendar
        currentMonthYearSpan.textContent = `${getMonthName(month)} ${year}`;

        // Add day headers
        const dayNames = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
        dayNames.forEach(dayName => {
            const header = document.createElement('div');
            header.className = 'day-header';
            header.textContent = dayName;
            calendarGrid.appendChild(header);
        });

        const firstDayOfMonth = new Date(year, month, 1);
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startDay = firstDayOfMonth.getDay(); // 0 for Sunday, 1 for Monday, etc.

        // Fetch reminders for the current month
        let monthlyReminders = [];
        try {
            const response = await fetch(`/get_reminders_for_month?year=${year}&month=${month + 1}`); // month is 0-indexed in JS, 1-indexed in Python
            monthlyReminders = await response.json();
        } catch (error) {
            console.error('Error fetching monthly reminders:', error);
        }

        // Create empty leading days
        for (let i = 0; i < startDay; i++) {
            const emptyDay = document.createElement('div');
            emptyDay.className = 'calendar-day empty-day';
            calendarGrid.appendChild(emptyDay);
        }

        // Create days of the month
        for (let day = 1; day <= daysInMonth; day++) {
            const dayElement = document.createElement('div');
            dayElement.className = 'calendar-day';
            // dayElement.textContent = day; // HAPUS BARIS INI UNTUK MENGHILANGKAN DUPLIKASI
            dayElement.dataset.date = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`; // YYYY-MM-DD
            dayElement.onclick = () => selectCalendarDay(dayElement);

            const dayNumberSpan = document.createElement('span');
            dayNumberSpan.className = 'day-number';
            dayNumberSpan.textContent = day;
            dayElement.appendChild(dayNumberSpan);

            // Add reminder markers
            const remindersOnThisDay = monthlyReminders.filter(r => {
                // Ensure r.date is correctly formatted 'YYYY-MM-DD'
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
            
            // Mark the selected day if it matches
            if (selectedCalendarDate && dayElement.dataset.date === selectedCalendarDate) {
                dayElement.classList.add('selected');
                showRemindersForSelectedDate(selectedCalendarDate);
            }

            calendarGrid.appendChild(dayElement);
        }
    }

    function selectCalendarDay(dayElement) {
        // Remove 'selected' class from previous selected day
        const previouslySelected = document.querySelector('.calendar-day.selected');
        if (previouslySelected) {
            previouslySelected.classList.remove('selected');
        }

        // Add 'selected' class to the new day
        dayElement.classList.add('selected');
        selectedCalendarDate = dayElement.dataset.date; // Store as YYYY-MM-DD string

        showRemindersForSelectedDate(selectedCalendarDate);
    }

    async function showRemindersForSelectedDate(dateString) {
        selectedDateRemindersDiv.innerHTML = '<p class="loading">Memuat pengingat...</p>';
        try {
            const response = await fetch('/get_reminders'); // Get all reminders
            const allReminders = await response.json();

            const remindersOnThisDate = allReminders.filter(r => {
                const reminderDate = new Date(r.datetime).toISOString().slice(0, 10); // Extract YYYY-MM-DD
                return reminderDate === dateString;
            });

            selectedDateRemindersDiv.innerHTML = '';

            if (remindersOnThisDate.length === 0) {
                selectedDateRemindersDiv.innerHTML = `<p class="no-reminders">Tidak ada jadwal pada ${dateString}.</p>`;
                return;
            }

            // Sort by time
            remindersOnThisDate.sort((a, b) => {
                const timeA = new Date(a.datetime).getTime();
                const timeB = new Date(b.datetime).getTime();
                return timeA - timeB;
            });

            remindersOnThisDate.forEach(r => {
                const reminderItem = document.createElement('div');
                reminderItem.className = 'reminder-item';
                if (r.notified) {
                    reminderItem.classList.add('notified');
                }

                const time = new Date(r.datetime).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
                const reminderText = document.createElement('span');
                reminderText.textContent = `${time} - ${r.event} ${r.repeat_type !== 'none' ? '(Berulang)' : ''} (${r.notified_status})`;
                
                const deleteButton = document.createElement('button');
                deleteButton.className = 'delete-btn';
                deleteButton.textContent = 'Hapus';
                deleteButton.onclick = () => deleteReminder(r.id);

                reminderItem.appendChild(reminderText);
                reminderItem.appendChild(deleteButton);
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
        renderCalendar(currentMonth, currentYear);
    });

    nextMonthBtn.addEventListener('click', () => {
        currentMonth++;
        if (currentMonth > 11) {
            currentMonth = 0;
            currentYear++;
        }
        renderCalendar(currentMonth, currentYear);
    });

    // --- Initialization ---
    fetchReminders(); // Initial load of general reminder list
    renderCalendar(currentMonth, currentYear); // Initial render of calendar

    // Refresh reminders list every 10 seconds and re-render calendar
    setInterval(() => {
        fetchReminders();
        renderCalendar(currentMonth, currentYear);
        if (selectedCalendarDate) {
            showRemindersForSelectedDate(selectedCalendarDate);
        }
    }, 10000); 
});
