CREATE TABLE IF NOT EXISTS workouts (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 owner uuid NOT NULL, city text NOT NULL, sport text NOT NULL, starts timestamp NOT NULL,
 minutes int NOT NULL, low real NOT NULL, high real NOT NULL, rain int NOT NULL, wind real NOT NULL,
 status text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','done','cancelled'))
);
CREATE INDEX IF NOT EXISTS workout_calendar ON workouts(owner, starts, id);
CREATE TABLE IF NOT EXISTS moves (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 workout bigint NOT NULL REFERENCES workouts(id) ON DELETE CASCADE,
 previous timestamp NOT NULL, replacement timestamp NOT NULL, changed timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS move_history ON moves(workout, id);
