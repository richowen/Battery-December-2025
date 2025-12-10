# Schedule Override System - Deployment Guide

## 🚀 Quick Start

This guide will help you deploy the schedule override system to your existing battery optimization setup.

**Estimated Time:** 30 minutes  
**Difficulty:** Medium  
**Downtime Required:** None (backward compatible)

---

## 📋 Prerequisites

✅ Existing hybrid battery optimizer running (v2.0)  
✅ MariaDB database accessible  
✅ Backend service deployed on Unraid (192.168.1.60:8000)  
✅ Node-RED running on Home Assistant VM (192.168.1.3)  
✅ Access to both systems via SSH/terminal

---

## 🔧 Step 1: Database Migration

### 1.1 Connect to MariaDB

```bash
# On Home Assistant VM
docker exec -it addon_core_mariadb mysql -u root -p
```

### 1.2 Run Migration Script

```sql
USE battery_optimizer;

-- Create schedule override table
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

-- Verify
DESCRIBE schedule_overrides;
SELECT 'Schedule override table created successfully!' AS status;

-- Exit
exit;
```

**Expected Output:**
```
+-------------------+--------------+------+-----+-------------------+
| Field             | Type         | Null | Key | Default           |
+-------------------+--------------+------+-----+-------------------+
| id                | int(11)      | NO   | PRI | NULL              |
| immersion_name    | varchar(50)  | NO   | MUL | NULL              |
| is_active         | tinyint(1)   | NO   | MUL | 0                 |
...
```

---

## 🐍 Step 2: Update Backend Service

### 2.1 Stop Backend Service

```bash
# On Unraid
cd /mnt/user/appdata/battery-optimizer
docker-compose down
```

### 2.2 Update Python Files

Copy the updated files:
- `backend/app/models.py` - Added `ScheduleOverride` model
- `backend/app/api.py` - Added 3 new endpoints + schedule query
- `backend/app/optimizer.py` - Added schedule priority logic

```bash
# Backup current files first
cp app/models.py app/models.py.backup
cp app/api.py app/api.py.backup
cp app/optimizer.py app/optimizer.py.backup

# Copy new files (adjust paths as needed)
# ... copy from your development system
```

### 2.3 Restart Backend Service

```bash
docker-compose up -d

# Check logs
docker-compose logs -f --tail=50
```

**Expected Log Output:**
```
battery-optimizer | INFO: Started server process
battery-optimizer | INFO: Uvicorn running on http://0.0.0.0:8000
```

### 2.4 Verify New Endpoints

```bash
# Test schedule status endpoint
curl http://192.168.1.60:8000/api/v1/schedule/status

# Expected response:
{
  "status": "success",
  "schedules": {
    "main": {"is_active": false, ...},
    "lucy": {"is_active": false, ...}
  },
  "any_active": false
}
```

---

## 🔴 Step 3: Deploy Enhanced Node-RED Flows

### 3.1 Import Schedule Flow

1. Open Node-RED: `http://192.168.1.3:1880`
2. Menu → Import → Clipboard
3. Paste contents of `nodered/flows-schedule-enhanced.json`
4. Click "Import"
5. **Deploy** (do NOT delete your old schedule flow yet)

### 3.2 Import Enhanced Hybrid Flow

1. Menu → Import → Clipboard
2. Paste contents of `nodered/flows-hybrid-enhanced.json`
3. Click "Import"
4. **Deploy**

### 3.3 Verify Flow Connections

Check that these are connected properly:
- Schedule timers → Prepare nodes → Report to Backend → Control switches
- Hybrid timer → Get Recommendation → Process → Control (separate from schedule)

---

## ✅ Step 4: Testing

### 4.1 Test Schedule Reporting

**Trigger manually:**
1. In Node-RED, find "Main Immersion Schedule" node
2. Click the button on the node to inject
3. Watch debug panel for:
   - ✓ Backend response: `{"status": "success", ...}`
   - ✓ Switch activation

**Verify in backend:**
```bash
curl http://192.168.1.60:8000/api/v1/schedule/status
```

**Expected:**
```json
{
  "schedules": {
    "main": {
      "is_active": true,
      "schedule_reason": "Time schedule: ... active period",
      "activated_at": "2025-12-10T15:00:00",
      "duration_minutes": 5
    }
  }
}
```

### 4.2 Test Optimizer with Schedule Active

1. Manually activate schedule (use inject button)
2. Wait for next optimizer run (every 5 min) OR trigger manually
3. Check optimizer response:

```bash
curl http://192.168.1.60:8000/api/v1/recommendation/now | jq
```

**Expected Response:**
```json
{
  "mode": "Self Use",
  "discharge_current": 30,
  "immersion_main": true,
  "immersion_main_source": "schedule_override",  ← KEY!
  "immersion_main_reason": "Time schedule: Wed active period",
  "schedule_override_active": true,  ← KEY!
  ...
}
```

### 4.3 Test Optimizer with Schedule Inactive

1. Manually deactivate schedule
2. Trigger optimizer
3. Verify `immersion_main_source: "optimizer"`

### 4.4 Test Priority Logic

**Scenario:** Schedule says ON, but price is expensive and SOC is low

1. Activate schedule (immersion ON)
2. Set test condition: price=30p, SOC=40%
3. Check recommendation

**Expected:** Immersion stays ON because schedule overrides optimizer

### 4.5 Test Dashboard Display

Navigate to: `http://192.168.1.3:1880/ui`

**Verify Display Shows:**
- ✅ "🔒 SCHEDULE OVERRIDE ACTIVE" when schedule active
- ✅ "⚡ OPTIMIZER CONTROL" when schedule inactive
- ✅ "Main: ON [schedule_override]" or "Main: OFF [optimizer]"
- ✅ Specific reasons displayed for each immersion

---

## 🐛 Troubleshooting

### Issue: Backend returns 500 error

**Symptoms:**
```bash
curl http://192.168.1.60:8000/api/v1/schedule/status
# Returns: {"detail": "Internal server error"}
```

**Solutions:**
```bash
# Check logs
docker-compose logs backend | grep ERROR

# Common causes:
# 1. Table not created
mysql -u root -p battery_optimizer -e "SHOW TABLES LIKE 'schedule%';"

# 2. Import error
docker-compose logs | grep "ImportError\|ModuleNotFoundError"

# 3. SQLAlchemy model mismatch
docker-compose restart
```

### Issue: Schedule doesn't report to backend

**Symptoms:**
- Node-RED shows error in "Report to Backend" node
- No schedule entries in database

**Solutions:**
```bash
# 1. Check backend is accessible
curl http://192.168.1.60:8000/health

# 2. Check Node-RED debug output
# Look for HTTP errors (404, 500, connection refused)

# 3. Verify URL in Node-RED HTTP request node
# Should be: http://192.168.1.60:8000/api/v1/schedule/update

# 4. Check JSON format
# In Node-RED debug, verify payload structure
```

### Issue: Immersion controlled by both flows

**Symptoms:**
- Switches turn on/off rapidly
- Conflicting commands in logs

**Solutions:**
```bash
# This shouldn't happen with new architecture, but if it does:

# 1. Disable old schedule flow temporarily
# In Node-RED, right-click tab → Disable

# 2. Check only ONE flow controls switches
# Enhanced schedule flow should be the only one sending to switches

# 3. Verify hybrid flow respects schedule override
curl http://192.168.1.60:8000/api/v1/recommendation/now | grep schedule_override
```

### Issue: Schedule shows as stale/inactive

**Symptoms:**
```json
{
  "schedules": {
    "main": {"is_active": false}
  }
}
```
But schedule should be active.

**Solutions:**
```sql
-- Check database
SELECT * FROM schedule_overrides 
WHERE immersion_name='main' 
ORDER BY id DESC 
LIMIT 5;

-- If activated_at is >5 minutes old, system considers it stale
-- Solution: Schedule flow must re-report every ~4 minutes or on state change

-- Add heartbeat to schedule flow (optional enhancement)
```

---

## 📊 Monitoring

### Check Schedule History

```bash
curl "http://192.168.1.60:8000/api/v1/schedule/history?limit=10" | jq
```

### Check Current Status

```bash
curl http://192.168.1.60:8000/api/v1/schedule/status | jq
```

### Watch Logs Live

```bash
# Backend
docker-compose logs -f backend | grep -i "schedule\|immersion"

# Look for:
# INFO: Schedule override for 'main' immersion set to active
# INFO: Optimizer recommendation: main=ON (schedule_override)
```

---

## 🎯 Validation Checklist

Before going live, verify:

- [ ] Database table `schedule_overrides` created
- [ ] Backend API returns schedule status successfully
- [ ] Schedule flow reports to backend on ON/OFF events
- [ ] Optimizer queries schedule status before making decisions
- [ ] Hybrid flow shows schedule override indicator
- [ ] Dashboard displays source correctly ([schedule] or [optimizer])
- [ ] Schedule overrides optimizer when active
- [ ] Optimizer takes control when schedule inactive
- [ ] No switch conflicts between flows
- [ ] Logs show clear priority decisions

---

## 🔄 Rollback Plan

If issues occur:

### Quick Rollback (5 minutes)

```bash
# 1. Stop new backend
cd /mnt/user/appdata/battery-optimizer
docker-compose down

# 2. Restore backup files
cp app/models.py.backup app/models.py
cp app/api.py.backup app/api.py
cp app/optimizer.py.backup app/optimizer.py

# 3. Restart
docker-compose up -d

# 4. In Node-RED, disable/delete new flows
# 5. Re-enable old flows
```

### Full Rollback (if needed)

```sql
-- Drop schedule override table (keeps data for analysis)
DROP TABLE schedule_overrides;
```

---

## 📈 Performance Impact

**Expected:**
- Database queries: +2 per optimizer run (~every 5 min)
- API response time: +20-30ms
- Database size: ~500KB/month
- CPU/Memory: Negligible (<1%)

**Monitor:**
```bash
# Check optimization time
curl http://192.168.1.60:8000/api/v1/recommendation/now | jq '.optimization_time_ms'
# Should still be <100ms
```

---

## 🎉 Success Criteria

System is working correctly when:

1. **Schedule active period:**
   - Dashboard shows "🔒 SCHEDULE OVERRIDE ACTIVE"
   - Immersion ON regardless of price/SOC
   - Source shown as [schedule_override]

2. **Schedule inactive period:**
   - Dashboard shows "⚡ OPTIMIZER CONTROL"
   - Immersion controlled by price/SOC logic
   - Source shown as [optimizer]

3. **Smooth transitions:**
   - When schedule ends, optimizer takes over within 5 minutes
   - No rapid on/off switching
   - Clear logs showing handover

---

## 📞 Support

If you encounter issues:

1. Check logs first (see Monitoring section)
2. Review Troubleshooting section
3. Verify each step was completed
4. Check API documentation: `http://192.168.1.60:8000/docs`

---

**Deployment Complete!** 🎊

Your schedule override system is now live and will prioritize your time-based schedules while still benefiting from the optimizer during non-schedule periods.