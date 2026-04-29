import os
import time
import re
import requests
import base64
from datetime import datetime, date as date_type
import zoneinfo
KST = zoneinfo.ZoneInfo("Asia/Seoul")
from playwright.sync_api import sync_playwright
import openpyxl

# ── 환경변수 (GitHub Secrets) ──────────────────────────────────
RESOM_ID    = os.getenv("RESOM_ID")
RESOM_PW    = os.getenv("RESOM_PW")
GH_TOKEN    = os.getenv("GH_TOKEN")
GITHUB_REPO = "kelixx-stack/resort-availability"

# ── 수집 설정 ─────────────────────────────────────────────────
MEMBERSHIP      = "EH55801000"
TARGET_REGIONS  = ["덕산", "안면도", "제천"]
TARGET_PYEONG   = []   # 빈 리스트 = 전체 수집


# ──────────────────────────────────────────────────────────────
# 로그인
# ──────────────────────────────────────────────────────────────
def login(page):
    print("로그인 중...")
    page.goto("https://book.resom.co.kr/login?resort=resom")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    page.fill("input[placeholder='아이디를 입력해주세요']", RESOM_ID)
    page.fill("input[placeholder='비밀번호를 입력해주세요']", RESOM_PW)
    page.locator("a.btn.login_btn").click()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    print("로그인 완료 →", page.url)


# ──────────────────────────────────────────────────────────────
# Select 유틸
# ──────────────────────────────────────────────────────────────
def get_options(page, index):
    selects = page.query_selector_all("select")
    options = selects[index].query_selector_all("option")
    result = []
    for opt in options:
        value = opt.get_attribute("value")
        text  = opt.inner_text().strip()
        if value:
            result.append({"label": text, "value": value})
    return result


def select_option(page, index, value):
    selects = page.query_selector_all("select")
    selects[index].select_option(value)
    page.wait_for_timeout(2000)


# ──────────────────────────────────────────────────────────────
# 달력 수집
# ──────────────────────────────────────────────────────────────
def collect_calendar(page, region, pyeong, month):
    results = []
    page.wait_for_timeout(3000)

    target_table = page.query_selector("table")
    all_tds = target_table.query_selector_all("tbody td")

    # td를 날짜 / ul 타입으로 분류
    td_list = []
    for td in all_tds:
        html = td.inner_html().strip()
        text = td.inner_text().strip()
        if "<ul" in html:
            td_list.append({"type": "ul", "td": td})
        else:
            td_list.append({"type": "date", "text": text})

    date_slots = [item["text"] for item in td_list if item["type"] == "date"]
    ul_slots   = [item["td"]   for item in td_list if item["type"] == "ul"]

    print(f"    [디버그] 날짜 슬롯: {len(date_slots)}개, ul 슬롯: {len(ul_slots)}개")

    for i, ul_td in enumerate(ul_slots):
        if i >= len(date_slots):
            break

        date = date_slots[i]
        if not date.isdigit():
            continue

        items = ul_td.query_selector_all("li a")
        for item in items:
            text = item.inner_text().strip()
            cls  = item.get_attribute("class") or ""
            status = "예약가능" if "disabled" in cls else "예약불가"

            match = re.match(r"(.+?)\((.+?)\)\s*-\s*(.+)", text)
            if match:
                # 요일 계산 (월: 2026.05 → 2026, 5)
                WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
                try:
                    y, m = int(month.split(".")[0]), int(month.split(".")[1])
                    weekday = WEEKDAYS[date_type(y, m, int(date)).weekday()]
                except Exception:
                    weekday = ""
                results.append({
                    "수집일시": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                    "월":      month,
                    "일":      int(date),
                    "요일":    weekday,
                    "지역":    region,
                    "평형":    pyeong,
                    "객실타입": match.group(1).strip(),
                    "리조트":  match.group(2).strip(),
                    "상태":    status,
                })

    print(f"    수집: {len(results)}건")
    return results


# ──────────────────────────────────────────────────────────────
# GitHub 업로드
# ──────────────────────────────────────────────────────────────
def upload_to_github(file_path: str, github_filename: str):
    url     = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_filename}"
    headers = {
        "Authorization": f"token {GH_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }

    with open(file_path, "rb") as f:
        content = base64.b64encode(f.read()).decode("utf-8")

    # 같은 파일명이 이미 존재하면 SHA 필요 (덮어쓰기)
    sha      = None
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        sha = response.json()["sha"]

    data = {
        "message": f"자동 업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M')}",
        "content": content,
    }
    if sha:
        data["sha"] = sha

    response = requests.put(url, headers=headers, json=data)
    if response.status_code in [200, 201]:
        print(f"✅ GitHub 업로드 완료: {github_filename}")
    else:
        print(f"❌ GitHub 업로드 실패: {response.status_code} - {response.text}")


# ──────────────────────────────────────────────────────────────
# 엑셀 생성 → GitHub 업로드 (로컬 임시 파일만 사용)
# ──────────────────────────────────────────────────────────────
def save_and_upload(all_data: list):
    # 예약가능만 필터링
    filtered = [row for row in all_data if row["상태"] == "예약가능"]
    print(f"\n예약가능 건수: {len(filtered)} / 전체 수집: {len(all_data)}")

    if not filtered:
        print("⚠️ 예약가능 데이터 없음 - 업로드 생략")
        return

    fields    = ["수집일시", "월", "일", "요일", "지역", "평형", "객실타입", "리조트", "상태"]
    timestamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")

    # 엑셀 생성 (임시 파일 /tmp 에 저장)
    tmp_path = f"/tmp/resom_{timestamp}.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "객실현황"
    ws.append(fields)
    for row in filtered:
        ws.append([row[f] for f in fields])
    wb.save(tmp_path)
    print(f"엑셀 생성 완료: {tmp_path}")

    # GitHub data 폴더에 업로드
    upload_to_github(tmp_path, f"data/resom_{timestamp}.xlsx")


# ──────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────
def main():
    all_data = []

    with sync_playwright() as p:
        # headless=True: GitHub Actions 서버 환경 (화면 없음)
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()

        try:
            # 1. 로그인
            login(page)

            # 2. 예약 페이지 이동
            page.goto("https://book.resom.co.kr/roomReservation?resort=resom")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            # 3. 회원권 선택
            print(f"\n회원권 선택: {MEMBERSHIP}")
            select_option(page, 0, MEMBERSHIP)

            # 4. 지역 / 월 옵션 확인
            region_options = get_options(page, 1)
            print(f"지역 목록: {[r['label'] for r in region_options]}")

            month_options  = get_options(page, 3)
            target_months  = month_options[0:3]   # 당월 + 익월 + 익익월
            print(f"수집 월: {[m['label'] for m in target_months]}")

            # 5. 지역별 순회
            for region in region_options:
                if not any(r in region["label"] for r in TARGET_REGIONS):
                    continue

                print(f"\n{'='*40}")
                print(f"▶ 지역: {region['label']}")
                select_option(page, 1, region["value"])

                pyeong_options = get_options(page, 2)
                print(f"  평형 목록: {[p['label'] for p in pyeong_options]}")

                for pyeong in pyeong_options:
                    if TARGET_PYEONG and not any(p in pyeong["label"] for p in TARGET_PYEONG):
                        continue

                    print(f"  ▶ 평형: {pyeong['label']}")
                    select_option(page, 2, pyeong["value"])

                    for month in target_months:
                        select_option(page, 3, month["value"])
                        page.locator("a.month_selector_btn").click()
                        page.wait_for_timeout(2000)

                        data = collect_calendar(
                            page,
                            region["label"],
                            pyeong["label"],
                            month["label"],
                        )
                        all_data.extend(data)
                        time.sleep(1)

                    time.sleep(1)

            # 6. 엑셀 저장 + GitHub 업로드
            if all_data:
                save_and_upload(all_data)
                print(f"\n🎉 완료! 총 {len(all_data)}건 수집")
            else:
                print("\n⚠️ 수집 데이터 없음 - 달력 구조 재확인 필요")

        except Exception as e:
            print(f"\n❌ 오류: {e}")
            import traceback
            traceback.print_exc()

        finally:
            browser.close()


if __name__ == "__main__":
    main()
