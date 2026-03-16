import os
import platform
import re
import shutil
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

DOWNLOAD_DIR = Path.home() / "Downloads" / "HLS-Downloader"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 진행 중인 작업 상태
jobs = {}
# 취소 요청된 job_id 집합
cancelled_jobs = set()


def fetch_page(url):
    """페이지 HTML 소스를 가져온다."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


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
            if not url.startswith("http"):
                url = urljoin(page_url, url)
            urls.append(url)

    # 2단계: mpegURL type이 지정된 source 태그에서 확장자 무관하게 추출
    for match in re.finditer(
        r'<source\s+[^>]*src=["\']([^"\']+)["\'][^>]*type=["\']application/x-mpegURL["\']',
        html, re.IGNORECASE
    ):
        url = match.group(1)
        if not url.startswith("http"):
            url = urljoin(page_url, url)
        urls.append(url)
    # type이 src보다 앞에 오는 경우
    for match in re.finditer(
        r'<source\s+[^>]*type=["\']application/x-mpegURL["\'][^>]*src=["\']([^"\']+)["\']',
        html, re.IGNORECASE
    ):
        url = match.group(1)
        if not url.startswith("http"):
            url = urljoin(page_url, url)
        urls.append(url)

    # 중복 제거, 순서 유지
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


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


def resolve_m3u8(url):
    """m3u8 URL을 받아 세그먼트 목록을 반환한다. 마스터면 최고 품질 선택."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    content = resp.text

    if not content.strip().startswith("#EXTM3U"):
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
            return resolve_m3u8(best_url)
        return None, []

    segments = parse_m3u8(content, url)
    return content, segments


def download_segment(args):
    """세그먼트 하나를 다운로드한다."""
    url, filepath, job_id = args
    if job_id in cancelled_jobs:
        return False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
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


def process_download(job_id, page_url):
    """전체 다운로드 프로세스를 실행한다."""
    job = jobs[job_id]

    try:
        # 1. 페이지에서 m3u8 URL 찾기
        job["status"] = "페이지 분석 중..."
        html = fetch_page(page_url)
        m3u8_urls = find_m3u8_urls(html, page_url)

        if not m3u8_urls:
            job["status"] = "error"
            job["error"] = "동영상 URL을 찾을 수 없습니다."
            return

        # 2. m3u8에서 세그먼트 추출
        job["status"] = "플레이리스트 분석 중..."
        m3u8_content = None
        segments = []
        for m3u8_url in m3u8_urls:
            m3u8_content, segments = resolve_m3u8(m3u8_url)
            if segments:
                break

        if not segments:
            job["status"] = "error"
            job["error"] = "세그먼트를 찾을 수 없습니다."
            return

        job["total_segments"] = len(segments)
        job["downloaded_segments"] = 0

        # 3. 임시 디렉토리에 세그먼트 다운로드
        tmp_dir = Path(tempfile.mkdtemp(prefix="hls_"))
        job["tmp_dir"] = str(tmp_dir)

        job["status"] = "세그먼트 다운로드 중..."
        tasks = []
        for i, seg_url in enumerate(segments):
            ext = Path(seg_url.split("?")[0]).suffix or ".ts"
            filepath = tmp_dir / f"segment_{i:05d}{ext}"
            tasks.append((seg_url, str(filepath), job_id))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(download_segment, t): t for t in tasks}
            for future in as_completed(futures):
                if job_id in cancelled_jobs:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise InterruptedError("cancelled")
                result = future.result()
                job["downloaded_segments"] += 1

        if job_id in cancelled_jobs:
            raise InterruptedError("cancelled")

        # 4. ffmpeg로 합치기
        job["status"] = "동영상 병합 중..."

        concat_file = tmp_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for i in range(len(segments)):
                ext = Path(segments[i].split("?")[0]).suffix or ".ts"
                f.write(f"file 'segment_{i:05d}{ext}'\n")

        output_name = f"video_{job_id}.mp4"
        output_path = DOWNLOAD_DIR / output_name

        cmd = [
            FFMPEG_BIN, "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy", "-bsf:a", "aac_adtstoasc",
            str(output_path), "-y"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)

        if result.returncode != 0 and not output_path.exists():
            # bsf 없이 재시도
            cmd = [
                FFMPEG_BIN, "-f", "concat", "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(output_path), "-y"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                    creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)

        if not output_path.exists():
            job["status"] = "error"
            job["error"] = f"병합 실패: {result.stderr[-500:]}"
            return

        # 5. 정리
        shutil.rmtree(tmp_dir, ignore_errors=True)

        file_size = output_path.stat().st_size
        job["status"] = "done"
        job["filename"] = output_name
        job["file_size"] = file_size

    except InterruptedError:
        job["status"] = "cancelled"
        if "tmp_dir" in job:
            shutil.rmtree(job["tmp_dir"], ignore_errors=True)
        cancelled_jobs.discard(job_id)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        if "tmp_dir" in job:
            shutil.rmtree(job["tmp_dir"], ignore_errors=True)


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


@app.route("/api/cleanup/<filename>", methods=["DELETE"])
def cleanup_file(filename):
    safe_name = Path(filename).name
    filepath = DOWNLOAD_DIR / safe_name
    if filepath.exists():
        filepath.unlink()
    if job_id := next((k for k, v in jobs.items() if v.get("filename") == safe_name), None):
        del jobs[job_id]
    return jsonify({"ok": True})


def open_browser():
    webbrowser.open("http://localhost:5000")


if __name__ == "__main__":
    is_frozen = getattr(sys, "frozen", False)
    if is_frozen:
        Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=not is_frozen)
