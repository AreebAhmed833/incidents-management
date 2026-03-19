-- Separates "Logs" from "Errors" on incidents (Declare + Edit forms).
-- Run on incident_db after deploying the updated app.

ALTER TABLE incidents
  ADD COLUMN IF NOT EXISTS system_logs TEXT DEFAULT NULL;

-- If your MySQL version does not support ADD COLUMN IF NOT EXISTS:
-- ALTER TABLE incidents ADD COLUMN system_logs TEXT DEFAULT NULL;
