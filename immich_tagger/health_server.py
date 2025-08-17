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
        """Health check endpoint with multi-library support."""
        try:
            # Save current library context
            original_index = self.processor.immich_client.current_library_index
            
            # Test connection for all libraries
            library_statuses = {}
            overall_healthy = True
            
            for i, library_config in enumerate(self.processor.immich_client.library_configs):
                library_name = library_config["name"]
                try:
                    # Switch to this library and test connection
                    self.processor.immich_client.switch_to_library(i)
                    connection_ok = self.processor.test_connection()
                    
                    # Get user info
                    user_info = self.processor.immich_client.get_current_user_info()
                    
                    library_statuses[library_name] = {
                        "status": "healthy" if connection_ok else "unhealthy",
                        "user": {
                            "name": user_info["name"],
                            "email": user_info["email"]
                        },
                        "metrics": self.processor.library_metrics.get(library_name, {})
                    }
                    
                    if not connection_ok:
                        overall_healthy = False
                        
                except Exception as e:
                    library_statuses[library_name] = {
                        "status": "error",
                        "error": str(e),
                        "metrics": {}
                    }
                    overall_healthy = False
            
            # Restore original library without logging
            self.processor.immich_client._switch_to_library_silent(original_index)
            
            # Get global metrics
            global_metrics = self.processor.get_metrics()
            
            health_status = HealthStatus(
                status="healthy" if overall_healthy else "unhealthy",
                metrics={
                    "libraries": library_statuses,
                    "global": global_metrics,
                    "total_libraries": len(self.processor.immich_client.library_configs)
                }
            )
            
            return web.json_response(
                health_status.dict(),
                status=200 if overall_healthy else 503
            )
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
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
            self.logger.error(f"Metrics retrieval failed: {e}")
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
        
        self.logger.info(f"Health server started on 0.0.0.0:{settings.health_port}")
        
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
