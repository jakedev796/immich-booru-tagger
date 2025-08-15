"""
Health server for monitoring the Immich Auto-Tagger service.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any
from aiohttp import web
from .models import HealthStatus
from .config import settings
from .logging import get_logger


class HealthServer:
    """Simple HTTP server for health checks and metrics."""
    
    def __init__(self, processor):
        self.processor = processor
        self.logger = get_logger("health_server")
        self.app = web.Application()
        self.setup_routes()
    
    def setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get("/health", self.health_handler)
        self.app.router.add_get("/metrics", self.metrics_handler)
        self.app.router.add_get("/", self.root_handler)
    
    async def health_handler(self, request):
        """Health check endpoint."""
        try:
            # Test connection to Immich
            connection_ok = self.processor.test_connection()
            
            # Get current metrics
            metrics = self.processor.get_metrics()
            
            health_status = HealthStatus(
                status="healthy" if connection_ok else "unhealthy",
                metrics=metrics
            )
            
            return web.json_response(
                health_status.dict(),
                status=200 if connection_ok else 503
            )
            
        except Exception as e:
            self.logger.error("Health check failed", error=str(e))
            return web.json_response(
                {"status": "unhealthy", "error": str(e)},
                status=503
            )
    
    async def metrics_handler(self, request):
        """Metrics endpoint."""
        try:
            metrics = self.processor.get_metrics()
            
            # Add additional system metrics
            import psutil
            system_metrics = {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage('/').percent,
            }
            
            metrics.update(system_metrics)
            
            return web.json_response(metrics)
            
        except Exception as e:
            self.logger.error("Metrics retrieval failed", error=str(e))
            return web.json_response(
                {"error": str(e)},
                status=500
            )
    
    async def root_handler(self, request):
        """Root endpoint with service information."""
        info = {
            "service": "Immich Auto-Tagger",
            "version": "1.0.0",
            "endpoints": {
                "/health": "Health check endpoint",
                "/metrics": "Processing metrics",
                "/": "Service information"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return web.json_response(info)
    
    async def start(self):
        """Start the health server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(
            runner,
            "0.0.0.0",
            settings.health_port
        )
        
        await site.start()
        
        self.logger.info(
            "Health server started",
            host="0.0.0.0",
            port=settings.health_port
        )
        
        return runner
    
    async def stop(self, runner):
        """Stop the health server."""
        await runner.cleanup()
        self.logger.info("Health server stopped")


async def run_health_server(processor):
    """Run the health server."""
    server = HealthServer(processor)
    runner = await server.start()
    
    try:
        # Keep the server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await server.stop(runner)
