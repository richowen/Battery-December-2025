# Manual Override System - Quick Reference

## Overview

**Problem Solved:** The system now distinguishes between manual user actions and automated system actions for immersion heater control. When you manually toggle an immersion switch, it stays that way for 2 hours instead of being overwritten in the next 5-minute cycle.

**Solution:** 3-tier priority system with automatic override detection and expiry.

## Control Priority Order

```
1. MANUAL OVERRIDE    (User toggles switch) 
   ↓ Wins over everything
   • Duration: 2 hours
   • Color: 🟡 Yellow
   • Clear: "Resume Auto" button
   
2. SCHEDULE OVERRIDE  (Time/temp based)
   ↓ Active only if no manual override
   • Duration: Until schedule ends
   • Color: 🟠 Orange
   • Clear: Schedule period ends
   
3. OPTIMIZER LOGIC    (Price/SOC/solar based)
   ↓ Active only if no manual or schedule
   • Duration: Continuous
   • Color: 🟢 Green
   • Clear: N/A (always active as fallback)
```

## How It Works

### Detection Flow

```
1. You toggle switch in HA
   ↓
2. Node-RED detects state change
   ↓
3. Checks: Was this system or user?
   • Within 10s of system action? → Ignore (system)
   • Has user_id in context? → Report (manual)
   ↓
4. Creates override in database
   • Immersion: main/lucy
   • State: ON/OFF
   • Expires: Now + 2 hours
   ↓
5. System respects override
   • Next 5-min cycle reads override
   • Skips automated control
   • Keeps your manual state
   ↓
6. Auto-expires after 2 hours
   • Background task clears old overrides
   • System resumes automatic control
```

### Database Structure

**Table:** `manual_overrides`

| Field | Purpose |
|-------|---------|
| `immersion_name` | 'main' or 'lucy' |
| `is_active` | Currently active? |
| `desired_state` | ON (true) or OFF (false) |
| `expires_at` | Auto-clear timestamp |
| `source` | 'user', 'dashboard', etc. |
| `cleared_by` | Who/what cleared it |

## API Endpoints

### Set Manual Override
```bash
POST /api/v1/manual-override/set
{
  "immersion_name": "main",
  "desired_state": true,
  "duration_hours": 2
}
```

### Check Status
```bash
GET /api/v1/manual-override/status
```

Response:
```json
{
  "overrides": {
    "main": {
      "is_active": true,
      "desired_state": true,
      "time_remaining_minutes": 115,
      "expires_at": "2025-12-10T20:48:00Z"
    },
    "lucy": {
      "is_active": false
    }
  },
  "any_active": true
}
```

### Clear Override
```bash
POST /api/v1/manual-override/clear?immersion_name=main
```

## Dashboard Indicators

### Status Colors

| Color | Meaning | Priority |
|-------|---------|----------|
| 🟡 Yellow | Manual Override Active | Highest |
| 🟠 Orange | Schedule Active | Medium |
| 🟢 Green | Optimizer Controlling | Normal |
| 🔴 Red | Error/Disconnected | Alert |

### Display Format

```
Main Immersion: 🟡 MANUAL OVERRIDE
State: ON | Expires in: 1h 45m
[Resume Auto Control]
```

```
Lucy Immersion: 🟢 AUTO
State: OFF | Reason: Price too high (25p)
[No Override Active]
```

## Common Scenarios

### Scenario 1: Turn Off During Cheap Period

**Situation:**
- Price: 2p/kWh (very cheap)
- Optimizer: Turn ON immersion
- You: Don't want it on (e.g., away from home)

**Action:**
1. Toggle immersion OFF in HA
2. System detects manual override
3. Override created: OFF for 2 hours

**Result:**
- Immersion stays OFF for 2 hours
- Optimizer respects your choice
- After 2 hours, optimizer resumes control

### Scenario 2: Turn On During Expensive Period

**Situation:**
- Price: 30p/kWh (expensive)
- Optimizer: Keep OFF
- You: Need hot water urgently

**Action:**
1. Toggle immersion ON in HA
2. System detects manual override
3. Override created: ON for 2 hours

**Result:**
- Immersion stays ON for 2 hours
- Ignores high price
- After 2 hours, optimizer resumes (likely turns OFF)

### Scenario 3: Override During Schedule

**Situation:**
- Schedule: Wednesday 15:00-17:00 (ON)
- Currently: 15:30
- You: Toggle OFF manually

**Result:**
- Manual override wins (highest priority)
- Immersion OFF despite schedule
- At 17:30 (override expires): Schedule still active, stays OFF
- At 17:01 (schedule ends): Optimizer takes over

### Scenario 4: Early Resume

**Situation:**
- Override set at 14:00 (expires 16:00)
- You: Want automation back at 14:30

**Action:**
1. Click "Resume Auto" button
2. Override cleared immediately

**Result:**
- System checks priorities
- No schedule active
- Optimizer controls based on current conditions

## Troubleshooting

### Override Not Created

**Symptoms:**
- Toggle switch manually
- No yellow indicator appears
- System overwrites in 5 minutes

**Checks:**
1. Node-RED state monitor flow active?
2. Debug panel shows "Manual override detected"?
3. Check recent system actions: `flow.get('last_system_action_main')`
4. Database: `SELECT * FROM manual_overrides WHERE is_active=1`

**Fix:**
- Ensure state monitor flow deployed
- Check HA state subscription working
- Verify 10-second window logic

### Override Not Respected

**Symptoms:**
- Override exists in database
- System still changes immersion state
- Yellow indicator shows but ignored

**Checks:**
1. API status: `GET /manual-override/status`
2. Optimizer logs: Check manual_override_status parameter
3. Hybrid flow: Verify priority logic applied

**Fix:**
- Ensure optimizer receives manual_override_status
- Check priority resolution in recommendation
- Verify hybrid flow updates timestamps

### Override Won't Clear

**Symptoms:**
- 2+ hours passed
- Override still active
- Can't resume auto control

**Checks:**
1. Background task running: Check app logs
2. Database: `SELECT * FROM manual_overrides WHERE expires_at < NOW() AND is_active=1`
3. Timezone issues: Check server vs database time

**Fix:**
- Manual clear: `POST /manual-override/clear`
- SQL clear: `UPDATE manual_overrides SET is_active=0 WHERE expires_at < NOW()`
- Restart background task

## Quick Commands

### Check Active Overrides
```bash
curl http://192.168.1.60:8000/api/v1/manual-override/status | jq
```

### Set Override (Main ON, 2hrs)
```bash
curl -X POST http://192.168.1.60:8000/api/v1/manual-override/set \
  -H "Content-Type: application/json" \
  -d '{"immersion_name":"main","desired_state":true,"duration_hours":2}'
```

### Clear Override
```bash
curl -X POST "http://192.168.1.60:8000/api/v1/manual-override/clear?immersion_name=main"
```

### Database Queries
```sql
-- View active overrides
SELECT * FROM manual_overrides 
WHERE is_active=1 
ORDER BY created_at DESC;

-- Override history today
SELECT * FROM manual_overrides 
WHERE DATE(created_at) = CURDATE()
ORDER BY created_at DESC;

-- Clear all overrides
UPDATE manual_overrides 
SET is_active=0, cleared_at=NOW(), cleared_by='manual_sql' 
WHERE is_active=1;

-- Override statistics
SELECT 
  immersion_name,
  COUNT(*) as total_overrides,
  AVG(TIMESTAMPDIFF(MINUTE, created_at, COALESCE(cleared_at, expires_at))) as avg_duration_min
FROM manual_overrides
WHERE DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
GROUP BY immersion_name;
```

## Configuration Options

### Change Default Duration

In Node-RED state monitor function:
```javascript
msg.payload = {
    immersion_name: immersionName,
    desired_state: newState,
    source: 'user',
    duration_hours: 3  // Change from 2 to 3 hours
};
```

### Adjust Detection Window

In state monitor function:
```javascript
// Change from 10 seconds to 15 seconds
if (timeSinceSystemAction < 15000) {
    // System-initiated, ignore
    return null;
}
```

### Change Expiry Check Frequency

In `backend/app/main.py`:
```python
@repeat_every(seconds=180)  # Change from 300 (5min) to 180 (3min)
async def expire_manual_overrides():
    # ...
```

## Best Practices

### When to Use Manual Override

✅ **Good Use Cases:**
- Away from home, don't need hot water
- Urgent hot water needed despite cost
- Testing different settings
- Temporary preference change

❌ **Avoid For:**
- Permanent preference (use schedules instead)
- Regular patterns (create a schedule)
- Long-term changes (adjust optimizer settings)

### Tips

1. **Check Dashboard First**
   - See what system wants to do
   - Understand current priority
   - Make informed override decision

2. **Use Resume Auto**
   - Don't wait for 2-hour expiry
   - Resume when ready
   - System adapts immediately

3. **Monitor Expiry Times**
   - Dashboard shows countdown
   - Plan when automation resumes
   - Set longer duration if needed

4. **Review Override History**
   - Check database weekly
   - Identify patterns
   - Create schedules for repeated overrides

## Related Documentation

- **Architecture:** [`ARCHITECTURE_Manual_Override.md`](ARCHITECTURE_Manual_Override.md) - Complete system design
- **Implementation:** [`IMPLEMENTATION_Manual_Override.md`](IMPLEMENTATION_Manual_Override.md) - Step-by-step setup guide
- **Schedule Override:** [`ARCHITECTURE_Schedule_Override.md`](ARCHITECTURE_Schedule_Override.md) - Schedule system
- **Main System:** [`README.md`](README.md) - Battery optimization overview

## Support

### Logs to Check

1. **Node-RED Debug Panel**
   - Manual override detection messages
   - System action timestamps
   - API call results

2. **Backend Logs**
   ```bash
   docker logs battery-optimizer | grep -i "manual"
   ```

3. **Database Activity**
   ```sql
   SELECT * FROM manual_overrides 
   ORDER BY created_at DESC 
   LIMIT 20;
   ```

### Common Questions

**Q: Can I override both immersions independently?**  
A: Yes, main and lucy have separate overrides.

**Q: What if I toggle multiple times?**  
A: Each toggle creates a new override, replacing the old one.

**Q: Does override survive system restart?**  
A: Yes, stored in database, persists across restarts.

**Q: Can I see override history?**  
A: Yes, query `manual_overrides` table for complete history.

**Q: What happens at exactly 2 hours?**  
A: Background task clears it within 5 minutes, system resumes auto control.

---

**Version:** 1.0  
**Last Updated:** 2025-12-10  
**System:** Battery Optimization v2.0 + Manual Override Extension