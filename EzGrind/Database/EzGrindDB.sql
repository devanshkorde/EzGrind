CREATE DATABASE ezgrind_db;
USE ezgrind_db;

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE muscle_groups (
    muscle_id INT AUTO_INCREMENT PRIMARY KEY,
    muscle_name VARCHAR(50) NOT NULL,
    image_path VARCHAR(255) NOT NULL
);

CREATE TABLE exercises (
    exercise_id INT AUTO_INCREMENT PRIMARY KEY,
    exercise_name VARCHAR(100) NOT NULL,
    muscle_id INT NOT NULL,
    equipment VARCHAR(50),
    description TEXT,
    FOREIGN KEY (muscle_id) REFERENCES muscle_groups(muscle_id)
);

CREATE TABLE workouts (
    workout_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    workout_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE workout_sets (
    set_id INT AUTO_INCREMENT PRIMARY KEY,
    workout_id INT NOT NULL,
    exercise_id INT NOT NULL,
    weight DECIMAL(5,2),
    reps INT,
    time_under_tension INT,
    FOREIGN KEY (workout_id) REFERENCES workouts(workout_id),
    FOREIGN KEY (exercise_id) REFERENCES exercises(exercise_id)
);

-- Queries
SHOW TABLES;
SELECT * FROM workout_sets;
SELECT user_id, full_name, email FROM users;
SELECT * FROM users;

-- Fix applied here
ALTER TABLE users
ADD COLUMN contact_number VARCHAR(15),
ADD COLUMN date_of_birth DATE,
ADD COLUMN height_cm INT,
ADD COLUMN weight_kg INT,
ADD COLUMN fitness_goal VARCHAR(20);

DESCRIBE users;

-- Modify datatype
ALTER TABLE users
MODIFY COLUMN height_cm FLOAT,
MODIFY COLUMN weight_kg FLOAT;

SELECT * FROM exercises;

-- Join query
SELECT 
    w.workout_date,
    e.exercise_name,
    ws.weight,
    ws.reps
FROM workouts w
JOIN workout_sets ws ON w.workout_id = ws.workout_id
JOIN exercises e ON ws.exercise_id = e.exercise_id
WHERE w.user_id = 1;

