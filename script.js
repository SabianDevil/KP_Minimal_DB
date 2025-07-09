document.addEventListener('DOMContentLoaded', function() {
    const reminderInput = document.getElementById('reminderInput');
    const addReminderBtn = document.getElementById('addReminderBtn');
    const reminderListDiv = document.getElementById('reminderList');

    // Function to fetch and display reminders
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
                if (r.notified) { // Jika sudah dinotifikasi
                    reminderItem.classList.add('notified');
                }

                const reminderText = document.createElement('span');
                // Menggunakan formatted_datetime dari backend
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

    // Function to add a reminder
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
                reminderInput.value = ''; // Clear input
                fetchReminders(); // Refresh list
            } else {
                alert('Gagal menambah pengingat: ' + result.message);
            }
        } catch (error) {
            console.error('Error adding reminder:', error);
            alert('Terjadi kesalahan saat menambahkan pengingat.');
        }
    });

    // Function to delete a reminder
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
                fetchReminders(); // Refresh list
            } else {
                alert('Gagal menghapus pengingat: ' + result.message);
            }
        } catch (error) {
            console.error('Error deleting reminder:', error);
            alert('Terjadi kesalahan saat menghapus pengingat.');
        }
    }

    // Initial fetch of reminders when page loads
    fetchReminders();

    // Refresh reminders list every 10 seconds (for simple updates)
    // For real-time updates without polling, WebSockets would be needed.
    setInterval(fetchReminders, 10000); 
});
