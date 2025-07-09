document.addEventListener('DOMContentLoaded', () => {
    // Register Form elements
    const regUsername = document.getElementById('regUsername');
    const regEmail = document.getElementById('regEmail');
    const regPassword = document.getElementById('regPassword');
    const registerBtn = document.getElementById('registerBtn');

    // Login Form elements
    const logUsername = document.getElementById('logUsername');
    const logPassword = document.getElementById('logPassword');
    const loginBtn = document.getElementById('loginBtn');

    // User List elements
    const loadUsersBtn = document.getElementById('loadUsersBtn');
    const userList = document.getElementById('userList');

    const messageArea = document.getElementById('messageArea');

    function showMessage(message, type) {
        messageArea.textContent = message;
        messageArea.className = `message-area visible ${type}`;
        setTimeout(() => {
            messageArea.classList.remove('visible');
        }, 5000);
    }

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
            showMessage(`Error: ${error.message}`, 'error');
            throw error; // Re-throw to be caught by caller
        }
    }

    // --- Register User ---
    registerBtn.addEventListener('click', async () => {
        const username = regUsername.value.trim();
        const email = regEmail.value.trim();
        const password = regPassword.value.trim();

        if (!username || !email || !password) {
            showMessage('Semua field registrasi harus diisi.', 'error');
            return;
        }

        try {
            const result = await sendRequest('/register', 'POST', { username, email, password });
            showMessage(result.message, 'success');
            regUsername.value = '';
            regEmail.value = '';
            regPassword.value = '';
            loadUsers(); // Refresh user list
        } catch (error) {
            // Error already shown by sendRequest
        }
    });

    // --- Login User ---
    loginBtn.addEventListener('click', async () => {
        const username = logUsername.value.trim();
        const password = logPassword.value.trim();

        if (!username || !password) {
            showMessage('Username dan password login harus diisi.', 'error');
            return;
        }

        try {
            const result = await sendRequest('/login', 'POST', { username, password });
            showMessage(result.message, 'success');
            logUsername.value = '';
            logPassword.value = '';
        } catch (error) {
            // Error already shown by sendRequest
        }
    });

    // --- Load All Users ---
    async function loadUsers() {
        userList.innerHTML = '<li>Memuat pengguna...</li>';
        try {
            const result = await sendRequest('/get_all_users', 'GET');
            userList.innerHTML = ''; // Clear list

            if (result.length === 0) {
                userList.innerHTML = '<li>Belum ada pengguna terdaftar.</li>';
            } else {
                result.forEach(user => {
                    const listItem = document.createElement('li');
                    listItem.textContent = `ID: ${user.id} | User: ${user.username} | Email: ${user.email}`;
                    userList.appendChild(listItem);
                });
            }
        } catch (error) {
            userList.innerHTML = '<li>Gagal memuat daftar pengguna.</li>';
        }
    }

    loadUsersBtn.addEventListener('click', loadUsers); // Button to manually load users
    loadUsers(); // Load users on page load
});
