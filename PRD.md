## PRD — Immich Auto-Tag Processor (Sidecar Service)

### **Summary**

A standalone service (“auto‑tagger”) that processes images/videos from an Immich instance, runs them through an anime-oriented tag inference model (e.g., WD‑14 or DeepDanbooru), then pushes the resulting tags back to Immich via its official API.

### **Goals**

* Auto-label anime-style assets in Immich without modifying Immich’s core code.
* Tags are stored in Immich’s system and usable in search (e.g., via `/search/random?tagIds=[…]`).
* The process is **idempotent**, incremental, and avoids re-tagging processed assets.

---

### **Functional Requirements**

1. **Authentication & Configuration**

   * Accept `IMMICH_BASE_URL` (e.g., `https://your-immich-server`, `192.168.1.100:3000`) and `IMMICH_API_KEY` (with `asset.read`, `asset.view/download`, and `tag.asset` scopes) via environment variables or config.
   * API key scope requirements:

     * `asset.read` for listing assets and search
     * `asset.view/download` for retrieving previews/originals
     * `tag.asset` for creating and assigning tags
       ([API permissions reference](https://immich.app/docs/api/search-random/) requires `asset.read`; tagging endpoints require `tag.asset`). ([Immich][1])

2. **Asset Discovery (Incremental Processing)**

   * Option A: One-time full run, then tag each processed asset with a special “marker” tag (e.g., `auto:processed`).
   * Use search filters or full listing as needed to identify unprocessed assets.

3. **Asset Download**

   * Download thumbnails or originals via `/api/assets/{id}/download` or `/api/assets/{id}/view` (Immich API) for inference use.

4. **Tagging Engine**

   * Locally run anime tag models (WD‑14 or DeepDanbooru).
   * Return a set of predicted tag names + confidence scores.
   * Filter tags using a confidence threshold (e.g., ≥ 0.35) and curated blacklist.

5. **Immich Tag Integration**

   * **List existing tags**: `GET /api/tags` (**getAllTags**) ([v1.102.3.archive.immich.app][2])
   * **Create new tags**: `POST /api/tags` (**createTag**) ([Immich][3])
   * **Bulk tag assignment**: `POST /api/tags/assets/bulk` (**bulkTagAssets**) with `{ assetIds: [...], tagIds: [...] }` ([Immich][4])
   * Optionally use `POST /api/tags/assets` (**tagAssets**) for single asset cases ([Immich][3])
   * After tagging, apply the “processed” marker to prevent reprocessing.

6. **Logging & Health**

   * Log metrics: number of assets processed, tags assigned, failures.
   * (Optional) Health endpoint (e.g., `/health`) for container orchestration.

---

### **Non-Functional Requirements**

* **Language**: Python (preferred) or Node.js.
* **Deployment**: Docker container build.
* **Batch processing**: Configurable batch size (e.g., 25 assets per run).
* **Retries**: Retry logic for transient API/inference errors.
* **Low interference**: Gentle on Immich API (don't overload with massive batch calls).
* **Performance Focused**: We have about 100k~ images to process, so we need to be efficient.

---

### **Out of Scope**

* No changes to the Immich UI or backend.
* No manual tag editing; tags are managed through Immich frontend or other tools.

---

### **Minimal Workflow (Pseudocode)**

```python
config = load_config()  # IMMICH_BASE_URL, API_KEY, thresholds, batch_size

while True:
    assets = fetch_unprocessed_assets(config)
    if not assets:
        break

    for asset in assets:
        img = download_asset(asset.id, config)
        predicted = run_tagger(img)  # [(tag_name, score), ...]
        tags_to_apply = filter_tags(predicted, threshold=config.threshold)
        existing_tags = get_all_tags(config)
        tagIds = resolve_or_create_tags(tags_to_apply, existing_tags, config)
        bulk_tag_assets([asset.id], tagIds, config)
        mark_asset_processed(asset.id, config)
```

---

### **Relevant Immich API Documentation Links**

* **Search & Random retrieval**: `POST /api/search/random` with filters like `tagIds`, `type`, `size` (\[searchRandom endpoint details]) ([v1.102.3.archive.immich.app][2], [Immich][1], [Immich][4])
* **Tag endpoints**: `getAllTags`, `createTag`, `tagAssets`, `bulkTagAssets` for listing, creating, and applying tags ([Immich][3])
* **General API reference**: Immich API landing page (version 1.138.0) ([Immich][5])

[1]: https://immich.app/docs/api/search-random/?utm_source=chatgpt.com "searchRandom"
[2]: https://v1.102.3.archive.immich.app/docs/api/search-assets/?utm_source=chatgpt.com "searchAssets"
[3]: https://immich.app/docs/api/tag-assets/?utm_source=chatgpt.com "tagAssets"
[4]: https://immich.app/docs/api/bulk-tag-assets/?utm_source=chatgpt.com "bulkTagAssets"
[5]: https://immich.app/docs/api?utm_source=chatgpt.com "Immich API"
