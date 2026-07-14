#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
회사 게시판 자동화 테스트 스크립트 (update_board.py)
==================================================
- Playwright를 활용해 사내 게시판 로그인 및 공지사항 팝업 호출을 수행합니다.
- 로컬 PC에서 동작 과정을 눈으로 확인할 수 있도록 GUI 브라우저(headless=False)를 실행합니다.
- 프레임 구조(iframe)에 대응할 수 있도록 방어적으로 헬퍼 함수를 구현했습니다.
"""

import os
import sys
import asyncio
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

def load_custom_env(filepath):
    """
    콜론(:) 또는 등호(=)로 이루어진 커스텀 .env 파일을 파싱합니다.
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

async def find_element_in_all_frames(page, selector):
    """
    메인 페이지 및 모든 iframe 내부를 순회하며 요소를 찾습니다.
    """
    # 1. 메인 페이지 검색
    locator = page.locator(selector)
    if await locator.count() > 0:
        print(f"  -> 메인 페이지에서 요소를 찾았습니다: {selector}")
        return locator.first, None
        
    # 2. 모든 iframe 검색
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        locator = frame.locator(selector)
        if await locator.count() > 0:
            print(f"  -> iframe [{frame.name or frame.url[:40]}] 에서 요소를 찾았습니다: {selector}")
            return locator.first, frame
            
    return None, None

async def main():
    # 1. 환경변수 로딩
    config = load_custom_env(ENV_PATH)
    user_id = config.get("id")
    user_pw = config.get("password")
    
    if not user_id or not user_pw:
        print("[오류] .env 파일에서 id 또는 password를 읽을 수 없습니다.")
        print(f"현재 읽은 키 목록: {list(config.keys())}")
        sys.exit(1)
        
    print(f"로드 성공 - ID: {user_id} (Password 로드 완료)")
    
    # 2. Playwright 구동
    async with async_playwright() as p:
        print("\n브라우저를 실행 중입니다 (로컬 테스트용 화면 표시 모드)...")
        browser = await p.chromium.launch(
            headless=True,  # 백그라운드(화면 비표시) 모드로 실행하여 화면 잠금/원격 해제 시에도 작동
            slow_mo=500      # 보안 차단(WAF) 회피 및 휴먼 딜레이 유지를 위해 0.5초 대기
        )
        
        # 브라우저 컨텍스트 설정 (화면 크기 넉넉하게 지정)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True
        )
        
        page = await context.new_page()
        
        # 3. 로그인 페이지 접속
        login_url = "https://dhr.hanati.co.kr/index.jsp"
        print(f"페이지 접속 중: {login_url}")
        await page.goto(login_url, timeout=30000)
        
        # 4. 로그인 정보 입력
        print("로그인 정보를 입력합니다...")
        await page.locator("#login_id").fill(user_id)
        await page.locator("#pd").fill(user_pw)
        
        # 비밀번호 칸에서 엔터를 쳐서 로그인 시도
        print("로그인 요청을 전송합니다 (Enter 키 입력)...")
        await page.locator("#pd").press("Enter")
        
        # 로그인 완료 대기 (JSP 페이지가 로딩되는 시간 고려)
        print("로그인 처리 대기 중...")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3) # 추가적인 동적 렌더링 대기
        
        # 5. '더보기' 버튼 찾기 및 클릭
        print("\n공지사항 '더보기' 버튼을 찾는 중입니다...")
        more_btn_selector = "a.btn_mlkg_more"
        
        btn_locator, target_frame = await find_element_in_all_frames(page, more_btn_selector)
        
        if not btn_locator:
            print("[오류] 공지사항 '더보기' 버튼을 찾지 못했습니다.")
            # 진단용 스크린샷 저장
            diag_screenshot = os.path.join(BASE_DIR, "login_failed_diagnosis.png")
            await page.screenshot(path=diag_screenshot)
            print(f"  -> 디버그용 스크린샷 저장됨: {diag_screenshot}")
            await browser.close()
            return
            
        print("공지사항 '더보기' 버튼을 클릭합니다...")
        await btn_locator.click()
        
        # 6. 모달 팝업이 뜨는 데 걸리는 시간 대기
        print("팝업창 로딩 대기 중 (5초)...")
        await asyncio.sleep(5)
        
        # 7. 확인용 스크린샷 캡처
        screenshot_path = os.path.join(BASE_DIR, "modal_opened.png")
        await page.screenshot(path=screenshot_path)
        print(f"[성공] 팝업 호출 후 스크린샷이 저장되었습니다: {screenshot_path}")
        
        # === 팝업 내 프레임 및 엘리먼트 진단 (debug_dump.txt에 저장) ===
        dump_path = os.path.join(BASE_DIR, "debug_dump.txt")
        print(f"\n[진단] 프레임 및 엘리먼트 정보를 파일에 쓰는 중: {dump_path}")
        
        with open(dump_path, "w", encoding="utf-8") as f_out:
            f_out.write("=== 프레임 진단 ===\n")
            for idx, frame in enumerate(page.frames):
                f_out.write(f"Frame {idx}: Name='{frame.name}', URL='{frame.url}'\n")
                
            for idx, frame in enumerate(page.frames):
                frame_label = frame.name or f"Frame_{idx}"
                if frame == page.main_frame:
                    frame_label = "Main"
                    
                inputs = await frame.locator("input").all()
                buttons = await frame.locator("button, a, input[type='button'], input[type='image']").all()
                
                f_out.write(f"\n[{frame_label}] 입력칸 수: {len(inputs)}개, 버튼 수: {len(buttons)}개\n")
                
                for i, inp in enumerate(inputs):
                    try:
                        html = await inp.evaluate("el => el.outerHTML")
                        f_out.write(f"  [Input {i}] {html}\n")
                    except Exception as e:
                        f_out.write(f"  [Input {i}] Error: {e}\n")
                        
                for b_idx, btn in enumerate(buttons):
                    try:
                        text = (await btn.text_content()).strip()
                        html = await btn.evaluate("el => el.outerHTML")
                        f_out.write(f"  [Button {b_idx}] Text='{text}', HTML='{html[:200]}'\n")
                    except Exception as e:
                        f_out.write(f"  [Button {b_idx}] Error: {e}\n")
                        
        print("[진단 완료] 파일 저장 성공.")
        

        
        # 얼럿창 자동 처리 (예: "저장하시겠습니까?", "저장되었습니다.")
        async def handle_dialog(dialog):
            print(f"  [알림창] 메시지: {dialog.message} -> [확인] 클릭")
            await dialog.accept()
            
        page.on("dialog", lambda d: asyncio.create_task(handle_dialog(d)))
        
        # 12개 게시글 정보 매핑 로드
        post_mappings = {
            "롯데": {
                "M1": config.get("post_id_lotte_m1"),
                "M2": config.get("post_id_lotte_m2"),
                "M3": config.get("post_id_lotte_m3")
            },
            "리솜": {
                "M1": config.get("post_id_resom_m1"),
                "M2": config.get("post_id_resom_m2"),
                "M3": config.get("post_id_resom_m3")
            },
            "소노": {
                "M1": config.get("post_id_sono_m1"),
                "M2": config.get("post_id_sono_m2"),
                "M3": config.get("post_id_sono_m3")
            },
            "한화": {
                "M1": config.get("post_id_hanhwa_m1"),
                "M2": config.get("post_id_hanhwa_m2"),
                "M3": config.get("post_id_hanhwa_m3")
            }
        }
        
        # 현재 날짜 기준 3개 년월(M1, M2, M3) 자동 계산
        kst = timezone(timedelta(hours=9))
        now = datetime.now(kst)
        target_months = []
        for i in range(3):
            m = now.month + i
            y = now.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            target_months.append(f"{y}{m:02d}")
        print(f"대상 년월 (M1, M2, M3): {target_months}")
        
        # 팝업 내 목록 프레임 접근
        iframe_name = "frame_dlg_CMU0010_10__OpenNoticePopup"
        print(f"\n[{iframe_name}] 프레임에서 조회 필터링을 시작합니다...")
        notice_frame = page.frame(name=iframe_name)
        if not notice_frame:
            print(f"[오류] [{iframe_name}] 프레임을 찾을 수 없습니다.")
            await browser.close()
            return
            
        print("검색어 입력창(#searchword)에 '[리조트]'를 입력합니다...")
        await notice_frame.locator("#searchword").fill("[리조트]")
        
        print("[조회] 버튼을 클릭하여 필터링합니다...")
        await notice_frame.locator("input[value='조회']").click()
        await asyncio.sleep(3)
        
        success_count = 0
        failure_count = 0
        
        for brand, offsets in post_mappings.items():
            for offset_code, post_id in offsets.items():
                if not post_id:
                    print(f"\n[경고] {brand} {offset_code}의 Seq ID가 .env에 없습니다. 건너뜁니다.")
                    continue
                
                print(f"\n=====================================================")
                print(f" ▶ 업데이트 진행: {brand} {offset_code} (Seq ID: {post_id})")
                print(f"=====================================================")
                
                # 1. 목록 프레임 재확인
                notice_frame = page.frame(name=iframe_name)
                if not notice_frame:
                    print("[오류] 목록 프레임을 찾을 수 없습니다.")
                    failure_count += 1
                    continue
                
                # 2. IBSheet 그리드 행을 Seq ID 기준으로 찾아서 클릭
                row_selector = f"tr.baseDataRow:has(td.HideCol0C14:has-text('{post_id}')) td.HideCol0C4"
                cell_locator = notice_frame.locator(row_selector).first
                
                if await cell_locator.count() == 0:
                    print(f"  -> [경고] 목록에서 Seq ID '{post_id}' 행을 찾지 못했습니다. 조회 버튼 클릭 후 재시도...")
                    await notice_frame.locator("input[value='조회']").click()
                    await asyncio.sleep(3)
                    
                    if await cell_locator.count() == 0:
                        print(f"  -> [오류] 재조회 후에도 Seq ID '{post_id}' 행을 찾지 못해 건너뜁니다.")
                        failure_count += 1
                        continue
                
                print(f"  Seq ID '{post_id}' 행을 클릭하여 상세 보기로 진입합니다...")
                await cell_locator.scroll_into_view_if_needed()
                await cell_locator.click()
                
                # 3. 상세 보기 팝업 로딩 대기
                detail_frame_name = "frame_dlg_CMU0030_51__detail"
                print("  상세 보기 팝업 로딩 대기 중...")
                await asyncio.sleep(3)
                detail_frame = page.frame(name=detail_frame_name)
                if not detail_frame:
                    print(f"  -> [오류] 상세 프레임 [{detail_frame_name}] 로딩 실패.")
                    failure_count += 1
                    continue
                
                # 4. [수정] 버튼 클릭
                edit_btn = detail_frame.locator("input[value='수정']")
                if await edit_btn.count() == 0:
                    print("  -> [오류] [수정] 버튼이 상세 화면에 없습니다. 창을 닫습니다.")
                    close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await close_btn.count() > 0:
                        await close_btn.click()
                    failure_count += 1
                    continue
                await edit_btn.click()
                
                # 5. 수정 팝업 로딩 대기
                modify_frame_name = "frame_dlg_CMU0040_53__modify"
                print("  수정 화면 로딩 대기 중...")
                await asyncio.sleep(3)
                modify_frame = page.frame(name=modify_frame_name)
                if not modify_frame:
                    print(f"  -> [오류] 수정 프레임 [{modify_frame_name}] 로딩 실패. 상세 창을 닫습니다.")
                    close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await close_btn.count() > 0:
                        await close_btn.click()
                    failure_count += 1
                    continue
                
                # 6. RAG 파일 읽기
                month_idx = int(offset_code[1]) - 1
                month_str = target_months[month_idx]
                filename = f"{brand}_{offset_code}_{month_str}.txt"
                rag_file_path = os.path.join(os.path.dirname(BASE_DIR), "rag_output", filename)
                
                if not os.path.exists(rag_file_path):
                    print(f"  -> [오류] RAG 텍스트 파일이 없습니다: {rag_file_path}. 작업을 취소하고 닫습니다.")
                    modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await modify_close.count() > 0:
                        await modify_close.click()
                    await asyncio.sleep(1)
                    detail_close = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await detail_close.count() > 0:
                        await detail_close.click()
                    failure_count += 1
                    continue
                
                with open(rag_file_path, "r", encoding="utf-8") as f_rag:
                    rag_text = f_rag.read()
                
                # 7. 제목 업데이트
                year_str = month_str[:4]
                m_str = month_str[4:]
                new_title = f"[리조트][{brand}] {year_str}년 {m_str}월 예약가능 잔여객실 현황"
                print(f"  제목 변경 입력: {new_title}")
                await modify_frame.locator("#title").fill(new_title)
                

                
                # 8. Summernote 에디터에 본문 주입
                editor_frame = None
                for cf in modify_frame.child_frames:
                    if cf.name == "content" or "summerNote.jsp" in cf.url:
                        editor_frame = cf
                        break
                
                if not editor_frame:
                    print("  -> [오류] Summernote 에디터 프레임을 찾을 수 없습니다. 작업을 취소합니다.")
                    modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await modify_close.count() > 0:
                        await modify_close.click()
                    await asyncio.sleep(1)
                    detail_close = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await detail_close.count() > 0:
                        await detail_close.click()
                    failure_count += 1
                    continue
                
                rag_html = "<p>" + rag_text.replace("\n", "<br>") + "</p>"
                print("  본문 RAG HTML 주입 중...")
                await editor_frame.locator("div.note-editable").evaluate("""(el, val) => {
                    el.innerHTML = val;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }""", rag_html)
                
                await asyncio.sleep(2)
                
                # 9. [저장] 버튼 클릭
                print("  [저장] 버튼을 클릭합니다...")
                save_btn = modify_frame.locator("input[value='저장'], button:has-text('저장')").first
                if await save_btn.count() == 0:
                    print("  -> [오류] 저장 버튼을 찾을 수 없습니다.")
                    modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await modify_close.count() > 0:
                        await modify_close.click()
                    await asyncio.sleep(1)
                    detail_close = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await detail_close.count() > 0:
                        await detail_close.click()
                    failure_count += 1
                    continue
                
                await save_btn.click()
                print("  저장 처리 대기 중 (5초)...")
                await asyncio.sleep(5) # 얼럿 및 저장 완료 대기
                
                # 10. 저장 결과 검증 (수정 창이 안 닫혔다면 저장 실패로 간주)
                is_modify_open = await page.locator("iframe[name='frame_dlg_CMU0040_53__modify']").count() > 0
                if is_modify_open:
                    print("  -> [오류] 필수값 누락 등으로 인해 저장이 실패했습니다. 수정 창을 강제로 닫고 넘어갑니다.")
                    modify_close = modify_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await modify_close.count() > 0:
                        await modify_close.click()
                        await asyncio.sleep(2)
                    
                    # 상세 창 닫기
                    detail_frame = page.frame(name=detail_frame_name)
                    if detail_frame:
                        close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                        if await close_btn.count() > 0:
                            await close_btn.click()
                            await asyncio.sleep(2)
                    failure_count += 1
                    continue
                
                # 11. 상세 창 닫아서 목록으로 이동
                detail_frame = page.frame(name=detail_frame_name)
                if detail_frame:
                    print("  상세 보기 팝업을 닫고 목록으로 이동합니다...")
                    close_btn = detail_frame.locator("input[value*='닫기'], button:has-text('닫기')").first
                    if await close_btn.count() > 0:
                        await close_btn.click()
                        await asyncio.sleep(2)
                
                print(f"  -> [성공] {brand} {offset_code} 업데이트 완료!")
                success_count += 1
                
        print("\n=====================================================")
        print(f" 업데이트 결과 요약: 성공 {success_count}개, 실패 {failure_count}개")
        print("=====================================================")
        
        # 완료 화면 캡처
        final_screenshot = os.path.join(BASE_DIR, "after_all_updates.png")
        await page.screenshot(path=final_screenshot)
        print(f"최종 화면 스크린샷 저장됨: {final_screenshot}")
        
        await browser.close()
        print("모든 작업 종료.")

if __name__ == "__main__":
    asyncio.run(main())
