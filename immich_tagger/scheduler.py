"""
Scheduler for continuous operation of the Immich Auto-Tagger.
"""

import asyncio
import time
from datetime import datetime
from typing import Optional
from croniter import croniter
import pytz

from .config import settings
from .logging import get_logger
from .processor import ImmichAutoTagger


class Scheduler:
    """Scheduler for running the auto-tagger at specified intervals."""
    
    def __init__(self):
        self.logger = get_logger("scheduler")
        self.processor = ImmichAutoTagger()
        self.running = False
        self.timezone = pytz.timezone(settings.timezone)
        
    def _get_next_run_time(self) -> datetime:
        """Get the next scheduled run time based on cron expression."""
        now = datetime.now(self.timezone)
        cron = croniter(settings.cron_schedule, now)
        return cron.get_next(datetime)
    
    def _should_run_now(self) -> bool:
        """Check if it's time to run based on the cron schedule."""
        now = datetime.now(self.timezone)
        next_run = self._get_next_run_time()
        
        # If next run time is in the past, we should run now
        return now >= next_run
    
    async def _run_processing_cycle(self):
        """Run a single processing cycle."""
        try:
            self.logger.info("Starting scheduled processing cycle")
            
            # Run the processor
            await self.processor.run_continuous()
            
            self.logger.info("Completed scheduled processing cycle")
            
        except Exception as e:
            self.logger.error("Error during scheduled processing cycle", error=str(e))
    
    async def _scheduler_loop(self):
        """Main scheduler loop."""
        self.logger.info(
            "Starting scheduler",
            cron_schedule=settings.cron_schedule,
            timezone=settings.timezone
        )
        
        while self.running:
            try:
                if self._should_run_now():
                    await self._run_processing_cycle()
                    
                    # Calculate next run time
                    next_run = self._get_next_run_time()
                    self.logger.info(
                        "Next scheduled run",
                        next_run=next_run.isoformat()
                    )
                
                # Sleep for a minute before checking again
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error("Error in scheduler loop", error=str(e))
                await asyncio.sleep(60)  # Wait before retrying
    
    async def start(self):
        """Start the scheduler."""
        if not settings.enable_scheduler:
            self.logger.info("Scheduler disabled, running single cycle")
            await self._run_processing_cycle()
            return
        
        self.running = True
        
        # Show initial schedule
        next_run = self._get_next_run_time()
        self.logger.info(
            "Scheduler started",
            cron_schedule=settings.cron_schedule,
            timezone=settings.timezone,
            next_run=next_run.isoformat()
        )
        
        await self._scheduler_loop()
    
    def stop(self):
        """Stop the scheduler."""
        self.logger.info("Stopping scheduler")
        self.running = False


async def run_scheduler():
    """Run the scheduler."""
    scheduler = Scheduler()
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        scheduler.stop()
        print("\nScheduler stopped by user")


if __name__ == "__main__":
    asyncio.run(run_scheduler())
