-- Database migration for schedule override functionality
-- Run this in your MariaDB database

USE battery_optimizer;

-- Create schedule_overrides table
CREATE TABLE IF NOT EXISTS schedule_overrides (
    id INT AUTO_INCREMENT PRIMARY KEY,
    immersion_name VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    schedule_reason VARCHAR(200),
    activated_at DATETIME,
    deactivated_at DATETIME NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_immersion_active (immersion_name, is_active),
    INDEX idx_activated (activated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Add comment for documentation
ALTER TABLE schedule_overrides COMMENT = 'Tracks schedule override status for immersion heaters';

-- Verify table was created
DESCRIBE schedule_overrides;

SELECT 'Schedule override table created successfully!' AS status;