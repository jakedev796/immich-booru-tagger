"""
Main entry point for the Immich Auto-Tagger service.
"""

import asyncio
import signal
import sys
import argparse
from typing import Optional
from .processor import ImmichAutoTagger, ProcessorError
from .config import settings
from .logging import setup_logging, get_logger
from .health_server import run_health_server
from .scheduler import Scheduler


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Immich Auto-Tagger - AI-powered image tagging for Immich"
    )
    
    parser.add_argument(
        "--mode",
        choices=["single", "continuous", "scheduler", "health-only"],
        default="continuous",
        help="Processing mode (default: continuous)"
    )
    
    parser.add_argument(
        "--max-cycles",
        type=int,
        help="Maximum number of processing cycles (continuous mode only)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Override batch size from configuration"
    )
    
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test connection to Immich and exit"
    )
    
    return parser.parse_args()


async def run_health_server_async(processor: ImmichAutoTagger):
    """Run the health server asynchronously."""
    try:
        await run_health_server(processor)
    except Exception as e:
        logger = get_logger("main")
        logger.error("Health server failed", error=str(e))


def run_single_cycle(processor: ImmichAutoTagger) -> bool:
    """Run a single processing cycle."""
    logger = get_logger("main")
    logger.info("Running single processing cycle")
    
    try:
        success = processor.run_processing_cycle()
        if success:
            logger.info("Single cycle completed successfully")
        else:
            logger.info("Single cycle completed - no more assets to process")
        return success
    except Exception as e:
        logger.error("Single cycle failed", error=str(e))
        return False


def run_continuous_processing(processor: ImmichAutoTagger, max_cycles: Optional[int] = None):
    """Run continuous processing."""
    logger = get_logger("main")
    logger.info("Starting continuous processing", max_cycles=max_cycles)
    
    try:
        processor.run_continuous_processing(max_cycles=max_cycles)
        logger.info("Continuous processing completed")
    except KeyboardInterrupt:
        logger.info("Continuous processing interrupted by user")
    except Exception as e:
        logger.error("Continuous processing failed", error=str(e))
        raise


async def run_with_health_server(processor: ImmichAutoTagger, mode: str, max_cycles: Optional[int] = None):
    """Run the processor with health server."""
    logger = get_logger("main")
    
    # Start health server in background
    health_task = asyncio.create_task(run_health_server_async(processor))
    
    try:
        if mode == "single":
            # Run single cycle
            success = run_single_cycle(processor)
            if not success:
                logger.info("No assets to process, exiting")
                return
        
        elif mode == "continuous":
            # Run continuous processing
            run_continuous_processing(processor, max_cycles)
        
        elif mode == "scheduler":
            # Run with scheduler
            logger.info("Running in scheduler mode")
            scheduler = Scheduler()
            await scheduler.start()
        
        elif mode == "health-only":
            # Only run health server
            logger.info("Running in health-only mode")
            await health_task
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down")
    finally:
        # Cancel health server
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass


def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    logger = get_logger("main")
    
    # Parse arguments
    args = parse_arguments()
    
    # Override batch size if specified
    if args.batch_size:
        settings.batch_size = args.batch_size
        logger.info("Overriding batch size", batch_size=args.batch_size)
    
    logger.info("Starting Immich Auto-Tagger", mode=args.mode)
    
    try:
        # Initialize processor
        processor = ImmichAutoTagger()
        
        # Test connection if requested
        if args.test_connection:
            logger.info("Testing connection to Immich")
            if processor.test_connection():
                logger.info("Connection test successful")
                return 0
            else:
                logger.error("Connection test failed")
                return 1
        
        # Run the service
        if args.mode == "health-only":
            # Run only health server
            asyncio.run(run_with_health_server(processor, "health-only"))
        else:
            # Run with health server
            asyncio.run(run_with_health_server(processor, args.mode, args.max_cycles))
        
        logger.info("Service completed successfully")
        return 0
        
    except ProcessorError as e:
        logger.error("Processor error", error=str(e))
        return 1
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
        return 0
    except Exception as e:
        logger.error("Unexpected error", error=str(e))
        return 1
    finally:
        # Clean up
        try:
            processor.close()
        except:
            pass


if __name__ == "__main__":
    sys.exit(main())
