#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리조트 예약현황 HTML 변환 스크립트
- 엑셀(.xlsx), CSV(.csv), 텍스트(.txt) 지원
- 상태='예약가능' 자동 필터링
- 단일 HTML 파일 생성

사용법:
  python convert_to_html.py                  # 자동 탐색 (현재 폴더)
  python convert_to_html.py 파일1.xlsx 파일2.csv
  python convert_to_html.py --folder ./data  # 특정 폴더
"""

import sys
import os
import json
import glob
import argparse
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("[오류] pandas가 없습니다. 설치: pip install pandas openpyxl")
    sys.exit(1)

try:
    import openpyxl  # noqa: F401
except ImportError:
    print("[오류] openpyxl이 없습니다. 설치: pip install openpyxl")
    sys.exit(1)

REQUIRED_COLS    = ["수집일시", "월", "일", "지역", "평형", "객실타입", "리조트", "상태"]
STATUS_AVAILABLE = "예약가능"
OUTPUT_FILE      = "resort_availability.html"

def read_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".xlsx", ".xls"):
        return None
    try:
        df = pd.read_excel(path, dtype=str)
        df.columns = df.columns.str.strip()
        print(f"  [읽기완료] {os.path.basename(path)} — {len(df)}행")
        return df
    except Exception as e:
        print(f"  [오류] {path}: {e}")
        return None

def normalize_columns(df):
    aliases = {
        "수집일시": ["수집일시", "수집 일시", "datetime", "date_time", "collected_at"],
        "월":      ["월", "month", "mon"],
        "일":      ["일", "day"],
        "지역":    ["지역", "region", "area", "location"],
        "평형":    ["평형", "size", "room_size", "평"],
        "객실타입":["객실타입", "객실 타입", "room_type", "type"],
        "리조트":  ["리조트", "resort", "resort_name"],
        "상태":    ["상태", "status", "availability"],
    }
    rename_map = {}
    for canonical, alts in aliases.items():
        for col in df.columns:
            if col.strip() in alts:
                rename_map[col] = canonical
                break
    return df.rename(columns=rename_map)

def collect_data(files):
    frames = []
    for f in files:
        df = read_file(f)
        if df is None:
            continue
        df = normalize_columns(df)
        missing = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing:
            print(f"  [경고] 컬럼 누락 {os.path.basename(f)}: {missing}")
        frames.append(df)

    if not frames:
        print("[오류] 읽을 수 있는 파일이 없습니다.")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    for col in REQUIRED_COLS:
        if col not in combined.columns:
            combined[col] = ""

    combined = combined[REQUIRED_COLS].copy()
    combined = combined.fillna("").apply(lambda col: col.map(lambda x: str(x).strip()))

    before = len(combined)
    combined = combined[combined["상태"] == STATUS_AVAILABLE]
    print(f"\n총 {before}행 → 예약가능 필터 후 {len(combined)}행")
    return combined

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>(Beta) 리솜 리조트 예약가능 현황</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f5f5f0;--card:#fff;--border:#e0ddd5;
  --text:#1a1a18;--muted:#6b6b68;--accent:#0F6E56;
  --tag-dk:#E1F5EE;--tag-dk-t:#085041;
  --tag-an:#EEEDFE;--tag-an-t:#26215C;
  --tag-jc:#FAECE7;--tag-jc-t:#4A1B0C;
  --tag-etc:#F1EFE8;--tag-etc-t:#2C2C2A;
}
body{background:var(--bg);color:var(--text);font-family:-apple-system,'Apple SD Gothic Neo',Pretendard,sans-serif;font-size:15px;padding-bottom:60px}
header{background:var(--accent);color:#fff;padding:13px 16px 11px;position:sticky;top:0;z-index:10}
header h1{font-size:16px;font-weight:600;letter-spacing:-.3px}
header p{font-size:11px;opacity:.75;margin-top:3px}
.filters{background:#fff;border-bottom:1px solid var(--border);padding:10px 12px;display:flex;gap:7px;flex-wrap:wrap;position:sticky;top:50px;z-index:9}
.filters select{
  border:1px solid var(--border);border-radius:8px;
  padding:7px 10px;font-size:13px;background:#fafaf8;
  color:var(--text);flex:1;min-width:90px;max-width:160px;outline:none;
  transition:border-color .15s
}
.filters select:focus{border-color:var(--accent)}
.filters select:disabled{opacity:.4;cursor:not-allowed}
.summary{padding:9px 14px;font-size:13px;color:var(--muted);display:flex;align-items:center;justify-content:space-between}
.summary strong{color:var(--accent);font-weight:600}
.reset-btn{font-size:12px;padding:4px 11px;background:transparent;color:var(--accent);border:1px solid var(--accent);border-radius:6px;cursor:pointer}
.list{padding:0 12px 24px;display:grid;gap:9px}
.card{background:var(--card);border-radius:12px;border:1px solid var(--border);padding:13px;display:flex;flex-direction:column;gap:6px}
.card-top{display:flex;align-items:center;justify-content:space-between}
.resort{font-size:15px;font-weight:600;letter-spacing:-.2px}
.rtag{font-size:11px;font-weight:600;padding:3px 9px;border-radius:20px}
.tag-dk{background:var(--tag-dk);color:var(--tag-dk-t)}
.tag-an{background:var(--tag-an);color:var(--tag-an-t)}
.tag-jc{background:var(--tag-jc);color:var(--tag-jc-t)}
.tag-etc{background:var(--tag-etc);color:var(--tag-etc-t)}
.card-mid{display:flex;gap:18px;flex-wrap:wrap}
.ii{display:flex;flex-direction:column;gap:2px}
.il{font-size:11px;color:var(--muted)}
.iv{font-size:13px;font-weight:500}
.card-bot{font-size:11px;color:var(--muted);border-top:1px solid var(--border);padding-top:6px}
.empty{text-align:center;padding:50px 20px;color:var(--muted);font-size:13px}
.top-btn{
  position:fixed;bottom:24px;right:18px;width:44px;height:44px;
  background:var(--accent);color:#fff;border:none;border-radius:50%;
  font-size:20px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 10px rgba(0,0,0,.18);
  opacity:0;pointer-events:none;
  transition:opacity .25s,transform .25s;
  transform:translateY(8px);
  z-index:100;
}
.top-btn.show{opacity:1;pointer-events:auto;transform:translateY(0)}
.top-btn:active{transform:scale(.92)}
</style>
</head>
<body>
<header>
  <h1>(Beta) 리솜 리조트 예약가능 현황</h1>
  <p>업데이트: __UPDATED__</p>
</header>

<div class="filters">
  <select id="s-region" onchange="onRegion()">
    <option value="">전체 지역</option>
    <option>덕산</option><option>안면도</option><option>제천</option>
  </select>
  <select id="s-month" onchange="onMonth()">
    <option value="">전체 월</option>
  </select>
  <select id="s-day" onchange="apply()" disabled>
    <option value="">전체 일</option>
  </select>
  <select id="s-size" onchange="apply()">
    <option value="">전체 평형</option>
  </select>
  <select id="s-type" onchange="apply()">
    <option value="">전체 타입</option>
  </select>
</div>

<div class="summary">
  <span><strong id="cnt">0</strong>건 예약가능</span>
  <button class="reset-btn" onclick="reset()">초기화</button>
</div>

<div class="list" id="list"></div>

<script>
const DATA = __DATA_JSON__;
const tagCls = {덕산:'tag-dk',안면도:'tag-an',제천:'tag-jc'};

function uniq(arr){return [...new Set(arr)].sort((a,b)=>Number(a)-Number(b));}

function populateSelect(id, vals, placeholder){
  const el = document.getElementById(id);
  const cur = el.value;
  el.innerHTML = `<option value="">${placeholder}</option>` +
    vals.map(v=>`<option${v===cur?' selected':''}>${v}</option>`).join('');
}

function onRegion(){
  const r = document.getElementById('s-region').value;
  const base = DATA.filter(x => !r || x.지역===r);
  populateSelect('s-month', uniq(base.map(x=>x.월)), '전체 월');
  document.getElementById('s-day').innerHTML = '<option value="">전체 일</option>';
  document.getElementById('s-day').disabled = true;
  populateSelect('s-size', uniq(base.map(x=>x.평형)), '전체 평형');
  populateSelect('s-type', uniq(base.map(x=>x.객실타입)), '전체 타입');
  apply();
}

function onMonth(){
  const m = document.getElementById('s-month').value;
  const dayEl = document.getElementById('s-day');
  if(!m){
    dayEl.innerHTML = '<option value="">전체 일</option>';
    dayEl.disabled = true;
  } else {
    const r = document.getElementById('s-region').value;
    const s = document.getElementById('s-size').value;
    const t = document.getElementById('s-type').value;
    const days = uniq(DATA.filter(x=>
      x.월===m && (!r||x.지역===r) && (!s||x.평형===s) && (!t||x.객실타입===t)
    ).map(x=>x.일));
    populateSelect('s-day', days, '전체 일');
    dayEl.disabled = false;
  }
  apply();
}

function apply(){
  const r = document.getElementById('s-region').value;
  const m = document.getElementById('s-month').value;
  const d = document.getElementById('s-day').value;
  const s = document.getElementById('s-size').value;
  const t = document.getElementById('s-type').value;
  const rows = DATA.filter(x=>
    (!r||x.지역===r) && (!m||x.월===m) && (!d||x.일===d) &&
    (!s||x.평형===s) && (!t||x.객실타입===t)
  );
  document.getElementById('cnt').textContent = rows.length.toLocaleString();
  const list = document.getElementById('list');
  if(!rows.length){
    list.innerHTML = '<div class="empty">조건에 맞는 예약가능 객실이 없습니다.</div>';
    return;
  }
  list.innerHTML = rows.map(d=>`
<div class="card">
  <div class="card-top">
    <span class="resort">${d.리조트}</span>
    <span class="rtag ${tagCls[d.지역]||'tag-etc'}">${d.지역}</span>
  </div>
  <div class="card-mid">
    <div class="ii"><span class="il">날짜</span><span class="iv">${d.월}월 ${d.일}일</span></div>
    <div class="ii"><span class="il">평형</span><span class="iv">${d.평형}</span></div>
    <div class="ii"><span class="il">객실타입</span><span class="iv">${d.객실타입}</span></div>
  </div>
  <div class="card-bot">수집일시: ${d.수집일시}</div>
</div>`).join('');
}

function reset(){
  ['s-region','s-month','s-day','s-size','s-type'].forEach(id=>{
    document.getElementById(id).value='';
  });
  document.getElementById('s-day').disabled = true;
  populateSelect('s-month', uniq(DATA.map(x=>x.월)), '전체 월');
  populateSelect('s-size',  uniq(DATA.map(x=>x.평형)), '전체 평형');
  populateSelect('s-type',  uniq(DATA.map(x=>x.객실타입)), '전체 타입');
  apply();
}

// 초기 옵션 세팅
populateSelect('s-month', uniq(DATA.map(x=>x.월)), '전체 월');
populateSelect('s-size',  uniq(DATA.map(x=>x.평형)), '전체 평형');
populateSelect('s-type',  uniq(DATA.map(x=>x.객실타입)), '전체 타입');
apply();
// 탑 버튼 스크롤 감지
window.addEventListener('scroll',()=>{
  document.getElementById('topBtn').classList.toggle('show', window.scrollY > 200);
},{passive:true});
</script>

<button class="top-btn" id="topBtn" onclick="window.scrollTo({top:0,behavior:'smooth'})" aria-label="맨 위로">
  <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M9 14V5M9 5L4.5 9.5M9 5L13.5 9.5" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
</button>
</body>
</html>
"""

def build_options(series):
    unique = sorted(set(v for v in series if v))
    return "\n".join(f'<option>{v}</option>' for v in unique)

def generate_html(df, output_path):
    data = df.to_dict(orient="records")
    data_json = json.dumps(data, ensure_ascii=False)
    updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = HTML_TEMPLATE
    html = html.replace("__DATA_JSON__", data_json)
    html = html.replace("__UPDATED__", updated)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[완료] HTML 생성: {output_path}  ({len(df)}건)")

def main():
    parser = argparse.ArgumentParser(description="리조트 예약현황 HTML 변환")
    parser.add_argument("files", nargs="*", help="입력 파일 (xlsx/xls)")
    parser.add_argument("--folder", default=".", help="데이터 폴더 경로")
    parser.add_argument("--output", default=OUTPUT_FILE, help="출력 HTML 파일명")
    parser.add_argument("--latest", action="store_true", help="가장 최근 파일 1개만 사용")
    args = parser.parse_args()

    if args.files:
        files = args.files
    else:
        patterns = ["*.xlsx", "*.xls"]
        files = []
        for p in patterns:
            files.extend(glob.glob(os.path.join(args.folder, p)))
        if not files:
            print(f"[오류] {args.folder} 폴더에 엑셀 파일이 없습니다.")
            sys.exit(1)

    if args.latest:
        # 파일명 내림차순 정렬 → 가장 마지막 이름(최신 날짜)을 선택
        latest = sorted(files, key=lambda f: os.path.basename(f))[-1]
        excluded = [os.path.basename(f) for f in files if f != latest]
        print(f"[최신파일] {os.path.basename(latest)}")
        if excluded:
            print(f"[제외파일] {excluded}")
        print()
        files = [latest]
    else:
        print(f"대상 파일: {[os.path.basename(f) for f in files]}\n")

    df = collect_data(files)
    generate_html(df, args.output)

if __name__ == "__main__":
    main()
