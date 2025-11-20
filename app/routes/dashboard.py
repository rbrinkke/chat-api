"""
Dashboard API routes - Technical monitoring and troubleshooting endpoints.

Provides comprehensive system metrics for operational monitoring:
- System health and resource usage
- Database statistics and trends
- WebSocket connection monitoring
- Performance metrics and slow request tracking
- Recent activity and error logs
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, HTMLResponse
from typing import Dict, Any

from app.services.dashboard_service import DashboardService
from app.services.connection_manager import manager
from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/api/data", response_model=None)
async def get_dashboard_data() -> Dict[str, Any]:
    """
    Get comprehensive dashboard metrics as JSON.

    Returns:
        Dashboard data including:
        - System health (API, MongoDB, uptime, resources)
        - Database statistics (groups, messages, top active groups)
        - WebSocket metrics (active connections, per-group breakdown)
        - Performance metrics (response times, error rates, slow requests)
        - Endpoint statistics (request counts, error rates per endpoint)
        - Recent activity (requests, errors, WebSocket events)

    Example:
        curl http://localhost:8001/dashboard/api/data
    """
    try:
        dashboard_service = DashboardService(connection_manager=manager)
        data = await dashboard_service.get_dashboard_data()
        return JSONResponse(content=data)
    except Exception as e:
        logger.error("dashboard_data_fetch_failed", error=str(e), exc_info=True)
        return JSONResponse(
            content={"error": "Failed to fetch dashboard data", "detail": str(e)},
            status_code=500
        )


@router.get("", response_class=HTMLResponse)
async def get_dashboard_html():
    """
    Serve the dashboard HTML interface.

    Returns:
        HTML page with real-time dashboard display and auto-refresh.
    """
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat API - Technical Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Courier New', monospace;
            background: #0a0a0a;
            color: #00ff00;
            padding: 20px;
            font-size: 13px;
            line-height: 1.4;
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
        }

        h1 {
            text-align: center;
            color: #00ff00;
            margin-bottom: 10px;
            font-size: 24px;
            text-shadow: 0 0 10px #00ff00;
        }

        .header-info {
            text-align: center;
            color: #888;
            margin-bottom: 20px;
            font-size: 12px;
        }

        .status-bar {
            background: #1a1a1a;
            border: 1px solid #00ff00;
            padding: 10px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
        }

        .status-item {
            margin: 5px 10px;
        }

        .status-label {
            color: #888;
        }

        .status-value {
            color: #00ff00;
            font-weight: bold;
        }

        .status-ok {
            color: #00ff00;
        }

        .status-warning {
            color: #ffaa00;
        }

        .status-error {
            color: #ff0000;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(500px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .panel {
            background: #1a1a1a;
            border: 1px solid #333;
            padding: 15px;
        }

        .panel-title {
            color: #00ff00;
            font-size: 16px;
            margin-bottom: 10px;
            border-bottom: 1px solid #333;
            padding-bottom: 5px;
            text-transform: uppercase;
        }

        .metric-row {
            display: flex;
            justify-content: space-between;
            padding: 5px 0;
            border-bottom: 1px solid #222;
        }

        .metric-label {
            color: #888;
        }

        .metric-value {
            color: #00ff00;
        }

        .metric-value.highlight {
            color: #00ffff;
            font-weight: bold;
        }

        .metric-value.warning {
            color: #ffaa00;
        }

        .metric-value.error {
            color: #ff0000;
        }

        .table-container {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11px;
        }

        th, td {
            text-align: left;
            padding: 5px;
            border-bottom: 1px solid #222;
        }

        th {
            color: #00ff00;
            font-weight: bold;
            position: sticky;
            top: 0;
            background: #1a1a1a;
        }

        td {
            color: #888;
        }

        .log-entry {
            padding: 8px;
            margin: 5px 0;
            background: #111;
            border-left: 3px solid #333;
            font-size: 11px;
        }

        .log-entry.error {
            border-left-color: #ff0000;
            background: #1a0000;
        }

        .log-entry.warning {
            border-left-color: #ffaa00;
        }

        .log-timestamp {
            color: #555;
        }

        .log-message {
            color: #888;
        }

        .log-correlation {
            color: #00ffff;
            font-size: 10px;
        }

        .loading {
            text-align: center;
            color: #888;
            padding: 20px;
        }

        .error-message {
            background: #1a0000;
            border: 1px solid #ff0000;
            color: #ff0000;
            padding: 15px;
            margin: 20px 0;
            text-align: center;
        }

        .refresh-info {
            text-align: center;
            color: #555;
            font-size: 11px;
            margin-top: 20px;
        }

        .ws-connection {
            padding: 5px;
            margin: 3px 0;
            background: #111;
            border-left: 2px solid #00ff00;
        }

        .progress-bar {
            width: 100%;
            height: 10px;
            background: #222;
            margin-top: 5px;
            position: relative;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00ff00, #00aa00);
            transition: width 0.3s ease;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ CHAT API - TECHNICAL DASHBOARD ⚡</h1>
        <div class="header-info">
            Real-time monitoring and troubleshooting interface
        </div>

        <div id="loading" class="loading">
            ⏳ Loading dashboard data...
        </div>

        <div id="error-container"></div>
        <div id="dashboard-content" style="display: none;"></div>

        <div class="refresh-info">
            Auto-refresh: <span id="refresh-countdown">10</span>s | Last update: <span id="last-update">-</span>
        </div>
    </div>

    <script>
        let refreshInterval;
        let countdownInterval;
        let countdown = 10;

        async function fetchDashboardData() {
            try {
                const response = await fetch('/dashboard/api/data');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                const data = await response.json();
                displayDashboard(data);
                clearError();
            } catch (error) {
                displayError(error.message);
            }
        }

        function displayError(message) {
            document.getElementById('loading').style.display = 'none';
            document.getElementById('dashboard-content').style.display = 'none';
            document.getElementById('error-container').innerHTML = `
                <div class="error-message">
                    ❌ ERROR: ${message}<br>
                    <small>Retrying in ${countdown} seconds...</small>
                </div>
            `;
        }

        function clearError() {
            document.getElementById('error-container').innerHTML = '';
            document.getElementById('loading').style.display = 'none';
            document.getElementById('dashboard-content').style.display = 'block';
        }

        function displayDashboard(data) {
            const system = data.system || {};
            const db = data.database || {};
            const ws = data.websockets || {};
            const perf = data.performance || {};
            const endpoints = data.endpoints || [];
            const activity = data.recent_activity || {};

            let html = '';

            // Status Bar
            const apiStatus = system.api_status === 'running' ? 'status-ok' : 'status-error';
            const mongoStatus = system.mongodb_healthy ? 'status-ok' : 'status-error';
            html += `
                <div class="status-bar">
                    <div class="status-item">
                        <span class="status-label">API:</span>
                        <span class="status-value ${apiStatus}">${system.api_status || 'unknown'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">MongoDB:</span>
                        <span class="status-value ${mongoStatus}">${system.mongodb_healthy ? 'CONNECTED' : 'ERROR'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Uptime:</span>
                        <span class="status-value">${system.uptime_formatted || '-'}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Active WS:</span>
                        <span class="status-value">${ws.total_active_connections || 0}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Total Requests:</span>
                        <span class="status-value">${perf.total_requests || 0}</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Error Rate:</span>
                        <span class="status-value ${perf.error_rate_percent > 5 ? 'status-warning' : ''}">${perf.error_rate_percent || 0}%</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Avg Response:</span>
                        <span class="status-value ${perf.average_response_time_ms > 500 ? 'status-warning' : ''}">${perf.average_response_time_ms || 0}ms</span>
                    </div>
                </div>
            `;

            // Main Grid
            html += '<div class="grid">';

            // System Resources
            html += `
                <div class="panel">
                    <div class="panel-title">⚙️ System Resources</div>
                    ${formatMetricRow('Process Memory', system.resources?.process_memory_mb ? `${system.resources.process_memory_mb} MB` : 'N/A')}
                    ${formatMetricRow('Memory Usage', system.resources?.process_memory_percent ? `${system.resources.process_memory_percent}%` : 'N/A')}
                    ${formatMetricRow('CPU Usage', system.resources?.process_cpu_percent ? `${system.resources.process_cpu_percent}%` : 'N/A')}
                    ${formatMetricRow('System Memory', system.resources?.system_memory_percent ? `${system.resources.system_memory_percent}%` : 'N/A')}
                    ${formatMetricRow('Available Memory', system.resources?.system_memory_available_mb ? `${system.resources.system_memory_available_mb} MB` : 'N/A')}
                </div>
            `;

            // Database Stats
            html += `
                <div class="panel">
                    <div class="panel-title">💾 Database Statistics</div>
                    ${formatMetricRow('Total Groups', db.total_groups || 0, 'highlight')}
                    ${formatMetricRow('Total Messages', db.total_messages || 0, 'highlight')}
                    ${formatMetricRow('Active Messages', db.active_messages || 0)}
                    ${formatMetricRow('Deleted Messages', db.deleted_messages || 0)}
                    ${formatMetricRow('Deletion Rate', `${db.deletion_rate_percent || 0}%`)}
                    ${formatMetricRow('Avg Messages/Group', db.avg_messages_per_group || 0)}
                    ${formatMetricRow('New Groups (24h)', db.last_24h?.new_groups || 0)}
                    ${formatMetricRow('New Messages (24h)', db.last_24h?.new_messages || 0)}
                </div>
            `;

            // WebSocket Metrics
            html += `
                <div class="panel">
                    <div class="panel-title">🔌 WebSocket Connections</div>
                    ${formatMetricRow('Total Active', ws.total_active_connections || 0, 'highlight')}
                    ${formatMetricRow('Groups with Connections', ws.groups_with_connections || 0)}
                    <div style="margin-top: 10px;">
                        <div style="color: #888; margin-bottom: 5px;">Per-Group Breakdown:</div>
                        ${(ws.connections_per_group || []).slice(0, 10).map(g => `
                            <div class="ws-connection">
                                Group: <span style="color: #00ffff;">${g.conversation_id}</span> →
                                <span style="color: #00ff00;">${g.connection_count} connections</span>
                            </div>
                        `).join('') || '<div style="color: #555;">No active connections</div>'}
                    </div>
                </div>
            `;

            // Performance Metrics
            const slowWarning = perf.slow_requests_count > 10 ? 'warning' : '';
            html += `
                <div class="panel">
                    <div class="panel-title">⚡ Performance Metrics</div>
                    ${formatMetricRow('Requests/Minute', (perf.requests_per_minute || 0).toFixed(2))}
                    ${formatMetricRow('Avg Response Time', `${perf.average_response_time_ms || 0}ms`, perf.average_response_time_ms > 500 ? 'warning' : '')}
                    ${formatMetricRow('Slow Requests (>1s)', perf.slow_requests_count || 0, slowWarning)}
                    ${formatMetricRow('Very Slow (>5s)', perf.very_slow_requests_count || 0, perf.very_slow_requests_count > 0 ? 'error' : '')}
                    ${formatMetricRow('Total Errors', perf.total_errors || 0, perf.total_errors > 0 ? 'warning' : '')}
                </div>
            `;

            html += '</div>'; // End grid

            // Top Active Groups
            if (db.top_active_groups && db.top_active_groups.length > 0) {
                html += `
                    <div class="panel" style="margin-bottom: 20px;">
                        <div class="panel-title">🔥 Most Active Groups</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Group Name</th>
                                        <th>Group ID</th>
                                        <th>Messages</th>
                                        <th>Last Activity</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${db.top_active_groups.map(g => `
                                        <tr>
                                            <td style="color: #00ffff; font-size: 10px;">${g.conversation_id}</td>
                                            <td style="color: #ffaa00;">${g.message_count}</td>
                                            <td>${formatTimestamp(g.last_message)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            // Endpoint Statistics
            if (endpoints.length > 0) {
                html += `
                    <div class="panel" style="margin-bottom: 20px;">
                        <div class="panel-title">📊 Endpoint Statistics</div>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Endpoint</th>
                                        <th>Requests</th>
                                        <th>Errors</th>
                                        <th>Error Rate</th>
                                        <th>Avg Time</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${endpoints.slice(0, 15).map(ep => `
                                        <tr>
                                            <td style="color: #00ffff; font-size: 11px;">${ep.endpoint}</td>
                                            <td>${ep.request_count}</td>
                                            <td style="color: ${ep.error_count > 0 ? '#ff0000' : '#888'};">${ep.error_count}</td>
                                            <td style="color: ${ep.error_rate_percent > 5 ? '#ffaa00' : '#888'};">${ep.error_rate_percent}%</td>
                                            <td style="color: ${ep.avg_response_time_ms > 500 ? '#ffaa00' : '#888'};">${ep.avg_response_time_ms}ms</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            // Recent Slow Requests
            if (perf.recent_slow_requests && perf.recent_slow_requests.length > 0) {
                html += `
                    <div class="panel" style="margin-bottom: 20px;">
                        <div class="panel-title">🐌 Recent Slow Requests</div>
                        ${perf.recent_slow_requests.map(req => `
                            <div class="log-entry ${req.very_slow ? 'error' : 'warning'}">
                                <div class="log-timestamp">${formatTimestamp(req.timestamp)}</div>
                                <div class="log-message">
                                    <strong>${req.method} ${req.endpoint}</strong> -
                                    <span style="color: ${req.very_slow ? '#ff0000' : '#ffaa00'};">${req.duration_ms}ms</span>
                                    ${req.very_slow ? ' ⚠️ VERY SLOW' : ''}
                                </div>
                                <div class="log-correlation">Correlation ID: ${req.correlation_id}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Recent Errors
            if (activity.recent_errors && activity.recent_errors.length > 0) {
                html += `
                    <div class="panel" style="margin-bottom: 20px;">
                        <div class="panel-title">❌ Recent Errors</div>
                        ${activity.recent_errors.map(err => `
                            <div class="log-entry error">
                                <div class="log-timestamp">${formatTimestamp(err.timestamp)}</div>
                                <div class="log-message">
                                    <strong>${err.method} ${err.endpoint}</strong> -
                                    Status: <span style="color: #ff0000;">${err.status_code}</span> -
                                    ${err.duration_ms}ms
                                </div>
                                <div class="log-correlation">Correlation ID: ${err.correlation_id}</div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            // Recent WebSocket Events
            if (ws.recent_events && ws.recent_events.length > 0) {
                html += `
                    <div class="panel" style="margin-bottom: 20px;">
                        <div class="panel-title">🔌 Recent WebSocket Events</div>
                        ${ws.recent_events.map(evt => `
                            <div class="log-entry">
                                <div class="log-timestamp">${formatTimestamp(evt.timestamp)}</div>
                                <div class="log-message">
                                    User <span style="color: #00ffff;">${evt.user_id}</span>
                                    <span style="color: ${evt.event_type === 'connected' ? '#00ff00' : '#ffaa00'};">${evt.event_type}</span>
                                    to group <span style="color: #00ffff;">${evt.conversation_id}</span>
                                    (${evt.connection_count} connections)
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            document.getElementById('dashboard-content').innerHTML = html;
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
        }

        function formatMetricRow(label, value, className = '') {
            return `
                <div class="metric-row">
                    <span class="metric-label">${label}:</span>
                    <span class="metric-value ${className}">${value}</span>
                </div>
            `;
        }

        function formatTimestamp(timestamp) {
            if (!timestamp) return '-';
            const date = new Date(timestamp);
            return date.toLocaleTimeString();
        }

        function startRefreshCountdown() {
            countdown = 10;
            countdownInterval = setInterval(() => {
                countdown--;
                document.getElementById('refresh-countdown').textContent = countdown;
                if (countdown <= 0) {
                    countdown = 10;
                }
            }, 1000);
        }

        // Initial load
        fetchDashboardData();
        startRefreshCountdown();

        // Auto-refresh every 10 seconds
        refreshInterval = setInterval(fetchDashboardData, 10000);

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            clearInterval(refreshInterval);
            clearInterval(countdownInterval);
        });
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)
