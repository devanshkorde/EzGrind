fetch("http://127.0.0.1:5000/api/workout-history", {
    credentials: "include"
})
.then(res => res.json())
.then(data => {

    const container = document.getElementById("historyContainer");
    container.innerHTML = "";

    if (data.length === 0) {
        container.innerHTML = "<p>No workout history yet 💭</p>";
        return;
    }

    data.forEach(item => {

        const div = document.createElement("div");
        div.classList.add("history-card");

        div.innerHTML = `
            <h3>${item.workout_date}</h3>
            <p><strong>${item.exercise_name}</strong></p>
            <p>${item.weight} kg × ${item.reps} reps</p>
            <hr>
        `;

        container.appendChild(div);
    });

});
