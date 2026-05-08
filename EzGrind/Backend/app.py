from flask import Flask, jsonify, request, session
from flask_cors import CORS
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import re

app = Flask(__name__)

# ✅ SECRET KEY
app.secret_key = "ezgrind_secret_key"

# ✅ FIX SESSION (IMPORTANT FOR LOGIN)
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = False

# ✅ FIX CORS (MAIN ISSUE FIXED HERE)
CORS(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})


def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="1234",
        database="ezgrind_db"
    )


@app.route("/")
def home():
    return jsonify({"message": "EzGrind backend is running successfully 🚀"})


# =========================
# MUSCLES
# =========================
@app.route("/api/muscles", methods=["GET"])
def get_muscles():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT muscle_id, muscle_name, image_path FROM muscle_groups")
    muscles = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(muscles)


# =========================
# EXERCISES
# =========================
@app.route("/api/exercises", methods=["GET"])
def get_exercises():
    muscle_id = request.args.get("muscle_id")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if muscle_id:
        cursor.execute("""
            SELECT exercise_id, exercise_name, equipment
            FROM exercises
            WHERE muscle_id = %s
            ORDER BY exercise_name
        """, (muscle_id,))
    else:
        cursor.execute("""
            SELECT exercise_id, exercise_name, equipment
            FROM exercises
            ORDER BY exercise_name
        """)

    exercises = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(exercises)


# =========================
# LOG WORKOUT
# =========================
@app.route("/api/log-workout", methods=["POST"])
def log_workout():
    if "user_id" not in session:
        return jsonify({"message": "Unauthorized"}), 401

    user_id = session["user_id"]
    data = request.json

    exercise_id = data["exercise_id"]
    weight = data["weight"]
    reps = data["reps"]
    tut = data.get("time_under_tension")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT workout_id FROM workouts WHERE user_id=%s AND workout_date=CURDATE()",
        (user_id,)
    )
    result = cursor.fetchone()

    if result:
        workout_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO workouts (user_id, workout_date) VALUES (%s, CURDATE())",
            (user_id,)
        )
        workout_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO workout_sets 
        (workout_id, exercise_id, weight, reps, time_under_tension)
        VALUES (%s, %s, %s, %s, %s)
    """, (workout_id, exercise_id, weight, reps, tut))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Workout logged successfully 💪"})


# =========================
# SIGNUP
# =========================
@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json

    full_name = data["full_name"]
    email = data["email"]
    password = data["password"]

    contact_number = data.get("contact_number")
    date_of_birth = data.get("date_of_birth")
    height_cm = data.get("height_cm")
    weight_kg = data.get("weight_kg")
    fitness_goal = data.get("fitness_goal")

    # VALIDATIONS
    if not re.match(r'^[A-Za-z ]+$', full_name):
        return jsonify({"message": "Invalid name"}), 400

    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        return jsonify({"message": "Invalid email"}), 400

    if len(password) < 6:
        return jsonify({"message": "Password too short"}), 400

    if contact_number and not re.match(r'^[0-9]{10}$', contact_number):
        return jsonify({"message": "Invalid contact number"}), 400

    if height_cm:
        try:
            height_cm = int(height_cm)
        except:
            return jsonify({"message": "Height must be number"}), 400

    if weight_kg:
        try:
            weight_kg = int(weight_kg)
        except:
            return jsonify({"message": "Weight must be number"}), 400

    if not fitness_goal:
        return jsonify({"message": "Fitness goal required"}), 400

    hashed_password = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT user_id FROM users WHERE email=%s", (email,))
    if cursor.fetchone():
        return jsonify({"message": "Email already exists"}), 400

    cursor.execute("""
        INSERT INTO users 
        (full_name, email, password_hash, contact_number, date_of_birth, height_cm, weight_kg, fitness_goal)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        full_name, email, hashed_password,
        contact_number, date_of_birth,
        height_cm, weight_kg, fitness_goal
    ))

    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"message": "Signup successful 🎉"})


# =========================
# LOGIN
# =========================
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json

    email = data["email"]
    password = data["password"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT user_id, full_name, password_hash FROM users WHERE email=%s",
        (email,)
    )
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"message": "Invalid credentials"}), 401

    session["user_id"] = user["user_id"]
    session["full_name"] = user["full_name"]

    return jsonify({"message": "Login successful"})


# =========================
# LOGOUT
# =========================
@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Logged out"})


# =========================
# PROFILE
# =========================
@app.route("/api/me", methods=["GET"])
def get_user():
    if "user_id" not in session:
        return jsonify({"message": "Not logged in"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT full_name, email, date_of_birth, height_cm, weight_kg, fitness_goal
        FROM users
        WHERE user_id = %s
    """, (session["user_id"],))

    user = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify(user)


# =========================
# TODAY WORKOUT
# =========================
@app.route("/api/today-workout", methods=["GET"])
def today_workout():
    if "user_id" not in session:
        return jsonify({"message": "Not logged in"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT e.exercise_name, COUNT(ws.set_id) AS total_sets
        FROM workouts w
        JOIN workout_sets ws ON w.workout_id = ws.workout_id
        JOIN exercises e ON ws.exercise_id = e.exercise_id
        WHERE w.user_id = %s AND w.workout_date = CURDATE()
        GROUP BY e.exercise_name
    """, (session["user_id"],))

    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)


# =========================
# WORKOUT HISTORY
# =========================
@app.route("/api/workout-history", methods=["GET"])
def history():
    if "user_id" not in session:
        return jsonify({"message": "Unauthorized"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT w.workout_date, e.exercise_name, ws.weight, ws.reps
        FROM workouts w
        JOIN workout_sets ws ON w.workout_id = ws.workout_id
        JOIN exercises e ON ws.exercise_id = e.exercise_id
        WHERE w.user_id = %s
        ORDER BY w.workout_date DESC
    """, (session["user_id"],))

    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)
