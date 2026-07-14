FROM python:3.10-slim

# OS 환경 설정 (한글 인코딩 및 headless 구동 목적)
ENV LANG=ko_KR.UTF-8 \
    LANGUAGE=ko_KR:ko \
    LC_ALL=ko_KR.UTF-8 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 필수 시스템 패키지 및 나눔 한글 폰트 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    unzip \
    ca-certificates \
    fonts-nanum \
    locales \
    # Chrome/Selenium 구동 필수 라이브러리
    libglib2.0-0 \
    libnss3 \
    libfontconfig1 \
    libxss1 \
    libasound2 \
    libxtst6 \
    libxi6 \
    && rm -rf /var/lib/apt/lists/*

# 시스템 로케일 한글 설정
RUN echo "ko_KR.UTF-8 UTF-8" > /etc/locale.gen && locale-gen

# Google Chrome Stable 버전 설치 (deb 패키지 직접 다운로드 방식 - apt-key 의존성 없음)
RUN curl -sS -o google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 파이썬 종속성 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium 브라우저 및 시스템 의존성 라이브러리 설치
RUN playwright install chromium \
    && playwright install-deps chromium

# 소스코드 복사
COPY . .

# 실행 스크립트 권한 부여
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
