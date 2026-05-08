const muscleSelect = document.getElementById("muscleSelect");
const exerciseSelect = document.getElementById("exerciseSelect");

fetch("http://127.0.0.1:5000/api/muscles")
.then(res => res.json())
.then(data => {
    muscleSelect.innerHTML = "<option value=''>Select Muscle</option>";

    data.forEach(muscle => {
        const option = document.createElement("option");
        option.value = muscle.muscle_id;
        option.textContent = muscle.muscle_name;
        muscleSelect.appendChild(option);
    });
});


muscleSelect.addEventListener("change", function () {

    const muscleId = this.value;

    if (!muscleId) {
        exerciseSelect.innerHTML = "";
        return;
    }

    fetch(`http://127.0.0.1:5000/api/exercises?muscle_id=${muscleId}`)
    .then(res => res.json())
    .then(data => {

        exerciseSelect.innerHTML = "";

        data.forEach(exercise => {
            const option = document.createElement("option");
            option.value = exercise.exercise_id;
            option.textContent = exercise.exercise_name;
            exerciseSelect.appendChild(option);
        });

    });

});


const statusText = document.getElementById("status");

// Load exercises into dropdown
fetch("http://127.0.0.1:5000/api/exercises")
    .then(res => res.json())
    .then(data => {
        data.forEach(ex => {
            const option = document.createElement("option");
            option.value = ex.exercise_id;
            option.text = ex.exercise_name;
            exerciseSelect.appendChild(option);
        });
    });

// Submit workout set
document.getElementById("workoutForm").addEventListener("submit", function (e) {
    e.preventDefault();

    const payload = {
        user_id: 1,  // demo user
        exercise_id: exerciseSelect.value,
        weight: document.getElementById("weight").value,
        reps: document.getElementById("reps").value,
        time_under_tension: document.getElementById("tut").value
    };

    fetch("http://127.0.0.1:5000/api/log-workout", {
        method: "POST",
        credentials: "include", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        statusText.innerText = data.message;
        document.getElementById("workoutForm").reset();
    });
});
