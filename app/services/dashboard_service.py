"""
Dashboard Service - Collects comprehensive technical metrics for monitoring and troubleshooting.

Provides real-time statistics on:
- System health (API, MongoDB, uptime)
- WebSocket connections (per group and total)
- Database statistics (groups, messages, growth)
- Performance metrics (response times, slow requests)
- Recent logs and errors
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict, deque
import psutil
import time

from app.core.logging_config import get_logger
# Group model removed - groups now fetched from Auth-API via GroupService
from app.models.message import Message
from app.services.connection_manager import ConnectionManager
from beanie import PydanticObjectId

logger = get_logger(__name__)


class MetricsCollector:
    """
    Singleton class to collect and track metrics throughout the application lifecycle.
    Thread-safe for concurrent access from multiple requests.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.start_time = time.time()

        # Performance tracking
        self.request_count = 0
        self.error_count = 0
        self.total_response_time = 0.0
        self.slow_requests = deque(maxlen=100)  # Last 100 slow requests
        self.recent_requests = deque(maxlen=50)  # Last 50 requests
        self.recent_errors = deque(maxlen=50)    # Last 50 errors

        # Endpoint statistics
        self.endpoint_stats = defaultdict(lambda: {"count": 0, "errors": 0, "total_time": 0.0})

        # WebSocket events
        self.ws_events = deque(maxlen=100)  # Last 100 WS connection events

        self._initialized = True

    def record_request(self, endpoint: str, method: str, duration_ms: float,
                      status_code: int, correlation_id: str):
        """Record a completed HTTP request."""
        self.request_count += 1
        self.total_response_time += duration_ms

        # Update endpoint stats
        self.endpoint_stats[f"{method} {endpoint}"]["count"] += 1
        self.endpoint_stats[f"{method} {endpoint}"]["total_time"] += duration_ms

        # Track errors
        if status_code >= 400:
            self.error_count += 1
            self.endpoint_stats[f"{method} {endpoint}"]["errors"] += 1

            self.recent_errors.append({
                "timestamp": datetime.utcnow().isoformat(),
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "correlation_id": correlation_id,
                "duration_ms": duration_ms
            })

        # Track slow requests
        if duration_ms > 1000:
            self.slow_requests.append({
                "timestamp": datetime.utcnow().isoformat(),
                "endpoint": endpoint,
                "method": method,
                "duration_ms": duration_ms,
                "correlation_id": correlation_id,
                "very_slow": duration_ms > 5000
            })

        # Track recent requests
        self.recent_requests.append({
            "timestamp": datetime.utcnow().isoformat(),
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "correlation_id": correlation_id
        })

    def record_ws_event(self, event_type: str, group_id: str, user_id: str,
                       connection_count: int):
        """Record a WebSocket connection event."""
        self.ws_events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,  # "connected" or "disconnected"
            "group_id": group_id,
            "user_id": user_id,
            "connection_count": connection_count
        })

    def get_uptime_seconds(self) -> float:
        """Get application uptime in seconds."""
        return time.time() - self.start_time

    def get_average_response_time(self) -> float:
        """Get average response time in milliseconds."""
        if self.request_count == 0:
            return 0.0
        return self.total_response_time / self.request_count

    def get_error_rate(self) -> float:
        """Get error rate as percentage."""
        if self.request_count == 0:
            return 0.0
        return (self.error_count / self.request_count) * 100

    def get_requests_per_minute(self) -> float:
        """Get average requests per minute."""
        uptime_minutes = self.get_uptime_seconds() / 60
        if uptime_minutes == 0:
            return 0.0
        return self.request_count / uptime_minutes


# Global metrics collector instance
metrics_collector = MetricsCollector()


class DashboardService:
    """Service for collecting and formatting dashboard metrics."""

    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.logger = get_logger(__name__)

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """
        Collect all dashboard metrics.

        Returns comprehensive technical data for monitoring and troubleshooting.
        """
        try:
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "system": await self._get_system_metrics(),
                "database": await self._get_database_metrics(),
                "websockets": self._get_websocket_metrics(),
                "performance": self._get_performance_metrics(),
                "endpoints": self._get_endpoint_metrics(),
                "recent_activity": self._get_recent_activity(),
            }
        except Exception as e:
            self.logger.error("dashboard_data_collection_failed", error=str(e), exc_info=True)
            raise

    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Get system health and resource metrics."""
        uptime_seconds = metrics_collector.get_uptime_seconds()

        # Try to get system resources, fallback gracefully if not available
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)

            system_memory = psutil.virtual_memory()

            resources = {
                "process_memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "process_memory_percent": round(process.memory_percent(), 2),
                "process_cpu_percent": round(cpu_percent, 2),
                "system_memory_percent": round(system_memory.percent, 2),
                "system_memory_available_mb": round(system_memory.available / 1024 / 1024, 2),
            }
        except Exception as e:
            self.logger.warning("system_resources_unavailable", error=str(e))
            resources = {
                "error": "System resource metrics unavailable"
            }

        # Check MongoDB health (using Message model - Group model removed)
        try:
            # Simple query to verify MongoDB is responsive
            await Message.find_one()
            mongodb_status = "connected"
            mongodb_healthy = True
        except Exception as e:
            self.logger.error("mongodb_health_check_failed", error=str(e))
            mongodb_status = f"error: {str(e)}"
            mongodb_healthy = False

        return {
            "api_status": "running",
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_formatted": self._format_uptime(uptime_seconds),
            "mongodb_status": mongodb_status,
            "mongodb_healthy": mongodb_healthy,
            "resources": resources,
        }

    async def _get_database_metrics(self) -> Dict[str, Any]:
        """
        Get database statistics and growth metrics.

        NOTE: Group stats removed - groups now managed by Auth-API.
        Only message stats available from MongoDB.
        """
        try:
            # Total counts (messages only - groups in Auth-API)
            total_messages = await Message.count()
            active_messages = await Message.find(Message.is_deleted == False).count()
            deleted_messages = total_messages - active_messages

            # Recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(hours=24)
            recent_messages = await Message.find(Message.created_at >= yesterday).count()

            # Most active groups (by message count)
            top_groups = await self._get_top_active_groups(limit=10)

            # Count unique groups from messages
            unique_groups = await Message.distinct("group_id")
            total_groups = len(unique_groups)

            # Average messages per group
            avg_messages_per_group = round(total_messages / total_groups, 2) if total_groups > 0 else 0

            return {
                "total_groups": f"{total_groups} (from messages)",  # Groups counted from messages, not Auth-API
                "total_messages": total_messages,
                "active_messages": active_messages,
                "deleted_messages": deleted_messages,
                "deletion_rate_percent": round((deleted_messages / total_messages * 100), 2) if total_messages > 0 else 0,
                "avg_messages_per_group": avg_messages_per_group,
                "last_24h": {
                    "new_groups": "N/A (Auth-API)",  # Can't track new groups without Auth-API integration
                    "new_messages": recent_messages,
                },
                "top_active_groups": top_groups,
            }
        except Exception as e:
            self.logger.error("database_metrics_failed", error=str(e), exc_info=True)
            return {"error": str(e)}

    async def _get_top_active_groups(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most active groups by message count.

        Uses denormalized group_name from Message model (no Auth-API call needed).
        """
        try:
            # Aggregate messages by group
            pipeline = [
                {"$match": {"is_deleted": False}},
                {"$group": {
                    "_id": "$group_id",
                    "group_name": {"$first": "$group_name"},  # Get group_name from denormalized field
                    "message_count": {"$sum": 1},
                    "last_message": {"$max": "$created_at"}
                }},
                {"$sort": {"message_count": -1}},
                {"$limit": limit}
            ]

            results = await Message.aggregate(pipeline).to_list()

            # Format results
            enriched = []
            for result in results:
                enriched.append({
                    "group_id": str(result["_id"]),
                    "group_name": result.get("group_name", "Unknown"),  # From denormalized field
                    "message_count": result["message_count"],
                    "last_message": result["last_message"].isoformat() if result.get("last_message") else None,
                })

            return enriched
        except Exception as e:
            self.logger.error("top_groups_aggregation_failed", error=str(e), exc_info=True)
            return []

    def _get_websocket_metrics(self) -> Dict[str, Any]:
        """Get real-time WebSocket connection statistics."""
        connections = self.connection_manager.active_connections

        total_connections = sum(len(group_conns) for group_conns in connections.values())
        active_groups = len(connections)

        # Per-group breakdown
        group_connections = []
        for group_id, group_conns in connections.items():
            group_connections.append({
                "group_id": group_id,
                "connection_count": len(group_conns),
            })

        # Sort by connection count
        group_connections.sort(key=lambda x: x["connection_count"], reverse=True)

        # Recent WebSocket events
        recent_events = list(metrics_collector.ws_events)

        return {
            "total_active_connections": total_connections,
            "groups_with_connections": active_groups,
            "connections_per_group": group_connections,
            "recent_events": recent_events[-20:],  # Last 20 events
        }

    def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance statistics."""
        return {
            "total_requests": metrics_collector.request_count,
            "total_errors": metrics_collector.error_count,
            "error_rate_percent": round(metrics_collector.get_error_rate(), 2),
            "average_response_time_ms": round(metrics_collector.get_average_response_time(), 2),
            "requests_per_minute": round(metrics_collector.get_requests_per_minute(), 2),
            "slow_requests_count": len(metrics_collector.slow_requests),
            "very_slow_requests_count": sum(1 for req in metrics_collector.slow_requests if req.get("very_slow")),
            "recent_slow_requests": list(metrics_collector.slow_requests)[-10:],  # Last 10 slow requests
        }

    def _get_endpoint_metrics(self) -> List[Dict[str, Any]]:
        """Get per-endpoint statistics."""
        endpoint_list = []

        for endpoint, stats in metrics_collector.endpoint_stats.items():
            avg_time = stats["total_time"] / stats["count"] if stats["count"] > 0 else 0
            error_rate = (stats["errors"] / stats["count"] * 100) if stats["count"] > 0 else 0

            endpoint_list.append({
                "endpoint": endpoint,
                "request_count": stats["count"],
                "error_count": stats["errors"],
                "error_rate_percent": round(error_rate, 2),
                "avg_response_time_ms": round(avg_time, 2),
            })

        # Sort by request count
        endpoint_list.sort(key=lambda x: x["request_count"], reverse=True)

        return endpoint_list

    def _get_recent_activity(self) -> Dict[str, Any]:
        """Get recent requests and errors."""
        return {
            "recent_requests": list(metrics_collector.recent_requests)[-20:],  # Last 20 requests
            "recent_errors": list(metrics_collector.recent_errors)[-20:],      # Last 20 errors
        }

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime as human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{secs}s")

        return " ".join(parts)
