# Battery Optimization System - Deployment Guide

**Version:** 2.0 - Hybrid Architecture  
**Date:** 2025-12-10  
**Infrastructure:** Unraid + Home Assistant VM

---

## Quick Start Summary

Your complete hybrid battery optimization system consists of:
1. **Python Service** (Unraid Docker) - Optimization engine at `192.168.1.2:8000`
2. **Node-RED** (HA VM) - Orchestration layer at `192.168.1.3:1880`
3. **MariaDB** (HA VM) - Database at `192.168.1.3:3306`
4. **InfluxDB** (External) - Metrics at `192.168.1.64:8086`

---

## Prerequisites Checklist

- [ ] Unraid server at 192.168.1.2
- [ ] Home Assistant VM at 192.168.1.3 with:
  - [ ] Node-RED addon installed
  - [ ] MariaDB addon installed
  - [ ] Long-lived access token created
- [ ] InfluxDB accessible at 192.168.1.64:8086
- [ ] Docker and docker-compose on Unraid
- [ ] Network connectivity verified (test app was successful ✓)

---

## Step 1: Database Setup (5 minutes)

### 1.1 Access MariaDB in Home Assistant

```bash
# SSH into Home Assistant or use Terminal addon
docker exec -it addon_core_mariadb mysql -u root -p
# Enter MariaDB root password from addon settings
```

### 1.2 Create Database and User

```sql
-- Create database
CREATE DATABASE IF NOT EXISTS battery_optimizer;

-- Create user (CHANGE PASSWORD!)
CREATE USER IF NOT EXISTS 'optimizer'@'%' IDENTIFIED BY 'YourStrongPassword123!';

-- Grant privileges
GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'%';

-- Allow Docker network access
GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'172.%';
FLUSH PRIVILEGES;

-- Verify
SHOW DATABASES;
SELECT User, Host FROM mysql.user WHERE User='optimizer';
EXIT;
```

### 1.3 Test Connection from Unraid

```bash
# From Unraid console
mysql -h 192.168.1.3 -u optimizer -p battery_optimizer
# Should connect successfully
```

---

## Step 2: Deploy Python Service (10 minutes)

### 2.1 Create Directory Structure

```bash
# On Unraid
mkdir -p /mnt/user/appdata/battery-optimizer/{data,logs}
cd /mnt/user/appdata/battery-optimizer
```

### 2.2 Copy Project Files

Copy the entire `backend/` directory from this project to `/mnt/user/appdata/battery-optimizer/`:

```bash
# Structure should be:
/mnt/user/appdata/battery-optimizer/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── optimizer.py
│   ├── api.py
│   ├── main.py
│   └── services/
│       ├── __init__.py
│       ├── home_assistant.py
│       └── octopus_energy.py
├── data/
├── logs/
├── .env
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

### 2.3 Create .env File

```bash
# Create .env from template
cp .env.example .env
nano .env
```

**Edit .env with your actual values:**

```bash
# Database Configuration
DB_HOST=192.168.1.3
DB_PORT=3306
DB_USER=optimizer
DB_PASSWORD=YourStrongPassword123!
DB_NAME=battery_optimizer

# Home Assistant Configuration
HA_URL=http://192.168.1.3:8123
HA_TOKEN=your_long_lived_access_token_here

# InfluxDB Configuration (optional)
INFLUX_ENABLED=false
INFLUX_URL=http://192.168.1.64:8086
INFLUX_TOKEN=
INFLUX_ORG=unraid
INFLUX_BUCKET=battery-optimizer

# Octopus Energy Configuration
OCTOPUS_PRODUCT=AGILE-24-10-01
OCTOPUS_TARIFF=E-1R-AGILE-24-10-01-E
OCTOPUS_REGION=E

# Application Configuration
LOG_LEVEL=INFO
OPTIMIZATION_INTERVAL=300
PRICE_FETCH_INTERVAL=1800
API_PORT=8000

# Battery Configuration (adjust for your system)
BATTERY_CAPACITY_KWH=10.0
BATTERY_MAX_CHARGE_KW=5.0
BATTERY_MAX_DISCHARGE_KW=5.0
BATTERY_EFFICIENCY=0.95
BATTERY_MIN_SOC=10
BATTERY_MAX_SOC=100

# Solar Configuration
SOLAR_CAPACITY_KW=8.0

# Home Assistant Entity IDs (verify these match your setup)
HA_ENTITY_BATTERY_SOC=sensor.foxinverter_battery_soc
HA_ENTITY_SOLAR_POWER=sensor.pv_power_foxinverter
HA_ENTITY_SOLAR_FORECAST_TODAY=sensor.solcast_pv_forecast_forecast_remaining_today
HA_ENTITY_SOLAR_FORECAST_NEXT_HOUR=sensor.solcast_pv_forecast_power_in_1_hour
HA_ENTITY_BATTERY_MODE=select.foxinverter_work_mode
HA_ENTITY_DISCHARGE_CURRENT=number.foxinverter_max_discharge_current
HA_ENTITY_IMMERSION_MAIN=switch.immersion_switch
HA_ENTITY_IMMERSION_LUCY=switch.immersion_lucy_switch
```

### 2.4 Build and Start Container

```bash
cd /mnt/user/appdata/battery-optimizer

# Build image
docker-compose build

# Start service
docker-compose up -d

# Check logs
docker-compose logs -f battery-optimizer
```

### 2.5 Verify Service is Running

```bash
# Check container status
docker ps | grep battery-optimizer

# Test API
curl http://localhost:8000/health

# Should return:
# {"status":"healthy","version":"1.0.0"}

# Check database tables created
docker exec -it addon_core_mariadb mysql -u optimizer -p -D battery_optimizer -e "SHOW TABLES;"
```

---

## Step 3: Initial Price Data Load (2 minutes)

```bash
# Fetch initial price data
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Should return:
# {
#   "status": "success",
#   "prices_stored": 96,
#   "coverage_hours": 48.0,
#   "statistics": {...}
# }

# Verify prices in database
docker exec -it addon_core_mariadb mysql -u optimizer -p -D battery_optimizer \
  -e "SELECT COUNT(*) as price_count FROM electricity_prices;"
```

---

## Step 4: Deploy Node-RED Flows (5 minutes)

### 4.1 Backup Existing Flows

In Home Assistant Node-RED:
1. Menu → Export → Select All → Download

### 4.2 Import New Hybrid Flows

1. Open Node-RED in Home Assistant (`http://192.168.1.3:1880`)
2. Menu → Import
3. Copy content from `nodered/flows-hybrid.json`
4. Click "Import"
5. Deploy

### 4.3 Verify Node-RED is Calling Python Service

1. Check Node-RED debug panel
2. Should see logs like:
   ```
   Price refresh: 96 prices stored
   Recommendation: Force Charge at 0A - Cheap price (8.5p) → Opportunity charging
   ```

---

## Step 5: Dashboard Access (1 minute)

Access your new dashboard at:
```
http://192.168.1.3:1880/ui
```

You should see:
- **Current Strategy** - Current battery mode
- **Battery** - SoC percentage
- **Solar** - Current and forecast
- **Price** - Current electricity price
- **Decision Reason** - Why the system made its choice
- **Last Update** - Timestamp

---

## Step 6: Monitoring & Verification (10 minutes)

### 6.1 Watch the Logs

```bash
# Python service logs
docker logs -f battery-optimizer

# Should see:
# INFO - Starting Battery Optimization Service v1.0.0
# INFO - Database initialized
# INFO - Fetched 96 price periods
# INFO - Optimization complete in 45.2ms - Force Charge at 0A
```

### 6.2 Check API Endpoints

```bash
# Get current recommendation
curl http://192.168.1.2:8000/api/v1/recommendation/now

# Get system state
curl http://192.168.1.2:8000/api/v1/state/current

# Get prices
curl http://192.168.1.2:8000/api/v1/prices/current?hours=24

# Get daily stats
curl http://192.168.1.2:8000/api/v1/stats/daily

# Get recommendation history
curl http://192.168.1.2:8000/api/v1/history/recommendations?hours=24
```

### 6.3 Verify Battery Control

1. Wait for 5-minute decision cycle
2. Check Home Assistant:
   - Battery mode should change based on recommendation
   - Discharge current should update
3. Monitor for 30 minutes to ensure stable operation

---

## Operational Schedule

| Task | Frequency | System | Details |
|------|-----------|--------|---------|
| Fetch Prices | Every 30 min | Node-RED → Python | Keeps 48hr price forecast |
| Get Recommendation | Every 5 min | Node-RED → Python | Optimizes and controls battery |
| Update Dashboard | Every 30 sec | Node-RED → Python | Real-time display |
| Database Cleanup | Daily 03:00 | Python | Removes old data >7 days |
| Health Check | Every 30 sec | Docker | Auto-restart if unhealthy |

---

## Troubleshooting

### Python Service Won't Start

**Check logs:**
```bash
docker logs battery-optimizer
```

**Common issues:**
1. **Database connection failed**
   - Verify MariaDB is running
   - Check DB_HOST, DB_USER, DB_PASSWORD in .env
   - Test: `mysql -h 192.168.1.3 -u optimizer -p`

2. **HA Token invalid**
   - Regenerate long-lived token in HA
   - Update HA_TOKEN in .env
   - Restart: `docker-compose restart`

3. **Port 8000 already in use**
   - Check: `netstat -tulpn | grep 8000`
   - Change API_PORT in .env

### No Price Data

```bash
# Manual refresh
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Check Octopus API directly
curl "https://api.octopus.energy/v1/products/AGILE-24-10-01/electricity-tariffs/E-1R-AGILE-24-10-01-E/standard-unit-rates/"
```

### Node-RED Not Connecting to Python Service

1. **Check network:**
   ```bash
   # From HA VM
   curl http://192.168.1.2:8000/health
   ```

2. **Update URLs in Node-RED flows:**
   - Edit HTTP request nodes
   - Change URL to match your Unraid IP

### Optimization Returns Fallback Mode

**Check logs:**
```bash
docker logs battery-optimizer | grep -i "optimization"
```

**Common causes:**
- No price data available
- Solver failed (PuLP issue)
- Invalid battery parameters

**Solution:**
```bash
# Refresh prices
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Check current state
curl http://192.168.1.2:8000/api/v1/state/current
```

---

## Maintenance

### Daily Checks

```bash
# Check service health
curl http://192.168.1.2:8000/health

# Check logs for errors
docker logs battery-optimizer --since 24h | grep -i error

# Check database size
docker exec -it addon_core_mariadb mysql -u optimizer -p -D battery_optimizer \
  -e "SELECT table_name, ROUND(data_length/1024/1024,2) AS 'Size (MB)' FROM information_schema.tables WHERE table_schema='battery_optimizer';"
```

### Weekly Maintenance

```bash
# Update price data
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Backup database
docker exec addon_core_mariadb mysqldump -u optimizer -p battery_optimizer > battery_optimizer_backup.sql

# Review optimization performance
curl http://192.168.1.2:8000/api/v1/history/recommendations?hours=168 | jq
```

### Monthly Updates

```bash
# Update Python service
cd /mnt/user/appdata/battery-optimizer
docker-compose pull
docker-compose up -d

# Check for new features
docker logs battery-optimizer | grep "version"
```

---

## Performance Monitoring

### Key Metrics to Track

```bash
# Optimization time (should be <100ms)
curl http://192.168.1.2:8000/api/v1/history/recommendations?hours=24 | \
  jq '.[] | .optimization_time_ms' | \
  awk '{sum+=$1; count++} END {print "Avg:", sum/count, "ms"}'

# Database query performance
docker exec -it addon_core_mariadb mysql -u optimizer -p -D battery_optimizer \
  -e "SHOW PROCESSLIST;"

# Docker resource usage
docker stats battery-optimizer --no-stream
```

### Expected Performance

| Metric | Target | Acceptable | Action if Exceeded |
|--------|--------|------------|-------------------|
| API Response Time | <50ms | <200ms | Check database indexes |
| Optimization Time | <100ms | <500ms | Review solver parameters |
| Memory Usage | <256MB | <512MB | Check for memory leaks |
| CPU Usage | <10% | <25% | Optimize algorithms |
| Database Size | <100MB | <500MB | Run cleanup |

---

## Backup Strategy

### Automated Backups (Recommended)

Create `/mnt/user/appdata/battery-optimizer/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/mnt/user/backups/battery-optimizer"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
docker exec addon_core_mariadb mysqldump -u optimizer -p battery_optimizer \
  > $BACKUP_DIR/database_$DATE.sql

# Backup config
cp /mnt/user/appdata/battery-optimizer/.env $BACKUP_DIR/env_$DATE.bak

# Keep only last 7 days
find $BACKUP_DIR -name "database_*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "env_*.bak" -mtime +7 -delete

echo "Backup completed: $DATE"
```

Run daily via Unraid User Scripts plugin at 02:00.

---

## Migration from Old System

If you have the old Node-RED-only system running:

1. **Run both in parallel** for 1 week
2. **Compare results:**
   ```bash
   # Old system battery mode
   # vs
   # New system recommendation
   curl http://192.168.1.2:8000/api/v1/recommendation/now
   ```
3. **Monitor cost savings** via InfluxDB dashboards
4. **Cutover** when confident (disable old Node-RED flow)
5. **Archive old flow** as backup

---

## Advanced Features (Optional)

### Enable InfluxDB Logging

1. Set INFLUX_ENABLED=true in .env
2. Provide INFLUX_TOKEN
3. Restart service
4. Create Grafana dashboard

### Add Email Alerts

Create `/mnt/user/appdata/battery-optimizer/alerts.sh`:

```bash
#!/bin/bash
STATUS=$(curl -s http://localhost:8000/health | jq -r '.status')

if [ "$STATUS" != "healthy" ]; then
    echo "Battery Optimizer is unhealthy!" | \
    mail -s "ALERT: Battery Optimizer Down" your@email.com
fi
```

### Machine Learning Load Forecasting (Future)

The system is designed to support ML load forecasting:
- Historical load data is being collected in SystemState table
- Future update will add TensorFlow model
- No code changes needed in Node-RED

---

## Support & Debugging

### Enable Debug Logging

```bash
# Edit .env
LOG_LEVEL=DEBUG

# Restart
docker-compose restart

# View detailed logs
docker logs -f battery-optimizer
```

### API Documentation

Once running, access interactive API docs at:
```
http://192.168.1.2:8000/docs
```

This provides:
- All available endpoints
- Request/response schemas
- Try-it-out functionality

### Get Help

1. Check logs first
2. Verify all configuration in .env
3. Test each component individually:
   - HA connection
   - Database connection  
   - Octopus API
   - Optimization algorithm
4. Create issue with:
   - Log output
   - Configuration (sanitized)
   - Expected vs actual behavior

---

## Success Criteria

Your system is working correctly when:

- ✅ Python service health check returns "healthy"
- ✅ Prices refresh every 30 minutes (check logs)
- ✅ Recommendations provided every 5 minutes
- ✅ Battery mode changes based on recommendations
- ✅ Dashboard updates in real-time
- ✅ No errors in logs for 24 hours
- ✅ Database grows predictably (~1MB/day)
- ✅ Optimization time stays <100ms

Expected cost savings: **30-50% improvement** over reactive rules (measure after 2-4 weeks)

---

## What's Next?

1. **Monitor for 1week** - Ensure stability
2. **Compare savings** - Track electricity costs
3. **Fine-tune** - Adjust battery parameters if needed
4. **Expand** - Add ML forecasting, grid services
5. **Share results** - Help others optimize their systems!

---

**System Status:** 🟢 Ready for Production  
**Documentation Version:** 2.0  
**Last Updated:** 2025-12-10