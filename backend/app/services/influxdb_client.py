"""
InfluxDB Client for metrics and price visualization
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from app.config import settings

logger = logging.getLogger(__name__)


class InfluxDBService:
    """Client for writing metrics to InfluxDB"""
    
    def __init__(self):
        self.enabled = settings.influx_enabled
        if not self.enabled:
            logger.info("InfluxDB logging disabled")
            return
        
        try:
            self.client = InfluxDBClient(
                url=settings.influx_url,
                token=settings.influx_token,
                org=settings.influx_org
            )
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.bucket = settings.influx_bucket
            
            # Verify bucket exists or create it
            try:
                buckets_api = self.client.buckets_api()
                bucket = buckets_api.find_bucket_by_name(self.bucket)
                
                if not bucket:
                    logger.info(f"Creating InfluxDB bucket: {self.bucket}")
                    buckets_api.create_bucket(bucket_name=self.bucket, org=settings.influx_org)
                    logger.info(f"InfluxDB bucket '{self.bucket}' created")
                else:
                    logger.info(f"Using existing InfluxDB bucket: {self.bucket}")
                    
            except Exception as bucket_error:
                logger.warning(f"Could not verify/create bucket: {bucket_error}")
                logger.info("Continuing anyway - bucket may exist")
            
            logger.info(f"InfluxDB client initialized for {settings.influx_url}")
        except Exception as e:
            logger.error(f"Failed to initialize InfluxDB: {e}")
            self.enabled = False
    
    def write_prices(self, prices: List[Dict]) -> bool:
        """
        Write electricity prices to InfluxDB
        
        Args:
            prices: List of price dicts with valid_from, valid_to, price_pence, classification
            
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            points = []
            for price_data in prices:
                # Create point for each price period
                point = Point("electricity_price") \
                    .tag("classification", price_data.get("classification", "unknown")) \
                    .tag("is_negative", "true" if price_data["price_pence"] < 0 else "false") \
                    .field("price_pence", float(price_data["price_pence"])) \
                    .field("price_pounds", float(price_data["price_pence"]) / 100) \
                    .time(price_data["valid_from"])
                
                points.append(point)
            
            self.write_api.write(bucket=self.bucket, record=points)
            logger.info(f"Wrote {len(points)} price points to InfluxDB")
            return True
        
        except Exception as e:
            logger.error(f"Failed to write prices to InfluxDB: {e}")
            return False
    
    def write_price_analysis(self, analysis: Dict) -> bool:
        """
        Write price analysis statistics to InfluxDB
        
        Args:
            analysis: Dict with price statistics
            
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            point = Point("price_analysis") \
                .tag("data_type", "daily_summary") \
                .field("min_price", float(analysis["min"])) \
                .field("max_price", float(analysis["max"])) \
                .field("mean_price", float(analysis["mean"])) \
                .field("median_price", float(analysis["median"])) \
                .field("cheap_threshold", float(analysis["cheap_threshold"])) \
                .field("expensive_threshold", float(analysis["expensive_threshold"])) \
                .field("negative_count", analysis["negative_count"]) \
                .field("cheap_count", analysis.get("cheap_count", 0)) \
                .field("expensive_count", analysis.get("expensive_count", 0)) \
                .field("total_periods", analysis["total_periods"]) \
                .time(datetime.now())
            
            self.write_api.write(bucket=self.bucket, record=point)
            logger.info("Wrote price analysis to InfluxDB")
            return True
        
        except Exception as e:
            logger.error(f"Failed to write price analysis to InfluxDB: {e}")
            return False
    
    def write_optimization_result(self, result: Dict) -> bool:
        """
        Write optimization decision to InfluxDB
        
        Args:
            result: Optimization result dict
            
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            rec = result.get("current_recommendation", {})
            
            point = Point("battery_decision") \
                .tag("mode", rec.get("mode", "unknown")) \
                .tag("optimization_status", result.get("status", "unknown")) \
                .field("discharge_current", rec.get("discharge_current", 0)) \
                .field("expected_soc", rec.get("expected_soc", 0)) \
                .field("immersion_main", rec.get("immersion_main", False)) \
                .field("immersion_lucy", rec.get("immersion_lucy", False)) \
                .field("optimization_time_ms", result.get("optimization_time_ms", 0)) \
                .time(datetime.now())
            
            self.write_api.write(bucket=self.bucket, record=point)
            return True
        
        except Exception as e:
            logger.error(f"Failed to write optimization result to InfluxDB: {e}")
            return False
    
    def write_system_state(self, state: Dict) -> bool:
        """
        Write current system state to InfluxDB
        
        Args:
            state: System state dict
            
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            point = Point("system_state") \
                .tag("battery_mode", state.get("battery_mode", "unknown")) \
                .field("battery_soc", float(state.get("battery_soc", 0))) \
                .field("solar_power_kw", float(state.get("solar_power_kw", 0))) \
                .field("solar_forecast_today_kwh", float(state.get("solar_forecast_today_kwh", 0))) \
                .field("discharge_current", state.get("discharge_current", 0)) \
                .field("immersion_main_on", state.get("immersion_main_on", False)) \
                .field("immersion_lucy_on", state.get("immersion_lucy_on", False)) \
                .time(datetime.now())
            
            if state.get("current_price") is not None:
                point.field("current_price_pence", float(state["current_price"]))
            
            self.write_api.write(bucket=self.bucket, record=point)
            return True
        
        except Exception as e:
            logger.error(f"Failed to write system state to InfluxDB: {e}")
            return False