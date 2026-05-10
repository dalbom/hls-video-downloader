import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Thread, Timer
from urllib.parse import urljoin

import requests
from flask import Flask, jsonify, render_template, request, send_file

# PyInstaller 번들 지원
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    FFMPEG_BIN = str(BASE_DIR / "ffmpeg" / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg"))
else:
    BASE_DIR = Path(__file__).parent
    FFMPEG_BIN = "ffmpeg"

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

HOST = "127.0.0.1"
DEFAULT_PORT = 5000
DIRECT_MEDIA_RANGE_SIZE = 1 * 1024 * 1024

DOWNLOAD_DIR = Path.home() / "Downloads" / "HLS-Downloader"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 진행 중인 작업 상태
jobs = {}
# 취소 요청된 job_id 집합
cancelled_jobs = set()


def request_headers(referer_url=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    if referer_url:
        headers["Referer"] = referer_url
    return headers


def fetch_page(url, referer_url=None):
    """페이지 HTML 소스를 가져온다."""
    headers = request_headers(referer_url)
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def normalize_url(url, page_url):
    if url.startswith("//"):
        return "https:" + url
    if not url.startswith("http"):
        return urljoin(page_url, url)
    return url


def find_m3u8_urls(html, page_url):
    """HTML에서 m3u8/HLS URL을 찾는다."""
    # 1단계: 확실한 패턴부터 (m3u8, mpegURL 명시)
    patterns = [
        r'["\']([^"\']*\.m3u8[^"\']*)["\']',
        r'source\s+src=["\']([^"\']+)["\'].*?application/x-mpegURL',
        r'file\s*:\s*["\']([^"\']+)["\']',
    ]
    urls = []
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            url = match.group(1)
            urls.append(normalize_url(url, page_url))

    # 2단계: mpegURL type이 지정된 source 태그에서 확장자 무관하게 추출
    for match in re.finditer(
        r'<source\s+[^>]*src=["\']([^"\']+)["\'][^>]*type=["\']application/x-mpegURL["\']',
        html, re.IGNORECASE
    ):
        url = match.group(1)
        urls.append(normalize_url(url, page_url))
    # type이 src보다 앞에 오는 경우
    for match in re.finditer(
        r'<source\s+[^>]*type=["\']application/x-mpegURL["\'][^>]*src=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    ):
        url = match.group(1)
        urls.append(normalize_url(url, page_url))

    # 중복 제거, 순서 유지
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def find_mp4_urls(html, page_url):
    patterns = [
        r'<source\s+[^>]*src=["\']([^"\']+\.mp4[^"\']*)["\']',
        r'<video\s+[^>]*src=["\']([^"\']+\.mp4[^"\']*)["\']',
        r'["\']([^"\']*\.mp4[^"\']*)["\']',
    ]
    urls = []
    for pattern in patterns:
        for match in re.finditer(pattern, html, re.IGNORECASE):
            urls.append(normalize_url(match.group(1), page_url))

    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def find_iframe_urls(html, page_url):
    urls = []
    for match in re.finditer(r'<iframe\s+[^>]*src=["\']([^"\']+)["\']', html, re.IGNORECASE):
        urls.append(normalize_url(match.group(1), page_url))

    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def discover_media_sources(page_url, max_iframes=5):
    html = fetch_page(page_url)
    m3u8_urls = [(url, page_url) for url in find_m3u8_urls(html, page_url)]
    mp4_urls = [(url, page_url) for url in find_mp4_urls(html, page_url)]

    for iframe_url in find_iframe_urls(html, page_url)[:max_iframes]:
        try:
            iframe_html = fetch_page(iframe_url, referer_url=page_url)
        except Exception:
            continue
        m3u8_urls.extend((url, iframe_url) for url in find_m3u8_urls(iframe_html, iframe_url))
        mp4_urls.extend((url, iframe_url) for url in find_mp4_urls(iframe_html, iframe_url))

    def dedupe(pairs):
        seen = set()
        unique = []
        for url, referer_url in pairs:
            if url not in seen:
                seen.add(url)
                unique.append((url, referer_url))
        return unique

    return dedupe(m3u8_urls), dedupe(mp4_urls)


def output_name_for_job(job_id, index, total):
    if total > 1:
        return f"video_{job_id}_{index:03d}.mp4"
    return f"video_{job_id}.mp4"


def preferred_media_sources(m3u8_sources, mp4_sources):
    if m3u8_sources:
        return [("hls", url, referer_url) for url, referer_url in m3u8_sources]
    return [("mp4", url, referer_url) for url, referer_url in mp4_sources]


def parse_m3u8(content, base_url):
    """m3u8 내용에서 세그먼트 URL 목록을 추출한다."""
    segments = []
    for line in content.strip().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if not line.startswith("http"):
                line = urljoin(base_url, line)
            segments.append(line)
    return segments


def is_master_playlist(content):
    """마스터 플레이리스트인지 확인한다."""
    return "#EXT-X-STREAM-INF" in content


def hls_key_uri(content):
    for line in content.splitlines():
        if not line.startswith("#EXT-X-KEY"):
            continue
        if "METHOD=AES-128" not in line:
            return None
        match = re.search(r'URI="([^"]+)"', line)
        return match.group(1) if match else None
    return None


def is_encrypted_playlist(content):
    return hls_key_uri(content) is not None


def resolve_m3u8(url, referer_url=None, include_url=False):
    """m3u8 URL을 받아 세그먼트 목록을 반환한다. 마스터면 최고 품질 선택."""
    headers = request_headers(referer_url)
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    content = resp.text

    if not content.strip().startswith("#EXTM3U"):
        if include_url:
            return None, [], url
        return None, []

    if is_master_playlist(content):
        # 최고 bandwidth 선택
        best_bw = 0
        best_url = None
        for i, line in enumerate(content.splitlines()):
            if line.startswith("#EXT-X-STREAM-INF"):
                bw_match = re.search(r"BANDWIDTH=(\d+)", line)
                bw = int(bw_match.group(1)) if bw_match else 0
                next_line = content.splitlines()[i + 1].strip()
                if not next_line.startswith("http"):
                    next_line = urljoin(url, next_line)
                if bw >= best_bw:
                    best_bw = bw
                    best_url = next_line
        if best_url:
            return resolve_m3u8(best_url, referer_url=referer_url, include_url=include_url)
        if include_url:
            return None, [], url
        return None, []

    segments = parse_m3u8(content, url)
    if include_url:
        return content, segments, url
    return content, segments


def download_segment(args):
    """세그먼트 하나를 다운로드한다."""
    if len(args) == 4:
        url, filepath, job_id, referer_url = args
    else:
        url, filepath, job_id = args
        referer_url = None
    if job_id in cancelled_jobs:
        return False
    headers = request_headers(referer_url)
    for attempt in range(3):
        if job_id in cancelled_jobs:
            return False
        try:
            resp = requests.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return True
        except Exception:
            if attempt == 2:
                return False
            time.sleep(1)


def content_range_total(content_range):
    if not content_range:
        return None
    match = re.search(r"/(\d+)$", content_range)
    return int(match.group(1)) if match else None


def download_direct_media(job_id, media_url, referer_url, output_path, range_size=DIRECT_MEDIA_RANGE_SIZE):
    job = jobs[job_id]
    start = 0
    total_size = None
    completed_ranges = 0
    bytes_written = 0

    job["total_segments"] = 1
    job["downloaded_segments"] = 0

    with open(output_path, "wb") as f:
        while True:
            if job_id in cancelled_jobs:
                return False

            end = start + range_size - 1
            headers = request_headers(referer_url)
            headers["Range"] = f"bytes={start}-{end}"

            with requests.get(media_url, headers=headers, stream=True, timeout=(10, 60)) as resp:
                if resp.status_code == 416 and bytes_written > 0:
                    break
                resp.raise_for_status()

                status_code = resp.status_code
                if total_size is None:
                    total_size = content_range_total(resp.headers.get("Content-Range"))
                    if total_size:
                        job["total_segments"] = max(1, (total_size + range_size - 1) // range_size)
                if status_code == 200:
                    total_size = int(resp.headers.get("Content-Length") or 0) or total_size

                response_bytes = 0
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if job_id in cancelled_jobs:
                        return False
                    if chunk:
                        f.write(chunk)
                        response_bytes += len(chunk)
                        bytes_written += len(chunk)

            if response_bytes == 0:
                return False

            completed_ranges += 1
            job["downloaded_segments"] = completed_ranges

            if status_code == 200:
                break

            start += response_bytes
            if total_size is not None and start >= total_size:
                break
            if total_size is None and response_bytes < range_size:
                break

    return bytes_written > 0


def has_valid_output(result, output_path):
    return (
        result.returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 0
    )


def ffmpeg_creationflags():
    return subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0


def source_metadata_args(source_url):
    source_value = f"Source URL: {source_url}"
    return [
        "-metadata", f"comment={source_value}",
        "-metadata", f"description={source_value}",
    ]


def apply_source_metadata(output_path, source_url):
    tmp_path = output_path.with_name(f"{output_path.stem}.metadata{output_path.suffix}")
    try:
        cmd = [
            FFMPEG_BIN,
            "-i", str(output_path),
            "-c", "copy",
            *source_metadata_args(source_url),
            str(tmp_path),
            "-y",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=ffmpeg_creationflags(),
        )
        if not has_valid_output(result, tmp_path):
            tmp_path.unlink(missing_ok=True)
            return False
        tmp_path.replace(output_path)
        return True
    except Exception:
        tmp_path.unlink(missing_ok=True)
        return False


def create_local_hls_playlist(content, playlist_url, tmp_dir, segment_count, referer_url):
    key_uri = hls_key_uri(content)
    if not key_uri:
        return None

    key_url = urljoin(playlist_url, key_uri)
    resp = requests.get(key_url, headers=request_headers(referer_url), timeout=30)
    resp.raise_for_status()
    key_path = tmp_dir / "key.bin"
    key_path.write_bytes(resp.content)

    local_lines = []
    segment_index = 0
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#EXT-X-KEY"):
            local_lines.append(re.sub(r'URI="[^"]+"', 'URI="key.bin"', line))
        elif stripped and not stripped.startswith("#"):
            if segment_index >= segment_count:
                continue
            local_lines.append(f"segment_{segment_index:05d}.ts")
            segment_index += 1
        else:
            local_lines.append(line)

    playlist_path = tmp_dir / "local_video.m3u8"
    playlist_path.write_text("\n".join(local_lines) + "\n", encoding="utf-8")
    return playlist_path


def add_completed_file(job, output_name, output_path):
    file_info = {
        "filename": output_name,
        "file_size": output_path.stat().st_size,
    }
    job.setdefault("files", []).append(file_info)
    job["file_size"] = sum(file["file_size"] for file in job["files"])
    job["filename"] = file_info["filename"] if len(job["files"]) == 1 else None
    return file_info


def download_mp4_source(job_id, media_url, media_referer_url, output_path, item_label, source_url):
    job = jobs[job_id]
    job["status"] = f"Downloading video {item_label}..."
    downloaded = download_direct_media(job_id, media_url, media_referer_url, output_path)

    if job_id in cancelled_jobs:
        raise InterruptedError("cancelled")

    if not downloaded or not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("Download failed")

    apply_source_metadata(output_path, source_url)


def download_hls_source(job_id, m3u8_url, media_referer_url, output_path, item_label, source_url):
    job = jobs[job_id]
    job["status"] = f"Analyzing playlist {item_label}..."
    m3u8_content, segments, resolved_m3u8_url = resolve_m3u8(
        m3u8_url,
        referer_url=media_referer_url,
        include_url=True,
    )

    if not segments:
        raise RuntimeError("No video segments found")

    job["total_segments"] = len(segments)
    job["downloaded_segments"] = 0
    encrypted_playlist = is_encrypted_playlist(m3u8_content or "")

    tmp_dir = Path(tempfile.mkdtemp(prefix="hls_"))
    job["tmp_dir"] = str(tmp_dir)

    try:
        job["status"] = f"Downloading segments {item_label}..."
        tasks = []
        for i, seg_url in enumerate(segments):
            ext = ".ts" if encrypted_playlist else (Path(seg_url.split("?")[0]).suffix or ".ts")
            filepath = tmp_dir / f"segment_{i:05d}{ext}"
            tasks.append((seg_url, str(filepath), job_id, media_referer_url))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(download_segment, t): t for t in tasks}
            for future in as_completed(futures):
                if job_id in cancelled_jobs:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("cancelled")
                if not future.result():
                    raise RuntimeError("Segment download failed")
                job["downloaded_segments"] += 1

        if job_id in cancelled_jobs:
            raise InterruptedError("cancelled")

        job["status"] = f"Merging video {item_label}..."
        if encrypted_playlist:
            input_path = create_local_hls_playlist(
                m3u8_content,
                resolved_m3u8_url,
                tmp_dir,
                len(segments),
                media_referer_url,
            )
            input_args = [
                FFMPEG_BIN,
                "-allowed_extensions", "ALL",
                "-i", str(input_path),
            ]
        else:
            concat_file = tmp_dir / "concat.txt"
            with open(concat_file, "w") as f:
                for i in range(len(segments)):
                    ext = Path(segments[i].split("?")[0]).suffix or ".ts"
                    f.write(f"file 'segment_{i:05d}{ext}'\n")
            input_args = [
                FFMPEG_BIN, "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
            ]

        metadata_args = source_metadata_args(source_url)
        cmd = input_args + ["-c", "copy", "-bsf:a", "aac_adtstoasc", *metadata_args, str(output_path), "-y"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                creationflags=ffmpeg_creationflags())

        if not has_valid_output(result, output_path):
            cmd = input_args + ["-c", "copy", *metadata_args, str(output_path), "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                    creationflags=ffmpeg_creationflags())

        if not has_valid_output(result, output_path):
            raise RuntimeError(f"Merge failed: {result.stderr[-500:]}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if job.get("tmp_dir") == str(tmp_dir):
            job.pop("tmp_dir", None)


def process_download(job_id, page_url):
    job = jobs[job_id]

    try:
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        job["download_dir"] = str(DOWNLOAD_DIR)
        job["files"] = []
        job["total_files"] = 0
        job["downloaded_files"] = 0
        job["status"] = "Analyzing page..."

        m3u8_sources, mp4_sources = discover_media_sources(page_url)
        sources = preferred_media_sources(m3u8_sources, mp4_sources)

        if not sources:
            job["status"] = "error"
            job["error"] = "No video URLs found."
            return

        total_files = len(sources)
        job["total_files"] = total_files

        for index, (source_type, media_url, media_referer_url) in enumerate(sources, start=1):
            if job_id in cancelled_jobs:
                raise InterruptedError("cancelled")

            job["current_file"] = index
            item_label = f"{index}/{total_files}"
            output_name = output_name_for_job(job_id, index, total_files)
            output_path = DOWNLOAD_DIR / output_name

            if source_type == "mp4":
                download_mp4_source(job_id, media_url, media_referer_url, output_path, item_label, page_url)
            else:
                download_hls_source(job_id, media_url, media_referer_url, output_path, item_label, page_url)

            add_completed_file(job, output_name, output_path)
            job["downloaded_files"] = index

        job["status"] = "done"

    except InterruptedError:
        job["status"] = "cancelled"
        if "tmp_dir" in job:
            shutil.rmtree(job["tmp_dir"], ignore_errors=True)
            job.pop("tmp_dir", None)
        cancelled_jobs.discard(job_id)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        if "tmp_dir" in job:
            shutil.rmtree(job["tmp_dir"], ignore_errors=True)
            job.pop("tmp_dir", None)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/download", methods=["POST"])
def start_download():
    data = request.json
    page_url = data.get("url", "").strip()
    if not page_url:
        return jsonify({"error": "URL을 입력해주세요."}), 400

    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {
        "status": "starting",
        "total_segments": 0,
        "downloaded_segments": 0,
        "error": None,
        "filename": None,
        "file_size": None,
        "files": [],
        "total_files": 0,
        "downloaded_files": 0,
        "download_dir": str(DOWNLOAD_DIR),
    }

    t = Thread(target=process_download, args=(job_id, page_url), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    return jsonify(job)


@app.route("/api/cancel/<job_id>", methods=["POST"])
def cancel_job(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "작업을 찾을 수 없습니다."}), 404
    cancelled_jobs.add(job_id)
    return jsonify({"ok": True})


@app.route("/api/file/<filename>")
def download_file(filename):
    # path traversal 방지
    safe_name = Path(filename).name
    filepath = DOWNLOAD_DIR / safe_name
    if not filepath.exists():
        return jsonify({"error": "파일을 찾을 수 없습니다."}), 404
    return send_file(filepath, as_attachment=True, download_name=safe_name)


def open_download_location(filepath):
    folder = filepath.parent
    if platform.system() == "Windows":
        os.startfile(folder)
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


@app.route("/api/reveal/<filename>", methods=["POST"])
def reveal_file(filename):
    safe_name = Path(filename).name
    filepath = DOWNLOAD_DIR / safe_name
    if not filepath.exists():
        return jsonify({"error": "?뚯씪??李얠쓣 ???놁뒿?덈떎."}), 404
    try:
        open_download_location(filepath)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/cleanup/<filename>", methods=["DELETE"])
def cleanup_file(filename):
    safe_name = Path(filename).name
    filepath = DOWNLOAD_DIR / safe_name
    if filepath.exists():
        filepath.unlink()

    for job_id, job in list(jobs.items()):
        files = job.get("files") or []
        if files:
            job["files"] = [file for file in files if file.get("filename") != safe_name]
            job["file_size"] = sum(file.get("file_size", 0) for file in job["files"])
            if job.get("filename") == safe_name:
                job["filename"] = job["files"][0]["filename"] if len(job["files"]) == 1 else None
            if not job["files"]:
                del jobs[job_id]
            continue

        if job.get("filename") == safe_name:
            del jobs[job_id]
    return jsonify({"ok": True})


def find_available_port(host=HOST, preferred_port=DEFAULT_PORT):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, preferred_port))
        return preferred_port
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, 0))
            return sock.getsockname()[1]


def app_url(host, port):
    return f"http://{host}:{port}"


def open_browser(host, port):
    webbrowser.open(app_url(host, port))


def run_desktop_app(is_frozen=None):
    if is_frozen is None:
        is_frozen = getattr(sys, "frozen", False)
    port = find_available_port(HOST, DEFAULT_PORT)
    print(f"HLS Video Downloader running at {app_url(HOST, port)}", flush=True)
    if is_frozen:
        Timer(1.5, open_browser, args=(HOST, port)).start()
    app.run(host=HOST, port=port, debug=not is_frozen, use_reloader=False)


if __name__ == "__main__":
    run_desktop_app()
