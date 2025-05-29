# full_mystery_automation.py

import os
import requests
import feedparser
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import schedule
import time
import logging

# 1) 로깅 설정
logging.basicConfig(
    filename='mystery.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# 2) 구글 시트 인증 정보 (파일 기반 방식)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
# PythonAnywhere 홈 디렉터리에 업로드된 credentials.json 경로
KEYFILE_PATH = os.path.expanduser('~/credentials.json')

creds = ServiceAccountCredentials.from_json_keyfile_name(KEYFILE_PATH, SCOPES)

gc = gspread.authorize(creds)

# 시트 URL (환경변수 또는 아래 기본값 사용)
SHEET_URL = os.environ.get(
    'SHEET_URL',
    'https://docs.google.com/spreadsheets/d/1jRIGFqmCGIWsMmE6XDnjuEnuMJ4e0pwYqa65JEae9Pg/edit?gid=0'
)
sheet = gc.open_by_url(SHEET_URL).sheet1

# 3) 유틸 함수들
def is_duplicate(title):
    return title in sheet.col_values(1)

def is_valid_url(url):
    try:
        return requests.head(url, timeout=5).status_code == 200
    except:
        return False

def ensure_header():
    if not sheet.row_values(1):
        sheet.append_row(['제목', '출처 링크', '요일', '출처'])

# 4) 요일별 스크래핑 소스 (목요일은 RSS로 변경)
DAY_SOURCES = {
    '월요일': [
        {'type': 'reddit', 'url': 'https://www.reddit.com/r/UnresolvedMysteries/top.json?t=week'},
        {'type': 'html',   'url': 'https://vault.fbi.gov/missing-persons', 'selector': '.views-row .title a'}
    ],
    '화요일': [
        {'type': 'reddit', 'url': 'https://www.reddit.com/r/HighStrangeness/top.json?t=week'},
        {'type': 'rss',    'url': 'http://export.arxiv.org/rss/physics.geo-ph'}
    ],
    '수요일': [
        {'type': 'rss',    'url': 'https://www.ancient-origins.net/rss.xml'},
        {'type': 'reddit', 'url': 'https://www.reddit.com/r/Archaeology/top.json?t=week'}
    ],
    '목요일': [
        {'type': 'rss',    'url': 'https://www.cia.gov/feeds/mk-ultra.rss'}
    ],
    '금요일': [
        {'type': 'reddit', 'url': 'https://www.reddit.com/r/Glitch_in_the_Matrix/top.json?t=week'},
        {'type': 'rss',    'url': 'https://alerts.weather.gov/cap/us.php?x=0'}
    ],
}

# 5) 파싱 함수들
def parse_reddit(src, top_n=5):
    headers = {
        'User-Agent': 'MysteryBot/1.0 (by /u/PoemRevolutionary984)',
        'Accept-Encoding': 'gzip'
    }
    try:
        r = requests.get(src['url'], headers=headers, timeout=10)
        r.raise_for_status()
        posts = r.json().get('data', {}).get('children', [])[:top_n]
        items = [(p['data']['title'], p['data']['url'], 'reddit') for p in posts]
    except Exception as e:
        logging.warning(f"Reddit 차단 또는 오류({src['url']}): {e} → Pushshift 대체")
        subreddit = src['url'].split("/r/")[1].split("/")[0]
        ps_url = f"https://api.pushshift.io/reddit/search/submission/?subreddit={subreddit}&size={top_n}&sort=desc"
        r = requests.get(ps_url, headers=headers, timeout=10)
        data = r.json().get('data', [])[:top_n]
        items = [(e.get('title',''), e.get('full_link') or e.get('url',''), 'reddit') for e in data]

    results = []
    for title, link, stype in items:
        if not title or is_duplicate(title) or not is_valid_url(link):
            continue
        results.append((title, link, stype))
    return results

def parse_rss(src, top_n=5):
    try:
        feed = feedparser.parse(src['url'])
        entries = feed.entries[:top_n]
    except Exception as e:
        logging.error(f"RSS 파싱 실패 ({src['url']}): {e}")
        return []

    results = []
    for e in entries:
        if is_duplicate(e.title) or not is_valid_url(e.link):
            continue
        results.append((e.title, e.link, 'rss'))
    return results

def parse_html(src, top_n=5):
    try:
        r = requests.get(src['url'], headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        elems = soup.select(src['selector'])[:top_n]
    except Exception as e:
        logging.error(f"HTML 스크래핑 실패 ({src['url']}): {e}")
        return []

    results = []
    for el in elems:
        title = el.get_text(strip=True)
        link = el.get('href','')
        if is_duplicate(title) or not is_valid_url(link):
            continue
        results.append((title, link, 'html'))
    return results

# 6) 데이터 수집 및 저장
def scrape_and_save(day):
    ensure_header()
    rows = []
    for src in DAY_SOURCES.get(day, []):
        if src['type'] == 'reddit':
            items = parse_reddit(src)
        elif src['type'] == 'rss':
            items = parse_rss(src)
        elif src['type'] == 'html':
            items = parse_html(src)
        else:
            continue
        for title, link, stype in items:
            rows.append([title, link, day, stype])

    if rows:
        try:
            sheet.append_rows(rows)
            logging.info(f"{day}: {len(rows)}건 저장 완료")
        except Exception as e:
            logging.error(f"시트 저장 에러: {e}")

# 7) 스케줄러 시작 및 실행
def job():
    wd = time.localtime().tm_wday
    mapping = {0:'월요일',1:'화요일',2:'수요일',3:'목요일',4:'금요일'}
    if wd in mapping:
        scrape_and_save(mapping[wd])

# KST 오전 9시 실행 → UTC 00:00
schedule.every().day.at("00:00").do(job)

if __name__ == "__main__":
    logging.info("스케줄러 시작")
    # 한 번만 실행 모드
    if os.getenv("GITHUB_ACTIONS"):
        job()
    else:
        while True:
            schedule.run_pending()
            time.sleep(30)
