# Battery Optimizer - Unraid Installation Guide

This guide will help you install and configure the Battery Optimizer Docker container on Unraid.

## Prerequisites

1. **Unraid 6.9.0 or later**
2. **MariaDB/MySQL Database** (can be installed via Community Applications)
3. **Home Assistant** (optional but recommended)
4. **InfluxDB** (optional, for advanced monitoring)

## Installation Steps

### Step 1: Build the Docker Image

Since this is a custom Docker image, you'll need to build it first:

1. **SSH into your Unraid server**

2. **Navigate to the backend directory:**
   ```bash
   cd /mnt/user/appdata/battery-optimizer-build
   ```

3. **Copy the backend files to this directory** (use your preferred method - WinSCP, rsync, etc.)

4. **Build the Docker image:**
   ```bash
   docker build -t battery-optimizer:latest .
   ```

### Step 2: Add Container via Unraid GUI

#### Method A: Using the Template File (Recommended)

1. **Copy the template file** [`unraid-battery-optimizer-template.xml`](unraid-battery-optimizer-template.xml) to:
   ```
   /boot/config/plugins/dockerMan/templates-user/
   ```

2. **In Unraid Web GUI:**
   - Go to **Docker** tab
   - Click **Add Container**
   - Select **battery-optimizer** from the template dropdown

3. **Configure the settings** (see Configuration section below)

4. **Click Apply** to create the container

#### Method B: Manual Configuration

1. **In Unraid Web GUI, go to Docker tab**

2. **Click "Add Container"**

3. **Fill in the following basic settings:**
   - **Name:** `battery-optimizer`
   - **Repository:** `battery-optimizer:latest`
   - **Network Type:** `Custom: br0` (or `Bridge` if you prefer)
   - **Fixed IP (if using br0):** `192.168.1.60` (adjust to your network)

4. **Add Port Mapping:**
   - Container Port: `8000`
   - Host Port: `8000`
   - Connection Type: `TCP`

5. **Add Path Mappings:**
   - Container Path: `/app/data` → Host Path: `/mnt/user/appdata/battery-optimizer/data`
   - Container Path: `/app/logs` → Host Path: `/mnt/user/appdata/battery-optimizer/logs`

6. **Add Environment Variables** (see Configuration section below)

## Configuration

### Required Environment Variables

#### Database Configuration
- **DB_HOST:** `192.168.1.3` - MySQL/MariaDB host address
- **DB_PORT:** `3306` - Database port
- **DB_USER:** `optimizer` - Database username
- **DB_PASSWORD:** `your_password` - Database password (⚠️ keep secure)
- **DB_NAME:** `battery_optimizer` - Database name

#### Home Assistant Configuration
- **HA_URL:** `http://192.168.1.3:8123` - Home Assistant URL
- **HA_TOKEN:** `your_long_lived_token` - Long-lived access token (⚠️ keep secure)

#### Battery Configuration
- **BATTERY_CAPACITY_KWH:** `10.6` - Your battery capacity in kWh
- **BATTERY_MAX_CHARGE_KW:** `10.5` - Maximum charge rate in kW
- **BATTERY_MAX_DISCHARGE_KW:** `5.0` - Maximum discharge rate in kW
- **BATTERY_MIN_SOC:** `10` - Minimum state of charge %
- **BATTERY_MAX_SOC:** `100` - Maximum state of charge %

#### Solar Configuration
- **SOLAR_CAPACITY_KW:** `10.6` - Your solar system capacity in kW

#### Octopus Energy Configuration
- **OCTOPUS_PRODUCT:** `AGILE-24-10-01` - Your Octopus product code
- **OCTOPUS_TARIFF:** `E-1R-AGILE-24-10-01-E` - Your tariff code
- **OCTOPUS_REGION:** `E` - Your region code

#### Home Assistant Entity IDs
- **HA_ENTITY_BATTERY_SOC:** `sensor.foxinverter_battery_soc`
- **HA_ENTITY_SOLAR_POWER:** `sensor.pv_power_foxinverter`
- **HA_ENTITY_BATTERY_MODE:** `select.foxinverter_work_mode`

### Optional Environment Variables

#### InfluxDB Configuration (for advanced monitoring)
- **INFLUX_ENABLED:** `true` - Enable/disable InfluxDB
- **INFLUX_URL:** `http://192.168.1.64:8086`
- **INFLUX_TOKEN:** `your_influx_token`
- **INFLUX_ORG:** `unraid`
- **INFLUX_BUCKET:** `battery-optimizer`

#### Application Settings
- **LOG_LEVEL:** `INFO` - Logging level (DEBUG, INFO, WARNING, ERROR)
- **OPTIMIZATION_INTERVAL:** `300` - Optimization interval (seconds)
- **PRICE_FETCH_INTERVAL:** `1800` - Price fetch interval (seconds)

## Database Setup

Before starting the container, you need to create the database:

### Using MariaDB Docker Container

1. **Install MariaDB from Community Applications** (if not already installed)

2. **Access the MariaDB console:**
   ```bash
   docker exec -it mariadb mysql -u root -p
   ```

3. **Create the database and user:**
   ```sql
   CREATE DATABASE battery_optimizer;
   CREATE USER 'optimizer'@'%' IDENTIFIED BY 'your_password';
   GRANT ALL PRIVILEGES ON battery_optimizer.* TO 'optimizer'@'%';
   FLUSH PRIVILEGES;
   EXIT;
   ```

4. **Run the schema creation script:**
   ```bash
   docker exec -i mariadb mysql -u optimizer -p battery_optimizer < create_schedule_override_table.sql
   ```

## Post-Installation

### 1. Verify Container is Running

- Check the Docker tab in Unraid
- Container should show as "Started"
- Health check should show as "healthy" after ~40 seconds

### 2. Access the Web UI

Open your browser and navigate to:
```
http://YOUR_UNRAID_IP:8000
```

Or if using br0:
```
http://192.168.1.60:8000
```

### 3. Check Logs

View logs in Unraid:
- Click the container icon → **Logs**

Or via command line:
```bash
docker logs battery-optimizer
```

Or check the log files:
```
/mnt/user/appdata/battery-optimizer/logs/
```

### 4. API Health Check

Test the API endpoint:
```bash
curl http://192.168.1.60:8000/health
```

Should return:
```json
{"status": "healthy"}
```

## Network Configuration

### Using Bridge Network (Default)

If you use bridge networking, the container will be accessible via:
```
http://YOUR_UNRAID_IP:8000
```

### Using Custom br0 Network (Recommended)

For direct network access with a static IP:

1. **In container settings:**
   - Network Type: `Custom: br0`
   - Fixed IP: `192.168.1.60` (adjust to your network)

2. **Container will be accessible at:**
   ```
   http://192.168.1.60:8000
   ```

## Troubleshooting

### Container Won't Start

1. **Check logs:**
   ```bash
   docker logs battery-optimizer
   ```

2. **Verify the image exists:**
   ```bash
   docker images | grep battery-optimizer
   ```

3. **Rebuild if necessary:**
   ```bash
   cd /mnt/user/appdata/battery-optimizer-build
   docker build -t battery-optimizer:latest .
   ```

### Database Connection Issues

1. **Verify database is running:**
   ```bash
   docker ps | grep mariadb
   ```

2. **Test database connection:**
   ```bash
   docker exec -it mariadb mysql -u optimizer -p -h localhost
   ```

3. **Check database credentials in environment variables**

### Home Assistant Connection Issues

1. **Verify HA_URL is correct and accessible**
2. **Verify HA_TOKEN is valid** (create a new long-lived token if needed)
3. **Check entity IDs exist in Home Assistant**

### Port Already in Use

If port 8000 is already in use:
1. Change the **host port** to something else (e.g., 8001)
2. Update the **HOST_IP** environment variable if needed

## Updating the Container

To update the container with code changes:

1. **Stop the container:**
   - In Unraid Docker tab, click container → Stop

2. **Rebuild the image:**
   ```bash
   cd /mnt/user/appdata/battery-optimizer-build
   # Copy new code files
   docker build -t battery-optimizer:latest .
   ```

3. **Start the container:**
   - In Unraid Docker tab, click container → Start

## Backup and Restore

### Backup

Important files to backup:
- `/mnt/user/appdata/battery-optimizer/data/` - Application data
- `/mnt/user/appdata/battery-optimizer/logs/` - Log files
- Database (using MariaDB backup tools)
- Container template configuration

### Restore

1. Restore the data and log directories
2. Restore the database
3. Recreate the container using the template
4. Start the container

## Advanced Configuration

### Resource Limits

In the container settings, you can add extra parameters:
```
--memory=512m --cpus=1.0
```

### Health Check Customization

The template includes a health check. Modify if needed in Extra Parameters:
```
--health-interval=30s --health-timeout=10s --health-retries=3
```

## Support

For issues and questions:
- Check the logs first: `/mnt/user/appdata/battery-optimizer/logs/`
- Review the [main documentation](README.md)
- Verify all configuration values match your setup

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never share your HA_TOKEN or DB_PASSWORD**
2. **Use strong passwords for the database**
3. **Consider using Docker secrets for sensitive data**
4. **Restrict network access if possible**
5. **Keep the Docker image updated**
6. **Regular database backups are essential**

## Next Steps

After installation:
1. Review the [Quick Start Guide](QUICK_START.md)
2. Check the [Deployment Guide](DEPLOYMENT_GUIDE.md)
3. Set up [InfluxDB Visualization](INFLUXDB_VISUALIZATION.md) (optional)
4. Configure [Schedule Overrides](README_Schedule_Override.md) via API