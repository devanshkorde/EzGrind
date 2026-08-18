-- =====================================================================
-- muscle_groups_and_exercises.sql                   PostgreSQL 16 (Neon)
-- =====================================================================
-- Reference data. Without this, a freshly created database has empty
-- muscle and exercise dropdowns, so no workout can be logged and every
-- downstream feature is dead. It is not optional for a fresh install.
--
-- WHY EXPLICIT IDs
-- ON CONFLICT DO NOTHING skips a row when it collides with ANY unique
-- constraint. Writing the ids out means the collision happens on the
-- primary key, so this file is re-runnable even before the unique index
-- on lower(muscle_name) exists. The ids below match the rows that were in
-- the MySQL database, so a migrated install and a fresh one agree.
--
-- Existing rows are never modified - a collision skips, so any description
-- edited by hand survives re-running this file.
--
-- THE setval AT THE BOTTOM IS NOT OPTIONAL. Supplying an explicit id does
-- not advance the identity sequence, so without it the next exercise
-- inserted by the application asks for id 1 and collides with 'Bench
-- Press'. Same reason the data migration ends with setval on every table.
--
-- Requires: migrations/001_schema.sql
-- Applied by: psql "$DATABASE_URL" -f muscle_groups_and_exercises.sql
-- =====================================================================


-- ---------------------------------------------------------------------
-- Muscle groups
--   1-12 have real artwork in Frontend/assets/muscles/.
--   13-16 arrived with the megaGymDataset import - 77 exercises land in
--   them - and share a generated placeholder until real artwork exists.
--   Dropping those exercises to avoid a missing image would be losing
--   data to protect a picture.
-- ---------------------------------------------------------------------
INSERT INTO muscle_groups (muscle_id, muscle_name, image_path) VALUES
    (1,  'Chest',      'assets/muscles/chest.png'),
    (2,  'Lats',       'assets/muscles/lats.png'),
    (3,  'Upper Back', 'assets/muscles/upper_back.png'),
    (4,  'Lower Back', 'assets/muscles/lower_back.png'),
    (5,  'Biceps',     'assets/muscles/biceps.png'),
    (6,  'Triceps',    'assets/muscles/triceps.png'),
    (7,  'Quads',      'assets/muscles/quads.png'),
    (8,  'Hamstrings', 'assets/muscles/hamstrings.png'),
    (9,  'Glutes',     'assets/muscles/glutes.png'),
    (10, 'Calves',     'assets/muscles/calves.png'),
    (11, 'Shoulders',  'assets/muscles/shoulders.png'),
    (12, 'Core',       'assets/muscles/core.png'),
    (13, 'Forearms',   'assets/muscles/placeholder.png'),
    (14, 'Abductors',  'assets/muscles/placeholder.png'),
    (15, 'Adductors',  'assets/muscles/placeholder.png'),
    (16, 'Neck',       'assets/muscles/placeholder.png')
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------
-- Exercises - four per muscle group
-- ids 1-24 match the rows already in the reference database; 25-48 extend it.
-- ---------------------------------------------------------------------
INSERT INTO exercises (exercise_id, exercise_name, muscle_id, equipment, description) VALUES
    -- Chest
    (1,  'Bench Press',             1,  'Barbell',    'Flat barbell press. The benchmark horizontal push; keep shoulder blades retracted and the bar over mid-chest.'),
    (2,  'Incline Dumbbell Press',  1,  'Dumbbell',   'Press on a 30-45 degree incline. Shifts emphasis toward the upper chest and shoulders.'),
    (25, 'Cable Fly',               1,  'Cable',      'Isolation. Constant tension through the full arc, with a slight bend held at the elbow throughout.'),
    (26, 'Push Ups',                1,  'Bodyweight', 'Bodyweight horizontal push. Scales by elevating the hands or the feet.'),

    -- Lats
    (3,  'Lat Pulldown',            2,  'Machine',    'Vertical pull. Drive the elbows down and back rather than pulling with the hands.'),
    (4,  'Pull Ups',                2,  'Bodyweight', 'Bodyweight vertical pull. The strength standard for the lats; assist with a band if needed.'),
    (27, 'Straight Arm Pulldown',   2,  'Cable',      'Isolation with locked elbows. Teaches lat engagement without the biceps taking over.'),
    (28, 'Single Arm Dumbbell Row', 2,  'Dumbbell',   'Unilateral row. Exposes and corrects left-right imbalance.'),

    -- Upper Back
    (5,  'Seated Cable Row',        3,  'Cable',      'Horizontal pull. Squeeze the shoulder blades together at the finish, without leaning back.'),
    (6,  'Face Pulls',              3,  'Cable',      'Rear delts and external rotators. High volume, light load; posture insurance.'),
    (29, 'Barbell Row',             3,  'Barbell',    'Bent-over horizontal pull. Heavy back builder; keep a neutral spine throughout.'),
    (30, 'Reverse Pec Deck',        3,  'Machine',    'Machine rear-delt fly. Isolates the upper back with no lower-back demand.'),

    -- Lower Back
    (7,  'Deadlift',                4,  'Barbell',    'Full posterior chain hinge. Highest systemic fatigue in the programme; brace hard before every rep.'),
    (8,  'Back Extensions',         4,  'Machine',    'Spinal erector isolation. Extend to a straight line, not past it.'),
    (31, 'Good Mornings',           4,  'Barbell',    'Loaded hinge with the bar on the back. Start far lighter than instinct suggests.'),
    (32, 'Superman Hold',           4,  'Bodyweight', 'Prone isometric hold. Low-load erector work suitable for warm-ups.'),

    -- Biceps
    (9,  'Bicep Curl',              5,  'Dumbbell',   'Standard supinated curl. Keep the elbows pinned to the ribs.'),
    (10, 'Hammer Curl',             5,  'Dumbbell',   'Neutral grip. Targets the brachialis and adds arm thickness.'),
    (33, 'Preacher Curl',           5,  'Machine',    'Elbows fixed on a pad, removing the swing. Strong stretch at the bottom.'),
    (34, 'Cable Curl',              5,  'Cable',      'Constant tension across the whole range, unlike free weights.'),

    -- Triceps
    (11, 'Tricep Pushdown',         6,  'Cable',      'Elbow extension against a cable. Keep the upper arms still.'),
    (12, 'Skull Crushers',          6,  'Barbell',    'Lying extension. Heavy stretch on the long head; go easy if elbows complain.'),
    (35, 'Close Grip Bench Press',  6,  'Barbell',    'Compound triceps press. Hands roughly shoulder width, elbows tucked.'),
    (36, 'Overhead Tricep Extension', 6, 'Dumbbell',  'Overhead position puts the long head under a full stretch.'),

    -- Quads
    (13, 'Squat',                   7,  'Barbell',    'Back squat. The primary lower-body compound; depth to at least parallel.'),
    (14, 'Leg Press',               7,  'Machine',    'Machine press. Heavy quad loading with the spine supported.'),
    (37, 'Bulgarian Split Squat',   7,  'Dumbbell',   'Rear foot elevated. Brutal unilateral work; also exposes balance issues.'),
    (38, 'Leg Extension',           7,  'Machine',    'Quad isolation. Useful finisher, and gentle on the lower back.'),

    -- Hamstrings
    (15, 'Romanian Deadlift',       8,  'Barbell',    'Hip hinge with soft knees. The main hamstring stretch movement.'),
    (16, 'Leg Curl',                8,  'Machine',    'Knee flexion isolation. Complements the hinge pattern.'),
    (39, 'Nordic Curl',             8,  'Bodyweight', 'Eccentric knee flexion. Very demanding; lower slowly and assist back up.'),
    (40, 'Seated Leg Curl',         8,  'Machine',    'Hip flexed rather than extended, which biases the hamstrings differently to the lying version.'),

    -- Glutes
    (17, 'Hip Thrust',              9,  'Barbell',    'Loaded hip extension. The highest-tension glute movement available.'),
    (18, 'Glute Bridge',            9,  'Bodyweight', 'Floor-based hip extension. The unloaded progression toward the hip thrust.'),
    (41, 'Cable Kickback',          9,  'Cable',      'Single-leg hip extension. Isolation with continuous tension.'),
    (42, 'Walking Lunge',           9,  'Dumbbell',   'Loaded stride. Glutes and quads together, with a balance demand.'),

    -- Calves
    (19, 'Standing Calf Raise',     10, 'Machine',    'Knee straight, which biases the gastrocnemius. Pause at the top.'),
    (20, 'Seated Calf Raise',       10, 'Machine',    'Knee bent, which biases the soleus. The two are not interchangeable.'),
    (43, 'Leg Press Calf Raise',    10, 'Machine',    'Calf raises on the leg press sled. Allows heavy loading without spinal compression.'),
    (44, 'Single Leg Calf Raise',   10, 'Bodyweight', 'One leg at a time. Bodyweight is enough load for most people here.'),

    -- Shoulders
    (21, 'Overhead Press',          11, 'Barbell',    'Standing vertical press. The core shoulder strength lift.'),
    (22, 'Lateral Raises',          11, 'Dumbbell',   'Side delt isolation. Light weight, strict form, high reps.'),
    (45, 'Arnold Press',            11, 'Dumbbell',   'Press with rotation, covering front and side delts in one movement.'),
    (46, 'Front Raise',             11, 'Dumbbell',   'Front delt isolation. Often already covered by pressing volume.'),

    -- Core
    (23, 'Plank',                   12, 'Bodyweight', 'Anti-extension isometric. Measured in seconds rather than reps.'),
    (24, 'Hanging Leg Raises',      12, 'Bodyweight', 'Hanging hip flexion. Control the descent instead of swinging.'),
    (47, 'Cable Crunch',            12, 'Cable',      'Loaded spinal flexion, so the abs can be progressed like any other muscle.'),
    (48, 'Russian Twist',           12, 'Bodyweight', 'Rotational core work. Move deliberately; speed defeats the purpose.')
ON CONFLICT DO NOTHING;


-- ---------------------------------------------------------------------
-- Move the identity sequences past the ids written above.
--
-- The third argument to setval is is_called: true means "the next value is
-- max + 1". It has to be computed rather than hardcoded, because on a
-- table that somehow ended up empty the answer must be setval(seq, 1,
-- false) - next value 1 - and not setval(seq, 1, true), which would skip
-- id 1 forever.
-- ---------------------------------------------------------------------
SELECT setval(
    pg_get_serial_sequence('muscle_groups', 'muscle_id'),
    COALESCE((SELECT MAX(muscle_id) FROM muscle_groups), 1),
    (SELECT COUNT(*) > 0 FROM muscle_groups)
);

SELECT setval(
    pg_get_serial_sequence('exercises', 'exercise_id'),
    COALESCE((SELECT MAX(exercise_id) FROM exercises), 1),
    (SELECT COUNT(*) > 0 FROM exercises)
);
