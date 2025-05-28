# full_mystery_automation.py

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

# 2) 구글 시트 인증 정보
SCOPE      = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
CREDS_FILE = "credentials.json"
SHEET_URL  = "여기에_구글_시트_URL_붙여넣기"

creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
gc    = gspread.authorize(creds)
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
        sheet.append_row(["제목","출처 링크","요일","출처"])

# 4) 요일별 스크래핑 소스
DAY_SOURCES = {
    "월요일": [
        {"type":"reddit", "url":"https://www.reddit.com/r/UnresolvedMysteries/top.json?t=week"},
        {"type":"html",   "url":"https://vault.fbi.gov/missing-persons", "selector":".views-row .title a"}
    ],
    "화요일": [
        {"type":"reddit", "url":"https://www.reddit.com/r/HighStrangeness/top.json?t=week"},
        {"type":"rss",    "url":"http://export.arxiv.org/rss/physics.geo-ph"}
    ],
    "수요일": [
        {"type":"rss",    "url":"https://www.ancient-origins.net/rss.xml"},
        {"type":"reddit", "url":"https://www.reddit.com/r/Archaeology/top.json?t=week"}
    ],
    "목요일": [
        {"type":"reddit", "url":"https://www.reddit.com/r/Conspiracy/top.json?t=week"},
        {"type":"html",   "url":"https://www.cia.gov/readingroom/collection/mk-ultra", "selector":".item-title a"}
    ],
    "금요일": [
        {"type":"reddit", "url":"https://www.reddit.com/r/Glitch_in_the_Matrix/top.json?t=week"},
        {"type":"rss",    "url":"https://alerts.weather.gov/cap/us.php?x=0"}
    ],
}

# 5) 파싱 함수 (생략 가능, 위 예제 참고)
# parse_reddit, parse_rss, parse_html 함수들도 함께 넣어주세요.

# 6) 스케줄러 등록
def job():
    wd = time.localtime().tm_wday
    mapping = {0:"월요일",1:"화요일",2:"수요일",3:"목요일",4:"금요일"}
    if wd in mapping:
        scrape_and_save(mapping[wd])

schedule.every().day.at("09:00").do(job)

if __name__ == "__main__":
    logging.info("스케줄러 시작")
    while True:
        schedule.run_pending()
        time.sleep(30)
