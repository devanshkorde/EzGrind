document.getElementById("signupForm").addEventListener("submit", function (e) {
    e.preventDefault();

    const fullName = document.getElementById("fullName").value.trim();
    const email = document.getElementById("email").value.trim();
    const contact = document.getElementById("contact").value.trim();
    const dob = document.getElementById("dob").value;
    const height = document.getElementById("height").value;
    const weight = document.getElementById("weight").value;
    const goal = document.getElementById("fitnessGoal").value;
    const password = document.getElementById("password").value;

    // 🔎 Name validation (letters and spaces only)
    const nameRegex = /^[A-Za-z ]+$/;
    if (!nameRegex.test(fullName)) {
        alert("Name should contain only letters.");
        return;
    }

    // 🔎 Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        alert("Enter a valid email address.");
        return;
    }

    // 🔎 Contact number validation (10 digits)
    const contactRegex = /^[0-9]{10}$/;
    if (!contactRegex.test(contact)) {
        alert("Contact number must be 10 digits.");
        return;
    }

    // 🔎 Height validation
    if (height <= 0 || height > 300) {
        alert("Enter a valid height in cm.");
        return;
    }

    // 🔎 Weight validation
    if (weight <= 0 || weight > 500) {
        alert("Enter a valid weight in kg.");
        return;
    }

    // 🔎 Fitness goal required
    if (!goal) {
        alert("Please select a fitness goal.");
        return;
    }

    // 🔎 Password validation (min 6 chars)
    if (password.length < 6) {
        alert("Password must be at least 6 characters.");
        return;
    }

    // If all validations pass → Send to backend
    fetch("http://127.0.0.1:5000/api/signup", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            full_name: fullName,
            email: email,
            password: password,
            contact_number: contact,
            date_of_birth: dob,
            height_cm: height,
            weight_kg: weight,
            fitness_goal: goal
        })
    })
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        if (data.message === "Signup successful 🎉") {
            window.location.href = "login.html";
        }
    });
});
