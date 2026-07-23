#!/bin/bash
# AWS ECS Fargate용 기동 셸 스크립트 (docker-entrypoint.sh)
set -e

echo "====================================================="
echo "  [AWS ECS Fargate Task] 컨테이너 초기화 및 실행 시작"
echo "  실행 시각: $(date)"
echo "  실행 모드 (JOB_TYPE): ${JOB_TYPE:-resort}"
echo "====================================================="

# AWS SNS를 이용해 오류/로그인 만료 발생 시 경보 메일 보낼 함수 정의
send_alert() {
    local job_name=$1
    local error_details=$2
    
    if [ -n "${SNS_TOPIC_ARN}" ]; then
        echo "  [경보 알림] AWS SNS를 통해 에러 경보 메일을 송신합니다... (대상: ${job_name})"
        
        local email_message="[휴양소 수집 자동화 시스템 장애 감지 알림]

작업 명칭: ${job_name}
발생 시각: $(date)

상세 장애 설명: 
${error_details}

★ 확인 사항:
1. 해당 리조트 사이트 혹은 사내 인사시스템의 3개월 비밀번호 변경 강제 주기 창이 표시되었는지 확인하십시오.
2. 수집 대상 사이트의 화면 디자인 또는 로그인 URL/API 구조가 개편되었는지 확인하십시오.
3. 자세한 실행 오류 로그(Traceback)는 AWS Console 내 CloudWatch Logs의 '/ecs/resort-automation-prod' 로그 그룹을 조회하십시오."

        aws sns publish \
            --topic-arn "${SNS_TOPIC_ARN}" \
            --subject "[경보] 휴양소/메뉴 수집 및 자동 업데이트 작업 실패 (${job_name})" \
            --message "${email_message}" || echo "  [경고] SNS 알림 발송 중 실패가 발생했습니다."
    else
        echo "  [주의] SNS_TOPIC_ARN 환경변수가 비어 있어 이메일 알림을 건너뜁니다."
    fi
}

# 1. AWS 환경변수를 기반으로 각 크롤러가 요구하는 .env 파일 동적 생성
echo "1. 수집용 루트 .env 파일 생성 중..."
cat <<EOF > /app/.env
RESOM_ID=${RESOM_ID}
RESOM_PW=${RESOM_PW}
DAEMYUNG_ID=${DAEMYUNG_ID}
DAEMYUNG_PW=${DAEMYUNG_PW}
LOTTE_ID=${LOTTE_ID}
LOTTE_PW=${LOTTE_PW}
HANHWA_ID=${HANHWA_ID}
HANHWA_PW=${HANHWA_PW}
HANHWA_MEMBERSHIP_PW=${HANHWA_MEMBERSHIP_PW}
EOF
echo "  -> 루트 .env 생성 완료."

echo "2. 사내 게시판 업데이트용 .env 파일 생성 중..."
mkdir -p /app/board_automation
cat <<EOF > /app/board_automation/.env
id : ${BOARD_ID}
Password : ${BOARD_PASSWORD}

POST_ID_LOTTE_M1=${POST_ID_LOTTE_M1}
POST_ID_LOTTE_M2=${POST_ID_LOTTE_M2}
POST_ID_LOTTE_M3=${POST_ID_LOTTE_M3}

POST_ID_RESOM_M1=${POST_ID_RESOM_M1}
POST_ID_RESOM_M2=${POST_ID_RESOM_M2}
POST_ID_RESOM_M3=${POST_ID_RESOM_M3}

POST_ID_SONO_M1=${POST_ID_SONO_M1}
POST_ID_SONO_M2=${POST_ID_SONO_M2}
POST_ID_SONO_M3=${POST_ID_SONO_M3}

POST_ID_HANHWA_M1=${POST_ID_HANHWA_M1}
POST_ID_HANHWA_M2=${POST_ID_HANHWA_M2}
POST_ID_HANHWA_M3=${POST_ID_HANHWA_M3}

POST_ID_MENU=${POST_ID_MENU:-${POST_ID_CAFETERIA}}
POST_ID_CAFETERIA=${POST_ID_CAFETERIA:-${POST_ID_MENU}}
EOF
echo "  -> 사내 게시판용 .env 생성 완료."

# 2. JOB_TYPE에 따른 구동 스크립트 실행 분기
if [ "${JOB_TYPE}" = "cafeteria" ]; then
    echo "====================================================="
    echo "  [식당 메뉴 자동화 모드] 구내식당 수집 및 업로드 시작"
    echo "====================================================="
    
    if [ -f "/app/board_automation/update_cafeteria.py" ]; then
        python /app/board_automation/update_cafeteria.py || send_alert "구내식당 메뉴 자동 수집 및 수정기" "식당 메뉴 정보를 가져와 사내 게시판 글을 수정하는 도중 에러가 발생했습니다. 사내망 패스워드가 만료되었거나 변경 주기가 도달했는지 체크해 보십시오."
    else
        echo "[경고] '/app/board_automation/update_cafeteria.py' 파일이 존재하지 않습니다."
        echo "구내식당 수집기 모듈을 프로젝트에 추가해 주세요."
        exit 1
    fi
else
    echo "====================================================="
    echo "  [리조트 잔여객실 모드] 4대 리조트 통합 크롤링 구동"
    echo "====================================================="
    
    echo "[단계 1/4] 리솜 리조트 수집 시작..."
    python /app/resom_crawler/resom_crawler.py || send_alert "리솜 리조트 크롤러" "리솜 예약 조회 도중 오류가 발생했습니다. 사이트 임시 패스워드 만료 상태를 체크해 보십시오."
    
    echo "[단계 1/4] 소노 호텔앤리조트 수집 시작..."
    python /app/sono_crawler/sono_crawler.py || send_alert "소노 리조트 크롤러" "소노 예약 조회 도중 오류가 발생했습니다. 사이트 임시 패스워드 만료 상태를 체크해 보십시오."
    
    echo "[단계 1/4] 롯데 리조트 수집 시작..."
    python /app/lotte_crawler/lotte_crawler.py || send_alert "롯데 리조트 크롤러" "롯데 예약 조회 도중 오류가 발생했습니다. 사이트 임시 패스워드 만료 상태를 체크해 보십시오."
    
    echo "[단계 1/4] 한화 리조트 수집 시작..."
    python /app/hanhwa_crawler/hanhwa_crawler.py || send_alert "한화 리조트 크롤러" "한화 예약 조회 도중 오류가 발생했습니다. 2차 비밀번호 불일치 및 사이트 패스워드 만료 상태를 체크해 보십시오."
    
    echo "[단계 2/4] 대시보드 HTML 취합 및 빌드 시작..."
    python /app/convert_to_html.py
    cp /app/resort_availability.html /app/index.html
    
    echo "[단계 3/4] RAG 표준 텍스트 데이터 변환 시작..."
    python /app/generate_rag_text.py
    
    echo "[단계 4/4] 사내 게시판 (dhr.hanati.co.kr) 자동 업데이트 실행..."
    python /app/board_automation/update_board.py || send_alert "사내 게시판 자동 수정기" "사내 인사시스템 게시판 로그인에 실패했거나 수정 과정에서 오류가 났습니다. 사내망 패스워드 만료 여부 및 변경 권장 창 유무를 확인하십시오."
    
    # 3. AWS S3 결과 파일 동기화 업로드
    if [ -n "${S3_BUCKET}" ]; then
        echo "====================================================="
        echo "  S3 결과 전송 시작 (Bucket: s3://${S3_BUCKET})"
        echo "====================================================="
        
        # 정적 웹 대시보드 업로드 (Cache-Control 설정으로 실시간 반영)
        aws s3 cp /app/resort_availability.html s3://${S3_BUCKET}/resort_availability.html --cache-control "no-cache, no-store, must-revalidate"
        aws s3 cp /app/index.html s3://${S3_BUCKET}/index.html --cache-control "no-cache, no-store, must-revalidate"
        
        # 객실 요금표 문서 업로드
        aws s3 sync /app/요금표 s3://${S3_BUCKET}/요금표/
        
        # 날짜별 원본 엑셀 파일 아카이빙 백업
        aws s3 sync /app/resom_crawler/data s3://${S3_BUCKET}/data/resom/
        aws s3 sync /app/sono_crawler/data s3://${S3_BUCKET}/data/sono/
        aws s3 sync /app/lotte_crawler/data s3://${S3_BUCKET}/data/lotte/
        aws s3 sync /app/hanhwa_crawler/data s3://${S3_BUCKET}/data/hanhwa/
        
        # RAG 텍스트 백업 업로드
        aws s3 sync /app/rag_output s3://${S3_BUCKET}/rag_output/
        
        echo "  -> S3 업로드 동기화가 정상 완료되었습니다."
    else
        echo "[주의] 'S3_BUCKET' 환경변수가 지정되지 않아 S3 업로드를 스킵합니다."
    fi
fi

echo "====================================================="
echo "  [AWS ECS Fargate Task] 모든 작업 완료 및 컨테이너 종료"
echo "  종료 시각: $(date)"
echo "====================================================="
