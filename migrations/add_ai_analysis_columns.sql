-- Run this on your incident_db before using AI integration.
-- Adds optional fields for incident details and stores AI-generated analysis.

ALTER TABLE incidents
  ADD COLUMN IF NOT EXISTS error_logs TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS system_logs TEXT DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS impact VARCHAR(500) DEFAULT NULL,
  ADD COLUMN IF NOT EXISTS ai_analysis TEXT DEFAULT NULL;

-- If your MySQL version does not support ADD COLUMN IF NOT EXISTS, use:
-- ALTER TABLE incidents ADD COLUMN error_logs TEXT DEFAULT NULL;
-- ALTER TABLE incidents ADD COLUMN system_logs TEXT DEFAULT NULL;
-- ALTER TABLE incidents ADD COLUMN impact VARCHAR(500) DEFAULT NULL;
-- ALTER TABLE incidents ADD COLUMN ai_analysis TEXT DEFAULT NULL;
