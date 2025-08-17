# Immich Booru-Tagger

A standalone service that processes images/videos from an Immich instance, runs them through anime-oriented tag inference models (WD-14 or DeepDanbooru), and pushes the resulting tags back to Immich via its official API.

## Why?

I have a lot of images in my Immich instance, and I want to tag them with booru styled tags. I don't want to use the Immich UI for this, because it's too slow and clunky (mostly because I have 100k~ images). Because of that, Immich Booru-Tagger was created. If you also use Immich to store booru-style images (anime), this is for you.

## How It Works

Immich Booru-Tagger uses a simple and efficient approach:

1. **Finds Untagged Images**: Uses Immich's metadata search to find image assets with no tags (excludes videos)
2. **Processes in Batches**: Takes ~250 images per cycle and runs AI tagging
3. **Marks as Processed**: Tags each image with `auto:processed` when complete
4. **Self-Filtering**: Tagged images automatically disappear from future searches
5. **Repeats Until Done**: Continues until no untagged images remain

This design is **resumable** (restart anytime), **efficient** (no complex queries), and **self-managing** (no manual checkpoint management needed).

**Note**: Only image assets are processed since WD-14 and DeepDanbooru models cannot analyze videos. Videos are automatically excluded from the search to improve efficiency.

## Failure Handling

The system includes robust failure handling for assets that consistently fail to process:

- **Retry Logic**: Failed assets are retried up to `FAILURE_TIMEOUT` times (default: 3)
- **Permanent Failures**: Assets exceeding the retry limit are marked as permanently failed
- **Smart Filtering**: Permanently failed assets are excluded from future processing cycles
- **Persistent Storage**: Failure data persists across restarts in `processing_failures.json`
- **Management Commands**: View and reset failure tracking via CLI commands
- **Cleanup Script**: Remove permanently failed assets from Immich (typically corrupted files)

**Configuration:**
- Set `FAILURE_TIMEOUT=0` to never retry failed assets (immediate permanent failure)
- Set `FAILURE_TIMEOUT=5` to allow up to 5 retry attempts per asset
- Use `--show-failures` to see which assets are failing and why
- Use `--reset-failures` to give failed assets another chance

### Cleanup Script for Failed Assets

For assets that consistently fail (often due to corruption, unsupported formats, or file system issues), you can use the cleanup script to remove them from Immich entirely:

```bash
# Preview what would be deleted (always run this first!)
python cleanup_failed_assets.py --dry-run

# Interactive cleanup with confirmations
python cleanup_failed_assets.py

# Remove specific failed assets only
python cleanup_failed_assets.py --asset-ids asset-id-1 asset-id-2

# Automated cleanup (use with extreme caution!)
python cleanup_failed_assets.py --force
```

**⚠️ IMPORTANT SAFETY NOTES:**
- **Always use `--dry-run` first** to preview what will be deleted
- **This permanently deletes assets from Immich** - have backups if needed
- Failed assets are typically corrupted, unreadable, or have format issues
- The script only processes assets that are marked as "permanently failed"
- Assets must exist in Immich to be deleted (handles missing assets gracefully)

## Recommended Usage

I highly recommend you run the continuous mode on a computer that is powered by a GPU. Then, after the bulk of the images are tagged, you can run the scheduler mode to keep the tags up to date on almost any PC, since this will be a lot less intensive.

## Features

- **AI-Powered Tagging**: Uses anime image recognition models (WD-14 or DeepDanbooru)
- **Smart Processing**: Automatically finds and processes untagged images (videos excluded)
- **Self-Managing**: Tagged assets are automatically excluded from future processing
- **Natural Batching**: Processes ~250 assets per cycle efficiently
- **Resumable**: Always picks up where it left off, no complex checkpointing needed
- **Health Monitoring**: Built-in health checks and metrics endpoint
- **Docker Support**: Easy deployment with Docker and docker-compose
- **High Performance**: 10+ assets/sec processing speed with robust error handling

## Quick Start

### Prerequisites

- Python 3.11+ or Docker
- Immich instance with API access
- API key with required scopes: `asset.read`, `asset.view/download`, `tag.asset`

### Using Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jakedev796/immich-booru-tagger.git
   cd immich-booru-tagger
   ```

2. **Create environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Configure your environment:**
   ```bash
   # Edit .env file with your Immich settings
   IMMICH_BASE_URL=https://your-immich-server.com
   IMMICH_API_KEY=your-api-key-with-required-scopes
   
   # Optional: Adjust batch size (default 250 works well)
   BATCH_SIZE=250
   ```

4. **Run with docker-compose:**
   ```bash
   docker-compose up -d
   ```

### Using Python

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```bash
   export IMMICH_BASE_URL="https://your-immich-server.com"
   export IMMICH_API_KEY="your-api-key-with-required-scopes"
   ```

3. **Run the service:**
   ```bash
   python -m immich_tagger.main
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `IMMICH_BASE_URL` | Your Immich server URL | Required |
| `IMMICH_API_KEY` | API key with required scopes | Required |
| `CONFIDENCE_THRESHOLD` | Minimum confidence for tag predictions | `0.35` |
| `BATCH_SIZE` | Number of assets to process per batch | `25` |
| `PROCESSED_TAG_NAME` | Tag name to mark processed assets | `auto:processed` |
| `TAGGING_MODEL` | AI model to use (`wd14` or `deepdanbooru`) | `wd14` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `MAX_RETRIES` | Maximum retry attempts for API calls | `3` |
| `RETRY_DELAY` | Base delay between retries (seconds) | `1.0` |
| `REQUEST_TIMEOUT` | HTTP request timeout (seconds) | `30.0` |
| `ENABLE_SCHEDULER` | Enable scheduled processing | `true` |
| `CRON_SCHEDULE` | Cron expression for scheduling | `0 2 * * *` |
| `TIMEZONE` | Timezone for scheduling | `UTC` |
| `TAG_CACHE_TTL` | Tag cache TTL (seconds) | `300` |
| `FAILURE_TIMEOUT` | Max retries for failed assets (0 = never retry) | `3` |

### API Key Scopes

Your Immich API key must have the following scopes:
- `asset.read` - For listing assets and search
- `asset.view/download` - For retrieving image thumbnails
- `tag.asset` - For creating and assigning tags

## Usage

### Command Line Options

```bash
python -m immich_tagger.main [OPTIONS]

Options:
  --mode {single,continuous,scheduler,health-only}  Processing mode (default: continuous)
  --max-cycles INT                        Maximum processing cycles (continuous mode)
  --batch-size INT                        Override batch size from configuration
  --test-connection                       Test connection to Immich and exit
  --progress-status                       Show processing progress and exit
  --reset-progress                        Reset processing progress counters
  --show-failures                         Show failed asset summary and IDs, then exit
  --reset-failures                        Reset all failure tracking and exit
  --reset-failure ASSET_ID                Reset failure tracking for specific asset ID
```

### Processing Modes

- **`continuous`** (default): Continuously process assets until none remain
- **`single`**: Process one batch of assets and exit
- **`scheduler`**: Run on a configurable schedule (e.g., daily at 2 AM)
- **`health-only`**: Only run the health server for monitoring

### Examples

```bash
# Test connection
python -m immich_tagger.main --test-connection

# Check processing progress
python -m immich_tagger.main --progress-status

# Process one batch
python -m immich_tagger.main --mode single

# Continuous processing with max cycles
python -m immich_tagger.main --mode continuous --max-cycles 10

# Reset progress counters (if needed)
python -m immich_tagger.main --reset-progress

# View failed assets
python -m immich_tagger.main --show-failures

# Reset all failure tracking
python -m immich_tagger.main --reset-failures

# Reset failure tracking for specific asset
python -m immich_tagger.main --reset-failure "asset-id-here"

# Clean up failed assets (preview first!)
python cleanup_failed_assets.py --dry-run

# Remove permanently failed assets from Immich  
python cleanup_failed_assets.py

# Override batch size
python -m immich_tagger.main --batch-size 50

# Run with scheduler (daily at 2 AM UTC)
python -m immich_tagger.main --mode scheduler
```

### Scheduling Configuration

When using `scheduler` mode, the service will run automatically based on the configured cron schedule:

```bash
# Environment variables for scheduling
ENABLE_SCHEDULER=true
CRON_SCHEDULE=0 2 * * *  # Daily at 2 AM
TIMEZONE=UTC
```

**Common Cron Schedules:**
- `0 2 * * *` - Daily at 2 AM
- `0 */6 * * *` - Every 6 hours
- `0 0 * * 0` - Weekly on Sunday at midnight
- `0 2 * * 1-5` - Weekdays at 2 AM

The scheduler will:
1. Check for new unprocessed images at the scheduled time
2. Process them in batches
3. Mark them as processed
4. Wait for the next scheduled run


## Health Monitoring

The service provides a health endpoint at `http://localhost:8000/health` with the following endpoints:

- `GET /health` - Health check with connection status
- `GET /metrics` - Processing metrics and system stats
- `GET /` - Service information

### Health Check Response

```json
{
  "status": "healthy",
  "timestamp": "2025-08-15T12:00:00",
  "version": "1.0.0",
  "metrics": {
    "assets_processed": 100,
    "tags_assigned": 500,
    "failures": 2,
    "processing_time": 120.5
  }
}
```

## AI Models

### WD-14 (Waifu Diffusion 1.4)

- **Model**: `SmilingWolf/wd-v1-4-vit-tagger-v2`
- **Specialization**: Anime and manga-style images
- **Tags**: Comprehensive anime character and scene tags
- **Performance**: Fast inference, good accuracy for anime content

### DeepDanbooru

- **Model**: `deepdanbooru/deepdanbooru`
- **Specialization**: Danbooru-style image tagging
- **Tags**: Extensive tag vocabulary
- **Performance**: High accuracy, slightly slower than WD-14

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Immich API    │    │  Auto-Tagger    │    │  AI Models      │
│                 │    │                 │    │                 │
│ • Asset Search  │◄──►│ • Asset Discovery│   │ • WD-14         │
│ • Tag Management│    │ • Image Download │   │ • DeepDanbooru  │
│ • Bulk Tagging  │    │ • Tag Prediction │   │                 │
└─────────────────┘    │ • Tag Assignment│    └─────────────────┘
                       │ • Health Server │
                       └─────────────────┘
```

## Processing Workflow

1. **Asset Discovery**: Query Immich for unprocessed assets
2. **Image Download**: Download thumbnails for processing
3. **Tag Prediction**: Run AI models to predict tags
4. **Tag Filtering**: Apply confidence threshold and blacklist
5. **Tag Creation**: Create missing tags in Immich
6. **Tag Assignment**: Apply tags to assets via bulk API
7. **Mark Processed**: Tag assets as processed to avoid reprocessing

## Performance Considerations

- **Batch Size**: Adjust based on your system resources and API limits
- **Model Selection**: WD-14 is faster, DeepDanbooru is more accurate
- **GPU Usage**: Models will use GPU if available, falling back to CPU
- **API Rate Limiting**: Built-in delays and retry logic to be gentle on Immich

## Troubleshooting

### Common Issues

1. **Connection Failed**
   - Verify `IMMICH_BASE_URL` is correct
   - Check API key has required scopes
   - Test with `--test-connection`

2. **No Assets Processed**
   - Check if assets already have the processed tag
   - Verify API key has `asset.read` scope
   - Check logs for specific errors

3. **Model Loading Issues**
   - Ensure sufficient disk space for model cache
   - Check internet connection for model download
   - Verify PyTorch installation

### Logs

The service uses structured logging. Key log levels:
- `INFO`: Processing progress and metrics
- `DEBUG`: Detailed API calls and model operations
- `ERROR`: Failures and exceptions

## Managing Failed Assets

### Common Causes of Processing Failures

Assets may fail to process for several reasons:

1. **Corrupted Files**: Images with file system corruption or incomplete downloads
2. **Unsupported Formats**: Rare image formats that WD-14 models cannot process
3. **Filesystem Issues**: Permission problems or disk errors
4. **Memory Issues**: Extremely large images that exceed processing limits
5. **Network Issues**: Temporary API failures (these usually retry successfully)

### Workflow for Managing Failed Assets

1. **Monitor Failures**: Use `--show-failures` to see which assets are failing
2. **Investigate**: Check file sizes, formats, and filesystem status in Immich web UI
3. **Decide Action**: 
   - **Fix Issues**: Repair corrupted files, fix permissions, etc.
   - **Reset and Retry**: Use `--reset-failures` after fixing underlying issues
   - **Remove Problem Assets**: Use `cleanup_failed_assets.py` for permanently corrupted files

### Example Cleanup Workflow

```bash
# 1. See what's failing
python -m immich_tagger.main --show-failures

# 2. Preview cleanup (safe to run)
python cleanup_failed_assets.py --dry-run

# 3. Investigate specific assets in Immich web UI
# (Look for file corruption, unusual formats, zero-byte files, etc.)

# 4a. If fixable: reset failures and retry processing
python -m immich_tagger.main --reset-failures

# 4b. If corrupted/unfixable: remove the problem assets
python cleanup_failed_assets.py
```

**💡 Pro Tip**: Failed assets are often a small percentage of your library. Removing them can significantly improve processing efficiency for large libraries (100k+ images).
