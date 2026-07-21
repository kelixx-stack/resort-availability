#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
스마트올리브 구내식당 메뉴 API 연동 및 사내 게시판 자동 업데이트 모듈 (update_cafeteria.py)
=============================================================================
- 스마트올리브 외부 API에서 주간 식단 정보를 자동으로 수집합니다.
- 수집된 식단 정보를 RAG 텍스트 및 HTML로 변환합니다.
- Playwright 헤드리스 모드로 사내 인사시스템(dhr.hanati.co.kr)에 접속하여
  구내식당 공지글(POST_ID_MENU / POST_ID_CAFETERIA)을 자동 수정·저장합니다.
- 매일 23시(KST) AWS ECS Fargate 태스크로 자동 구동됩니다.
"""

import os
import sys
import json
import re
import requests
import asyncio
from datetime import datetime, date, timedelta, timezone
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────────────────
#  디렉터리 및 환경 설정
# ─────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
RAG_PATH = os.path.join(BASE_DIR, "menu_weekly_latest.txt")

# 스마트올리브 API 설정
BASE_URL = "http://devapi.smartolivecorp.com"
API_KEY  = "08c45e0d58ec1d66a8f3102a0fae13b8"
STORE_ID = 3343  # 하나금융데이터센터 구내식당

HEADERS = {
    "Api-Key": API_KEY,
    "Accept-Language": "ko-KR",
    "Content-Type": "application/json",
}

MEAL_ORDER = ["BREAKFAST", "LUNCH", "DINNER", "SNACK"]
MEAL_LABEL = {
    "BREAKFAST": "조식",
    "LUNCH":     "중식",
    "DINNER":    "석식",
    "SNACK":     "간식",
}
DAY_LABEL = {
    "MONDAY":    "월요일",
    "TUESDAY":   "화요일",
    "WEDNESDAY": "수요일",
    "THURSDAY":  "목요일",
    "FRIDAY":    "금요일",
    "SATURDAY":  "토요일",
    "SUNDAY":    "일요일",
}


def load_custom_env(filepath):
    """
    콜론(:) 또는 등호(=) 형태의 .env 파일을 파싱합니다.
    """
    config = {}
    if not os.path.exists(filepath):
        print(f"[오류] .env 파일을 찾을 수 없습니다: {filepath}")
        return config
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                config[k.strip().lower()] = v.strip()
            elif "=" in line:
                k, v = line.split("=", 1)
                config[k.strip().lower()] = v.strip()
    return config


# ─────────────────────────────────────────────────────────
#  스마트올리브 API 수집 및 RAG 변환 함수
# ─────────────────────────────────────────────────────────
def clean_html(text: str) -> str:
    """<br> 태그를 줄바꿈으로 변경하고 나머지 HTML 태그를 제거합니다."""
    if not text:
        return ""
    text = text.replace("<br>", "\n").replace("<BR>", "\n")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_weekly_menu() -> dict:
    """이번 주 전체 메뉴를 API에서 가져옵니다."""
    url = f"{BASE_URL}/api/v1/external/cafeterias/{STORE_ID}/weekly-meal-menus"
    print(f"[API 호출] 주간 메뉴 조회: {url}")
    r = requests.get(url, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def format_menus(menus: list) -> str:
    """메뉴 항목 리스트를 텍스트 블록으로 변환합니다."""
    lines = []
    for m in menus:
        title = m.get("menuTitle", "").strip()
        desc  = clean_html(m.get("menuDescription", ""))
        price = m.get("price", 0)

        if title and title not in ("식사", "간식"):
            lines.append(f"  [{title}]  {price:,}원")
        else:
            lines.append(f"  가격: {price:,}원")

        for item in desc.split("\n"):
            item = item.strip()
            if item:
                lines.append(f"  - {item}")

    return "\n".join(lines)


def weekly_to_rag(data: dict) -> str:
    """주간 API 응답 데이터를 RAG 텍스트 규격으로 변환합니다."""
    item = data.get("item", {})
    store_name = item.get("store", {}).get("storeName", "구내식당")
    days = item.get("days", [])
    now  = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")

    today  = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    lines = []
    lines.append(f"# {store_name} 주간 메뉴")
    lines.append(f"기간: {monday.strftime('%Y년 %m월 %d일')} (월) ~ {friday.strftime('%m월 %d일')} (금)")
    lines.append(f"업데이트: {now}")
    lines.append(f"출처: 스마트올리브 API (자동 수집)")
    lines.append("")
    lines.append("---")
    lines.append("")

    for day in days:
        day_type  = day.get("dayType", "")
        day_label = DAY_LABEL.get(day_type, day_type)
        meal_times = day.get("mealTimes", [])

        if not meal_times:
            continue

        day_offset = {"MONDAY":0,"TUESDAY":1,"WEDNESDAY":2,"THURSDAY":3,"FRIDAY":4,"SATURDAY":5,"SUNDAY":6}
        day_date = monday + timedelta(days=day_offset.get(day_type, 0))

        lines.append(f"## {day_date.strftime('%m/%d')} ({day_label})")
        lines.append("")

        meal_map = {m["mealTimeCode"]: m for m in meal_times}
        for code in MEAL_ORDER:
            if code not in meal_map:
                continue
            mt = meal_map[code]
            label = MEAL_LABEL.get(code, mt.get("mealTimeDescription", code))
            menus = mt.get("menus", [])

            lines.append(f"### {label}")
            lines.append(format_menus(menus))
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────
#  메인 실행 (API 수집 + 사내 게시판 수정)
# ─────────────────────────────────────────────────────────
async def main():
    print("=====================================================")
    print("  [구내식당 자동화 모드] 스마트올리브 API 수집 및 게시판 업데이트")
    print(f"  실행 시각: {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')}")
    print("=====================================================")

    # 1. API 수집 진행
    try:
        data = fetch_weekly_menu()
        rag_text = weekly_to_rag(data)
        
        # 텍스트 파일 저장
        with open(RAG_PATH, "w", encoding="utf-8-sig") as f:
            f.write(rag_text)
        print(f"[성공] 주간 메뉴 수집 및 텍스트 파일 생성 완료 ({RAG_PATH})")
    except Exception as e:
        print(f"[오류] 스마트올리브 API 수집 실패: {e}")
        sys.exit(1)

    # 2. 계정 및 게시글 설정 로드
    config  = load_custom_env(ENV_PATH)
    user_id = config.get("id")
    user_pw = config.get("password")
    post_id = config.get("post_id_menu") or config.get("post_id_cafeteria")

    if not user_id or not user_pw:
        print("[오류] .env에서 계정 정보(id/password)를 읽을 수 없습니다.")
        sys.exit(1)
    if not post_id:
        print("[오류] .env에서 구내식당 게시물 고유 번호(post_id_menu 또는 post_id_cafeteria)를 읽을 수 없습니다.")
        sys.exit(1)

    print(f"설정 로드 완료 - ID: {user_id}, 구내식당 게시물 Seq: {post_id}")
    new_title = "[총무] 하나금융데이터센터 구내식당 주간 메뉴"

    # 3. Playwright 백그라운드 브라우저 구동
    async with async_playwright() as p:
        print("\n브라우저 실행 중 (백그라운드 모드)...")
        browser = await p.chromium.launch(headless=True, slow_mo=500)
        context = await browser.new_context(viewport={"width": 1280, "height": 800}, ignore_https_errors=True)
        page = await context.new_page()

        # 알림창 자동 수락 설정
        async def handle_dialog(dialog):
            print(f"  [알림창] {dialog.message} → [확인]")
            await dialog.accept()
        page.on("dialog", lambda d: asyncio.create_task(handle_dialog(d)))

        # 로그인
        login_url = "https://dhr.hanati.co.kr/index.jsp"
        print(f"로그인 페이지 접속: {login_url}")
        await page.goto(login_url, timeout=30000)

        await page.locator("#login_id").fill(user_id)
        await page.locator("#pd").fill(user_pw)
        await page.locator("#pd").press("Enter")

        print("로그인 처리 대기 중...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        print("로그인 완료")

        # 공지사항 '더보기' 버튼 클릭
        print("\n공지사항 '더보기' 버튼 탐색 중...")
        more_btn_selector = "a.btn_mlkg_more"
        btn_locator = None

        loc = page.locator(more_btn_selector)
        if await loc.count() > 0:
            btn_locator = loc.first
        else:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                loc = frame.locator(more_btn_selector)
                if await loc.count() > 0:
                    btn_locator = loc.first
                    break

        if not btn_locator:
            print("[오류] '더보기' 버튼을 찾지 못했습니다.")
            diag = os.path.join(BASE_DIR, "diag_cafeteria_login.png")
            await page.screenshot(path=diag)
            await browser.close()
            sys.exit(1)

        print("'더보기' 버튼 클릭...")
        await btn_locator.click()
        await asyncio.sleep(5)

        # 공지사항 목록 팝업 프레임 접근
        iframe_name = "frame_dlg_CMU0010_10__OpenNoticePopup"
        notice_frame = page.frame(name=iframe_name)
        if not notice_frame:
            print(f"[오류] 공지사항 목록 프레임을 찾을 수 없습니다: {iframe_name}")
            await browser.close()
            sys.exit(1)

        print("'구내식당' 키워드로 게시물 검색 중...")
        await notice_frame.locator("#searchword").fill("구내식당")
        await notice_frame.locator("input[value='조회']").click()
        await asyncio.sleep(3)

        # Seq ID로 해당 게시물 행 클릭
        row_selector = f"tr.baseDataRow:has(td.HideCol0C14:has-text('{post_id}')) td.HideCol0C4"
        cell_locator = notice_frame.locator(row_selector).first

        if await cell_locator.count() == 0:
            print(f"  → Seq ID '{post_id}' 미발견, 재조회 시도...")
            await notice_frame.locator("input[value='조회']").click()
            await asyncio.sleep(3)

        if await cell_locator.count() == 0:
            print(f"[오류] Seq ID '{post_id}' 행을 찾을 수 없습니다.")
            diag = os.path.join(BASE_DIR, "diag_cafeteria_row.png")
            await page.screenshot(path=diag)
            await browser.close()
            sys.exit(1)

        print(f"Seq ID '{post_id}' 행 클릭 → 상세 보기 진입...")
        await cell_locator.scroll_into_view_if_needed()
        await cell_locator.click()
        await asyncio.sleep(3)

        # 상세 보기 프레임 → [수정] 버튼 클릭
        detail_frame_name = "frame_dlg_CMU0030_51__detail"
        detail_frame = page.frame(name=detail_frame_name)
        if not detail_frame:
            print(f"[오류] 상세 프레임 로딩 실패: {detail_frame_name}")
            await browser.close()
            sys.exit(1)

        edit_btn = detail_frame.locator("input[value='수정']")
        if await edit_btn.count() == 0:
            print("[오류] [수정] 버튼이 없습니다. 게시글 수정 권한을 확인하세요.")
            await browser.close()
            sys.exit(1)

        print("[수정] 버튼 클릭...")
        await edit_btn.click()
        await asyncio.sleep(3)

        # 수정 팝업 프레임
        modify_frame_name = "frame_dlg_CMU0040_53__modify"
        modify_frame = page.frame(name=modify_frame_name)
        if not modify_frame:
            print(f"[오류] 수정 프레임 로딩 실패: {modify_frame_name}")
            close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
            if await close_btn.count() > 0:
                await close_btn.click()
            await browser.close()
            sys.exit(1)

        # 제목 업데이트
        print(f"제목 입력: {new_title}")
        await modify_frame.locator("#title").fill(new_title)

        # Summernote 에디터에 본문 주입
        editor_frame = None
        for cf in modify_frame.child_frames:
            if cf.name == "content" or "summerNote.jsp" in cf.url:
                editor_frame = cf
                break

        if not editor_frame:
            print("[오류] Summernote 에디터 프레임을 찾을 수 없습니다.")
            modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
            if await modify_close.count() > 0:
                await modify_close.click()
            await browser.close()
            sys.exit(1)

        # 텍스트 → HTML 변환
        lines = rag_text.split("\n")
        html_lines = []
        for line in lines:
            if line.startswith("# "):
                html_lines.append(f"<h2>{line[2:]}</h2>")
            elif line.startswith("## "):
                html_lines.append(f"<h3>{line[3:]}</h3>")
            elif line.startswith("### "):
                html_lines.append(f"<h4>{line[4:]}</h4>")
            elif line.startswith("---"):
                html_lines.append('<div style="border-top: 1px solid #cccccc; margin: 10px 0;"></div>')
            elif line.startswith("  - "):
                html_lines.append(f"&nbsp;&nbsp;• {line[4:]}<br>")
            elif line.startswith("  "):
                html_lines.append(f"&nbsp;&nbsp;{line.strip()}<br>")
            elif line == "":
                html_lines.append("<br>")
            else:
                html_lines.append(f"{line}<br>")

        rag_html = "<p>" + "\n".join(html_lines) + "</p>"

        print("본문 내용 주입 중...")
        await editor_frame.locator("div.note-editable").evaluate("""(el, val) => {
            el.innerHTML = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""", rag_html)
        await asyncio.sleep(2)

        # [저장] 버튼 클릭
        print("[저장] 버튼 클릭...")
        save_btn = modify_frame.locator("input[value='저장'], button:has-text('저장')").first
        if await save_btn.count() == 0:
            print("[오류] 저장 버튼을 찾을 수 없습니다.")
            await browser.close()
            sys.exit(1)

        await save_btn.click()
        print("저장 처리 대기 중 (5초)...")
        await asyncio.sleep(5)

        # 저장 결과 검증
        is_modify_open = await page.locator("iframe[name='frame_dlg_CMU0040_53__modify']").count() > 0
        if is_modify_open:
            print("[오류] 저장에 실패했습니다.")
            modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
            if await modify_close.count() > 0:
                await modify_close.click()
            await browser.close()
            sys.exit(1)

        # 상세 창 닫기
        detail_frame = page.frame(name=detail_frame_name)
        if detail_frame:
            close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
            if await close_btn.count() > 0:
                await close_btn.click()
                await asyncio.sleep(2)

        final_shot = os.path.join(BASE_DIR, "after_cafeteria_update.png")
        await page.screenshot(path=final_shot)

        print("\n=====================================================")
        print("  [성공] 구내식당 메뉴 게시물 업데이트 완료!")
        print(f"  제목: {new_title}")
        print(f"  완료 시각: {datetime.now(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')}")
        print("=====================================================")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
