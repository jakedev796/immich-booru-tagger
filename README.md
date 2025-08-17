# Immich Booru-Tagger

AI-powered image tagging for Immich using anime recognition models (WD-14/DeepDanbooru). Automatically tags your anime/manga images with booru-style tags.

## Quick Start

### Docker (Recommended)
```bash
git clone https://github.com/jakedev796/immich-booru-tagger.git
cd immich-booru-tagger
cp .env.example .env
# Edit .env with your Immich settings
docker-compose up -d
```

### Python
```bash
pip install -r requirements.txt
export IMMICH_BASE_URL="https://your-immich-server.com"
export IMMICH_API_KEY="your-api-key"
python -m immich_tagger.main
```

## How It Works

1. **Finds Untagged Images**: Uses Immich's metadata search to find images with no tags
2. **AI Processing**: Runs ~250 images at a time through WD-14/DeepDanbooru models
3. **Auto-Tagging**: Applies predicted tags with confidence filtering
4. **Self-Managing**: Tagged images disappear from future searches
5. **Repeats**: Continues until no untagged images remain

**Features**: Resumable, efficient, self-managing, GPU-accelerated, multi-library support.

## Configuration

### Essential Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `IMMICH_BASE_URL` | Your Immich server URL | Required |
| `IMMICH_API_KEY` | API key (single library) | Required |
| `IMMICH_API_KEYS` | Multiple API keys (JSON array) | `[]` |
| `CONFIDENCE_THRESHOLD` | Minimum tag confidence | `0.35` |
| `BATCH_SIZE` | Assets per batch | `250` |
| `FAILURE_TIMEOUT` | Max retries for failed assets | `3` |

### Multi-Library Support

```bash
# Multiple users
IMMICH_API_KEYS='["key1", "key2"]'

# Named libraries
IMMICH_LIBRARIES='{"Alice": "key1", "Bob": "key2"}'
```

## Usage

### Processing Modes

```bash
# Test connection
python -m immich_tagger.main --test-connection

# Process one batch
python -m immich_tagger.main --mode single

# Continuous processing (recommended for bulk)
python -m immich_tagger.main --mode continuous

# Scheduled processing (daily at 2 AM)
python -m immich_tagger.main --mode scheduler

# Health monitoring only
python -m immich_tagger.main --mode health-only
```

### Failure Management

```bash
# View failed assets
python -m immich_tagger.main --show-failures

# Reset all failures
python -m immich_tagger.main --reset-failures

# Clean up permanently failed assets
python cleanup_failed_assets.py --dry-run  # Preview
python cleanup_failed_assets.py            # Remove
python cleanup_failed_assets.py --force    # Force removal
```

## Health Monitoring

- **Health Check**: `http://localhost:8000/health`
- **Metrics**: `http://localhost:8000/metrics`
- **Service Info**: `http://localhost:8000/`

## AI Models

- **WD-14**: Fast, anime-optimized (`SmilingWolf/wd-v1-4-vit-tagger-v2`)
- **DeepDanbooru**: High accuracy, extensive tags (`deepdanbooru/deepdanbooru`)

## Performance

- **Speed**: 10+ assets/sec with GPU (Tested on 4080 Super)
- **Efficiency**: 250-asset batches
- **Resumable**: Always picks up where it left off
- **Multi-Library**: Processes all libraries sequentially

## Troubleshooting

### Common Issues

1. **Connection Failed**: Check `IMMICH_BASE_URL` and API key scopes
2. **No Assets Processed**: Verify assets don't already have `auto:processed` tag
3. **Model Issues**: Ensure sufficient disk space and PyTorch installation

### API Key Requirements

Your Immich API key needs these scopes:
- `asset.read` - List and search assets
- `asset.view/download` - Download thumbnails  
- `tag.asset` - Create and assign tags

## Architecture

```
Immich API ←→ Auto-Tagger ←→ AI Models (WD-14/DeepDanbooru)
                ↓
         Health Server (Port 8000)
```

**Recommended**: Use GPU for bulk processing, then switch to scheduler mode for maintenance.
