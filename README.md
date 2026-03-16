# HLS Video Downloader

[English](README_EN.md)

HLS(HTTP Live Streaming) 동영상을 다운로드할 수 있는 데스크톱 애플리케이션입니다.
동영상 페이지 URL을 입력하면 자동으로 HLS 스트림을 감지하고, 세그먼트를 다운로드한 뒤 하나의 MP4 파일로 병합합니다.

## 주요 기능

- 페이지 URL에서 HLS 플레이리스트(m3u8) 자동 감지
- 위장된 확장자(.jpg, .shtml, .txt 등) 자동 처리
- 마스터 플레이리스트 지원 (최고 품질 자동 선택)
- 10개 병렬 다운로드로 빠른 세그먼트 수집
- 실시간 진행률 표시
- 다운로드 취소 기능
- 병합 완료 후 세그먼트 자동 정리

## 설치 및 실행

### 방법 1: 실행파일 다운로드 (권장)

별도의 설치 없이 바로 사용할 수 있습니다.

1. [Releases](https://github.com/dalbom/hls-video-downloader/releases) 페이지에서 OS에 맞는 파일 다운로드
   - Windows: `HLS-Downloader-Windows.zip`
   - macOS: `HLS-Downloader-macOS.zip`
2. 압축 해제
3. `HLS-Downloader` 실행
4. 브라우저가 자동으로 열립니다

다운로드된 동영상은 `~/Downloads/HLS-Downloader/` 폴더에 저장됩니다.

### 방법 2: 소스코드에서 직접 실행

Python 3.10+과 FFmpeg가 필요합니다.

#### Python 설치

- **Windows**: [python.org](https://www.python.org/downloads/) 또는 `winget install Python.Python.3.12`
- **macOS**: `brew install python3`
- **Linux**: `sudo apt install python3 python3-pip`

#### FFmpeg 설치

- **Windows**: `winget install Gyan.FFmpeg` 또는 [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)에서 다운로드 후 PATH에 추가
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

#### 실행

```bash
git clone https://github.com/dalbom/hls-video-downloader.git
cd hls-video-downloader
pip install flask requests
python app.py
```

브라우저에서 http://localhost:5000 접속 후 동영상 페이지 URL을 입력하면 됩니다.

## 사용 방법

1. 동영상이 있는 페이지의 URL을 입력
2. **다운로드** 클릭
3. 진행률 확인 (취소 가능)
4. 완료 후 **파일 저장**으로 MP4 다운로드
5. 필요시 **서버에서 삭제**로 임시 파일 정리

## 면책 조항

이 소프트웨어는 HLS 스트림 다운로드 **기능만을 제공**합니다. 본 도구의 사용으로 발생하는 모든 법적 책임은 전적으로 사용자에게 있습니다.

- 저작권이 있는 콘텐츠를 권리자의 허가 없이 다운로드하거나 재배포하는 행위는 관련 법률에 의해 처벌받을 수 있습니다.
- 사용자는 본 도구를 사용하기 전에 해당 콘텐츠의 이용 약관 및 관련 법률을 확인할 책임이 있습니다.
- 개발자는 본 도구의 오용 또는 불법적 사용에 대해 어떠한 책임도 지지 않습니다.

## 라이선스

[MIT License](LICENSE)
