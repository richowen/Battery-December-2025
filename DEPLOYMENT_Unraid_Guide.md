# Deployment Guide - Unraid Infrastructure

## Your Current Setup Analysis

```
┌─────────────────────────────────────────────────────────────┐
│                      UNRAID HOST                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Home Assistant VM                            │  │
│  │  • Node-RED (internal)                               │  │
│  │  • MariaDB (internal)                                │  │
│  │  • AppDaemon (internal)                              │  │
│  │  • InfluxDB (?)                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Docker Containers (available)                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Recommended Architecture for Unraid

### ✅ RECOMMENDED: Hybrid Approach

```
┌─────────────────────────────────────────────────────────────────┐
│                         UNRAID HOST                             │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │              Home Assistant VM                            │ │
│  │  ✅ Node-RED (keep here - already installed)             │ │
│  │  ✅ MariaDB (keep here - HA uses it anyway)              │ │
│  │  ❌ AppDaemon (DON'T use for optimization service)       │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           ↕ API                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │         Docker Container (Unraid native)                  │ │
│  │  ✅ Python Optimization Service (FastAPI)                 │ │
│  │     - Runs 24/7 independently                             │ │
│  │     - Survives HA restarts                                │ │
│  │     - Full Python ecosystem access                        │ │
│  │     - Easy updates via Docker                             │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           ↕ SQL                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │         Docker Container (Unraid native) - OPTIONAL       │ │
│  │  ⚠️ PostgreSQL (for optimization service state)           │ │
│  │     OR just use MariaDB in HA VM via network              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │         Docker Container (existing)                       │ │
│  │  ✅ InfluxDB (keep as-is for metrics)                     │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Key Recommendations

### 1. ✅ Node-RED - KEEP Inside Home Assistant VM

**Why:**
- Already installed and configured
- Native HA integration (no network calls)
- Shares HA's add-on ecosystem
- Your existing [`flows.json`](flows.json) works as-is
- Dashboard already integrated

**No changes needed** - this is optimal placement.

---

### 2. ✅ MariaDB - KEEP Inside Home Assistant VM

**Why:**
- Home Assistant already uses MariaDB for recorder
- Single database for both HA history and optimization state
- Backup/restore handled by HA supervisor
- No network latency for HA database queries
- Can create separate database/user for optimization service

**Configuration:**
```yaml
# In HA configuration.yaml (if not already set)
recorder:
  db_url: mysql://homeassistant:password@core-mariadb/homeassistant
```

**For Optimization Service:**
Create a separate database in the same MariaDB instance:
```sql
CREATE DATABASE battery_optimizer;
CREATE USER 'optimizer'@'%' IDENTIFIED BY 'strong_password';
GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'%';
FLUSH PRIVILEGES;
```

---

### 3. ❌ AppDaemon - DON'T USE for Optimization Service

**Why AppDaemon is NOT ideal:**
- ❌ Limited to HA ecosystem and restart cycle
- ❌ Slower than FastAPI for REST APIs
- ❌ Can't use scientific computing libraries easily (NumPy/SciPy issues)
- ❌ Harder to test and develop locally
- ❌ Couples optimization service lifecycle to HA
- ❌ Limited debugging tools
- ❌ Can't scale independently

**Why Standalone Docker Container IS better:**
- ✅ **Independence:** Runs 24/7 even during HA restarts/updates
- ✅ **Performance:** FastAPI is significantly faster than AppDaemon
- ✅ **Libraries:** Full access to scientific Python (PuLP, CVXPY, NumPy, Pandas)
- ✅ **Development:** Easy local testing with Docker
- ✅ **Updates:** Deploy new versions without touching HA
- ✅ **Debugging:** Full Python debugging tools (pdb, logging, profiling)
- ✅ **Monitoring:** Prometheus metrics built-in
- ✅ **Scaling:** Can move to dedicated hardware later if needed

---

### 4. ⚙️ PostgreSQL vs MariaDB Decision

**Option A: Use MariaDB in HA VM (RECOMMENDED for simplicity)**

Pros:
- ✅ Already installed
- ✅ One database to backup
- ✅ No additional containers
- ✅ MariaDB is perfectly capable for this workload

Cons:
- ⚠️ Network connection from Docker to VM (minimal latency)
- ⚠️ Couples database to HA restart (but data persists)

**Option B: Separate PostgreSQL Docker Container**

Pros:
- ✅ PostgreSQL has better JSON support
- ✅ Completely independent from HA
- ✅ Native Docker networking

Cons:
- ❌ Another container to manage
- ❌ Another backup routine
- ❌ Overkill for this workload

**Recommendation:** **Use MariaDB** in HA VM. It's simpler and works great. You can always migrate later if needed.

---

## Deployment Architecture

### Network Topology

```
┌─────────────────────────────────────────────────────────────────┐
│ UNRAID HOST (192.168.1.x)                                       │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Home Assistant VM: 192.168.1.64 (assumed)                │  │
│  │                                                           │  │
│  │  Node-RED → http://192.168.1.64:1880                     │  │
│  │  HA API   → http://192.168.1.64:8123/api                 │  │
│  │  MariaDB  → 192.168.1.64:3306                            │  │
│  │            (accessible from Docker via bridge)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                    ↕                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Docker Container: battery-optimizer                      │  │
│  │                                                           │  │
│  │  FastAPI  → http://192.168.1.x:8000 (Unraid IP)         │  │
│  │            (accessible from Node-RED in VM)              │  │
│  │                                                           │  │
│  │  Connects to MariaDB: 192.168.1.64:3306                 │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                    ↕                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ InfluxDB Container (existing)                            │  │
│  │  → http://192.168.1.64:8086                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Docker Compose for Unraid

Create this as `/mnt/user/appdata/battery-optimizer/docker-compose.yml`:

```yaml
version: '3.8'

services:
  battery-optimizer:
    image: ghcr.io/yourusername/battery-optimizer:latest  # We'll build this
    container_name: battery-optimizer
    restart: unless-stopped
    
    ports:
      - "8000:8000"  # FastAPI port
    
    environment:
      # Database connection
      - DB_HOST=192.168.1.64  # Your HA VM IP
      - DB_PORT=3306
      - DB_USER=optimizer
      - DB_PASSWORD=${DB_PASSWORD}  # Set in .env file
      - DB_NAME=battery_optimizer
      
      # Home Assistant connection
      - HA_URL=http://192.168.1.64:8123
      - HA_TOKEN=${HA_TOKEN}  # Long-lived access token
      
      # InfluxDB (optional, for metrics)
      - INFLUX_URL=http://192.168.1.64:8086
      - INFLUX_TOKEN=${INFLUX_TOKEN}
      - INFLUX_ORG=unraid
      - INFLUX_BUCKET=battery-optimizer
      
      # Application settings
      - LOG_LEVEL=INFO
      - OPTIMIZATION_INTERVAL=300  # 5 minutes
      - PRICE_FETCH_INTERVAL=1800  # 30 minutes
      
    volumes:
      - /mnt/user/appdata/battery-optimizer/data:/app/data
      - /mnt/user/appdata/battery-optimizer/logs:/app/logs
      - /mnt/user/appdata/battery-optimizer/config:/app/config
    
    networks:
      - battery-net
    
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    
    # Resource limits (adjust based on your Unraid hardware)
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M

networks:
  battery-net:
    driver: bridge
```

**Create `.env` file in same directory:**

```bash
# /mnt/user/appdata/battery-optimizer/.env
DB_PASSWORD=your_strong_password_here
HA_TOKEN=your_long_lived_access_token
INFLUX_TOKEN=your_influx_token_if_using
```

---

## Why This Architecture is Optimal for Unraid

### 1. **Resilience**
- HA VM can restart without killing optimization service
- Optimization service can restart without affecting HA
- Node-RED stays integrated with HA but calls independent service

### 2. **Simplicity**
- No extra databases (reuse MariaDB in HA)
- Docker on Unraid is native and well-supported
- Single docker-compose file to manage

### 3. **Performance**
- Node-RED ↔ HA: Internal VM communication (fast)
- Node-RED → Optimizer: Network call (acceptable, infrequent)
- Optimizer → MariaDB: Network call (acceptable, cached)

### 4. **Maintainability**
- Update Python service: `docker-compose pull && docker-compose up -d`
- Update Node-RED: Through HA supervisor
- Backup: Unraid backup captures Docker volumes + HA backup captures HA config

### 5. **Development Workflow**
```bash
# Develop locally on your machine
cd battery-optimizer
docker build -t battery-optimizer:dev .
docker run -p 8000:8000 battery-optimizer:dev

# Test against your real HA
# Deploy to Unraid via docker-compose
```

---

## Alternative: AppDaemon Approach (NOT RECOMMENDED)

If you insist on using AppDaemon despite limitations:

**Pros:**
- Everything in HA VM
- Native HA integration
- No Docker knowledge needed

**Cons:**
- Limited to HA lifecycle
- Harder to test optimization algorithms
- Scientific libraries may have install issues
- Slower API performance
- Couples everything together

**When to use AppDaemon:**
- You're ONLY doing simple automations
- You don't need heavy computation
- You want everything in one place despite limitations

**For this project:** AppDaemon is **not suitable** because:
- Linear programming needs SciPy/PuLP (problematic in AppDaemon)
- Need fast API responses (<100ms)
- Want 24/7 availability independent of HA

---

## Comparison Matrix

| Aspect | Docker FastAPI (✅ RECOMMENDED) | AppDaemon (❌ NOT RECOMMENDED) |
|--------|----------------------------------|--------------------------------|
| **Independence** | Runs 24/7, survives HA restarts | Coupled to HA lifecycle |
| **Performance** | <50ms API response | ~200ms API response |
| **Libraries** | Full Python ecosystem | Limited to HA add-on compatible |
| **Development** | Local testing easy | Must deploy to HA to test |
| **Debugging** | Full Python tools | Limited HA logs |
| **Updates** | `docker-compose pull` | Restart HA supervisor |
| **Scaling** | Can move to dedicated server | Stuck in HA |
| **Complexity** | Docker setup needed | Simpler initial setup |
| **Resource Usage** | ~200MB RAM | ~150MB RAM |
| **Monitoring** | Prometheus metrics | HA logs only |
| **Testing** | Unit tests, integration tests | Manual testing in HA |

**Verdict:** The extra complexity of Docker is worth it for this use case.

---

## Next Steps - Deployment Plan

### Immediate Actions (Phase 1 - This Week)

1. **Prepare MariaDB in HA**
   ```bash
   # Access HA terminal/SSH
   docker exec -it addon_core_mariadb mysql -u root -p
   
   # Run SQL commands from earlier
   CREATE DATABASE battery_optimizer;
   CREATE USER 'optimizer'@'%' IDENTIFIED BY 'strong_password';
   # etc.
   ```

2. **Get HA Long-Lived Access Token**
   - HA → Profile → Long-Lived Access Tokens → Create Token
   - Save for Docker `.env` file

3. **Fix Critical Issues in Current Node-RED**
   - I'll provide updated [`flows.json`](flows.json) next
   - Fix price data gap
   - Add error handling
   - Enable persistent context

4. **Prepare Unraid Docker Environment**
   ```bash
   # Create directories
   mkdir -p /mnt/user/appdata/battery-optimizer/{data,logs,config}
   
   # Create docker-compose.yml (content above)
   # Create .env file (content above)
   ```

### Phase 2 (Next 2-4 Weeks)

- Build Python optimization service
- I'll provide complete source code
- Deploy to Unraid Docker
- Run in parallel with existing system for validation

---

## Hardware Requirements

### Minimum (for testing):
- **CPU:** 2 cores (Unraid can handle this easily)
- **RAM:** 512MB for optimizer + existing HA/Node-RED
- **Storage:** 5GB for Docker images + data

### Recommended (for production):
- **CPU:** 4 cores (Unraid typical)
- **RAM:** 1GB for optimizer, 4GB total system
- **Storage:** 10GB for growth

Your Unraid server almost certainly exceeds these requirements.

---

## Questions to Answer

Before proceeding, please confirm:

1. **What's your HA VM IP address?** (I assumed 192.168.1.64)
2. **Where is InfluxDB running?** (Unraid Docker or HA addon?)
3. **Do you have Docker experience, or should I provide more detailed Docker setup?**
4. **Backup strategy for Unraid?** (Appdata backup plugin recommended)
5. **Do you want to proceed with Phase 1 fixes immediately?**

---

**Status:** ✅ Architecture design complete, ready to implement  
**Next:** Provide Phase 1 code changes for Node-RED  
**After That:** Build Python optimization service