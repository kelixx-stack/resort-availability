#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions용 한국 VPN 자동 연결 및 검증 스크립트 (setup_vpn.py)
============================================================
- VPNGate API에서 한국(KR) VPN 프로필 목록을 가져옵니다.
- 핑(Ping)이 낮고 속도(Speed)가 빠른 순으로 정렬합니다.
- 작동 가능한 서버를 찾을 때까지 최대 10개의 서버에 순차적으로 연결을 시도합니다.
- 외부 IP 주소를 실시간으로 체크하여 실제 국가 코드가 'KR'로 변경되었는지 최종 검증합니다.
"""

import urllib.request
import base64
import os
import subprocess
import json
import time

def check_ip():
    """현재 외부 IP 및 국가 정보를 ipinfo.io API를 통해 확인합니다."""
    try:
        req = urllib.request.Request('https://ipinfo.io/json', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            return data.get('country'), data.get('ip'), data.get('region')
    except Exception:
        return None, None, None

def main():
    print("1. VPNGate에서 한국 VPN 서버 목록 가져오는 중...")
    try:
        req = urllib.request.Request('https://www.vpngate.net/api/iphone/', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as res:
            data = res.read().decode('utf-8')
    except Exception as e:
        print(f"[오류] VPN 서버 리스트 획득 실패: {e}")
        return False

    lines = data.split('\n')
    kr_servers = []
    for line in lines:
        if not line.strip() or line.startswith('*') or line.startswith('#'):
            continue
        parts = line.strip().split(',')
        if len(parts) >= 15 and parts[6] == 'KR':
            kr_servers.append({
                'ping': int(parts[3]) if parts[3].isdigit() else 999,
                'speed': int(parts[4]) if parts[4].isdigit() else 0,
                'config': parts[14]
            })

    # Ping 오름차순, Speed 내림차순 정렬
    kr_servers.sort(key=lambda x: (x['ping'], -x['speed']))
    print(f"  [정보] 총 {len(kr_servers)}개의 한국 VPN 서버 후보를 찾았습니다.")

    if not kr_servers:
        print("[오류] 사용 가능한 한국 VPN 서버가 없습니다.")
        return False

    # 상위 10개 서버에 대해 순차적으로 연결 시도
    for idx, svr in enumerate(kr_servers[:10]):
        print(f"\n[시도 {idx+1}/10] VPN 서버 연결 시도 (Ping: {svr['ping']}ms, Speed: {svr['speed']/1000000:.2f} Mbps)...")
        
        # 설정 파일 작성
        try:
            ovpn_content = base64.b64decode(svr['config']).decode('utf-8')
        except Exception as e:
            print(f"  [경고] 프로필 디코딩 오류: {e}")
            continue

        # systemd-resolved DNS 연동 옵션 추가 (Ubuntu용)
        extra_opts = (
            "\nscript-security 2\n"
            "up /etc/openvpn/update-systemd-resolved\n"
            "down /etc/openvpn/update-systemd-resolved\n"
            "down-pre\n"
        )
        
        with open('client.ovpn', 'w') as f:
            f.write(ovpn_content + extra_opts)

        # 기존 openvpn 데몬들 종료
        subprocess.run(["sudo", "killall", "openvpn"], capture_output=True)
        time.sleep(2)

        # OpenVPN 실행
        try:
            subprocess.Popen(["sudo", "openvpn", "--config", "client.ovpn", "--daemon"])
        except Exception as e:
            print(f"  [경고] OpenVPN 프로세스 시작 실패: {e}")
            continue

        # 최대 16초 동안 2초마다 IP 체크 (안정화 시간 고려)
        connected = False
        print("  연결 수립 대기 및 IP 확인 중...")
        for check_idx in range(8):
            time.sleep(2)
            country, ip, region = check_ip()
            if country:
                print(f"    - IP: {ip} | 국가: {country} | 지역: {region}")
                if country == 'KR':
                    print(f"\n  [성공] 한국 VPN 연결이 최종 확인되었습니다! IP: {ip} ({region})")
                    connected = True
                    break
            else:
                print("    - IP 응답 대기 중...")

        if connected:
            return True
        else:
            print("  [실패] 연결 타임아웃 또는 IP가 한국으로 변경되지 않았습니다. 다음 서버로 넘어갑니다.")

    print("\n[오류] 상위 10개 한국 VPN 서버 모두 연결에 실패했습니다.")
    return False

if __name__ == '__main__':
    success = main()
    if not success:
        exit(1)
