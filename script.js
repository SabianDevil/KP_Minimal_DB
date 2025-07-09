document.addEventListener('DOMContentLoaded', function() {
    const myButton = document.getElementById('myButton');

    if (myButton) {
        myButton.addEventListener('click', function() {
            alert('Halo dari JavaScript di Dockerized Root App!');
        });
    } else {
        console.error('Tombol dengan ID "myButton" tidak ditemukan.');
    }
});
