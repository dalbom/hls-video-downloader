# HLS Video Downloader

[한국어](README.md)

A desktop application for downloading HLS (HTTP Live Streaming) videos.
Enter a video page URL and it will automatically detect the HLS stream, download all segments, and merge them into a single MP4 file.

## Features

- Automatic HLS playlist (m3u8) detection from page URL
- Handles disguised file extensions (.jpg, .shtml, .txt, etc.)
- Master playlist support (auto-selects highest quality)
- Fast segment download with 10 parallel connections
- Real-time progress display
- Download cancellation
- Automatic segment cleanup after merge

## Installation & Usage

### Option 1: Download pre-built binary (Recommended)

No installation required.

1. Download the file for your OS from the [Releases](https://github.com/dalbom/hls-video-downloader/releases) page
   - Windows: `HLS-Downloader-Windows.zip`
   - macOS: `HLS-Downloader-macOS.zip`
2. Extract the archive
3. Run `HLS-Downloader`
4. Your browser will open automatically

Downloaded videos are saved to `~/Downloads/HLS-Downloader/`.

### Option 2: Run from source

Requires Python 3.10+ and FFmpeg.

#### Install Python

- **Windows**: [python.org](https://www.python.org/downloads/) or `winget install Python.Python.3.12`
- **macOS**: `brew install python3`
- **Linux**: `sudo apt install python3 python3-pip`

#### Install FFmpeg

- **Windows**: `winget install Gyan.FFmpeg` or download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) and add to PATH
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

#### Run

```bash
git clone https://github.com/dalbom/hls-video-downloader.git
cd hls-video-downloader
pip install flask requests
python app.py
```

Open http://localhost:5000 in your browser and enter a video page URL.

## How to Use

1. Enter the URL of a page containing a video
2. Click **Download**
3. Monitor progress (cancel anytime)
4. Click **Save File** to download the MP4
5. Optionally click **Delete from Server** to clean up

## Disclaimer

This software is provided solely as a **technical tool** for downloading HLS streams. All legal responsibility arising from the use of this tool lies entirely with the user.

- Downloading or redistributing copyrighted content without authorization from the rights holder may be punishable under applicable laws.
- Users are responsible for reviewing the terms of service and applicable laws before using this tool.
- The developer assumes no liability for any misuse or illegal use of this tool.

## License

[MIT License](LICENSE)
