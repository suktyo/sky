import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import os
import json
import matplotlib.pyplot as plt
from matplotlib import font_manager
import logging
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import io
import tempfile
import requests
import matplotlib
matplotlib.use('Agg')

# 환경 변수 로드
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# 디스코드 봇 설정
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 한글 폰트 설정
font_path = "C:/Users/home/Desktop/플어봇/NanumGothicCoding-2.5/NanumGothicCoding-Bold.ttf"
font_prop = font_manager.FontProperties(fname=font_path)

# 접속 기록을 저장할 파일 경로
DATA_FILE = "player_access_data.json"

# 플레이어 목록을 가져오는 클래스

class PlayerLocationFetcher:
    def __init__(self):
        self.driver = None
        self.players = []

    def start_driver(self):
        options = Options()
        options.headless = True
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.get("https://map.planetearth.kr/")

    def fetch_players(self):
        if not self.driver:
            self.start_driver()

        try:
            # 플레이어 버튼 클릭
            players_button = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.CLASS_NAME, "button--players"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", players_button)
            players_button.click()

            player_list_section = WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.ID, "players-content"))
            )

            # 스크롤하여 모든 플레이어 목록을 로드하기
            prev_height = self.driver.execute_script("return document.body.scrollHeight")
            while True:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # 페이지가 로드될 시간을 기다림
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == prev_height:  # 더 이상 로드되지 않으면 종료
                    break
                prev_height = new_height

            # 플레이어 목록 추출
            players_list = self.driver.find_elements(By.CSS_SELECTOR, "span.player__name")

            if players_list:
                self.players = [player.text for player in players_list if player.text != '']
                self.players = list(set(self.players))  # 중복 제거
            else:
                self.players = ["접속중인 플레이어가 없습니다."]
        except Exception as e:
            print(f"오류 발생: {e}")
            self.players = []

    def stop_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

# 접속 기록을 저장하는 함수
def save_access_data(nickname):
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)

    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 데이터를 메모리로 불러옴
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    
    if nickname not in data:
        data[nickname] = []
    
    # 중복된 시간 기록 방지
    if current_time not in data[nickname]:
        data[nickname].append(current_time)

    # 데이터를 파일에 저장
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

# 접속 기록을 3초마다 기록하는 작업
@tasks.loop(seconds=3)
async def track_player_access():
    fetcher = PlayerLocationFetcher()
    fetcher.fetch_players()

    players = fetcher.players
    if players:
        for player in players:
            save_access_data(player)

            # 그래프를 메모리에서 바로 갱신
            graph_file = generate_access_graph(player, 1)
            if graph_file:
                channel = discord.utils.get(bot.get_all_channels(), name="하루의4번사랑을말하고8번웃고6번의키스를해줘")
                if channel:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                        temp_file.write(graph_file.getvalue())
                        temp_file_path = temp_file.name
                    
                    try:
                        await channel.send(file=discord.File(temp_file_path))
                    finally:
                        os.remove(temp_file_path)

# 접속 그래프 생성 함수
def generate_access_graph(nickname, days_ago):
    target_date = datetime.now() - timedelta(days=days_ago)
    target_date_str = target_date.strftime('%Y-%m-%d')

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    if nickname not in data:
        return None

    records = [record for record in data[nickname] if record.startswith(target_date_str)]

    if not records:
        return None

    times = []
    for record in records:
        login_time = datetime.strptime(record, '%Y-%m-%d %H:%M:%S')
        start_hour = login_time.hour
        start_minute = (login_time.minute // 10) * 10

        for i in range(6):
            current_time = (start_hour, start_minute + i * 10)
            times.append(current_time)

    hours = [(h, m) for h in range(24) for m in [0, 10, 20, 30, 40, 50]]
    access_color = ['green' if (h, m) in times else 'red' for h, m in hours]

    plt.figure(figsize=(10, 6))
    plt.scatter([f"{h}:{m}" for h, m in hours], [0] * len(hours), c=access_color, marker='o')
    plt.title(f"{nickname}의 {target_date_str} 접속 시간대별 그래프", fontproperties=font_prop)
    plt.xlabel("시간대", fontproperties=font_prop)
    
    plt.yticks([])
    hour_labels = [f"{h}:00" for h in range(24)]
    plt.xticks([i * 6 for i in range(24)], hour_labels, rotation=45)

    plt.grid(True)

    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='png')
    plt.close()
    img_bytes.seek(0)

    return img_bytes

@bot.command()
async def 접속(ctx, nickname: str, days_ago: int):
    img_bytes = generate_access_graph(nickname, days_ago)
    
    if img_bytes:
        await ctx.send(file=discord.File(img_bytes, filename=f"{nickname}_access_graph.png"))
    else:
        await ctx.send(f"{nickname}의 {days_ago}일 전 접속 기록이 없습니다.")

# 국가 접속 그래프 전송 명령어
@bot.command()
async def 국가접속(ctx, nation_name: str, days_ago: int):
    nation_url = f"https://api.planetearth.kr/nation?name={nation_name}"
    response = requests.get(nation_url)

    if response.status_code == 200:
        nation_data = response.json()

        if "data" not in nation_data or not nation_data["data"]:
            await ctx.send(f"{nation_name} 국가 데이터를 찾을 수 없습니다.")
            return
        
        nation_info = nation_data["data"][0]
        towns_str = nation_info.get("towns", "")
        town_list = towns_str.split(", ") if towns_str else []

        if not town_list:
            await ctx.send(f"{nation_name} 국가에는 연결된 도시가 없습니다.")
            return

        all_residents = []
        for town in town_list:
            town_url = f"https://api.planetearth.kr/town?name={town}"
            town_response = requests.get(town_url)

            if town_response.status_code == 200:
                town_data = town_response.json()

                if "data" in town_data and town_data["data"]:
                    town_info = town_data["data"][0]
                    residents_str = town_info.get("residents", "")
                    residents_list = residents_str.split(", ") if residents_str else []

                    all_residents.extend(residents_list)

        if not all_residents:
            await ctx.send(f"{nation_name} 국가에 속한 도시에서 주민 정보가 없습니다.")
            return
        
        # 국가 내 모든 플레이어들의 접속 기록을 저장
        fetcher = PlayerLocationFetcher()
        fetcher.fetch_players()
        actual_players = fetcher.players

        # 실제 접속한 플레이어들만 기록
        for resident in all_residents:
            if resident in actual_players:
                save_access_data(resident)  # 실제로 접속한 사람만 기록

        # 국가 내 플레이어들의 접속 현황을 기반으로 접속 시간대별 그래프 생성
        graph_file = generate_nation_access_graph(all_residents, nation_name, days_ago)
        if graph_file:
            print(f"국가 접속 그래프 파일 생성 완료")
            # 명령어를 입력한 채널에 그래프 전송
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                temp_file.write(graph_file.getvalue())
                temp_file_path = temp_file.name
                
            print(f"파일 경로: {temp_file_path}")
            
            # 명령어를 입력한 채널에 전송
            await ctx.send(file=discord.File(temp_file_path))
            os.remove(temp_file_path)
            print(f"그래프 전송 완료")
        else:
            await ctx.send("그래프 생성 중 문제가 발생했습니다.")
            print(f"그래프 생성 실패")
    else:
        await ctx.send(f"{nation_name} 국가 정보를 가져오는 데 실패했습니다.")

# 국가 접속 그래프 생성 함수
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 한글 폰트 설정
font_path = "C:/Users/home/Desktop/플어봇/NanumGothicCoding-2.5/NanumGothicCoding-Bold.ttf"
font_prop = font_manager.FontProperties(fname=font_path)

def generate_nation_access_graph(residents, nation_name, days_ago):
    target_date = datetime.now() - timedelta(days=days_ago)
    target_date_str = target_date.strftime('%Y-%m-%d')

    # 국가명 검증
    if not nation_name or nation_name == "0":
        raise ValueError("유효한 국가명을 입력해주세요.")

    with open(DATA_FILE, "r") as f:
        data = json.load(f)

    records_by_time = {}  # 10분 단위로 접속 기록을 세는 딕셔너리

    # 국가에 속한 모든 주민들의 접속 기록을 추출
    processed_residents = set()  # 이미 처리된 국가원들을 추적
    for resident in residents:
        if not resident or resident not in data:
            continue

        # 국가원에 대한 시간대 기록 추가
        if resident not in processed_residents:
            processed_residents.add(resident)
            seen_times = set()  # 중복 시간대 추적
            for record in data[resident]:
                if record.startswith(target_date_str):  # 해당 날짜의 기록만
                    login_time = datetime.strptime(record, '%Y-%m-%d %H:%M:%S')

                    # 10분 단위로 변환
                    rounded_time = login_time.replace(second=0, microsecond=0, minute=(login_time.minute // 10) * 10)
                    time_index = rounded_time.strftime('%Y-%m-%d %H:%M')

                    if time_index not in seen_times:
                        seen_times.add(time_index)

                        # 해당 시간대에 접속한 인원만 기록
                        if time_index not in records_by_time:
                            records_by_time[time_index] = set()

                        # 해당 시간대에 실제로 접속한 사람만 추가
                        records_by_time[time_index].add(resident)

    # 모든 시간대에 대해 접속자가 없을 경우 0으로 초기화
    all_times = []
    for hour in range(24):
        for minute in [0, 10, 20, 30, 40, 50]:  # 10분 단위로
            time_str = f"{target_date_str} {str(hour).zfill(2)}:{str(minute).zfill(2)}"
            all_times.append(time_str)

    access_count = [len(records_by_time.get(time, set())) for time in all_times]  # set의 길이를 카운트

    # 3시간 간격 레이블
    hour_labels = [f"{target_date_str} {str(i).zfill(2)}:00" for i in range(0, 24, 3)]

    # 그래프 그리기
    plt.figure(figsize=(12, 6))
    plt.plot(all_times, access_count, color='b', linestyle='-', linewidth=2)

    plt.title(f"{nation_name} - {target_date_str} 접속 시간대별 국가원 접속 현황", fontproperties=font_prop)
    plt.xlabel("시간 (10분 단위)", fontproperties=font_prop)
    plt.ylabel("접속한 국가원 수", fontproperties=font_prop)

    plt.xticks(hour_labels, rotation=45)
    plt.yticks(range(0, max(access_count) + 1))

    plt.grid(True)

    img_bytes = io.BytesIO()
    plt.savefig(img_bytes, format='png')
    plt.close()
    img_bytes.seek(0)

    return img_bytes


@bot.event
async def on_ready():
    track_player_access.start()

bot.run(TOKEN)
