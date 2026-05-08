const API_URL = "http://127.0.0.1:5000/api/exercises";

fetch(API_URL)
    .then(response => response.json())
    .then(data => {
        renderExercises(data);
    })
    .catch(error => {
        console.error("Error fetching exercises:", error);
    });

function renderExercises(exercises) {
    const grid = document.getElementById("exerciseGrid");

    exercises.forEach(ex => {
        const card = document.createElement("div");
        card.className = "exercise-card";

        card.innerHTML = `
            <img src="${ex.image_path}" alt="${ex.muscle_name}">
            <h3>${ex.exercise_name}</h3>
            <p>${ex.muscle_name}</p>
            <span>${ex.equipment}</span>
        `;

        grid.appendChild(card);
    });
}
