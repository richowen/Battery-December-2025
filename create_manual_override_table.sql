-- Manual Override Table for Immersion Heater Control
-- Creates table to track user manual overrides of automated system

CREATE TABLE IF NOT EXISTS manual_overrides (
    id INT PRIMARY KEY AUTO_INCREMENT,
    immersion_name VARCHAR(50) NOT NULL COMMENT 'Immersion heater identifier: "main" or "lucy"',
    is_active BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Whether override is currently active',
    desired_state BOOLEAN NOT NULL COMMENT 'Desired switch state: ON (true) or OFF (false)',
    source VARCHAR(50) DEFAULT 'user' COMMENT 'Source of override: user, dashboard, api',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'When override was created',
    expires_at DATETIME NOT NULL COMMENT 'When override should auto-expire',
    cleared_at DATETIME NULL COMMENT 'When override was manually cleared',
    cleared_by VARCHAR(50) NULL COMMENT 'Who/what cleared the override: user, system_expiry, api',
    
    -- Indexes for efficient querying
    INDEX idx_active_immersion (immersion_name, is_active, expires_at),
    INDEX idx_expires (expires_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='Tracks manual user overrides of automated immersion heater control';

-- Example queries:

-- Check current active overrides
-- SELECT * FROM manual_overrides WHERE is_active = 1 AND expires_at > NOW() ORDER BY created_at DESC;

-- Get override status for specific immersion
-- SELECT * FROM manual_overrides 
-- WHERE immersion_name = 'main' AND is_active = 1 AND expires_at > NOW()
-- ORDER BY created_at DESC LIMIT 1;

-- Clear expired overrides (run by background task)
-- UPDATE manual_overrides 
-- SET is_active = 0, cleared_at = NOW(), cleared_by = 'system_expiry'
-- WHERE is_active = 1 AND expires_at <= NOW();

-- Override history for today
-- SELECT * FROM manual_overrides 
-- WHERE DATE(created_at) = CURDATE()
-- ORDER BY created_at DESC;