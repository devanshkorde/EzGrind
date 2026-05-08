console.log("Dashboard JS loaded");

// Fetch logged-in user info for greeting
fetch("http://127.0.0.1:5000/api/me", {
    credentials: "include"
})
.then(res => {
    if (res.status === 401) {
        // Not logged in → show generic message
        const greeting = document.getElementById("greetingText");
        if (greeting) {
            greeting.innerText = "Welcome to EzGrind 👋";
        }
        return null;
    }
    return res.json();
})
.then(data => {
    if (!data) return;

    const greeting = document.getElementById("greetingText");
    if (greeting) {
        greeting.innerText = `Welcome back, ${data.full_name} 👋`;
    }

// 🔥 SHOW HISTORY BUTTON
    const historyBtn = document.getElementById("historyBtn");
    if (historyBtn) {
        historyBtn.style.display = "inline-block";
    }

});

// Fetch today's workout (only if logged in)
fetch("http://127.0.0.1:5000/api/today-workout", {
    credentials: "include"
})
.then(res => {
    if (res.status === 401) {
        // Not logged in → keep section hidden
        return null;
    }
    return res.json();
})
.then(data => {
    if (!data) return;

    const section = document.getElementById("todayWorkoutSection");
    const list = document.getElementById("todayWorkoutList");

    section.style.display = "block";

    if (data.length === 0) {
    list.innerHTML = `
        <li>You haven’t logged a workout today 💭</li>
        <li>
            <button id="logWorkoutBtn" class="small-cta-btn">
                Log a Workout
            </button>
        </li>
    `;

    document.getElementById("logWorkoutBtn").addEventListener("click", function () {
        window.location.href = "log-workout.html";
    });

    return;

}

    data.forEach(item => {
        const li = document.createElement("li");
        li.innerText = `${item.exercise_name} – ${item.total_sets} sets`;
        list.appendChild(li);
    });
});



document.addEventListener("DOMContentLoaded", function () {

    const authModal = document.getElementById("authModal");
    const startBtn = document.getElementById("startTodayBtn");
    const profileBtn = document.getElementById("profileBtn");
    const loginBtn = document.getElementById("loginRedirectBtn");
    const signupBtn = document.getElementById("signupRedirectBtn");

    function showAuthModal() {
        if (authModal) {
            authModal.style.display = "flex";
        }
    }

    // START TODAY BUTTON
    if (startBtn) {
        startBtn.addEventListener("click", function () {

            fetch("http://127.0.0.1:5000/api/me", {
                credentials: "include"
            })
            .then(res => {
                if (res.status === 401) {
                    showAuthModal();
                } else {
                    window.location.href = "log-workout.html";
                }
            });

        });
    }

    // PROFILE BUTTON
    if (profileBtn) {
        profileBtn.addEventListener("click", function () {

            fetch("http://127.0.0.1:5000/api/me", {
                credentials: "include"
            })
            .then(res => {
                if (res.status === 401) {
                    showAuthModal();
                } else {
                    window.location.href = "profile.html";
                }
            });

        });
    }

    // LOGIN BUTTON IN MODAL
    if (loginBtn) {
        loginBtn.addEventListener("click", function () {
            window.location.href = "login.html";
        });
    }

    // SIGNUP BUTTON IN MODAL
    if (signupBtn) {
        signupBtn.addEventListener("click", function () {
            window.location.href = "signup.html";
        });
    }

});


const startTodayBtn = document.getElementById("startTodayBtn");
const letsGrindBtn = document.getElementById("letsGrindBtn");

fetch("http://127.0.0.1:5000/api/me", {
    credentials: "include"
})
.then(res => {
    if (res.status === 401) {
        // User NOT logged in
        startTodayBtn.style.display = "inline-block";
        letsGrindBtn.style.display = "none";
    } else {
        // User logged in
        startTodayBtn.style.display = "none";
        letsGrindBtn.style.display = "inline-block";
    }
});


if (startTodayBtn) {
    startTodayBtn.addEventListener("click", function () {
        showAuthModal();  // your existing modal function
    });
}

if (letsGrindBtn) {
    letsGrindBtn.addEventListener("click", function () {
        window.location.href = "log-workout.html";
    });
}

