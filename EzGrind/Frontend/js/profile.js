fetch("http://127.0.0.1:5000/api/me", {
    credentials: "include"
})
.then(res => res.json())
.then(data => {

    document.getElementById("name").textContent = data.full_name;
    document.getElementById("email").textContent = data.email;

    // Calculate Age
    const dob = new Date(data.date_of_birth);
    const today = new Date();
    let age = today.getFullYear() - dob.getFullYear();
    const monthDiff = today.getMonth() - dob.getMonth();

    if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < dob.getDate())) {
        age--;
    }

    document.getElementById("age").textContent = age;
    document.getElementById("height").textContent = data.height_cm + " cm";
    document.getElementById("weight").textContent = data.weight_kg + " kg";
    document.getElementById("goal").textContent = data.fitness_goal;
});


// Logout logic
document.getElementById("logoutBtn").addEventListener("click", function () {
    fetch("http://127.0.0.1:5000/api/logout", {
        method: "POST",
        credentials: "include"
    })
    .then(res => res.json())
    .then(() => {
        window.location.href = "login.html";
    });
});
