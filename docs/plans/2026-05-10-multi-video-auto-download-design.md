# Multi Video Auto Download Design

## Goal

When a page exposes multiple downloadable videos, the app downloads every selected source automatically and writes the finished MP4 files to `~/Downloads/HLS-Downloader/`.

## Approach

- Keep the current discovery layer: it returns ordered HLS and MP4 source lists with referer URLs.
- Preserve the existing preference for HLS when HLS sources exist; otherwise use MP4 sources. This avoids downloading common HLS/MP4 fallback duplicates.
- Treat one submitted page URL as one batch job. A batch job has `total_files`, `downloaded_files`, and a `files` array.
- Name multi-file outputs as `video_<job_id>_001.mp4`, `video_<job_id>_002.mp4`, and so on. Keep the existing `video_<job_id>.mp4` name for single-file pages.
- Write outputs to `Path.home() / "Downloads" / "HLS-Downloader"`.
- Write the submitted page URL into the MP4 `comment` and `description` metadata fields.
- Update the result UI to show the saved local path and one row per file. The main action opens the saved file location instead of triggering a browser download prompt.

## Error Handling

If discovery finds no sources, keep the current error behavior. If a batch source fails while processing, mark the job as `error` and keep any files already written on disk.

## Testing

Add tests for filename numbering, batch MP4 download behavior, cleanup against `files`, and the template's multi-file result UI hooks.
