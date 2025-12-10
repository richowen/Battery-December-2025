# Recommended Hybrid Architecture - Visual Reference

## System Overview

```mermaid
graph TB
    subgraph "External Data Sources"
        OCTOPUS[Octopus Energy API<br/>Agile Pricing]
        SOLCAST[Solcast API<br/>Solar Forecast]
        HA[Home Assistant<br/>Sensors & Actuators]
    end

    subgraph "Python Optimization Service"
        API[FastAPI REST API]
        OPT[Optimization Engine<br/>Linear Programming]
        PRICE_DB[(Price Database<br/>PostgreSQL)]
        STATE_DB[(State Cache<br/>Redis)]
        METRICS[Metrics & Monitoring]
    end

    subgraph "Node-RED Orchestration"
        FETCH[Data Fetcher<br/>Every 30min]
        DECIDE[Decision Trigger<br/>Every 5min]
        CONTROL[Device Controller<br/>HA Service Calls]
        DASH[Dashboard UI<br/>Real-time Display]
        FALLBACK[Fallback Rules<br/>Safety Net]
    end

    subgraph "Physical Devices"
        BATTERY[Fox Inverter<br/>Battery System]
        IMMERSION[Immersion Heaters<br/>Hot Water]
    end

    OCTOPUS -->|48hr prices| FETCH
    SOLCAST -->|forecast| FETCH
    HA -->|sensor states| FETCH
    
    FETCH -->|store prices| API
    FETCH -->|update forecasts| API
    
    DECIDE -->|request recommendation| API
    API -->|optimal schedule| DECIDE
    
    API --> OPT
    OPT --> PRICE_DB
    OPT --> STATE_DB
    OPT --> METRICS
    
    DECIDE -->|on error| FALLBACK
    DECIDE -->|commands| CONTROL
    FALLBACK -->|commands| CONTROL
    
    CONTROL -->|set mode/discharge| HA
    CONTROL -->|switch on/off| HA
    
    HA -->|controls| BATTERY
    HA -->|controls| IMMERSION
    
    METRICS -->|logs| DASH
    CONTROL -->|status| DASH

    style OPT fill:#90EE90
    style CONTROL fill:#87CEEB
    style FALLBACK fill:#FFB6C1
    style BATTERY fill:#FFD700
    style IMMERSION fill:#FFD700
```

## Data Flow - Optimization Cycle

```mermaid
sequenceDiagram
    participant NR as Node-RED
    participant PY as Python Service
    participant DB as Database
    participant HA as Home Assistant
    participant DEV as Battery/Devices

    Note over NR,DB: Every 30 minutes
    NR->>PY: POST /api/v1/prices/update
    PY->>DB: Store 48hr price forecast
    PY-->>NR: OK

    Note over NR,DEV: Every 5 minutes  
    NR->>HA: Get current sensors
    HA-->>NR: SoC, Solar, Load
    
    NR->>PY: GET /api/v1/recommendation/now
    PY->>DB: Fetch prices, forecasts, state
    PY->>PY: Run optimization (LP solver)
    PY->>DB: Cache result
    PY-->>NR: { mode, discharge, reason }
    
    alt Optimization successful
        NR->>HA: Set battery mode
        NR->>HA: Set discharge current
        HA->>DEV: Apply settings
    else Optimization failed
        NR->>NR: Use fallback rules
        NR->>HA: Set safe defaults
        HA->>DEV: Apply settings
    end

    NR->>NR: Update dashboard
```

## Component Responsibilities

| Component | Responsibilities | Technology |
|-----------|-----------------|------------|
| **Node-RED** | - Orchestration & scheduling<br/>- Home Assistant integration<br/>- Device control execution<br/>- Dashboard UI<br/>- Fallback safety rules | JavaScript, Node-RED nodes |
| **Python Service** | - Mathematical optimization<br/>- Price data management<br/>- State persistence<br/>- Metrics & analytics<br/>- API endpoints | Python 3.11+, FastAPI, PuLP |
| **PostgreSQL** | - Price history (48hr rolling)<br/>- Optimization results<br/>- System configuration<br/>- Audit logs | PostgreSQL 15 |
| **Redis** | - Current state cache<br/>- Fast lookups<br/>- Session data | Redis 7 |
| **Home Assistant** | - Physical device control<br/>- Sensor data collection<br/>- External integrations | HA Core |

## Optimization Algorithm Flow

```mermaid
flowchart TD
    START[Start Optimization] --> GATHER[Gather Inputs]
    GATHER --> INPUTS{Inputs Valid?}
    INPUTS -->|No| ERROR[Return Error]
    INPUTS -->|Yes| BUILD[Build LP Problem]
    
    BUILD --> VARS[Define Variables:<br/>charge[], discharge[], soc[]]
    VARS --> OBJ[Objective Function:<br/>Minimize Total Cost]
    OBJ --> CONST[Add Constraints:<br/>Battery limits, Physics]
    
    CONST --> SOLVE[Solve with PuLP]
    SOLVE --> SOL{Solution Found?}
    
    SOL -->|No| FALLBACK[Use Heuristic Fallback]
    SOL -->|Yes| EXTRACT[Extract Schedule]
    
    EXTRACT --> NOW[Get Current Action]
    FALLBACK --> NOW
    
    NOW --> CACHE[Cache Full Schedule]
    CACHE --> RETURN[Return Recommendation]
    RETURN --> END[End]
    
    style SOLVE fill:#90EE90
    style FALLBACK fill:#FFB6C1
    style RETURN fill:#87CEEB
```

## Migration Phases

```mermaid
gantt
    title Migration Timeline (6 Months)
    dateFormat YYYY-MM-DD
    section Phase 1: Fixes
    Price data gap fix           :p1a, 2025-12-15, 3d
    Error handling              :p1b, after p1a, 3d
    Persistent state            :p1c, after p1b, 2d
    Batch API calls             :p1d, after p1c, 2d
    Testing & validation        :p1e, after p1d, 4d
    
    section Phase 2: Build
    Python service core         :p2a, 2025-12-30, 14d
    Optimization engine         :p2b, after p2a, 14d
    Integration & testing       :p2c, after p2b, 14d
    Parallel validation         :p2d, after p2c, 21d
    
    section Phase 3: Migration
    Shadow mode deployment      :p3a, 2026-03-15, 14d
    A/B testing                 :p3b, after p3a, 14d
    Primary mode cutover        :p3c, after p3b, 14d
    Cleanup & optimization      :p3d, after p3c, 14d
    
    section Phase 4: Advanced
    ML load forecasting         :p4a, 2026-05-15, 21d
    Enhanced features           :p4b, after p4a, 21d
```

## Quick Decision Matrix

| Scenario | Recommended Action |
|----------|-------------------|
| **System working fine, no budget** | Implement Phase 1 fixes only |
| **Want better results, moderate budget** | Full hybrid architecture (all phases) |
| **Need quick wins** | Phase 1 + simple optimization (skip ML) |
| **Large battery (>10kWh), complex tariff** | Full optimization - highest ROI |
| **Small battery (<5kWh), simple tariff** | Improved rules may suffice |
| **Planning to add EV/V2G** | Full hybrid - future-proof |

## Expected Outcomes by Phase

```mermaid
graph LR
    A[Current System<br/>£500/yr savings] -->|Phase 1| B[Fixed System<br/>£520/yr<br/>+4% reliability]
    B -->|Phase 2-3| C[Optimized System<br/>£750/yr<br/>+50% savings]
    C -->|Phase 4| D[Advanced System<br/>£850/yr<br/>+70% savings]
    
    style A fill:#FFB6C1
    style B fill:#87CEEB
    style C fill:#90EE90
    style D fill:#FFD700
```

## Key Success Metrics

| Metric | Current | Phase 1 Target | Phase 3 Target |
|--------|---------|----------------|----------------|
| Annual savings | £500 | £520 | £750+ |
| System uptime | 95% | 99% | 99.9% |
| Response latency | 2s | 500ms | 100ms |
| Optimization accuracy | N/A (reactive) | N/A | 95%+ vs theoretical optimal |
| Data gaps | 6hr/day | 0 | 0 |
| Test coverage | 0% | 20% | 80% |

## Technology Stack Summary

```
┌────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                       │
│  Node-RED Dashboard UI (existing)                       │
│  Optional: React dashboard for advanced features        │
└────────────────────────────────────────────────────────┘
                         ↑ HTTP/WebSocket
┌────────────────────────────────────────────────────────┐
│                 ORCHESTRATION LAYER                     │
│  Node-RED v3.x                                         │
│  - Flow-based orchestration                            │
│  - HA integration nodes                                │
│  - Safety fallback logic                               │
└────────────────────────────────────────────────────────┘
                         ↑ REST API
┌────────────────────────────────────────────────────────┐
│                  BUSINESS LOGIC LAYER                   │
│  Python 3.11+ FastAPI Service                          │
│  - PuLP/CVXPY (optimization)                           │
│  - NumPy/Pandas (data processing)                      │
│  - Pydantic (validation)                               │
│  - APScheduler (background tasks)                      │
└────────────────────────────────────────────────────────┘
                         ↑ SQL/Redis
┌────────────────────────────────────────────────────────┐
│                    DATA LAYER                           │
│  PostgreSQL 15: Persistent storage                     │
│  Redis 7: Fast cache                                   │
│  InfluxDB: Time-series metrics (existing)              │
└────────────────────────────────────────────────────────┘
                         ↑ API Calls
┌────────────────────────────────────────────────────────┐
│                 INTEGRATION LAYER                       │
│  Home Assistant: Device control                        │
│  Octopus Energy API: Pricing                           │
│  Solcast: Solar forecasts                              │
└────────────────────────────────────────────────────────┘
```

## Deployment Architecture

```
Host Machine (Raspberry Pi 4 / NUC / Server)
│
├── Docker Compose Stack
│   ├── Node-RED Container (port 1880)
│   ├── Python Service Container (port 8000)
│   ├── PostgreSQL Container (port 5432)
│   ├── Redis Container (port 6379)
│   └── InfluxDB Container (existing, port 8086)
│
├── Home Assistant (separate install or container)
│
└── Shared Volumes
    ├── /data/nodered (flows, context)
    ├── /data/postgres (database files)
    └── /data/config (shared configs)
```

---

**Version:** 1.0  
**Last Updated:** 2025-12-10  
**For:** Hybrid Architecture Implementation  
**Status:** ✅ Ready for Review