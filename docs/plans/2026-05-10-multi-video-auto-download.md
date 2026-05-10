# Multi Video Auto Download Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Download every video source from a page automatically and save completed files under `~/Downloads/HLS-Downloader/`.

**Architecture:** The existing discovery functions remain the source of truth. `process_download` becomes a batch coordinator that chooses HLS sources when present, otherwise MP4 sources, then writes one numbered MP4 per source and records all outputs in `job["files"]`.

**Tech Stack:** Flask, requests, FFmpeg, vanilla HTML/CSS/JS, Python unittest.

---

### Task 1: Batch Naming And Selection Tests

**Files:**
- Modify: `tests/test_media_discovery.py`
- Modify: `app.py`

**Step 1: Write failing tests**

Add tests for:
- `video_<job>.mp4` when there is one output.
- `video_<job>_001.mp4` and `video_<job>_012.mp4` for multi-output batches.
- HLS sources are selected when available, otherwise MP4 sources are selected.

**Step 2: Run tests to verify failure**

Run: `python -m unittest tests.test_media_discovery`

**Step 3: Implement minimal helpers**

Add `output_name_for_job` and `preferred_media_sources`.

**Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_media_discovery`

### Task 2: Batch Download Behavior

**Files:**
- Modify: `tests/test_media_discovery.py`
- Modify: `app.py`

**Step 1: Write failing test**

Mock discovery and direct media download. Verify `process_download` calls the downloader for every MP4 source and returns a `files` array with numbered filenames.

**Step 2: Run test to verify failure**

Run: `python -m unittest tests.test_media_discovery`

**Step 3: Implement batch coordinator**

Refactor `process_download` into a loop over preferred sources. Record `files`, `total_files`, `downloaded_files`, `download_dir`, and backward-compatible single-file `filename`/`file_size`.

**Step 4: Run tests to verify pass**

Run: `python -m unittest tests.test_media_discovery`

### Task 3: Result UI

**Files:**
- Modify: `tests/test_template_ui.py`
- Modify: `templates/index.html`

**Step 1: Write failing tests**

Assert the template contains `resultList`, reads `job.files`, and calls `/api/reveal/`.

**Step 2: Run test to verify failure**

Run: `python -m unittest tests.test_template_ui`

**Step 3: Implement UI changes**

Render a file row per completed output. Show the local download directory and use a reveal endpoint as the primary file action.

**Step 4: Run test to verify pass**

Run: `python -m unittest tests.test_template_ui`

### Task 4: Final Verification

Run: `python -m unittest discover tests`

Expected: all tests pass.
