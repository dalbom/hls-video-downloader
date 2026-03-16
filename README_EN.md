# HLS Video Downloader

[한국어](README.md)

A web application for downloading HLS (HTTP Live Streaming) videos.
Enter a video page URL and it will automatically detect the HLS stream, download all segments, and merge them into a single MP4 file.

## Features

- Automatic HLS playlist (m3u8) detection from page URL
- Handles disguised file extensions (.jpg, .shtml, .txt, etc.)
- Master playlist support (auto-selects highest quality)
- Fast segment download with 10 parallel connections
- Real-time progress display
- Download cancellation
- Automatic segment cleanup after merge

## Prerequisites

### Python 3.10+

#### Windows
Install from [python.org](https://www.python.org/downloads/) or use micromamba/conda:
```bash
micromamba create -n hlsdl python=3.12 flask requests -c conda-forge -y
```

#### macOS
```bash
brew install python3
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt install python3 python3-pip
```

### FFmpeg

Required for merging video segments.

#### Windows
Download the essentials build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the `bin` folder to your system PATH.

Or use winget:
```bash
winget install Gyan.FFmpeg
```

#### macOS
```bash
brew install ffmpeg
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt install ffmpeg
```

### Verify Installation
```bash
python --version   # Python 3.10 or higher
ffmpeg -version    # Should print version info
```

## Installation & Usage

```bash
git clone https://github.com/dalbom/hls-video-downloader.git
cd hls-video-downloader
pip install flask requests
python app.py
```

With micromamba:
```bash
git clone https://github.com/dalbom/hls-video-downloader.git
cd hls-video-downloader
micromamba create -n hlsdl python=3.12 flask requests -c conda-forge -y
micromamba run -n hlsdl python app.py
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
