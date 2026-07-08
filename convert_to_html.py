#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사내 리조트 잔여객실 통합 HTML 변환기
=====================================
지원 브랜드: 리솜, 한화, 소노(대명), 롯데
- 각 브랜드 data 폴더에서 최신 XLSX 자동 탐색
- 공통 스키마로 정규화
- 단일 HTML 파일 생성 -> resort_availability.html
"""

import sys, os, json, glob, argparse
from datetime import datetime, timezone, timedelta

try:
    import pandas as pd
except ImportError:
    print("[오류] pandas 없음. 설치: pip install pandas openpyxl")
    sys.exit(1)

# ============================================================
# 설정
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BRAND_CONFIG = {
    "리솜": {
        "folders": [
            os.path.join(BASE_DIR, "resom_crawler", "data"),
            os.path.join(BASE_DIR, "resom_crawler"),
        ],
        "pattern": "resom_*.xlsx",
        "col_map": {"월": "년월", "리조트": "리조트명", "객실타입": "객실타입"},
        "status_col": "상태",        # "예약가능" 행만 포함
        "count_col": None,           # 없으면 1로 채움
        "color": "#0F6E56",
    },
    "한화": {
        "folders": [
            os.path.join(BASE_DIR, "hanhwa_crawler", "data"),
            os.path.join(BASE_DIR, "hanhwa_crawler"),
        ],
        "pattern": "hanwha_*.xlsx",
        "col_map": {"객실타입명": "객실타입"},
        "status_col": None,
        "count_col": "예약가능수",
        "color": "#E95D0F",
    },
    "소노": {
        "folders": [os.path.join(BASE_DIR, "sono_crawler", "data")],
        "pattern": "sono_*.xlsx",
        "col_map": {},
        "status_col": None,
        "count_col": "예약가능수",
        "color": "#1A56DB",
    },
    "롯데": {
        "folders": [os.path.join(BASE_DIR, "lotte_crawler", "data")],
        "pattern": "lotte_*.xlsx",
        "col_map": {},
        "status_col": None,
        "count_col": "예약가능수",
        "color": "#DC2626",
    },
}

# 통합 공통 컬럼
UNIFIED = ["수집일시", "브랜드", "리조트명", "지역", "년월", "일", "요일", "객실타입", "예약가능수", "요금"]
OUTPUT_HTML = os.path.join(BASE_DIR, "resort_availability.html")

# ============================================================
# 데이터 로드 및 정규화
# ============================================================

def find_latest(brand, cfg):
    for folder in cfg["folders"]:
        if not os.path.isdir(folder):
            continue
        files = sorted(
            glob.glob(os.path.join(folder, cfg["pattern"])),
            reverse=True
        )
        if files:
            print(f"  [{brand}] {os.path.basename(files[0])}")
            return files[0]
    print(f"  [{brand}] [경고] 파일 없음 (스킵)")
    return None

def map_region(row):
    resort_name = str(row.get("리조트명", "")).strip()
    brand = row.get("브랜드", "")
    original_region = str(row.get("지역", "")).strip()
    
    # 1. 강원
    if any(k in resort_name for k in ["속초", "델피노", "비발디파크", "삼척", "양양", "설악", "평창"]):
        return "강원"
    # 2. 경기/서울
    if any(k in resort_name for k in ["고양", "용인", "산정호수", "패쓰온", "더플라자"]):
        return "경기/서울"
    # 3. 충청
    if any(k in resort_name for k in ["부여", "단양", "천안", "대전", "스플라스", "아일랜드", "포레스트", "덕산", "안면도", "제천", "대천"]):
        return "충청"
    # 4. 경상
    if any(k in resort_name for k in ["김해", "해운대", "청송", "거제", "경주", "남해", "오시리아"]):
        return "경상"
    # 5. 전라
    if any(k in resort_name for k in ["변산", "진도", "여수"]):
        return "전라"
    # 6. 제주
    if any(k in resort_name for k in ["제주", "아트빌라스"]):
        return "제주"
        
    if original_region in ["덕산", "안면도", "제천"]:
        return "충청"
        
    return original_region if original_region else "기타"

def standardize_year_month(val):
    import re
    val = str(val).strip()
    if not val:
        return ""
    m_yr = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월", val)
    if m_yr:
        return f"{m_yr.group(1)}.{int(m_yr.group(2)):02d}"
    m_dot = re.search(r"(\d{4})\s*\.\s*(\d{1,2})", val)
    if m_dot:
        return f"{m_dot.group(1)}.{int(m_dot.group(2)):02d}"
    m_num = re.search(r"^(\d{4})(\d{2})$", val)
    if m_num:
        return f"{m_num.group(1)}.{m_num.group(2)}"
    return val

def compute_weekday(row):
    import re
    year_month = str(row.get("년월", "")).strip()
    day = str(row.get("일", "")).strip()
    yoil = str(row.get("요일", "")).strip()
    
    if yoil in ["월", "화", "수", "목", "금", "토", "일"]:
        return yoil
        
    try:
        m = re.search(r"(\d{4})\s*\.\s*(\d{1,2})", year_month)
        if m:
            y = int(m.group(1))
            mon = int(m.group(2))
            d = int(day)
            dt = datetime(y, mon, d)
            weekdays = ["월", "화", "수", "목", "금", "토", "일"]
            return weekdays[dt.weekday()]
    except Exception:
        pass
    return yoil

def filter_past_dates(df):
    import re
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).date()
    valid_indices = []
    for idx, row in df.iterrows():
        try:
            yr_mo = str(row.get("년월", "")).strip()
            day_str = str(row.get("일", "")).strip()
            m = re.search(r"(\d{4})\.(\d{2})", yr_mo)
            if m and day_str.isdigit():
                y = int(m.group(1))
                mon = int(m.group(2))
                d = int(day_str)
                target_date = datetime(y, mon, d).date()
                if target_date < today:
                    continue  # 과거 날짜 제외
        except Exception:
            pass
        valid_indices.append(idx)
    return df.loc[valid_indices].copy()

def normalize(df, brand, cfg):
    df.columns = df.columns.str.strip()
    df = df.rename(columns=cfg["col_map"])

    # 브랜드 컬럼 강제 지정
    df["브랜드"] = brand

    # 상태 필터 (리솜)
    if cfg["status_col"] and cfg["status_col"] in df.columns:
        df = df[df[cfg["status_col"]].str.strip() == "예약가능"].copy()

    # 예약가능수
    if "예약가능수" not in df.columns:
        df["예약가능수"] = "1"

    # 리솜: 평형 + 객실타입 합치기 (중복 방지)
    if brand == "리솜" and "평형" in df.columns:
        pyeong = df["평형"].fillna("").str.strip()
        room_type = df.get("객실타입", pd.Series([""] * len(df))).fillna("").str.strip()
        df["객실타입"] = [
            f"{p} {rt}" if p and not rt.lower().startswith(p.lower()) else rt
            for p, rt in zip(pyeong, room_type)
        ]

    # 롯데: 객실타입 명칭 직관적으로 번역 (C->콘도형, H->호텔형, P->펫동반, D->더블, T->트윈, H->온돌 등)
    if brand == "롯데":
        def translate_lotte_room(name):
            name = str(name).strip()
            table = {
                "Deluxe Double": "디럭스 더블",
                "Deluxe Family Twin": "디럭스 패밀리 트윈",
                "Grand Deluxe Family": "그랜드 디럭스 패밀리",
                "Junior Family Suite": "주니어 패밀리 스위트",
                "Superior Suite": "슈페리어 스위트",
                "Superior Suite With Tempur": "슈페리어 스위트 (템퍼)",
                "Luxury 45A": "럭셔리 45평 A타입",
                "Luxury 45B": "럭셔리 45평 B타입",
                "Suite 33D": "스위트 33평 D타입",
                "Suite 33T": "스위트 33평 T타입",
                "Family 23": "패밀리 23평",
                "LOTTY&LORRY 23": "로티로리 캐릭터 23평",
                "LOTTY&LORRY 33": "로티로리 캐릭터 33평",
                "Deluxe 18F": "디럭스 18평 F타입",
                "Deluxe 18H": "디럭스 18평 H타입",
                "C 패밀리(D)": "콘도형 패밀리 더블",
                "C 패밀리(T)": "콘도형 패밀리 트윈",
                "C 훼미리(D)": "콘도형 패밀리 더블",
                "C 훼미리(T)": "콘도형 패밀리 트윈",
                "C럭셔리(T)": "콘도형 럭셔리 트윈",
                "C스위트(D)": "콘도형 스위트 더블",
                "C스위트(T)": "콘도형 스위트 트윈",
                "C훼미리(T)": "콘도형 패밀리 트윈",
                "C훼미리(D)": "콘도형 패밀리 더블",
                "C패밀리(T)": "콘도형 패밀리 트윈",
                "C패밀리(D)": "콘도형 패밀리 더블",
                "H 디럭스(D)": "호텔형 디럭스 더블",
                "H 디럭스(F)": "호텔형 디럭스 패밀리",
                "H 디럭스(T)": "호텔형 디럭스 트윈",
                "H 스위트(D)": "호텔형 스위트 더블",
                "H 스위트(M)": "호텔형 스위트 멜로디",
                "H 스위트(T)": "호텔형 스위트 트윈",
                "H 패밀리(F)": "호텔형 패밀리 패밀리",
                "H 훼미리(F)": "호텔형 패밀리 패밀리",
                "H 훼미리(H)": "호텔형 패밀리 온돌",
                "H 훼미리(T)": "호텔형 패밀리 트윈",
                "P 훼미리(A)": "펫동반 패밀리 타입A",
                "P 패밀리(A)": "펫동반 패밀리 타입A",
                "18 A- TYPE 온돌": "18평 A타입 온돌",
                "18 A- TYPE 트윈": "18평 A타입 트윈",
                "18 C-TYPE 온돌 트윈": "18평 C타입 온돌트윈",
                "23 A-TYPE 더블+온돌": "23평 A타입 더블+온돌",
                "23 C-TYPE 온돌 더블+온돌": "23평 C타입 더블+온돌",
                "23 C-TYPE 온돌 싱글더블": "23평 C타입 싱글더블",
                "31 A-TYPE 더블+온돌온돌": "31평 A타입 더블+온돌",
                "31 A-TYPE 트윈+온돌": "31평 A타입 트윈+온돌",
                "31 A-TYPE 트윈+온돌온돌": "31평 A타입 트윈+온돌",
                "31 B-TYPE 더블+온돌온돌": "31평 B타입 더블+온돌",
                "31 B-TYPE 트윈+온돌온돌": "31평 B타입 트윈+온돌",
                "31 C-TYPE 온돌 더블+온돌온돌": "31평 C타입 더블+온돌",
                "31 C-TYPE 온돌 트윈+온돌온돌": "31평 C타입 트윈+온돌",
                "31 C-TYPE 풀 더블+온돌": "31평 C타입 풀빌라 더블+온돌",
                "31 C-TYPE 키즈 온돌": "31평 C타입 키즈 온돌",
                "31 C-TYPE 키즈 패밀리": "31평 C타입 키즈 패밀리",
                "45 B-TYPE 더블+더블온돌": "45평 B타입 더블+더블+온돌",
                "45 B-TYPE 트윈+더블온돌": "45평 B타입 트윈+더블+온돌",
            }
            if name in table:
                return table[name]
            
            norm_name = name.replace(" ", "")
            if norm_name in table:
                return table[norm_name]
                
            transformed = name
            if transformed.startswith("C ") or transformed.startswith("C"):
                transformed = "콘도형 " + transformed[1:].strip()
            elif transformed.startswith("H ") or transformed.startswith("H"):
                transformed = "호텔형 " + transformed[1:].strip()
            elif transformed.startswith("P ") or transformed.startswith("P"):
                transformed = "펫동반 " + transformed[1:].strip()
                
            transformed = transformed.replace("훼미리", "패밀리")
            transformed = transformed.replace("(D)", " 더블")
            transformed = transformed.replace("(T)", " 트윈")
            transformed = transformed.replace("(F)", " 패밀리")
            transformed = transformed.replace("(H)", " 온돌")
            transformed = transformed.replace("(A)", " 타입A")
            transformed = transformed.replace("  ", " ")
            return transformed.strip()
            
        df["객실타입"] = df["객실타입"].apply(translate_lotte_room)

    # 누락 컬럼 보충
    for col in UNIFIED:
        if col not in df.columns:
            df[col] = ""

    df = df[UNIFIED].copy()
    df = df.fillna("").apply(lambda c: c.map(lambda x: str(x).strip()))
    
    # 년월 표준화
    df["년월"] = df["년월"].apply(standardize_year_month)
    
    # 일 표준화 (01 -> 1)
    def clean_day(val):
        val = str(val).strip()
        if not val:
            return ""
        try:
            return str(int(float(val)))
        except ValueError:
            return val
    df["일"] = df["일"].apply(clean_day)
    
    # 요일 계산
    df["요일"] = df.apply(compute_weekday, axis=1)
    
    # 지역 매핑 적용
    df["지역"] = df.apply(map_region, axis=1)
    df = df.drop_duplicates()
    df = filter_past_dates(df)
    return df

def load_data(brands):
    frames = []
    print("\n데이터 로드 중...")
    for brand in brands:
        cfg = BRAND_CONFIG.get(brand)
        if not cfg:
            continue
        f = find_latest(brand, cfg)
        if not f:
            continue
        try:
            df = pd.read_excel(f, dtype=str)
            df = normalize(df, brand, cfg)
            frames.append(df)
            print(f"    -> {len(df)}행")
        except Exception as e:
            print(f"  [{brand}] 읽기 오류: {e}")

    if not frames:
        print("\n[오류] 읽을 수 있는 데이터가 없습니다.")
        sys.exit(1)

    result = pd.concat(frames, ignore_index=True)
    # 날짜순 정렬 (년월, 일 정렬)
    try:
        result["_day_int"] = pd.to_numeric(result["일"], errors="coerce").fillna(0).astype(int)
        result = result.sort_values(by=["년월", "_day_int", "브랜드", "리조트명", "객실타입"]).drop(columns=["_day_int"])
    except Exception as e:
        print(f"[경고] 정렬 중 오류 발생: {e}")
    print(f"\n총 {len(result)}건 로드 완료\n")
    return result

# ============================================================
# HTML 생성
# ============================================================

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>휴양소 예약가능 현황</title>
<link rel="stylesheet" as="style" crossorigin href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.css" />
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  /* Default Light Mode */
  --bg: #f4f6f5;
  --card: #ffffff;
  --card-hover: #f9fafb;
  --border: #e2e8f0;
  --border-hover: #cbd5e1;
  --text: #1f2937;
  --text-muted: #6b7280;
  --header-bg: #0A6E4F;
  --header-border: rgba(255, 255, 255, 0.15);
  --header-text: #ffffff;
  --header-text-muted: rgba(255, 255, 255, 0.85);
  --filter-bg: rgba(255, 255, 255, 0.85);
  --filter-border: rgba(0, 0, 0, 0.06);
  --select-bg: #ffffff;
  --select-option-bg: #ffffff;
  --select-option-color: #1f2937;
  --chip-bg: #ffffff;
  --chip-hover-bg: #f3f4f6;
  --accent-text: #059669;
  
  --리솜: #059669;
  --한화: #ea580c;
  --소노: #2563eb;
  --롯데: #dc2626;

  --bubble-bg: #ffffff;
  --bubble-border: #cbd5e1;
  --bubble-text: #4b5563;
  --bubble-title: #111827;
  --bubble-strong: #059669;
  --top-btn-bg: #0A6E4F;
}
body.dark-mode{
  /* Dark Mode Override */
  --bg: #090b11;
  --card: rgba(20, 24, 38, 0.6);
  --card-hover: rgba(28, 33, 53, 0.85);
  --border: rgba(255, 255, 255, 0.07);
  --border-hover: rgba(255, 255, 255, 0.15);
  --text: #f3f4f6;
  --text-muted: #9ca3af;
  --header-bg: rgba(9, 11, 17, 0.8);
  --header-border: rgba(255, 255, 255, 0.07);
  --header-text: #ffffff;
  --header-text-muted: #9ca3af;
  --filter-bg: rgba(15, 18, 28, 0.4);
  --filter-border: rgba(255, 255, 255, 0.07);
  --select-bg: rgba(255, 255, 255, 0.05);
  --select-option-bg: #111827;
  --select-option-color: #f3f4f6;
  --chip-bg: rgba(255, 255, 255, 0.04);
  --chip-hover-bg: rgba(255, 255, 255, 0.08);
  --accent-text: #a5b4fc;
  
  --리솜: #10b981;
  --한화: #f97316;
  --소노: #3b82f6;
  --롯데: #f43f5e;

  --bubble-bg: rgba(15, 23, 42, 0.98);
  --bubble-border: rgba(255, 255, 255, 0.12);
  --bubble-text: #9ca3af;
  --bubble-title: #ffffff;
  --bubble-strong: #a5b4fc;
  --top-btn-bg: rgba(30, 41, 59, 0.85);
}
body{
  background: var(--bg);
  color: var(--text);
  font-family: Pretendard, -apple-system, sans-serif;
  font-size: 14px;
  padding-bottom: 80px;
  min-height: 100vh;
  letter-spacing: -0.3px;
  transition: background 0.3s, color 0.3s;
}
body.dark-mode{
  background-image: radial-gradient(circle at 10% 20%, rgba(90, 120, 250, 0.05) 0%, transparent 40%),
                    radial-gradient(circle at 90% 80%, rgba(250, 90, 120, 0.03) 0%, transparent 40%);
}
header{
  background: var(--header-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--header-border);
  padding: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  justify-content: space-between;
  align-items: center;
  transition: background 0.3s, border-color 0.3s;
}
header h1{
  font-size: 18px;
  font-weight: 800;
  color: var(--header-text);
}
body.dark-mode header h1{
  background: linear-gradient(135deg, #fff 30%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
header p{
  font-size: 11px;
  color: var(--header-text-muted);
  font-weight: 500;
}
.update-info-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
}
.info-container {
  position: relative;
  display: inline-block;
  height: 20px;
}
.info-trigger, .theme-toggle {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid var(--header-border);
  color: rgba(255, 255, 255, 0.9);
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  padding: 0;
  outline: none;
  text-decoration: none;
  font-size: 11px;
}
.info-trigger:hover, .info-trigger.active, .theme-toggle:hover {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.6);
  color: #ffffff;
}
body.dark-mode .info-trigger, body.dark-mode .theme-toggle {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  color: var(--text-muted);
}
body.dark-mode .info-trigger:hover, body.dark-mode .info-trigger.active, body.dark-mode .theme-toggle:hover {
  background: rgba(165, 180, 252, 0.15);
  border-color: rgba(165, 180, 252, 0.4);
  color: #a5b4fc;
}
.info-bubble {
  position: absolute;
  top: 30px;
  right: -10px;
  width: 280px;
  background: var(--bubble-bg);
  border: 1px solid var(--bubble-border);
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.08);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  z-index: 200;
  display: none;
  text-align: left;
}
body.dark-mode .info-bubble {
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.6), 0 8px 10px -6px rgba(0, 0, 0, 0.6);
}
.info-bubble.show {
  display: block;
  animation: infoBubbleFadeIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes infoBubbleFadeIn {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}
.info-bubble-arrow {
  position: absolute;
  top: -6px;
  right: 15px;
  width: 10px;
  height: 10px;
  background: var(--bubble-bg);
  border-top: 1px solid var(--bubble-border);
  border-left: 1px solid var(--bubble-border);
  transform: rotate(45deg);
}
.info-bubble-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--bubble-title);
  margin-bottom: 6px;
}
.info-bubble-divider {
  margin-top: 10px;
  border-top: 1px solid var(--bubble-border);
  padding-top: 8px;
}
.info-bubble-content {
  font-size: 11px;
  color: var(--bubble-text);
  line-height: 1.5;
}
.info-bubble-content strong {
  color: var(--bubble-strong);
  font-weight: 600;
  display: block;
  margin-top: 4px;
}

/* Dashboard Style */
.dashboard{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 8px;
  padding: 14px 16px 8px;
}
.dash-card{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
  text-align: center;
  transition: all 0.25s ease;
  cursor: pointer;
}
.dash-card:hover, .dash-card.active{
  border-color: var(--border-hover);
  transform: translateY(-2px);
}
.dash-card.active-all{ background: rgba(0, 0, 0, 0.05); border-color: rgba(0, 0, 0, 0.15); }
.dash-card.active-리솜{ background: rgba(16, 185, 129, 0.08); border-color: var(--리솜); }
.dash-card.active-한화{ background: rgba(249, 115, 22, 0.08); border-color: var(--한화); }
.dash-card.active-소노{ background: rgba(59, 130, 246, 0.08); border-color: var(--소노); }
.dash-card.active-롯데{ background: rgba(244, 63, 94, 0.08); border-color: var(--롯데); }

body.dark-mode .dash-card.active-all{ background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.2); }
body.dark-mode .dash-card.active-리솜{ background: rgba(16, 185, 129, 0.15); border-color: var(--리솜); }
body.dark-mode .dash-card.active-한화{ background: rgba(249, 115, 22, 0.15); border-color: var(--한화); }
body.dark-mode .dash-card.active-소노{ background: rgba(59, 130, 246, 0.15); border-color: var(--소노); }
body.dark-mode .dash-card.active-롯데{ background: rgba(244, 63, 94, 0.15); border-color: var(--롯데); }

.dash-name{ font-size: 11px; color: var(--text-muted); font-weight: 600; margin-bottom: 2px; }
.dash-val{ font-size: 16px; font-weight: 800; }
.dash-val.val-리솜{ color: var(--리솜); }
.dash-val.val-한화{ color: var(--한화); }
.dash-val.val-소노{ color: var(--소노); }
.dash-val.val-롯데{ color: var(--롯데); }
.dash-time{ font-size: 9px; color: var(--text-muted); margin-top: 4px; font-weight: 500; display: block; }
.dash-time.warning{ color: #ef4444; font-weight: 700; }

/* Filter Section */
.filter-section{
  background: var(--filter-bg);
  border-bottom: 1px solid var(--filter-border);
  padding: 12px 16px;
  position: sticky;
  top: 61px;
  z-index: 90;
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: background 0.3s, border-color 0.3s;
}
.search-wrapper{
  position: relative;
  width: 100%;
}
.search-input{
  width: 100%;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 12px 8px 32px;
  color: var(--text);
  font-size: 13px;
  outline: none;
  transition: all 0.2s;
}
.search-input:focus{
  border-color: rgba(165, 180, 252, 0.4);
  background: rgba(255, 255, 255, 0.08);
}
.search-icon{
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  pointer-events: none;
}

/* Yoil Filter Styles */
.yoil-filter-container{
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  padding: 2px 0;
  flex-wrap: wrap;
  gap: 8px;
}
.yoil-left-group {
  display: flex;
  align-items: center;
  gap: 12px;
}
.yoil-label{
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 700;
}
.yoil-chips{
  display: flex;
  gap: 6px;
}
.yoil-chip{
  background: var(--chip-bg);
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
}
.yoil-chip:hover{
  background: var(--chip-hover-bg);
  color: var(--text);
}

/* Rate Dropdown Styles */
.rate-dropdown {
  position: relative;
  display: inline-block;
}
.rate-dropdown-btn {
  background: var(--chip-bg);
  border: 1px solid var(--border);
  color: var(--text-muted);
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s ease;
  outline: none;
}
.rate-dropdown-btn:hover {
  background: var(--chip-hover-bg);
  color: var(--text);
  border-color: var(--border-hover);
}
.rate-dropdown-content {
  display: none;
  position: absolute;
  right: 0;
  background-color: var(--bubble-bg);
  min-width: 210px;
  box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.06);
  border: 1px solid var(--bubble-border);
  border-radius: 8px;
  z-index: 150;
  overflow: hidden;
}
body.dark-mode .rate-dropdown-content {
  box-shadow: 0px 8px 16px 0px rgba(0,0,0,0.5);
}
.rate-dropdown-content a {
  color: var(--text);
  padding: 8px 12px;
  text-decoration: none;
  display: block;
  font-size: 12px;
  font-weight: 500;
  transition: background-color 0.2s;
  text-align: left;
}
.rate-dropdown-content a:hover {
  background-color: var(--chip-hover-bg);
  color: var(--accent-text);
}
.rate-dropdown.active .rate-dropdown-content {
  display: block;
}
.yoil-chip.active{
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  border-color: #6366f1;
  color: #fff;
  box-shadow: 0 0 10px rgba(99, 102, 241, 0.35);
}

.filter-dropdowns{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
}
.filter-dropdowns select{
  width: 100%;
  background: var(--select-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 20px 6px 8px;
  color: var(--text);
  font-size: 12px;
  outline: none;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  transition: all 0.2s;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239ca3af' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 6px center;
}
.filter-dropdowns select:focus{
  border-color: rgba(165, 180, 252, 0.4);
}
.filter-dropdowns select:disabled{
  opacity: 0.3;
  cursor: not-allowed;
}
.filter-dropdowns select option{
  background-color: var(--select-option-bg);
  color: var(--select-option-color);
}

/* Control & Summary Info */
.info-bar{
  padding: 8px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--text-muted);
}
.info-bar strong{
  color: var(--accent-text);
  font-weight: 700;
  font-size: 13px;
}
.reset-btn{
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.reset-btn:hover{
  background: var(--chip-hover-bg);
  border-color: var(--border-hover);
}

/* Card List */
.list{
  padding: 0 16px 24px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.card{
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  overflow: hidden;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  animation: cardFadeIn 0.35s cubic-bezier(0.16, 1, 0.3, 1) both;
}
@keyframes cardFadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.card:hover{
  background: var(--card-hover);
  border-color: var(--border-hover);
  transform: translateY(-3px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.05);
}
body.dark-mode .card:hover{
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
}
.card::before{
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
}
.card-리솜::before{ background: var(--리솜); }
.card-한화::before{ background: var(--한화); }
.card-소노::before{ background: var(--소노); }
.card-롯데::before{ background: var(--롯데); }

.card-top{
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.resort-name{
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.brand-tag{
  font-size: 10px;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 20px;
  text-transform: uppercase;
}
.tag-리솜{ background: rgba(16, 185, 129, 0.12); color: var(--리솜); border: 1.5px solid rgba(16, 185, 129, 0.2); }
.tag-한화{ background: rgba(249, 115, 22, 0.12); color: var(--한화); border: 1.5px solid rgba(249, 115, 22, 0.2); }
.tag-소노{ background: rgba(59, 130, 246, 0.12); color: var(--소노); border: 1.5px solid rgba(59, 130, 246, 0.2); }
.tag-롯데{ background: rgba(244, 63, 94, 0.12); color: var(--롯데); border: 1.5px solid rgba(244, 63, 94, 0.2); }

.card-mid{
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 4px 0;
}
.info-row{
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.info-label{
  color: var(--text-muted);
}
.info-val{
  font-weight: 600;
  color: var(--text);
}
.info-val.avail-cnt{
  font-size: 13px;
  font-weight: 800;
}
.avail-리솜{ color: var(--리솜); }
.avail-한화{ color: var(--한화); }
.avail-소노{ color: var(--소노); }
.avail-롯데{ color: var(--롯데); }

.card-bot{
  font-size: 10px;
  color: var(--text-muted);
  border-top: 1px solid var(--border);
  padding-top: 6px;
  display: flex;
  justify-content: space-between;
}

.empty{
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 14px;
}

/* Floating Actions */
.top-btn{
  position: fixed;
  bottom: 24px;
  right: 18px;
  width: 44px;
  height: 44px;
  background: var(--top-btn-bg);
  border: 1px solid var(--border);
  backdrop-filter: blur(8px);
  color: #fff;
  border-radius: 50%;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0,0,0,.08);
  opacity: 0;
  pointer-events: none;
  transition: all .25s ease;
  transform: translateY(8px);
  z-index: 100;
}
body.dark-mode .top-btn{
  box-shadow: 0 4px 12px rgba(0,0,0,.3);
}
.top-btn.show{
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}
.top-btn:hover{
  background: var(--top-btn-bg);
  transform: scale(1.05);
  opacity: 0.95;
}


@media(max-width: 640px) {
  header h1 {
    font-size: 15px;
  }
  .update-info-wrapper {
    position: static;
  }
  .info-container {
    position: static;
  }
  .info-bubble {
    left: 12px;
    right: 12px;
    width: auto;
    top: 50px;
  }
  .info-bubble-arrow {
    right: 100px;
  }
  .dashboard{
    gap: 4px;
    padding: 10px 8px 6px;
  }
  .dash-card{
    padding: 6px;
    border-radius: 8px;
  }
  .dash-name{
    font-size: 9px;
  }
  .dash-val{
    font-size: 13px;
  }
  .filter-section{
    padding: 8px 10px;
    top: 57px;
  }
  .yoil-filter-container {
    gap: 8px;
  }
  .yoil-chip {
    padding: 4px 10px;
    font-size: 11px;
  }
  .filter-dropdowns{
    grid-template-columns: repeat(3, 1fr);
  }
  .filter-dropdowns select{
    font-size: 11px;
  }
  .list{
    padding: 0 8px 20px;
    grid-template-columns: 1fr;
  }
}
</style>
</head>
<body>
<header>
  <h1>휴양소 예약가능 현황</h1>
  <div class="update-info-wrapper">
    <button class="theme-toggle" id="themeToggleBtn" onclick="toggleTheme(event)" title="다크 모드 전환">🌙</button>
    <a class="info-trigger" href="mailto:kelixx@hanafn.com" title="메일 발송">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
        <polyline points="22,6 12,13 2,6"></polyline>
      </svg>
    </a>
    <div class="info-container">
      <button class="info-trigger" onclick="toggleInfoBubble(event)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
          <line x1="12" y1="17" x2="12.01" y2="17"></line>
        </svg>
      </button>
      <div class="info-bubble" id="infoBubble">
        <div class="info-bubble-arrow"></div>
        <div class="info-bubble-title">💡 데이터 수집 안내</div>
        <div class="info-bubble-content">
          평일 기준 2시간 단위로 하루 총 5회 수집됩니다.
          <strong>수집 시간: 월~금 08:00, 10:00, 12:00, 14:00, 16:00</strong>
        </div>
        <div class="info-bubble-title info-bubble-divider">📢 서비스 이용 유의사항</div>
        <div class="info-bubble-content">
          본 웹페이지는 임직원 편의를 위해 임시 구축된 시스템으로 일시적인 오류가 발생할 수 있습니다. 아울러 대시보드에 잔여 객실이 표시되더라도 리조트별 사내 예약 한도 정책에 따라 실제 예약이 불가할 수 있으니, 예약 진행 전 반드시 사내 담당 직원에게 가능 여부를 확인해 주시기 바랍니다.
        </div>
        <div class="info-bubble-title info-bubble-divider">📬 기능개선 & 오류제보</div>
        <div class="info-bubble-content">
          시스템 개선 요청, 오류 신고 및 기타 문의 사항은 좌측 '메일 발송' 기능을 통해 담당자에게 전달해 주시면 감사하겠습니다.
        </div>
      </div>
    </div>
    <p>__UPDATED__ 기준</p>
  </div>
</header>

<div class="dashboard">
  <div class="dash-card active active-all" onclick="setBrand('')" data-brand="">
    <div class="dash-name">전체</div>
    <div class="dash-val" id="cnt-all">0</div>
    <div class="dash-time" style="opacity: 0;">-</div>
  </div>
  <div class="dash-card" onclick="setBrand('리솜')" data-brand="리솜">
    <div class="dash-name">리솜</div>
    <div class="dash-val val-리솜" id="cnt-리솜">0</div>
    <div class="dash-time" id="time-리솜">-</div>
  </div>
  <div class="dash-card" onclick="setBrand('한화')" data-brand="한화">
    <div class="dash-name">한화</div>
    <div class="dash-val val-한화" id="cnt-한화">0</div>
    <div class="dash-time" id="time-한화">-</div>
  </div>
  <div class="dash-card" onclick="setBrand('소노')" data-brand="소노">
    <div class="dash-name">소노</div>
    <div class="dash-val val-소노" id="cnt-소노">0</div>
    <div class="dash-time" id="time-소노">-</div>
  </div>
  <div class="dash-card" onclick="setBrand('롯데')" data-brand="롯데">
    <div class="dash-name">롯데</div>
    <div class="dash-val val-롯데" id="cnt-롯데">0</div>
    <div class="dash-time" id="time-롯데">-</div>
  </div>
</div>


<div class="filter-section">
  <div class="yoil-filter-container">
    <div class="yoil-left-group">
      <span class="yoil-label">요일 퀵 필터 :</span>
      <div class="yoil-chips">
        <button class="yoil-chip" onclick="toggleYoil(this)" data-yoil="금">금</button>
        <button class="yoil-chip" onclick="toggleYoil(this)" data-yoil="토">토</button>
        <button class="yoil-chip" onclick="toggleYoil(this)" data-yoil="일">일</button>
      </div>
    </div>
    <div class="rate-dropdown" id="rateDropdown">
      <button class="rate-dropdown-btn" onclick="toggleRateDropdown(event)">📁 객실 요금표 ▾</button>
      <div class="rate-dropdown-content">
        <a href="요금표/리솜/2026년+객실이용요금표(+레스트리+키즈룸).pdf" target="_blank">리솜 객실 요금표</a>
        <a href="요금표/한화/2026년_회원요금표.xlsx" download>한화 객실 요금표</a>
        <a href="요금표/소노/2026년+소노리조트_회원요금표_260716+까지.pdf" target="_blank">소노 객실 요금표 (~26.07.16)</a>
        <a href="요금표/소노/2026년+소노리조트_회원요금표_260717~270715.pdf" target="_blank">소노 객실 요금표 (26.07.17~)</a>
        <a href="요금표/롯데/2026년 객실 요금표_속초부여.pdf" target="_blank">롯데 객실 요금표 (속초/부여)</a>
        <a href="요금표/롯데/2026년 객실 요금표_김해.pdf" target="_blank">롯데 객실 요금표 (김해)</a>
      </div>
    </div>
  </div>

  <div class="filter-dropdowns">
    <select id="s-region" onchange="onDropdownChange()"><option value="">지역 전체</option></select>
    <select id="s-resort" onchange="onDropdownChange()"><option value="">리조트 지점</option></select>
    <select id="s-month" onchange="onMonthChange()"><option value="">조회 월</option></select>
    <select id="s-day" onchange="onDropdownChange()" disabled><option value="">조회 일</option></select>
    <select id="s-type" onchange="onDropdownChange()"><option value="">객실 타입</option></select>
  </div>
</div>

<div class="info-bar">
  <span>검색결과: <strong id="cnt">0</strong>건 예약가능</span>
  <button class="reset-btn" onclick="reset()">검색 필터 초기화</button>
</div>

<div class="list" id="list"></div>
<div id="sentinel" style="padding: 24px 0; text-align: center; width: 100%; color: var(--text-muted); font-size: 13px; font-weight: 500; display: none;">
  <span id="sentinel-text">불러오는 중...</span>
</div>

<script>
const DATA = __DATA_JSON__;
const UPDATED_TIMES = __UPDATED_TIMES_JSON__;
let curBrand = '';
let activeRows = [];
let renderedCount = 0;
const PAGE_SIZE = 60;
let observer = null;

// 상수 매핑 기법 (배열 인덱스 매칭으로 용량 압축)
const BRAND  = 0;  // 브랜드 (리솜, 한화 등)
const RESORT = 1;  // 리조트 지점명
const REGION = 2;  // 권역 (충청, 강원 등)
const MONTH  = 3;  // 년월
const DAY    = 4;  // 일
const YOIL   = 5;  // 요일
const TYPE   = 6;  // 객실타입
const COUNT  = 7;  // 예약가능수

function uniq(arr){return [...new Set(arr.filter(Boolean))].sort((a,b)=>isNaN(a)?a.localeCompare(b,'ko'):Number(a)-Number(b));}

// Cascading Filter Logic: Get filtered dataset EXCEPT the specified select element filter
function getFilteredDataExcluding(excludeId) {
  const activeYoils = Array.from(document.querySelectorAll('.yoil-chip.active')).map(c => c.dataset.yoil);
  
  return DATA.filter(x => {
    if (excludeId !== 'brand' && curBrand && x[BRAND] !== curBrand) return false;
    if (excludeId !== 's-resort' && sel('s-resort') && x[RESORT] !== sel('s-resort')) return false;
    if (excludeId !== 's-region' && sel('s-region') && x[REGION] !== sel('s-region')) return false;
    if (excludeId !== 's-month' && sel('s-month') && x[MONTH] !== sel('s-month')) return false;
    if (excludeId !== 's-day' && sel('s-day') && x[DAY] !== sel('s-day')) return false;
    if (excludeId !== 's-type' && sel('s-type') && x[TYPE] !== sel('s-type')) return false;
    
    // Always filter by Yoil
    if (activeYoils.length > 0 && !activeYoils.includes(x[YOIL])) return false;
    
    return true;
  });
}

function filtered(){
  return getFilteredDataExcluding(null);
}

function sel(id){return document.getElementById(id).value;}

function pop(id, vals, ph){
  const el=document.getElementById(id);
  const cur=el.value;
  el.innerHTML=`<option value="">${ph}</option>`+vals.map(v=>`<option${v===cur?' selected':''}>${v}</option>`).join('');
}

function base(){
  return DATA.filter(x=>!curBrand||x[BRAND]===curBrand);
}


function setBrand(b){
  curBrand=b;
  document.querySelectorAll('.dash-card').forEach(card=>{
    const bv=card.dataset.brand;
    card.className='dash-card'+(b===bv?' active active-'+(b||'all'):'');
  });
  
  // Reset child dropdowns when changing brand
  ['s-region','s-resort','s-month','s-day','s-type'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('s-day').disabled=true;
  
  refreshFilters();
  apply();
}

function refreshFilters(){
  const ids = ['s-region', 's-resort', 's-month', 's-day', 's-type'];
  const oldVals = ids.map(id => document.getElementById(id).value);
  
  // Populate dropdown options dynamically based on other active filters (Cascading)
  pop('s-resort', uniq(getFilteredDataExcluding('s-resort').map(x => x[RESORT])), '리조트 지점');
  pop('s-region', uniq(getFilteredDataExcluding('s-region').map(x => x[REGION])), '지역 전체');
  pop('s-month',  uniq(getFilteredDataExcluding('s-month').map(x => x[MONTH])), '조회 월');
  
  const m = sel('s-month');
  const dayEl = document.getElementById('s-day');
  if (!m) {
    dayEl.innerHTML = '<option value="">조회 일</option>';
    dayEl.disabled = true;
  } else {
    const uniqueDays = uniq(getFilteredDataExcluding('s-day').map(x => x[DAY]));
    const filteredForDay = getFilteredDataExcluding('s-day');
    const dayOpts = uniqueDays.map(d => {
      const found = filteredForDay.find(x => x[DAY] === d && x[MONTH] === m);
      const yoil = found ? found[YOIL] : '';
      return {
        value: d,
        text: d + (yoil ? ` (${yoil})` : '')
      };
    });
    
    const curVal = dayEl.value;
    dayEl.innerHTML = '<option value="">조회 일</option>' + dayOpts.map(opt => {
      const selected = opt.value === curVal ? ' selected' : '';
      return `<option value="${opt.value}"${selected}>${opt.text}</option>`;
    }).join('');
    
    dayEl.disabled = false;
  }
  
  pop('s-type', uniq(getFilteredDataExcluding('s-type').map(x => x[TYPE])), '객실 타입');
  
  // Re-check value change programmatically
  const newVals = ids.map(id => document.getElementById(id).value);
  let changed = false;
  for (let i = 0; i < ids.length; i++) {
    if (oldVals[i] !== newVals[i]) {
      changed = true;
      break;
    }
  }
  if (changed) {
    refreshFilters();
  }
}

function onDropdownChange() {
  // Brand auto-matching: If resort is selected, automatically activate its brand card!
  const resortVal = sel('s-resort');
  if (resortVal) {
    const matched = DATA.find(x => x[RESORT] === resortVal);
    if (matched && matched[BRAND]) {
      curBrand = matched[BRAND];
      document.querySelectorAll('.dash-card').forEach(card => {
        const bv = card.dataset.brand;
        card.className = 'dash-card' + (curBrand === bv ? ' active active-' + (curBrand || 'all') : '');
      });
    }
  }
  refreshFilters();
  apply();
}

function onMonthChange(){
  const m = sel('s-month');
  const dayEl = document.getElementById('s-day');
  if (!m) {
    dayEl.value = '';
    dayEl.disabled = true;
  }
  refreshFilters();
  apply();
}

function toggleYoil(btn) {
  btn.classList.toggle('active');
  refreshFilters();
  apply();
}

function refreshDashboard() {
  document.getElementById('cnt-all').textContent = DATA.length.toLocaleString();
  
  const now = new Date();
  
  ['리솜', '한화', '소노', '롯데'].forEach(brand => {
    const count = DATA.filter(x => x[BRAND] === brand).length;
    document.getElementById('cnt-' + brand).textContent = count.toLocaleString();
    
    const timeEl = document.getElementById('time-' + brand);
    if (timeEl && UPDATED_TIMES[brand]) {
      const tStr = UPDATED_TIMES[brand];
      if (tStr === '-') {
        timeEl.textContent = '수집 데이터 없음';
        timeEl.classList.add('warning');
      } else {
        try {
          const parts = tStr.split(' ');
          const dateParts = parts[0].split('-');
          const timeParts = parts[1].split(':');
          const fileDate = new Date(
            parseInt(dateParts[0]),
            parseInt(dateParts[1]) - 1,
            parseInt(dateParts[2]),
            parseInt(timeParts[0]),
            parseInt(timeParts[1])
          );
          
          const diffMs = now - fileDate;
          const diffHrs = diffMs / (1000 * 60 * 60);
          
          const displayTime = `${dateParts[1]}-${dateParts[2]} ${parts[1]}`;
          
          if (diffHrs >= 24) {
            timeEl.innerHTML = `⚠ ${displayTime}`;
            timeEl.classList.add('warning');
            timeEl.title = `마지막 수집 후 24시간 초과 (${tStr})`;
          } else {
            timeEl.textContent = displayTime;
            timeEl.classList.remove('warning');
            timeEl.title = `수집일시: ${tStr}`;
          }
        } catch (e) {
          timeEl.textContent = tStr;
        }
      }
    }
  });
}

function apply(){
  activeRows = filtered();
  document.getElementById('cnt').textContent = activeRows.length.toLocaleString();
  
  const list = document.getElementById('list');
  list.innerHTML = ''; // Clear existing cards
  renderedCount = 0;
  
  const sentinel = document.getElementById('sentinel');
  const sentinelText = document.getElementById('sentinel-text');
  
  if (!activeRows.length) {
    list.innerHTML = '<div class="empty">조건에 맞는 예약가능 객실이 없습니다.</div>';
    sentinel.style.display = 'none';
    return;
  }
  
  sentinel.style.display = 'block';
  sentinelText.textContent = '불러오는 중...';
  
  // Load initial batch
  loadMore();
  
  // Initialize intersection observer if not already done
  if (!observer) {
    observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        loadMore();
      }
    }, { rootMargin: '250px' });
    observer.observe(sentinel);
  }
}

function loadMore() {
  if (renderedCount >= activeRows.length) {
    document.getElementById('sentinel-text').textContent = '모든 예약가능 객실을 조회했습니다.';
    return;
  }
  
  const list = document.getElementById('list');
  const nextBatch = activeRows.slice(renderedCount, renderedCount + PAGE_SIZE);
  
  const html = nextBatch.map(d => {
    const avail = d[COUNT] && d[COUNT] !== '1' ? `${d[COUNT]}실 가능` : '예약가능';
    const region = d[REGION] ? d[REGION] : '-';
    
    // 날짜 포맷팅: 2026.07 -> 2026년 07월, 일 -> 04일
    let dateDisplay = `${d[MONTH]} ${d[DAY]}일`;
    try {
      const parts = d[MONTH].split('.');
      if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {
        const yStr = parts[0] + '년';
        const mStr = parts[1].padStart(2, '0') + '월';
        const dStr = d[DAY].padStart(2, '0') + '일';
        dateDisplay = `${yStr} ${mStr} ${dStr}`;
      }
    } catch (err) {}

    let yoilSpan = d[YOIL] ? `(${d[YOIL]})` : '';
    
    return `
<div class="card card-${d[BRAND]}">
  <div class="card-top">
    <span class="resort-name">${d[RESORT] || '-'}</span>
    <span class="brand-tag tag-${d[BRAND]}">${d[BRAND]}</span>
  </div>
  <div class="card-mid">
    <div class="info-row">
      <span class="info-label">투숙 날짜</span>
      <span class="info-val">${dateDisplay}${yoilSpan}</span>
    </div>
    <div class="info-row">
      <span class="info-label">지역 분류</span>
      <span class="info-val">${region}</span>
    </div>
    <div class="info-row">
      <span class="info-label">객실타입</span>
      <span class="info-val">${d[TYPE] || '-'}</span>
    </div>
    <div class="info-row">
      <span class="info-label">잔여 상태</span>
      <span class="info-val avail-cnt avail-${d[BRAND]}">${avail}</span>
    </div>
  </div>
</div>`;
  }).join('');
  
  list.insertAdjacentHTML('beforeend', html);
  renderedCount += nextBatch.length;
  
  if (renderedCount >= activeRows.length) {
    document.getElementById('sentinel-text').textContent = '모든 예약가능 객실을 조회했습니다.';
  }
}

function reset(){
  ['s-region','s-resort','s-month','s-day','s-type'].forEach(id=>document.getElementById(id).value='');
  document.getElementById('s-day').disabled=true;
  document.querySelectorAll('.yoil-chip').forEach(c => c.classList.remove('active'));
  refreshFilters();
  apply();
}

function toggleInfoBubble(event) {
  event.stopPropagation();
  const bubble = document.getElementById('infoBubble');
  const trigger = event.currentTarget;
  const isShow = bubble.classList.toggle('show');
  trigger.classList.toggle('active', isShow);
}

function toggleRateDropdown(event) {
  if (event) event.stopPropagation();
  const dropdown = document.getElementById('rateDropdown');
  if (dropdown) {
    dropdown.classList.toggle('active');
  }
}

document.addEventListener('click', (e) => {
  const bubble = document.getElementById('infoBubble');
  const trigger = document.querySelector('.info-trigger');
  if (bubble && bubble.classList.contains('show')) {
    if (!bubble.contains(e.target) && !trigger.contains(e.target)) {
      bubble.classList.remove('show');
      trigger.classList.remove('active');
    }
  }
  
  const dropdown = document.getElementById('rateDropdown');
  if (dropdown && dropdown.classList.contains('active')) {
    if (!dropdown.contains(e.target)) {
      dropdown.classList.remove('active');
    }
  }
});

function toggleTheme(event) {
  if (event) event.stopPropagation();
  const body = document.body;
  const btn = document.getElementById('themeToggleBtn');
  const isDark = body.classList.toggle('dark-mode');
  
  if (isDark) {
    btn.textContent = '☀️';
    btn.title = '라이트 모드 전환';
    localStorage.setItem('theme', 'dark');
  } else {
    btn.textContent = '🌙';
    btn.title = '다크 모드 전환';
    localStorage.setItem('theme', 'light');
  }
}

function initTheme() {
  const savedTheme = localStorage.getItem('theme');
  const body = document.body;
  const btn = document.getElementById('themeToggleBtn');
  
  if (savedTheme === 'dark') {
    body.classList.add('dark-mode');
    if (btn) {
      btn.textContent = '☀️';
      btn.title = '라이트 모드 전환';
    }
  } else {
    body.classList.remove('dark-mode');
    if (btn) {
      btn.textContent = '🌙';
      btn.title = '다크 모드 전환';
    }
  }
}

// 초기화
refreshDashboard();
refreshFilters();
apply();
initTheme();

window.addEventListener('scroll',()=>{
  document.getElementById('topBtn').classList.toggle('show',window.scrollY>200);
},{passive:true});
</script>

<button class="top-btn" id="topBtn" onclick="window.scrollTo({top:0,behavior:'smooth'})">
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
    <path d="M9 14V5M9 5L4.5 9.5M9 5L13.5 9.5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</button>
</body>
</html>
"""

def get_file_update_times():
    times = {}
    kst = timezone(timedelta(hours=9))
    for brand, cfg in BRAND_CONFIG.items():
        f = find_latest(brand, cfg)
        if f:
            mtime = os.path.getmtime(f)
            # Convert timestamp to UTC datetime, then convert to KST timezone
            dt = datetime.fromtimestamp(mtime, tz=timezone.utc).astimezone(kst)
            times[brand] = dt.strftime("%Y-%m-%d %H:%M")
        else:
            times[brand] = "-"
    return times

def generate(df):
    export_cols = ["브랜드", "리조트명", "지역", "년월", "일", "요일", "객실타입", "예약가능수"]
    data_list = df[export_cols].values.tolist()
    data_json = json.dumps(data_list, ensure_ascii=False)
    kst = timezone(timedelta(hours=9))
    updated   = datetime.now(tz=kst).strftime("%m-%d %H:%M")
    updated_times = get_file_update_times()
    updated_times_json = json.dumps(updated_times, ensure_ascii=False)
    
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json) \
                         .replace("__UPDATED__", updated) \
                         .replace("__UPDATED_TIMES_JSON__", updated_times_json)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[완료] HTML 생성: {OUTPUT_HTML}  ({len(df)}건)")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brand", nargs="*", default=list(BRAND_CONFIG.keys()),
                        help="브랜드 선택 (기본: 전체)")
    args = parser.parse_args()
    df = load_data(args.brand)
    generate(df)

if __name__ == "__main__":
    main()
