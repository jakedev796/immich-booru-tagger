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
        self.last_run_time: Optional[datetime] = None
        
    def _get_next_run_time(self) -> datetime:
        """Get the next scheduled run time based on cron expression."""
        now = datetime.now(self.timezone)
        cron = croniter(settings.cron_schedule, now)
        return cron.get_next(datetime)
    
    def _should_run_now(self) -> bool:
        """Check if it's time to run based on the cron schedule."""
        now = datetime.now(self.timezone)
        
        # If we've never run, check if we're past the first scheduled time
        if self.last_run_time is None:
            # Get the most recent scheduled time (previous occurrence)
            cron = croniter(settings.cron_schedule, now)
            last_scheduled = cron.get_prev(datetime)
            
            # If the last scheduled time was within the last 24 hours, we should run
            time_since_scheduled = (now - last_scheduled).total_seconds()
            return time_since_scheduled <= 86400  # 24 hours
        
        # If we have run before, check if there's been a scheduled time since our last run
        cron = croniter(settings.cron_schedule, self.last_run_time)
        next_after_last_run = cron.get_next(datetime)
        
        # If the next scheduled time after our last run is now or in the past, we should run
        return now >= next_after_last_run
    
    async def _run_processing_cycle(self):
        """Run a processing cycle for all libraries."""
        try:
            self.logger.info("🚀 Starting scheduled multi-library processing cycle")
            
            # Update last run time
            self.last_run_time = datetime.now(self.timezone)
            
            total_processed = 0
            total_tags = 0
            library_configs = self.processor.immich_client.library_configs
            
            for i, library_config in enumerate(library_configs):
                library_name = library_config["name"]
                
                try:
                    # Get user info for this library
                    self.processor.immich_client.switch_to_library(i)
                    user_info = self.processor.immich_client.get_current_user_info()
                    
                    self.logger.info(f"🏛️ Processing library '{library_name}' ({i+1}/{len(library_configs)}) - User: {user_info['name']} ({user_info['email']})")
                    
                    # Set current library in processor
                    self.processor.set_current_library(library_name)
                    
                    # Process this library until complete
                    library_start_processed = self.processor.library_metrics.get(library_name, {}).get("processed_assets", 0)
                    library_start_tags = self.processor.library_metrics.get(library_name, {}).get("assigned_tags", 0)
                    
                    while True:
                        cycle_result = self.processor.run_processing_cycle()
                        if not cycle_result:
                            break
                    
                    # Calculate library totals
                    library_processed = self.processor.library_metrics.get(library_name, {}).get("processed_assets", 0) - library_start_processed
                    library_tags = self.processor.library_metrics.get(library_name, {}).get("assigned_tags", 0) - library_start_tags
                    
                    total_processed += library_processed
                    total_tags += library_tags
                    
                    self.logger.info(f"✅ Library '{library_name}' complete: {library_processed} assets processed, {library_tags} tags assigned")
                    
                except Exception as e:
                    self.logger.error(f"❌ Error processing library '{library_name}': {e}")
                    continue
            
            self.logger.info(f"🎉 All libraries processed: {total_processed} total assets, {total_tags} total tags assigned")
            
        except Exception as e:
            self.logger.error(f"❌ Error during scheduled processing cycle: {e}")
    
    async def _scheduler_loop(self):
        """Main scheduler loop."""
        self.logger.info(f"Starting scheduler - Schedule: {settings.cron_schedule}, Timezone: {settings.timezone}")
        
        while self.running:
            try:
                should_run = self._should_run_now()
                self.logger.debug(f"🔍 Should run now: {should_run}")
                
                if should_run:
                    await self._run_processing_cycle()
                    
                    # Calculate next run time
                    next_run = self._get_next_run_time()
                    self.logger.info(f"⏭️  Next scheduled run: {next_run.isoformat()}")
                
                # Sleep for a minute before checking again
                await asyncio.sleep(60)
                
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def start(self):
        """Start the scheduler."""
        if not settings.enable_scheduler:
            self.logger.info("Scheduler disabled, running single continuous processing session")
            await self._run_processing_cycle()
            return
        
        self.running = True
        
        # Show initial schedule
        next_run = self._get_next_run_time()
        self.logger.info(f"⏰ Scheduler started - Schedule: {settings.cron_schedule}, Timezone: {settings.timezone}, Next run: {next_run.isoformat()}")
        
        # Check if we should run immediately (first time or missed schedule)
        if self._should_run_now():
            self.logger.info("🚀 Running immediately (first time or missed schedule)")
            await self._run_processing_cycle()
        
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
