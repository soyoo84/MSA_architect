import os
import logging
from concurrent_log_handler import ConcurrentRotatingFileHandler
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 루트 로거 가져오기 및 레벨 설정
logger = logging.getLogger()
logger.setLevel(logging.ERROR)

# 핸들러 중복 추가 방지
if not logger.handlers:
    # 멀티 프로세스 안전성을 보장하는 파일 락 기반의 로그 핸들러 적용
    handler = ConcurrentRotatingFileHandler(
        filename='error.log',
        mode='a',
        maxBytes=10 * 1024 * 1024, # 10MB 크기 도달 시 새로운 파일로 백업
        backupCount=5,
        encoding='utf-8'
    )
    formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# 프로젝트 폴더에 있는 .env 파일을 찾아 환경변수로 로드합니다.
load_dotenv()

# 환경변수에서 설정값들을 가져옵니다.
SOURCE_DIRECTORY = os.getenv("SOURCE_DIRECTORY", "./monolith_source")

LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "qwen3.5")

# 워커 수 설정 (문자열을 정수로 변환, 기본값 5)
LLM_MAX_WORKERS = int(os.getenv("LLM_MAX_WORKERS", 5))

# 개별 워커 타임아웃 (정수 변환, 기본값 300초)
WORKER_TIMEOUT_SECONDS = int(os.getenv("WORKER_TIMEOUT_SECONDS", 300))

# 파일 분할(Chunking) 비동기 처리 시 동시 요청 제한 수 (기본값 3)
ASYNC_CHUNK_CONCURRENCY = int(os.getenv("ASYNC_CHUNK_CONCURRENCY", 3))

# 필수 API 설정 누락에 대한 방어 로직
if not LLM_BASE_URL or not LLM_API_KEY:
    raise ValueError("LLM_BASE_URL 또는 LLM_API_KEY가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# 사내 LLM 초기화 (대부분의 오픈소스 LLM은 OpenAI 호환 API를 제공하므로 openai 패키지를 사용합니다)
llm_client = AsyncOpenAI(
    base_url=LLM_BASE_URL,
    api_key=LLM_API_KEY
)

print("환경변수 로드 및 사내 LLM 초기화 성공!")
print(f"- 대상 모델: {LLM_MODEL_NAME}")
print(f"- 소스 경로: {SOURCE_DIRECTORY}")