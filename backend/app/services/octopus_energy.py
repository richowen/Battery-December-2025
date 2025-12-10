"""
Octopus Energy API Client
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta, timezone
import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class OctopusEnergyClient:
    """Client for fetching electricity prices from Octopus Energy API"""
    
    def __init__(self):
        self.base_url = settings.octopus_api_url
        self.timeout = 30.0
    
    async def fetch_prices(self) -> List[Dict]:
        """
        Fetch electricity prices from Octopus Agile API
        
        Octopus publishes prices between 4pm-8pm daily for:
        - 11pm tonight → 11pm tomorrow (24 hours)
        - Before 4pm: Only have prices until 11pm tonight
        - After 4pm: Get tomorrow's prices too
        
        Returns:
            List of all available price periods with valid_from, valid_to, price_pence
        """
        try:
            logger.info("Fetching all available Agile prices from Octopus")
            
            # Don't use period_from/period_to - get all available data
            # Octopus API returns what's available (handles their publishing schedule)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url)
                response.raise_for_status()
                data = response.json()
            
            # Process results - keep from midnight today onwards for full day visualization
            prices = []
            now = datetime.now(timezone.utc)
            
            # Get midnight today in UTC
            today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            for result in data.get("results", []):
                try:
                    valid_from = datetime.fromisoformat(
                        result["valid_from"].replace("Z", "+00:00")
                    )
                    valid_to = datetime.fromisoformat(
                        result["valid_to"].replace("Z", "+00:00")
                    )
                    price_pence = float(result["value_inc_vat"])
                    
                    # Keep all prices from midnight today onwards
                    # This includes past prices (for visualization) and future prices (for optimization)
                    if valid_from >= today_midnight:
                        prices.append({
                            "valid_from": valid_from,
                            "valid_to": valid_to,
                            "price_pence": price_pence
                        })
                
                except (KeyError, ValueError) as e:
                    logger.warning(f"Skipping invalid price data: {e}")
                    continue
            
            # Calculate coverage
            if prices:
                prices.sort(key=lambda x: x["valid_from"])
                earliest = prices[0]["valid_from"]
                latest = prices[-1]["valid_to"]
                hours_total = (latest - earliest).total_seconds() / 3600
                hours_ahead = (latest - now).total_seconds() / 3600
                
                logger.info(f"Fetched {len(prices)} price periods: {hours_total:.1f} hours total, {hours_ahead:.1f} hours ahead")
            else:
                logger.warning("No valid price periods received from Octopus API")
            
            return prices
        
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching prices: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return []
    
    def classify_prices(self, prices: List[Dict]) -> List[Dict]:
        """
        Classify prices as negative, cheap, normal, or expensive
        
        Args:
            prices: List of price dicts
            
        Returns:
            Prices with added 'classification' field
        """
        if not prices:
            return []
        
        # Extract price values
        price_values = [p["price_pence"] for p in prices]
        price_values.sort()
        
        # Calculate percentile thresholds
        cheap_index = int(len(price_values) * 0.20)  # Bottom 20%
        expensive_index = int(len(price_values) * 0.75)  # Top 25%
        
        cheap_threshold = price_values[cheap_index] if cheap_index < len(price_values) else price_values[0]
        expensive_threshold = price_values[expensive_index] if expensive_index < len(price_values) else price_values[-1]
        
        # Classify each price
        classified = []
        for price in prices:
            value = price["price_pence"]
            
            if value < 0:
                classification = "negative"
            elif value <= cheap_threshold:
                classification = "cheap"
            elif value >= expensive_threshold:
                classification = "expensive"
            else:
                classification = "normal"
            
            classified.append({
                **price,
                "classification": classification
            })
        
        logger.info(
            f"Classified prices: {sum(1 for p in classified if p['classification'] == 'negative')} negative, "
            f"{sum(1 for p in classified if p['classification'] == 'cheap')} cheap, "
            f"{sum(1 for p in classified if p['classification'] == 'expensive')} expensive"
        )
        
        return classified
    
    def get_price_statistics(self, prices: List[Dict]) -> Dict:
        """
        Calculate price statistics
        
        Args:
            prices: List of price dicts
            
        Returns:
            Dict with min, max, mean, median, thresholds
        """
        if not prices:
            return {}
        
        values = [p["price_pence"] for p in prices]
        values.sort()
        
        cheap_index = int(len(values) * 0.20)
        expensive_index = int(len(values) * 0.75)
        
        return {
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
            "median": values[len(values) // 2],
            "cheap_threshold": values[cheap_index],
            "expensive_threshold": values[expensive_index],
            "total_periods": len(values),
            "negative_count": sum(1 for v in values if v < 0),
            "cheap_count": sum(1 for v in values if v <= values[cheap_index]),
            "expensive_count": sum(1 for v in values if v >= values[expensive_index])
        }