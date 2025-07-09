document.addEventListener('DOMContentLoaded', function() {
    const myButton = document.getElementById('myButton');

    if (myButton) { // Pastikan tombol ada sebelum menambahkan event listener
        myButton.addEventListener('click', function() {
            alert('Halo dari JavaScript di root!');
        });
    }
});
