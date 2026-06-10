@echo off
chcp 65001 > nul
echo.
echo =====================================================
echo  사내 리조트 잔여객실 통합 수집기 실행 (로컬 모드)
echo =====================================================
echo.

echo [1/5] 리솜 리조트 수집 시작...
cd /d D:\휴양소\resom_crawler
python resom_crawler.py
echo.

echo [2/5] 소노 호텔앤리조트 수집 시작...
cd /d D:\휴양소\sono_crawler
python sono_crawler.py
echo.

echo [3/5] 롯데 리조트 수집 시작...
cd /d D:\휴양소\lotte_crawler
python lotte_crawler.py
echo.

echo [4/5] 한화 리조트 수집 시작...
cd /d D:\휴양소\hanhwa_crawler
python hanhwa_crawler.py
echo.

echo [5/5] 통합 대시보드 HTML 변환 시작...
cd /d D:\휴양소
python convert_to_html.py
echo.

echo =====================================================
echo  모든 수집 및 HTML 취합 완료!
echo  최종 결과 파일: D:\휴양소\resort_availability.html
echo =====================================================
pause
