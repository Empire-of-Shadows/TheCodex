"""
Health Endpoint Module for TheCodex Bot
Provides HTTP endpoint for centralized health monitoring

Port: 50002 (as defined in HealthCheck/README.md)
"""

import http.server
import socketserver
import threading
import time
import logging
import json

logger = logging.getLogger(__name__)

_health_server = None


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class HealthCheckHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for health check requests"""

    # Class variables to store bot state
    bot_instance = None
    db_manager = None

    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Build health response with bot-specific details
            response = {
                "status": "healthy",
                "timestamp": time.time(),
                "bot": "TheCodex",
                "service": "Discord Guide & FAQ Bot"
            }

            # Add Discord connection status if bot is available
            if self.bot_instance:
                try:
                    response["discord_connected"] = self.bot_instance.is_ready()
                    response["guilds"] = len(self.bot_instance.guilds) if hasattr(self.bot_instance, 'guilds') else 0
                    response["latency_ms"] = round(self.bot_instance.latency * 1000, 2) if hasattr(self.bot_instance, 'latency') else None
                except Exception as e:
                    logger.warning(f"Failed to get bot status: {e}")
                    response["discord_connected"] = False

            # Add database connection status if available
            if self.db_manager:
                try:
                    # Check if db_manager has a connection check method
                    if hasattr(self.db_manager, 'is_connected'):
                        response["database_connected"] = self.db_manager.is_connected()
                    else:
                        response["database_connected"] = True  # Assume connected if manager exists
                except Exception as e:
                    logger.warning(f"Failed to get database status: {e}")
                    response["database_connected"] = False

            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Disable default logging to reduce noise"""
        pass


def stop_health_server():
    """Shut down the health check server if running."""
    global _health_server
    if _health_server:
        _health_server.shutdown()
        _health_server.server_close()
        _health_server = None
        logger.info("Health check server stopped")


def initialize_health_server(port=50002, bot=None, db_manager=None):
    """
    Initialize the health server in a background thread

    Args:
        port (int): Port to listen on (default: 50002)
        bot: Discord bot instance (optional)
        db_manager: Database manager instance (optional)

    Returns:
        threading.Thread: The health server thread
    """
    global _health_server

    HealthCheckHandler.bot_instance = bot
    HealthCheckHandler.db_manager = db_manager

    try:
        _health_server = ReusableTCPServer(("0.0.0.0", port), HealthCheckHandler)
    except Exception as e:
        logger.error(f"Failed to start health server on port {port}: {e}")
        return None

    health_thread = threading.Thread(target=_health_server.serve_forever, daemon=True, name="HealthCheckServer")
    health_thread.start()
    logger.info(f"Health check server running on port {port}")
    return health_thread
