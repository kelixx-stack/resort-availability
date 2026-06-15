import os
import csv
import time
import json
import urllib.parse
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
import openpyxl

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
RESOM_ID = os.getenv("RESOM_ID")
RESOM_PW = os.getenv("RESOM_PW")

MEMBERSHIP = "EH55801000"
TARGET_REGIONS = ["덕산", "안면도", "제천"]
KEEP_DAYS = 7
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(FOLDER, exist_ok=True)

# Fallback catalog in case selectCondos API response fails to capture
FALLBACK_CATALOG = [
  {
    "condoCd": "1027",
    "condoNm": "스플라스 리솜",
    "bizNm": "덕산",
    "roomTypeList": [
      {"rmTypeCd": "D36", "pyeongTypeCd": "G40", "rmTypeNm": "G40 스테이"},
      {"rmTypeCd": "D54", "pyeongTypeCd": "G50", "rmTypeNm": "G50 스테이"},
      {"rmTypeCd": "D18", "pyeongTypeCd": "S20", "rmTypeNm": "S20 스테이"},
      {"rmTypeCd": "D18Z", "pyeongTypeCd": "S20", "rmTypeNm": "S20 스테이 케어룸"},
      {"rmTypeCd": "D18H", "pyeongTypeCd": "S20", "rmTypeNm": "S20 스테이 클린A"},
      {"rmTypeCd": "D18T", "pyeongTypeCd": "S20", "rmTypeNm": "S20 스테이 클린B"},
      {"rmTypeCd": "D23", "pyeongTypeCd": "S25", "rmTypeNm": "S25 스테이"},
      {"rmTypeCd": "D23H", "pyeongTypeCd": "S25", "rmTypeNm": "S25 스테이 클린A"},
      {"rmTypeCd": "D23T", "pyeongTypeCd": "S25", "rmTypeNm": "S25 스테이 클린B"},
      {"rmTypeCd": "D27", "pyeongTypeCd": "S30", "rmTypeNm": "S30 스테이"},
      {"rmTypeCd": "D27H", "pyeongTypeCd": "S30", "rmTypeNm": "S30 스테이 클린"},
      {"rmTypeCd": "D36P", "pyeongTypeCd": "G40", "rmTypeNm": "G40 플렉스"},
      {"rmTypeCd": "D36C", "pyeongTypeCd": "G40", "rmTypeNm": "G40 플렉스 클린"},
      {"rmTypeCd": "D54C", "pyeongTypeCd": "G50", "rmTypeNm": "G50 플렉스 클린"},
      {"rmTypeCd": "D18C", "pyeongTypeCd": "S20", "rmTypeNm": "S20 플렉스 클린"},
      {"rmTypeCd": "D18CZ", "pyeongTypeCd": "S20", "rmTypeNm": "S20 플렉스 클린 케어룸"},
      {"rmTypeCd": "D23P", "pyeongTypeCd": "S25", "rmTypeNm": "S25 플렉스"},
      {"rmTypeCd": "D23C", "pyeongTypeCd": "S25", "rmTypeNm": "S25 플렉스 클린"},
      {"rmTypeCd": "D27CA", "pyeongTypeCd": "S30", "rmTypeNm": "S30 플렉스 클린A"},
      {"rmTypeCd": "D27PB", "pyeongTypeCd": "S30", "rmTypeNm": "S30 플렉스B"},
      {"rmTypeCd": "D27CB", "pyeongTypeCd": "S30", "rmTypeNm": "S30 플렉스 클린B"},
      {"rmTypeCd": "D27PC", "pyeongTypeCd": "S30", "rmTypeNm": "S30 플렉스C"},
      {"rmTypeCd": "D27CC", "pyeongTypeCd": "S30", "rmTypeNm": "S30 플렉스 클린C"}
    ]
  },
  {
    "condoCd": "1001",
    "condoNm": "아일랜드 리솜",
    "bizNm": "안면도",
    "roomTypeList": [
      {"rmTypeCd": "H36", "pyeongTypeCd": "G40", "rmTypeNm": "G40 타워 콘도"},
      {"rmTypeCd": "H36H", "pyeongTypeCd": "G40", "rmTypeNm": "G40 타워 클린"},
      {"rmTypeCd": "H18", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 콘도"},
      {"rmTypeCd": "H18H", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 클린"},
      {"rmTypeCd": "H18Z", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 콘도 케어룸"},
      {"rmTypeCd": "H24", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 콘도"},
      {"rmTypeCd": "H24H", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 클린"},
      {"rmTypeCd": "H24K", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 키즈"},
      {"rmTypeCd": "H24Z", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 콘도 케어룸"},
      {"rmTypeCd": "H24HZ", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 클린 케어룸"},
      {"rmTypeCd": "H28", "pyeongTypeCd": "S30", "rmTypeNm": "S30 타워 콘도"},
      {"rmTypeCd": "H28H", "pyeongTypeCd": "S30", "rmTypeNm": "S30 타워 클린"},
      {"rmTypeCd": "H28Z", "pyeongTypeCd": "S30", "rmTypeNm": "S30 타워 콘도 케어룸"},
      {"rmTypeCd": "V34", "pyeongTypeCd": "G40", "rmTypeNm": "G40 빌라"},
      {"rmTypeCd": "V56", "pyeongTypeCd": "G50", "rmTypeNm": "G50 빌라 단층"},
      {"rmTypeCd": "V56M", "pyeongTypeCd": "G50", "rmTypeNm": "G50 빌라 멀티"},
      {"rmTypeCd": "V50", "pyeongTypeCd": "G50", "rmTypeNm": "G50 빌라 복층"}
    ]
  },
  {
    "condoCd": "1075",
    "condoNm": "포레스트 리솜",
    "bizNm": "제천",
    "roomTypeList": [
      {"rmTypeCd": "V36H", "pyeongTypeCd": "G40", "rmTypeNm": "G40 빌라 클린"},
      {"rmTypeCd": "V54H", "pyeongTypeCd": "G50", "rmTypeNm": "G50 빌라 클린"},
      {"rmTypeCd": "V24H", "pyeongTypeCd": "S25", "rmTypeNm": "S25 빌라 클린"},
      {"rmTypeCd": "V28H", "pyeongTypeCd": "S30", "rmTypeNm": "S30 빌라 클린"},
      {"rmTypeCd": "R36H", "pyeongTypeCd": "G40", "rmTypeNm": "G40 타워 클린"},
      {"rmTypeCd": "R54C", "pyeongTypeCd": "G50", "rmTypeNm": "G50 타워 콘도"},
      {"rmTypeCd": "R54H", "pyeongTypeCd": "G50", "rmTypeNm": "G50 타워 클린"},
      {"rmTypeCd": "R20H", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 클린"},
      {"rmTypeCd": "R20HK", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 클린 키즈"},
      {"rmTypeCd": "R20HZ", "pyeongTypeCd": "S20", "rmTypeNm": "S20 타워 클린 케어룸"},
      {"rmTypeCd": "R24H", "pyeongTypeCd": "S25", "rmTypeNm": "S25 타워 클린"},
      {"rmTypeCd": "R28H", "pyeongTypeCd": "S30", "rmTypeNm": "S30 타워 클린"}
    ]
  }
]

def build_month_ranges():
    """Build date ranges for current month, next month, and month after next."""
    today = date.today()
    ranges = []
    for i in range(3):
        target_month = today + relativedelta(months=i)
        if i == 0:
            start_date = today
        else:
            start_date = target_month.replace(day=1)
            
        if target_month.month == 12:
            next_month = target_month.replace(year=target_month.year + 1, month=1, day=1)
        else:
            next_month = target_month.replace(month=target_month.month + 1, day=1)
        end_date = next_month - relativedelta(days=1)
        
        ranges.append({
            "displayName": target_month.strftime("%Y.%m"),
            "startDate": start_date.strftime("%Y%m%d"),
            "endDate": end_date.strftime("%Y%m%d"),
            "monthLabel": f"{target_month.year}년 {target_month.month}월"
        })
    return ranges

def condo_name_map(region, room_type_name):
    if "스플라스" in room_type_name or region == "덕산":
        return "스플라스 덕산"
    elif "아일랜드" in room_type_name or region == "안면도":
        return "아일랜드 안면도"
    elif "포레스트" in room_type_name or region == "제천":
        if "레스트리" in room_type_name:
            return "레스트리 제천"
        return "포레스트 제천"
    return region

def save_results(all_data):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 필터: 예약가능만 포함
    all_data = [row for row in all_data if row["상태"] == "예약가능"]
    fields = ["수집일시", "월", "일", "지역", "평형", "객실타입", "리조트", "상태"]

    # 엑셀 저장
    xlsx_path = os.path.join(FOLDER, f"resom_{timestamp}.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "객실현황"
    ws.append(fields)
    for row in all_data:
        ws.append([row[f] for f in fields])
    wb.save(xlsx_path)
    print(f"[성공] 엑셀 저장 완료: {xlsx_path}")
    cleanup_old_files()

def cleanup_old_files():
    import glob as gb
    now = datetime.now()
    for pattern in [os.path.join(FOLDER, "resom_*.xlsx"),
                    os.path.join(FOLDER, "resom_*.csv"),
                    os.path.join(FOLDER, "resom_*.txt")]:
        for f in gb.glob(pattern):
            if (now - datetime.fromtimestamp(os.path.getmtime(f))).days >= KEEP_DAYS:
                try:
                    os.remove(f)
                    print(f"  [삭제] 오래된 파일 삭제: {os.path.basename(f)}")
                except Exception:
                    pass

def main():
    print("\n" + "="*55)
    print("  리솜리조트 초고속 API 객실 수집기")
    print("="*55)
    
    auth_headers = {}
    captured_catalog = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # API 요청 감시하여 인증 토큰과 카탈로그 획득
        def handle_request(request):
            url = request.url
            if "selectCondos" in url:
                auth_headers["authorization"] = request.headers.get("authorization")
                auth_headers["login-id"] = request.headers.get("login-id")
                auth_headers["user-device"] = request.headers.get("user-device")
                auth_headers["accept"] = request.headers.get("accept", "application/json")
                auth_headers["referer"] = request.headers.get("referer")

        def handle_response(response):
            url = response.url
            if "selectCondos" in url:
                try:
                    text = response.text()
                    data = json.loads(text)
                    if isinstance(data, list) and len(data) > 0:
                        captured_catalog.extend(data)
                except Exception:
                    pass

        page.on("request", handle_request)
        page.on("response", handle_response)

        # 1. 로그인
        print("로그인 페이지 접속...")
        page.goto("https://book.resom.co.kr/login?resort=resom")
        page.wait_for_load_state("networkidle")
        page.fill("input[placeholder='아이디를 입력해주세요']", RESOM_ID)
        page.fill("input[placeholder='비밀번호를 입력해주세요']", RESOM_PW)
        page.click("a.btn.login_btn")
        page.wait_for_timeout(3000)
        
        # 2. 예약 페이지로 이동
        page.goto("https://book.resom.co.kr/roomReservation?resort=resom")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # 3. 회원권 선택 (토큰 및 지점/객실 데이터 수집 유도)
        print(f"회원권 선택: {MEMBERSHIP}")
        selects = page.query_selector_all("select")
        if selects:
            selects[0].select_option(MEMBERSHIP)
            page.wait_for_timeout(3000)

        # 헤더 캡처 확인
        if not auth_headers.get("authorization"):
            print("[경고] 인증 토큰 가로채기 실패! 브라우저가 종료됩니다.")
            browser.close()
            return
            
        print("인증 키 및 헤더 수집 완료.")

        # 카탈로그 데이터 셋업 (가로채기 성공 시 그것을 쓰고, 실패 시 하드코딩 백업 적용)
        condos_data = captured_catalog if captured_catalog else FALLBACK_CATALOG
        print(f"카탈로그 로드 완료 (리조트 개수: {len(condos_data)}개)")

        # 수집 대상 조합 리스트 생성
        query_targets = []
        for condo in condos_data:
            condo_cd = condo.get("condoCd")
            condo_nm = condo.get("condoNm")
            biz_nm = condo.get("bizNm")
            
            if not any(r in biz_nm for r in TARGET_REGIONS):
                continue
                
            pyeong_rooms = {}
            for rt in condo.get("roomTypeList", []):
                p_cd = rt.get("pyeongTypeCd")
                rt_cd = rt.get("rmTypeCd")
                pyeong_rooms.setdefault(p_cd, []).append(rt_cd)
                
            for p_cd, rt_codes in pyeong_rooms.items():
                query_targets.append({
                    "condoCd": condo_cd,
                    "condoNm": condo_nm,
                    "bizNm": biz_nm,
                    "pyeongTypeCd": p_cd,
                    "rmTypeCds": ",".join(rt_codes)
                })

        months = build_month_ranges()
        
        # API 요청 생성
        tasks = []
        for target in query_targets:
            for month in months:
                sel_month_json = json.dumps({
                    "displayName": month["displayName"],
                    "startDate": month["startDate"],
                    "endDate": month["endDate"]
                }, ensure_ascii=False)
                
                url = (
                    f"/api/user/reservation/roomReservation/calendarRooms?"
                    f"memNo={MEMBERSHIP}&memInd=01"
                    f"&condoCd={target['condoCd']}"
                    f"&rmTypeCd={urllib.parse.quote(target['rmTypeCds'])}"
                    f"&ciYmd={month['startDate']}"
                    f"&coYmd={month['endDate']}"
                    f"&nights=1&rmCnt=1"
                    f"&pyeongTypeCd={target['pyeongTypeCd']}"
                    f"&copnNo="
                    f"&selectedMonth={urllib.parse.quote(sel_month_json)}"
                )
                tasks.append({
                    "url": url,
                    "bizNm": target["bizNm"],
                    "pyeong": target["pyeongTypeCd"],
                    "monthLabel": month["monthLabel"]
                })

        print(f"API 데이터 요청 시작 (총 요청 수: {len(tasks)}개)...")
        
        js_code = """
        async function fetchAll(tasks, headers) {
            const results = [];
            const chunkSize = 10;
            for (let i = 0; i < tasks.length; i += chunkSize) {
                const chunk = tasks.slice(i, i + chunkSize);
                const promises = chunk.map(task => 
                    fetch(task.url, { headers })
                        .then(async r => {
                            if (r.status !== 200) {
                                return { task, success: false, error: 'Status ' + r.status };
                            }
                            const data = await r.json();
                            return { task, data, success: true };
                        })
                        .catch(err => ({ task, error: err.message, success: false }))
                );
                const chunkResults = await Promise.all(promises);
                results.push(...chunkResults);
            }
            return results;
        }
        """
        
        t0 = time.time()
        results = page.evaluate(
            f"async (args) => {{ {js_code}; return await fetchAll(args.tasks, args.headers); }}",
            {"tasks": tasks, "headers": auth_headers}
        )
        
        all_data = []
        for r in results:
            task = r["task"]
            if not r["success"]:
                continue
                
            data = r["data"]
            if not isinstance(data, dict):
                continue
                
            for date_str, rooms in data.items():
                if not rooms:
                    continue
                day = date_str[6:8]
                for rm in rooms:
                    if rm.get("rsvPsblYn") == "Y" and int(rm.get("remdRmCnt", 0)) > 0:
                        all_data.append({
                            "수집일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "월": task["monthLabel"],
                            "일": str(int(day)),
                            "지역": task["bizNm"],
                            "평형": task["pyeong"],
                            "객실타입": rm.get("rmTypeNm"),
                            "리조트": condo_name_map(task["bizNm"], rm.get("rmTypeNm")),
                            "상태": "예약가능"
                        })
                        
        print(f"API 수집 완료 (소요시간: {time.time() - t0:.2f}초, 수집 건수: {len(all_data)}건)")
        browser.close()

    # 결과물 저장
    if all_data:
        save_results(all_data)
        print(f"\n[완료] 총 {len(all_data)}건 저장 완료")
    else:
        print("\n[경고] 수집된 예약가능 객실 데이터가 없습니다.")

if __name__ == "__main__":
    main()