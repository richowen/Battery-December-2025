# Phase 1 Implementation - Quick Start Guide

## Overview

This guide will walk you through implementing the **critical fixes** to your current Node-RED system while preparing for the Python optimization service. Estimated time: **2-4 hours**.

---

## Pre-Implementation Checklist

Before starting, please answer these questions:

- [ ] **HA VM IP Address:** _________________ (I assumed 192.168.1.64 in examples)
- [ ] **InfluxDB Location:** 
  - [ ] Unraid Docker container
  - [ ] Home Assistant addon
  - **IP/Port:** _________________
- [ ] **MariaDB accessible from Unraid Docker?** 
  - [ ] Yes (preferred)
  - [ ] No - need to configure networking
- [ ] **Backup taken?**
  - [ ] Node-RED flows exported
  - [ ] Home Assistant snapshot created
  - [ ] Unraid appdata backed up

---

## Phase 1A: Fix Critical Issues (1-2 hours)

### Step 1: Enable Node-RED Persistent Context

**Why:** Prevents state loss on Node-RED restart (fixes immersion switch tracking issue)

**Node-RED Settings** (in HA):

1. Edit Node-RED configuration (HA → Settings → Add-ons → Node-RED → Configuration tab)

2. Add this to the configuration:

```yaml
credential_secret: your_existing_secret_here  # Don't change if already set
settings:
  contextStorage:
    default:
      module: localfilesystem
    memory:
      module: memory
```

3. Restart Node-RED addon

4. **Verify:** Check Node-RED logs for "Context store 'default' : localfilesystem"

---

### Step 2: Fix Price Data Gap

**Current Problem:** Only stores today's prices, loses data overnight

**Solution:** Update the Octopus API URL to fetch 48 hours of data

**In Node-RED flow [`flows.json`](flows.json):**

Find the HTTP Request node (node ID: `3eef13cddbe27a5e`, line 78):

**CHANGE FROM:**
```json
"url": "https://api.octopus.energy/v1/products/AGILE-24-10-01/electricity-tariffs/E-1R-AGILE-24-10-01-E/standard-unit-rates/"
```

**CHANGE TO:**
```javascript
// Use a function node before HTTP request to build URL with date range
const now = new Date();
const tomorrow = new Date(now);
tomorrow.setDate(tomorrow.getDate() + 2);

const periodFrom = now.toISOString();
const periodTo = tomorrow.toISOString();

msg.url = `https://api.octopus.energy/v1/products/AGILE-24-10-01/electricity-tariffs/E-1R-AGILE-24-10-01-E/standard-unit-rates/?period_from=${periodFrom}&period_to=${periodTo}`;

return msg;
```

**Better approach:** I'll provide a complete updated Price Fetcher function that handles this properly.

---

### Step 3: Add Error Handling

**Current Problem:** No retry logic if Octopus API fails

**Solution:** Add a catch node and retry logic

In Node-RED:
1. Add a **Catch** node
2. Configure it to catch errors from HTTP request node
3. Add a **Delay** node (5 seconds)
4. Add a **Function** node to count retries
5. Loop back to HTTP request if retries < 3

**Or use the updated flow I'll provide** which includes this.

---

### Step 4: Update Price Fetcher Function

Replace the Price Fetcher function node (line 104-106) content with this improved version:

```javascript
// Enhanced Price Fetcher Function Node
// Fetches 48hr forecast and handles dates properly

function fetchPrices(msg) {
    try {
        // Input validation
        if (!msg.payload?.results) {
            node.error("Invalid API response format - missing results array");
            node.status({
                fill: 'red',
                shape: 'ring',
                text: 'Invalid API response'
            });
            return null;
        }

        const rawPrices = msg.payload.results;

        if (!Array.isArray(rawPrices) || rawPrices.length === 0) {
            node.error("No price data received from API");
            node.status({
                fill: 'red',
                shape: 'ring',
                text: 'No price data'
            });
            return null;
        }

        const now = new Date();
        const cutoff = new Date(now.getTime() - 24 * 60 * 60 * 1000); // 24 hours ago

        // Process raw API data - keep data from last 24hrs + next 48hrs
        const processedPrices = rawPrices
            .map(rate => {
                try {
                    const fromDate = new Date(rate.valid_from);
                    const toDate = new Date(rate.valid_to);

                    // Skip old data
                    if (fromDate < cutoff) {
                        return null;
                    }

                    return {
                        from: fromDate,
                        to: toDate,
                        price: parseFloat(rate.value_inc_vat),
                        hour: fromDate.getHours(),
                        timestamp: fromDate.toISOString()
                    };
                } catch (error) {
                    node.warn(`Invalid price period data: ${error.message}`);
                    return null;
                }
            })
            .filter(price => price !== null);

        if (processedPrices.length === 0) {
            node.error("No valid price periods found");
            node.status({
                fill: 'red',
                shape: 'ring',
                text: 'No valid prices'
            });
            return null;
        }

        // Sort by time for consistency
        processedPrices.sort((a, b) => a.from.getTime() - b.from.getTime());

        const fetchTimestamp = new Date().toISOString();
        
        // Calculate coverage
        const oldestDate = processedPrices[0].from;
        const newestDate = processedPrices[processedPrices.length - 1].from;
        const hoursOfData = (newestDate - oldestDate) / (1000 * 60 * 60);

        node.log(`Successfully processed ${processedPrices.length} price periods ` +
                 `covering ${hoursOfData.toFixed(1)} hours`);
        node.status({
            fill: 'green',
            shape: 'dot',
            text: `${processedPrices.length} periods (${hoursOfData.toFixed(0)}h) - ${new Date().toLocaleTimeString()}`
        });

        return {
            payload: processedPrices,
            metadata: {
                fetch_timestamp: fetchTimestamp,
                total_periods: processedPrices.length,
                coverage_hours: hoursOfData,
                oldest: oldestDate.toISOString(),
                newest: newestDate.toISOString()
            }
        };

    } catch (error) {
        node.error("Price fetcher error: " + error.message);
        node.status({
            fill: 'red',
            shape: 'ring',
            text: 'Fetch error'
        });
        return null;
    }
}

// Execute price fetching
return fetchPrices(msg);
```

---

### Step 5: Update Context Builder to Handle Missing Data

Replace Context Builder function (line 367) to be more defensive:

```javascript
// Enhanced Context Builder Function Node
// More defensive against missing data

function buildDecisionContext(msg) {
    try {
        const config = flow.get('system_config');
        if (!config) {
            node.error("System configuration not found");
            return null;
        }
        
        // Get price data with fallback
        const priceData = flow.get('price.all') || [];
        const priceAnalysis = flow.get('price.analysis') || {};
        
        if (priceData.length === 0) {
            node.warn("No price data available - using safe defaults");
            // Return safe default context
            return {
                payload: {
                    timestamp: new Date().toISOString(),
                    time: { hour: new Date().getHours() },
                    battery: { soc: Number(msg.soc) || 50 },
                    solar: { current: Number(msg.solar_now) || 0 },
                    price: { current: 25, classification: 'unknown' }, // Safe expensive assumption
                    flags: { preserve_battery: true } // Safe mode
                }
            };
        }
        
        const now = new Date();
        
        // Find current price period
        const currentPrice = priceData.find(p => {
            const start = new Date(p.from).getTime();
            const end = new Date(p.to).getTime();
            const nowTime = now.getTime();
            return nowTime >= start && nowTime < end;
        });
        
        if (!currentPrice) {
            node.warn("Cannot find exact current price period - using closest");
            // Find closest future price
            const futurePrices = priceData.filter(p => new Date(p.from) > now);
            if (futurePrices.length > 0) {
                currentPrice = futurePrices[0];
            } else {
                node.error("No usable price data");
                return null;
            }
        }
        
        // ... rest of original context builder code ...
        // (keep the existing logic for soc, solar, flags, etc.)
        
        const soc = Number(msg.soc) || 0;
        const solarNow = Number(msg.solar_now) || 0;
        const solarNext = Number(msg.solar_next) / 1000 || 0;
        const solarRemain = Number(msg.solar_remain) || 0;
        
        const currentHour = now.getHours() + now.getMinutes() / 60;
        
        const context = {
            timestamp: now.toISOString(),
            
            time: {
                hour: now.getHours(),
                minute: now.getMinutes(),
                decimal: currentHour,
                is_afternoon: currentHour >= config.timeWindows.afternoon.start && 
                             currentHour < config.timeWindows.afternoon.end,
                is_evening: currentHour >= config.timeWindows.evening.start && 
                           currentHour < config.timeWindows.evening.end,
                is_night: currentHour >= config.timeWindows.night.start || 
                         currentHour < config.timeWindows.night.end
            },
            
            battery: {
                soc: soc,
                is_low: soc < config.thresholds.battery.low,
                is_high: soc >= config.thresholds.battery.high,
                is_full: soc >= config.thresholds.battery.full
            },
            
            solar: {
                current: solarNow,
                next_hour: solarNext,
                remaining_today: solarRemain,
                is_high: solarNow >= config.thresholds.solar.high_threshold,
                is_low: solarNow < config.thresholds.solar.low_threshold
            },
            
            price: {
                current: currentPrice.price,
                classification: currentPrice.classification,
                is_negative: currentPrice.classification === 'negative',
                is_cheap: currentPrice.classification === 'cheap',
                is_expensive: currentPrice.classification === 'expensive'
            },
            
            flags: {
                high_solar_afternoon: solarNow >= config.thresholds.solar.high_threshold && 
                                     currentHour >= 12 && currentHour < 18,
                charge_opportunity: currentPrice.classification === 'negative' || 
                                   currentPrice.classification === 'cheap',
                immersion_opportunity: currentPrice.price < config.thresholds.price.immersion_trigger &&
                                      (soc >= config.thresholds.battery.full || solarNow > 5)
            }
        };
        
        flow.set('decision.context', context);
        flow.set('decision.context_updated', context.timestamp);
        
        node.status({
            fill: 'green',
            shape: 'dot',
            text: `${soc}% | ${solarNow.toFixed(1)}kW | ${currentPrice.price.toFixed(1)}p`
        });
        
        return {
            payload: context
        };
        
    } catch (error) {
        node.error("Context builder error: " + error.message);
        return null;
    }
}

return buildDecisionContext(msg);
```

---

## Phase 1B: Prepare for Python Service (30 min)

### Step 1: Setup MariaDB Database

**SSH into Home Assistant or use Terminal addon:**

```bash
# Access MariaDB
docker exec -it addon_core_mariadb mysql -u root -p

# Enter root password (from HA MariaDB addon settings)
```

**Run these SQL commands:**

```sql
-- Create database for optimization service
CREATE DATABASE IF NOT EXISTS battery_optimizer;

-- Create user (change password!)
CREATE USER IF NOT EXISTS 'optimizer'@'%' IDENTIFIED BY 'your_strong_password_here';

-- Grant privileges
GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'%';

-- Allow connections from Unraid Docker network
FLUSH PRIVILEGES;

-- Verify
SHOW DATABASES;
SELECT User, Host FROM mysql.user WHERE User='optimizer';

-- Exit
EXIT;
```

**Test connection from Unraid:**

```bash
# From Unraid console
mysql -h 192.168.1.64 -u optimizer -p battery_optimizer

# Should connect successfully
```

---

### Step 2: Get Home Assistant Long-Lived Access Token

1. In Home Assistant web UI:
   - Click your profile (bottom left)
   - Scroll to "Long-Lived Access Tokens"
   - Click "Create Token"
   - Name: "Battery Optimizer Service"
   - Copy the token (you can't see it again!)

2. Save it securely - you'll need it for Docker `.env` file

---

### Step 3: Create Unraid Docker Directory Structure

**From Unraid console:**

```bash
# Create directory structure
mkdir -p /mnt/user/appdata/battery-optimizer/{data,logs,config,src}

# Set permissions
chmod -R 755 /mnt/user/appdata/battery-optimizer

# Create .env file
cat > /mnt/user/appdata/battery-optimizer/.env << 'EOF'
# Database Configuration
DB_HOST=192.168.1.64
DB_PORT=3306
DB_USER=optimizer
DB_PASSWORD=your_strong_password_here
DB_NAME=battery_optimizer

# Home Assistant Configuration
HA_URL=http://192.168.1.64:8123
HA_TOKEN=your_long_lived_token_here

# InfluxDB Configuration (optional)
INFLUX_URL=http://192.168.1.64:8086
INFLUX_TOKEN=
INFLUX_ORG=unraid
INFLUX_BUCKET=battery-optimizer

# Application Configuration
LOG_LEVEL=INFO
OPTIMIZATION_INTERVAL=300
PRICE_FETCH_INTERVAL=1800
EOF

# Edit the .env file to add your actual values
nano /mnt/user/appdata/battery-optimizer/.env
```

---

### Step 4: Verify Network Connectivity

**Test from Node-RED (in HA):**

1. Add a temporary HTTP Request node in Node-RED
2. Set URL to: `http://UNRAID_IP:8000/health` (port we'll use)
3. This should fail for now (service not running yet)
4. Make note of any network errors

**Test from Unraid to HA:**

```bash
# Test HA API
curl -H "Authorization: Bearer YOUR_TOKEN" http://192.168.1.64:8123/api/

# Should return {"message": "API running."}

# Test MariaDB (already done above)
```

---

## Phase 1C: Deploy Test Version (Optional - 30 min)

This creates a minimal "hello world" Python service to verify infrastructure.

### Create minimal Dockerfile:

```dockerfile
# /mnt/user/appdata/battery-optimizer/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn

# Copy minimal app
COPY test_app.py /app/app.py

# Expose port
EXPOSE 8000

# Run
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Create test app:

```python
# /mnt/user/appdata/battery-optimizer/test_app.py
from fastapi import FastAPI
from datetime import datetime

app = FastAPI(title="Battery Optimizer - Test")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Battery Optimizer Service", "timestamp": datetime.now().isoformat()}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/v1/recommendation/now")
async def get_recommendation():
    # Mock response
    return {
        "mode": "Self Use",
        "discharge_current": 50,
        "reason": "Test response - real optimizer not yet deployed",
        "timestamp": datetime.now().isoformat()
    }
```

### Build and run:

```bash
cd /mnt/user/appdata/battery-optimizer

# Build image
docker build -t battery-optimizer:test .

# Run container
docker run -d \
  --name battery-optimizer-test \
  --restart unless-stopped \
  -p 8000:8000 \
  battery-optimizer:test

# Check logs
docker logs battery-optimizer-test

# Test
curl http://localhost:8000/health
```

### Test from Node-RED:

1. Add HTTP Request node
2. URL: `http://UNRAID_IP:8000/api/v1/recommendation/now`
3. Should return mock recommendation

---

## Verification Checklist

After Phase 1, verify:

- [ ] Node-RED context is persistent (check `/addon_configs/...nodered/context/`)
- [ ] Price data includes future periods (check debug output)
- [ ] MariaDB connection works from Unraid
- [ ] HA API accessible from Unraid via token
- [ ] Test Python service responds (if deployed)
- [ ] All Node-RED flows still working
- [ ] Dashboard still updating
- [ ] Battery control still functioning

---

## Troubleshooting

### "Cannot connect to MariaDB from Unraid"

**Solution:**
```sql
-- In MariaDB
GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'172.%';
FLUSH PRIVILEGES;
```

Docker containers typically use 172.x.x.x network.

### "Node-RED context not persisting"

**Check:**
```bash
# In HA terminal
ls -la /config/.storage/
ls -la /addon_configs/*/nodered/context/
```

Should see `default/` directory with `.json` files.

### "Price fetcher returning empty data"

**Check Octopus API directly:**
```bash
curl "https://api.octopus.energy/v1/products/AGILE-24-10-01/electricity-tariffs/E-1R-AGILE-24-10-01-E/standard-unit-rates/"
```

Should return JSON with results array.

---

## Next Steps

Once Phase 1 is complete:

1. **Switch to Code mode** to implement the full Python optimization service
2. I'll provide:
   - Complete Python source code
   - Database schema
   - Docker build files
   - Node-RED flow updates to call Python service
3. Run in parallel validation (2-4 weeks)
4. Cutover to production

---

## Estimated Timelines

| Phase | Duration | Effort |
|-------|----------|--------|
| **1A: Critical Fixes** | 1-2 hours | Low - mostly copy/paste |
| **1B: Infrastructure Setup** | 30 min | Low - database setup |
| **1C: Test Deploy** | 30 min | Medium - docker basics |
| **Total Phase 1** | 2-3 hours | **Can be done in one evening** |

---

## Questions Before Proceeding?

Please confirm:

1. ✅ You understand the Docker vs AppDaemon recommendation?
2. ✅ You're comfortable with the Phase 1 changes to Node-RED?
3. ✅ You have access to HA terminal/SSH?
4. ✅ You have access to Unraid console?
5. ✅ You've taken backups?

**When ready, let me know and I'll:**
- Provide the complete updated [`flows.json`](flows.json) with all Phase 1 fixes
- Or guide you step-by-step through each change
- Or switch to Code mode to start building the Python service

---

**Status:** 📋 Phase 1 plan complete, awaiting your go-ahead  
**Next:** Apply fixes or build Python service (your choice)