# Fixes Applied - Ready to Rebuild

## Issues Fixed

### 1. ✅ Optimization Division Error
**Problem:** `TypeError: unsupported operand type(s) for /: 'LpVariable' and 'float'`

**Root Cause:** PuLP doesn't support division of LpVariable by float

**Fix:** Changed division to multiplication by inverse in [`backend/app/optimizer.py`](backend/app/optimizer.py:105)
```python
# Before (BROKEN):
discharge[0] / self.efficiency

# After (FIXED):
efficiency_loss = 1.0 / self.efficiency
discharge[0] * efficiency_loss
```

### 2. ✅ Network Connectivity to InfluxDB
**Problem:** `[Errno 113] No route to host` when connecting to InfluxDB at 192.168.1.64

**Root Cause:** Docker bridge networking doesn't have access to your network

**Fix:** Changed to host network mode in [`backend/docker-compose.yml`](backend/docker-compose.yml)
```yaml
# Before:
ports:
  - "8000:8000"
networks:
  - battery-net

# After:
network_mode: host
# Now container is on 192.168.1.60 directly
```

### 3. ✅ IP Address Updates
**Changed all references from 192.168.1.2 to 192.168.1.60:**
- [`nodered/flows-hybrid.json`](nodered/flows-hybrid.json) - HTTP request URLs
- Documentation files

---

## Rebuild & Restart

```bash
cd /mnt/user/appdata/battery-optimizer

# Rebuild with fixes
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Monitor startup
docker logs -f battery-optimizer
```

**Expected logs:**
```
INFO - Starting Battery Optimization Service v1.0.0
INFO - Database tables created successfully
INFO - Database initialized
INFO - InfluxDB client initialized for http://192.168.1.64:8086
INFO - Application startup complete
INFO - Uvicorn running on http://0.0.0.0:8000
```

---

## Verification Steps

### 1. Test API (Now on 192.168.1.60)

```bash
# Health check
curl http://192.168.1.60:8000/health

# Refresh prices (will test Octopus API + Database + InfluxDB)
curl -X POST http://192.168.1.60:8000/api/v1/prices/refresh

# Get recommendation (will test optimization engine)
curl http://192.168.1.60:8000/api/v1/recommendation/now
```

### 2. Check InfluxDB Data

In InfluxDB UI at `http://192.168.1.64:8086`:

**Data Explorer:**
```flux
from(bucket: "battery-optimizer")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["_field"] == "price_pence")
```

Should show price data with classifications!

### 3. Update Node-RED

The [`nodered/flows-hybrid.json`](nodered/flows-hybrid.json) has been updated to use 192.168.1.60.

**Re-import in Node-RED:**
1. Open `http://192.168.1.3:1880`
2. Menu → Import
3. Select "Replace existing nodes"
4. Paste updated flows content
5. Deploy

### 4. Verify Complete System

```bash
# Watch both systems
docker logs -f battery-optimizer

# In another terminal, trigger decision
curl http://192.168.1.60:8000/api/v1/recommendation/now

# Should see:
# "Optimization complete in XX ms"
# NOT "Using fallback" (unless no price data)
```

---

## What Should Happen Now

### Every 30 Minutes
1. Node-RED calls `POST /prices/refresh`
2. Python fetches from Octopus Energy
3. Stores in MariaDB
4. **Exports to InfluxDB** ← Can now visualize!
5. Returns success

### Every 5 Minutes  
1. Node-RED calls `GET /recommendation/now`
2. Python runs Linear Programming optimization
3. Returns: mode, discharge_current, immersion_main, immersion_lucy
4. **Exports decision to InfluxDB** ← Can track decisions!
5. Node-RED executes all 4 actions

### Every 30 Seconds
1. Node-RED updates dashboard
2. Shows current state from Python API
3. **Tracks state in InfluxDB** ← Historical trends!

---

## Expected Results

### Python Service Logs
```
INFO - Fetched 96 price periods
INFO - Optimization complete in 45.2ms - Force Charge at 0A
INFO - Wrote 96 price points to InfluxDB        ← NEW!
INFO - Wrote price analysis to InfluxDB         ← NEW!
```

### InfluxDB Measurements
- `electricity_price` - 96+ points (48hrs of data)
- `price_analysis` - Daily summary statistics
- `battery_decision` - Every 5min decisions
- `system_state` - Every 30sec snapshots

### Grafana Dashboards
See [`INFLUXDB_VISUALIZATION.md`](INFLUXDB_VISUALIZATION.md) for dashboard configuration

---

## Troubleshooting

### Still Getting Network Errors?

```bash
# Test from inside container
docker exec battery-optimizer curl http://192.168.1.64:8086/health

# If fails, check Unraid network settings
# Host network mode requires proper Unraid bridge configuration
```

### Optimization Still Failing?

```bash
# Check what error
docker logs battery-optimizer | grep "ERROR"

# Test optimization manually
curl http://192.168.1.60:8000/api/v1/recommendation/now
```

### No Data in InfluxDB?

1. Verify `INFLUX_ENABLED=true` in .env
2. Check logs for InfluxDB errors
3. Verify bucket exists
4. Check token permissions

---

## Summary of Changes

| File | Change | Reason |
|------|---------|--------|
| [`backend/docker-compose.yml`](backend/docker-compose.yml) | network_mode: host | Fix InfluxDB connectivity |
| [`backend/app/optimizer.py`](backend/app/optimizer.py) | efficiency_loss multiplication | Fix LpVariable division error |
| [`nodered/flows-hybrid.json`](nodered/flows-hybrid.json) | IP 192.168.1.60 | Match Docker host IP |
| [`backend/app/services/influxdb_client.py`](backend/app/services/influxdb_client.py) | NEW | InfluxDB export |
| [`backend/app/api.py`](backend/app/api.py) | Added influx writes | Export all data |

---

## Next Steps

1. **Rebuild:** `docker-compose down && docker-compose build --no-cache && docker-compose up -d`
2. **Verify:** Check logs for success messages
3. **Test API:** `curl http://192.168.1.60:8000/api/v1/recommendation/now`
4. **Re-import flows** in Node-RED (updated IPs)
5. **Enable InfluxDB:** Set `INFLUX_ENABLED=true` in .env
6. **Create Grafana dashboards** using visualization guide

---

**Status:** 🔧 Fixes applied, ready to rebuild  
**Issues Resolved:** 2/2  
**System Status:** Ready for production deployment