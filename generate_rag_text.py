#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사내 RAG 챗봇 최적화 텍스트 컨버터 (generate_rag_text.py)
======================================================
- convert_to_html.py의 정규화 데이터 로더를 활용합니다.
- 금월(M1), 익월(M2), 익익월(M3) 3개월 데이터를 브랜드별로 분류합니다.
- 지점(리조트명)별로 그룹화하고 날짜순으로 정제된 RAG 친화적 텍스트 파일을 생성합니다.
- 결과물은 'rag_output/' 폴더에 리조트사별, 개월별 총 12개 파일로 저장됩니다.
"""

import os
import sys
import shutil
from datetime import datetime, timezone, timedelta

# 패키지 경로 탐색을 위해 현재 디렉토리 추가
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

try:
    import pandas as pd
except ImportError:
    print("[오류] pandas 패키지가 없습니다. 설치: pip install pandas openpyxl")
    sys.exit(1)

# convert_to_html에서 정규화 로직 및 설정 불러오기
try:
    from convert_to_html import load_data, BRAND_CONFIG
except ImportError:
    print("[오류] convert_to_html.py 파일을 찾을 수 없거나 load_data를 가져올 수 없습니다.")
    sys.exit(1)

# 결과 저장 폴더 설정
OUTPUT_DIR = os.path.join(BASE_DIR, "rag_output")

# 요일 매핑 (풀네임 '요일' 형식으로 매핑하여 RAG 자연어 매칭 성능 극대화)
YOIL_MAP = {
    "월": "월요일",
    "화": "화요일",
    "수": "수요일",
    "목": "목요일",
    "금": "금요일",
    "토": "토요일",
    "일": "일요일"
}

def get_target_months():
    """
    현재 일자 기준 3개 달(M1, M2, M3)의 년월 목록을 리턴합니다.
    예: 오늘이 2026-06-12이면 -> ['2026.06', '2026.07', '2026.08']
    """
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    months = []
    for i in range(3):
        m = now.month + i
        y = now.year + (m - 1) // 12
        m = (m - 1) % 12 + 1
        months.append(f"{y}.{m:02d}")
    return months

def format_yoil(yoil_str):
    """요일 텍스트를 '(요일)' 형태로 변환하기 위해 가공합니다."""
    yoil_str = str(yoil_str).strip().replace("(", "").replace(")", "")
    if not yoil_str:
        return ""
    if len(yoil_str) == 1:
        return YOIL_MAP.get(yoil_str, yoil_str)
    if yoil_str.endswith("요일"):
        return yoil_str
    return YOIL_MAP.get(yoil_str[0], yoil_str)

def get_collect_time(df_brand):
    """해당 브랜드 데이터셋에서 가장 최근 수집 일시를 추출합니다."""
    if "수집일시" not in df_brand.columns:
        return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    
    times = df_brand["수집일시"].dropna().unique()
    times = [str(t).strip() for t in times if str(t).strip()]
    if not times:
        return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    
    try:
        # 문자열 정렬 후 가장 최신 타임스탬프 반환
        latest = sorted(times)[-1]
        if len(latest) > 16:
            latest = latest[:16]  # YYYY-MM-DD HH:MM 까지만 유지
        return latest
    except Exception:
        return times[0]

def convert_to_rag_text(df, brand, target_month):
    """
    특정 브랜드와 특정 년월에 대한 RAG 최적화 표준 텍스트를 빌드합니다.
    """
    # 브랜드 및 해당 월로 필터링
    df_filtered = df[(df["브랜드"] == brand) & (df["년월"] == target_month)].copy()
    
    # 해당 브랜드 데이터 전체에서 수집일시 추출
    df_brand = df[df["브랜드"] == brand]
    collect_time = get_collect_time(df_brand)
    
    # 년월 포맷팅 (예: 2026.06 -> 2026년 06월)
    year, month = target_month.split(".")
    formatted_month = f"{year}년 {month}월"
    
    # 텍스트 구조 빌드
    lines = []
    lines.append(f"[{brand}] {formatted_month} 예약가능 잔여객실 현황")
    lines.append(f"수집일시: {collect_time}")
    lines.append("=" * 50)
    lines.append("")
    
    if df_filtered.empty:
        lines.append("※ 예약 가능한 잔여 객실이 없습니다.")
        return "\n".join(lines)
    
    # 지점(리조트명)별로 정렬 및 그룹화
    branches = sorted(df_filtered["리조트명"].unique())
    
    for branch in branches:
        df_branch = df_filtered[df_filtered["리조트명"] == branch]
        # 해당 지점의 지역명 가져오기
        region = df_branch["지역"].iloc[0] if "지역" in df_branch.columns else "기타"
        
        lines.append(f"■ 지점명: {branch} ({region})")
        
        # 지점별 가용 객실 리스트를 날짜(일) 순으로 정렬하여 출력
        # convert_to_html에서 이미 정렬되었지만 방어적으로 재정렬
        try:
            df_branch = df_branch.assign(_day_num=pd.to_numeric(df_branch["일"], errors="coerce").fillna(0).astype(int))
            df_branch = df_branch.sort_values(by=["_day_num", "객실타입"])
        except Exception:
            pass
            
        for _, row in df_branch.iterrows():
            day_padded = f"{int(float(row['일'])):02d}" if str(row['일']).replace('.','',1).isdigit() else str(row['일'])
            yoil = format_yoil(row['요일'])
            yoil_str = f"({yoil})" if yoil else ""
            
            room_type = str(row['객실타입']).strip()
            
            # 예약가능수 표시 (한화/소노 등은 실제 실수가 있고, 리솜은 여부만 오므로 1실 처리)
            avail_count = str(row['예약가능수']).strip()
            if not avail_count or avail_count == "0" or avail_count == "예약가능":
                avail_count = "1"
                
            # 요금 정보가 있으면 포함 (선택 사항)
            price_info = ""
            if "요금" in row and str(row["요금"]).strip():
                price_info = f" | 요금: {row['요금']}"
            
            lines.append(f"  - {year}년 {month}월 {day_padded}일 {yoil_str} | {room_type} | 예약가능 ({avail_count}실){price_info}")
        
        lines.append("")  # 지점 간 줄바꿈
        
    return "\n".join(lines).strip()

def main():
    print("=== RAG 텍스트 파일 생성 시작 ===")
    
    # 1. 기존 출력 폴더 비우기 또는 생성
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 2. 데이터 수집 로드 (convert_to_html 로직 활용)
    brands = list(BRAND_CONFIG.keys())
    df = load_data(brands)
    
    # 3. 기준 3개 월 구하기
    target_months = get_target_months()
    print(f"대상 년월: {target_months} (M1, M2, M3)")
    
    # 4. 리조트별, 월별 텍스트 변환 및 저장 (총 12개 파일)
    total_files = 0
    for brand in brands:
        print(f"\n[{brand}] 텍스트 변환 중...")
        for idx, month in enumerate(target_months):
            m_code = f"M{idx+1}" # M1, M2, M3
            text_content = convert_to_rag_text(df, brand, month)
            
            # 파일명: {brand}_{M_code}_{YYYYMM}.txt
            file_month_str = month.replace(".", "")
            filename = f"{brand}_{m_code}_{file_month_str}.txt"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text_content)
                
            print(f"  -> {filename} 저장 완료")
            total_files += 1
            
    print(f"\n=== 성공적으로 총 {total_files}개의 RAG 텍스트 파일을 생성했습니다. ===")
    print(f"저장 위치: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
