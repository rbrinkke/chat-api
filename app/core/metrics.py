"""
Prometheus metrics for chat-api business operations.

This module defines custom metrics for WebSocket connections, message operations,
and MongoDB performance tracking. These metrics complement the HTTP metrics
provided by prometheus-fastapi-instrumentator.
"""

from prometheus_client import Counter, Gauge, Histogram

# ============================================================================
# WebSocket Metrics
# ============================================================================

websocket_connections_active = Gauge(
    'chat_websocket_connections_active',
    'Number of active WebSocket connections',
    ['group_id']
)

websocket_connections_total = Counter(
    'chat_websocket_connections_total',
    'Total number of WebSocket connections established',
    ['group_id']
)

websocket_disconnections_total = Counter(
    'chat_websocket_disconnections_total',
    'Total number of WebSocket disconnections',
    ['group_id', 'reason']
)

websocket_messages_broadcast_total = Counter(
    'chat_websocket_messages_broadcast_total',
    'Total number of messages broadcast via WebSocket',
    ['group_id']
)

websocket_broadcast_errors_total = Counter(
    'chat_websocket_broadcast_errors_total',
    'Total number of WebSocket broadcast failures',
    ['group_id']
)

# ============================================================================
# Message Operation Metrics
# ============================================================================

messages_created_total = Counter(
    'chat_messages_created_total',
    'Total number of messages created',
    ['group_id']
)

messages_updated_total = Counter(
    'chat_messages_updated_total',
    'Total number of messages updated',
    ['group_id']
)

messages_deleted_total = Counter(
    'chat_messages_deleted_total',
    'Total number of messages soft-deleted',
    ['group_id']
)

message_operation_duration_seconds = Histogram(
    'chat_message_operation_duration_seconds',
    'Duration of message operations in seconds',
    ['operation', 'group_id'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

message_operation_errors_total = Counter(
    'chat_message_operation_errors_total',
    'Total number of message operation errors',
    ['operation', 'error_type']
)

# ============================================================================
# MongoDB Operation Metrics
# ============================================================================

mongodb_operations_total = Counter(
    'chat_mongodb_operations_total',
    'Total number of MongoDB operations',
    ['operation', 'collection', 'status']
)

mongodb_operation_duration_seconds = Histogram(
    'chat_mongodb_operation_duration_seconds',
    'Duration of MongoDB operations in seconds',
    ['operation', 'collection'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

mongodb_connection_pool_active = Gauge(
    'chat_mongodb_connection_pool_active',
    'Number of active MongoDB connections in the pool'
)

mongodb_connection_pool_size = Gauge(
    'chat_mongodb_connection_pool_size',
    'Total size of the MongoDB connection pool'
)

# ============================================================================
# Group Metrics
# ============================================================================

groups_total = Gauge(
    'chat_groups_total',
    'Total number of groups in the database'
)

groups_with_active_connections = Gauge(
    'chat_groups_with_active_connections',
    'Number of groups with at least one active WebSocket connection'
)

# ============================================================================
# Message Storage Metrics
# ============================================================================

messages_stored_total = Gauge(
    'chat_messages_stored_total',
    'Total number of messages stored in the database (not soft-deleted)'
)

messages_deleted_count = Gauge(
    'chat_messages_deleted_count',
    'Total number of soft-deleted messages in the database'
)
