-- =====================================================================
-- 002_search.sql                                    PostgreSQL 16 (Neon)
-- =====================================================================
-- Substring search over ~2,900 exercise names, for the log-workout
-- combobox and the catalogue search box.
--
-- WHAT THIS REPLACES
--   MySQL had FULLTEXT INDEX ft_exercises_name and queried it with
--   MATCH ... AGAINST (... IN BOOLEAN MODE). Postgres has no FULLTEXT.
--
-- WHY TRIGRAMS AND NOT tsvector
--   tsvector indexes WORDS. to_tsquery('squat:*') matches at the start of
--   a word and nowhere else, so it can never find "ress" inside "Press" -
--   and it needs a stored, triggered, reindexed tsvector column to be fast.
--   pg_trgm indexes every three-character window, which makes an ordinary
--   ILIKE '%squa%' index-backed. That is what a type-ahead picker actually
--   does: match the middle of a name from a partial word.
--
--   The trade is a larger index (a few MB here) and slower writes, on a
--   table written once by an importer and read on every keystroke.
--
-- WHAT THIS FIXES ALONG THE WAY
--   InnoDB ignored tokens shorter than innodb_ft_min_token_size (3), so
--   exercise_repo fell back to an ANCHORED LIKE 'sq%' below that length -
--   which does not find "Barbell Squat" at all. Here 1-2 characters simply
--   fall back to a sequential scan of 2,900 rows (about 1.5ms, invisible
--   behind the network round trip) and return the RIGHT answer.
--
--   Keystroke 1  "s"    seq scan,     correct
--   Keystroke 2  "sq"   seq scan,     correct
--   Keystroke 3  "squ"  index scan,   correct   <- "Barbell Squat" found
--
-- WHY THE INDEX IS ON THE RAW COLUMN
--   pg_trgm lowercases when it extracts trigrams, so ILIKE is served
--   directly by an index on exercise_name. Wrapping the column in lower()
--   here would mean the index expression no longer matches the query and
--   the planner would ignore it.
--
-- Applied by: psql "$DATABASE_URL" -f 002_search.sql
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_exercises_name_trgm
    ON exercises USING GIN (exercise_name gin_trgm_ops);
