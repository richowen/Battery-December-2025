# InfluxDB Visualization Guide

## Overview

Your system now exports all prices, classifications, decisions, and system state to InfluxDB for beautiful visualizations and analysis.

---

## Enable InfluxDB Export

### Step 1: Update .env Configuration

Edit `/mnt/user/appdata/battery-optimizer/.env`:

```bash
# InfluxDB Configuration
INFLUX_ENABLED=true                        # ← Change from false to true
INFLUX_URL=http://192.168.1.64:8086        # Your InfluxDB URL
INFLUX_TOKEN=your_influxdb_token_here      # Get from InfluxDB admin
INFLUX_ORG=unraid                          # Your InfluxDB organization
INFLUX_BUCKET=battery-optimizer            # Bucket name (will be created)
```

### Step 2: Create InfluxDB Bucket

Access InfluxDB UI at `http://192.168.1.64:8086`:

1. Login to InfluxDB
2. Go to **Load Data** → **Buckets**
3. Click **Create Bucket**
4. Name: `battery-optimizer`
5. Retention: 30 days (or unlimited)
6. Click **Create**

### Step 3: Generate API Token

In InfluxDB:

1. Go to **Load Data** → **API Tokens**
2. Click **Generate API Token** → **All Access Token**
3. Description: "Battery Optimizer Service"
4. Copy the token
5. Paste into `.env` as `INFLUX_TOKEN`

### Step 4: Restart Python Service

```bash
docker-compose restart battery-optimizer

# Verify InfluxDB is enabled
docker logs battery-optimizer | grep InfluxDB
# Should see: "InfluxDB client initialized for http://192.168.1.64:8086"
```

### Step 5: Trigger Initial Data Load

```bash
# Load prices (will write to InfluxDB)
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Get recommendation (will write decision to InfluxDB)
curl http://192.168.1.2:8000/api/v1/recommendation/now

# Check InfluxDB has data
# In InfluxDB UI → Data Explorer:
# from(bucket: "battery-optimizer")
#   |> range(start: -1h)
#   |> filter(fn: (r) => r["_measurement"] == "electricity_price")
```

---

## Data Schema in InfluxDB

### Measurement: `electricity_price`

Individual price points every 30 minutes:

| Field | Type | Description |
|-------|------|-------------|
| price_pence | float | Price in pence/kWh |
| price_pounds | float | Price in £/kWh |

| Tag | Values | Description |
|-----|--------|-------------|
| classification | negative, cheap, normal, expensive | Price category |
| is_negative | true, false | Quick filter for negative prices |

**Timestamp:** `valid_from` field (when price period starts)

### Measurement: `price_analysis`

Daily summary statistics:

| Field | Type | Description |
|-------|------|-------------|
| min_price | float | Minimum price today |
| max_price | float | Maximum price today |
| mean_price | float | Average price |
| median_price | float | Median price |
| cheap_threshold | float | Threshold for "cheap" classification |
| expensive_threshold | float | Threshold for "expensive" |
| negative_count | int | Number of negative price periods |
| cheap_count | int | Number of cheap periods |
| expensive_count | int | Number of expensive periods |
| total_periods | int | Total price periods |

### Measurement: `battery_decision`

Optimization decisions every 5 minutes:

| Field | Type | Description |
|-------|------|-------------|
| discharge_current | int | Recommended discharge current (A) |
| expected_soc | float | Expected state of charge (%) |
| immersion_main | bool | Main immersion on/off |
| immersion_lucy | bool | Lucy immersion on/off |
| optimization_time_ms | float | How long optimization took |

| Tag | Values | Description |
|-----|--------|-------------|
| mode | Self Use, Force Charge, Feed-in First | Battery mode |
| optimization_status | optimal, feasible, fallback | Quality of decision |

### Measurement: `system_state`

Actual system state every 30 seconds (from HA):

| Field | Type | Description |
|-------|------|-------------|
| battery_soc | float | Actual battery SoC (%) |
| solar_power_kw | float | Current solar generation (kW) |
| solar_forecast_today_kwh | float | Remaining solar today (kWh) |
| discharge_current | int | Actual discharge setting (A) |
| current_price_pence | float | Current electricity price |
| immersion_main_on | bool | Main immersion actual state |
| immersion_lucy_on | bool | Lucy immersion actual state |

| Tag | Values | Description |
|-----|--------|-------------|
| battery_mode | Self Use, etc. | Actual battery mode |

---

## Flux Query Examples

### Current Price

```flux
from(bucket: "battery-optimizer")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["_field"] == "price_pence")
  |> last()
```

### Today's Full Price Pattern (Past + Future)

```flux
import "date"

start = date.truncate(t: now(), unit: 1d)
stop = date.add(to: start, d: 1d)

from(bucket: "battery-optimizer")
  |> range(start: start, stop: stop)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["_field"] == "price_pence")
  |> sort(columns: ["_time"])
```

### Negative Price Periods (Including Future)

```flux
import "date"

start = date.truncate(t: now(), unit: 1d)
stop = date.add(to: start, d: 1d)

from(bucket: "battery-optimizer")
  |> range(start: start, stop: stop)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["classification"] == "negative")
  |> filter(fn: (r) => r["_field"] == "price_pence")
```

### Battery Decisions vs Actual State

```flux
// Recommendations
decision = from(bucket: "battery-optimizer")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "battery_decision")
  |> filter(fn: (r) => r["_field"] == "expected_soc")

// Actual state
actual = from(bucket: "battery-optimizer")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "system_state")
  |> filter(fn: (r) => r["_field"] == "battery_soc")

// Compare on same graph
```

### Optimization Performance

```flux
from(bucket: "battery-optimizer")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "battery_decision")
  |> filter(fn: (r) => r["_field"] == "optimization_time_ms")
  |> mean()
  |> yield(name: "avg_optimization_time")
```

---

## Grafana Dashboard

### Install Grafana (Optional)

If you don't have Grafana, install on Unraid:

```bash
# Add Grafana container
docker run -d \
  --name=grafana \
  -p 3000:3000 \
  -v /mnt/user/appdata/grafana:/var/lib/grafana \
  --restart unless-stopped \
  grafana/grafana:latest
```

Access at: `http://192.168.1.2:3000` (default: admin/admin)

### Add InfluxDB Data Source

1. In Grafana → Configuration → Data Sources
2. Add Data Source → InfluxDB
3. Configure:
   - **Query Language:** Flux
   - **URL:** `http://192.168.1.64:8086`
   - **Organization:** `unraid`
   - **Token:** Your InfluxDB token
   - **Default Bucket:** `battery-optimizer`
4. Save & Test

### Import Dashboard

Create a new dashboard with these panels:

#### Panel 1: Price Timeline (Last 24h)

```json
{
  "title": "Electricity Prices - 24 Hour View",
  "type": "graph",
  "targets": [{
    "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"electricity_price\")\n  |> filter(fn: (r) => r[\"_field\"] == \"price_pence\")\n  |> sort(columns: [\"_time\"])"
  }],
  "fieldConfig": {
    "defaults": {
      "color": {
        "mode": "thresholds"
      },
      "thresholds": {
        "steps": [
          { "value": -10, "color": "dark-red" },
          { "value": 0, "color": "dark-green" },
          { "value": 15, "color": "yellow" },
          { "value": 25, "color": "orange" },
          { "value": 35, "color": "red" }
        ]
      }
    }
  }
}
```

#### Panel 2: Price Classifications (Pie Chart)

```json
{
  "title": "Price Classification Distribution",
  "type": "piechart",
  "targets": [{
    "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"price_analysis\")\n  |> filter(fn: (r) => r[\"_field\"] =~ /.*_count/)\n  |> last()"
  }]
}
```

#### Panel 3: Battery SoC vs Price

```json
{
  "title": "Battery SoC & Price Correlation",
  "type": "graph",
  "targets": [
    {
      "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"system_state\")\n  |> filter(fn: (r) => r[\"_field\"] == \"battery_soc\")"
    },
    {
      "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"system_state\")\n  |> filter(fn: (r) => r[\"_field\"] == \"current_price_pence\")"
    }
  ]
}
```

#### Panel 4: Immersion Heater Activity

```json
{
  "title": "Immersion Heater Usage",
  "type": "state-timeline",
  "targets": [
    {
      "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_main\")"
    },
    {
      "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_lucy\")"
    }
  ]
}
```

#### Panel 5: Optimization Performance

```json
{
  "title": "Optimization Time (ms)",
  "type": "stat",
  "targets": [{
    "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -1h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"optimization_time_ms\")\n  |> mean()"
  }],
  "fieldConfig": {
    "defaults": {
      "thresholds": {
        "steps": [
          { "value": 0, "color": "green" },
          { "value": 100, "color": "yellow" },
          { "value": 500, "color": "red" }
        ]
      },
      "unit": "ms"
    }
  }
}
```

---

## Complete Grafana Dashboard JSON

Save this as `grafana-dashboard-battery.json` and import:

```json
{
  "dashboard": {
    "title": "Battery Optimization Dashboard",
    "panels": [
      {
        "title": "Electricity Price Timeline",
        "type": "timeseries",
        "gridPos": { "x": 0, "y": 0, "w": 24, "h": 8 },
        "targets": [{
          "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart,stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"electricity_price\")\n  |> filter(fn: (r) => r[\"_field\"] == \"price_pence\")",
          "refId": "A"
        }],
        "fieldConfig": {
          "defaults": {
            "custom": {
              "lineWidth": 2,
              "fillOpacity": 20,
              "gradientMode": "hue"
            },
            "color": {
              "mode": "thresholds"
            },
            "thresholds": {
              "mode": "absolute",
              "steps": [
                { "value": -10, "color": "dark-red" },
                { "value": 0, "color": "dark-green" },
                { "value": 10, "color": "green" },
                { "value": 20, "color": "yellow" },
                { "value": 30, "color": "orange" },
                { "value": 40, "color": "red" }
              ]
            },
            "unit": "p/kWh"
          }
        }
      },
      {
        "title": "Price Classifications",
        "type": "piechart",
        "gridPos": { "x": 0, "y": 8, "w": 8, "h": 6 },
        "targets": [{
          "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -24h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"electricity_price\")\n  |> group(columns: [\"classification\"])\n  |> count()",
          "refId": "A"
        }]
      },
      {
        "title": "Battery State of Charge",
        "type": "timeseries",
        "gridPos": { "x": 8, "y": 8, "w": 16, "h": 6 },
        "targets": [{
          "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"system_state\")\n  |> filter(fn: (r) => r[\"_field\"] == \"battery_soc\")",
          "refId": "A"
        }],
        "fieldConfig": {
          "defaults": {
            "min": 0,
            "max": 100,
            "unit": "percent"
          }
        }
      },
      {
        "title": "Solar Generation vs Price",
        "type": "timeseries",
        "gridPos": { "x": 0, "y": 14, "w": 12, "h": 6 },
        "targets": [
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"system_state\")\n  |> filter(fn: (r) => r[\"_field\"] == \"solar_power_kw\")",
            "refId": "Solar"
          },
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"system_state\")\n  |> filter(fn: (r) => r[\"_field\"] == \"current_price_pence\")\n  |> map(fn: (r) => ({ r with _value: r._value / 10.0 }))",
            "refId": "Price"
          }
        ]
      },
      {
        "title": "Immersion Heater Activity",
        "type": "state-timeline",
        "gridPos": { "x": 12, "y": 14, "w": 12, "h": 6 },
        "targets": [
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_main\")",
            "refId": "Main"
          },
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_lucy\")",
            "refId": "Lucy"
          }
        ]
      },
      {
        "title": "Optimization Performance",
        "type": "stat",
        "gridPos": { "x": 0, "y": 20, "w": 6, "h": 4 },
        "targets": [{
          "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -1h)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"optimization_time_ms\")\n  |> mean()",
          "refId": "A"
        }],
        "fieldConfig": {
          "defaults": {
            "thresholds": {
              "steps": [
                { "value": 0, "color": "green" },
                { "value": 100, "color": "yellow" },
                { "value": 500, "color": "red" }
              ]
            },
            "unit": "ms"
          }
        }
      },
      {
        "title": "Today's Price Range",
        "type": "stat",
        "gridPos": { "x": 6, "y": 20, "w": 6, "h": 4 },
        "targets": [
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: today())\n  |> filter(fn: (r) => r[\"_measurement\"] == \"price_analysis\")\n  |> filter(fn: (r) => r[\"_field\"] == \"min_price\")\n  |> last()",
            "refId": "Min"
          },
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: today())\n  |> filter(fn: (r) => r[\"_measurement\"] == \"price_analysis\")\n  |> filter(fn: (r) => r[\"_field\"] == \"max_price\")\n  |> last()",
            "refId": "Max"
          }
        ]
      },
      {
        "title": "Current Battery Mode",
        "type": "stat",
        "gridPos": { "x": 12, "y": 20, "w": 6, "h": 4 },
        "targets": [{
          "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -5m)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"mode\"] != \"\")\n  |> last()\n  |> keep(columns: [\"mode\"])",
          "refId": "A"
        }]
      },
      {
        "title": "Immersion Status",
        "type": "stat",
        "gridPos": { "x": 18, "y": 20, "w": 6, "h": 4 },
        "targets": [
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -5m)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_main\")\n  |> last()",
            "refId": "Main"
          },
          {
            "query": "from(bucket: \"battery-optimizer\")\n  |> range(start: -5m)\n  |> filter(fn: (r) => r[\"_measurement\"] == \"battery_decision\")\n  |> filter(fn: (r) => r[\"_field\"] == \"immersion_lucy\")\n  |> last()",
            "refId": "Lucy"
          }
        ],
        "mappings": [
          { "value": 0, "text": "OFF" },
          { "value": 1, "text": "ON" }
        ]
      }
    ],
    "refresh": "30s",
    "time": { "from": "now-24h", "to": "now" }
  }
}
```

---

## Simple InfluxDB Queries

### In InfluxDB Data Explorer

**View all prices for today:**
```flux
from(bucket: "battery-optimizer")
  |> range(start: today())
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["_field"] == "price_pence")
  |> sort(columns: ["_time"])
```

**Show negative prices only:**
```flux
from(bucket: "battery-optimizer")
  |> range(start: -48h)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> filter(fn: (r) => r["classification"] == "negative")
  |> filter(fn: (r) => r["_field"] == "price_pence")
```

**Battery decisions when immersion was ON:**
```flux
from(bucket: "battery-optimizer")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "battery_decision")
  |> filter(fn: (r) => r["_field"] == "immersion_main")
  |> filter(fn: (r) => r["_value"] == true)
```

---

## Verification

After enabling InfluxDB, verify data is flowing:

```bash
# Trigger price refresh
curl -X POST http://192.168.1.2:8000/api/v1/prices/refresh

# Check Python logs
docker logs battery-optimizer | grep InfluxDB

# Should see:
# "Wrote 96 price points to InfluxDB"
# "Wrote price analysis to InfluxDB"
```

In InfluxDB UI → Data Explorer, run:
```flux
from(bucket: "battery-optimizer")
  |> range(start: -1h)
  |> filter(fn: (r) => r["_measurement"] == "electricity_price")
  |> count()
```

Should return the number of price points written.

---

## Troubleshooting

### "No data in InfluxDB"

1. Check `.env` has `INFLUX_ENABLED=true`
2. Verify `INFLUX_TOKEN` is correct
3. Check bucket name matches
4. Restart service: `docker-compose restart`
5. Check logs: `docker logs battery-optimizer | grep InfluxDB`

### "InfluxDB connection failed"

```bash
# Test from container
docker exec battery-optimizer curl -H "Authorization: Token YOUR_TOKEN" \
  http://192.168.1.64:8086/api/v2/buckets
```

### "Data shows but dashboard is empty"

- Check Flux queries match your measurement names
- Verify time range in Grafana
- Ensure data source is configured correctly

---

## What You Can Visualize

With InfluxDB + Grafana you can now see:

- ✅ **48-hour price forecast** with color-coded classifications
- ✅ **Battery SoC trends** correlated with prices
- ✅ **Solar generation** vs electricity prices
- ✅ **Immersion heater activation pattern**
- ✅ **Optimization performance** over time
- ✅ **Decision quality** (optimal vs fallback)
- ✅ **Cost savings** trends
- ✅ **System health** metrics

**Create beautiful dashboards to understand and validate your system's behavior!** 📊

---

**Status:** ✅ InfluxDB Integration Complete  
**Next:** Enable in .env, restart service, create Grafana dashboard