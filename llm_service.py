import openai
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm
from config import llm_client, LLM_MODEL_NAME

def log_retry_to_terminal(retry_state):
    """재시도 발생 시 터미널(tqdm)에 원인 에러와 대기 시간을 출력합니다."""
    exc = retry_state.outcome.exception()
    wait_time = retry_state.next_action.sleep
    tqdm.write(f"⚠️ [API 재시도] {type(exc).__name__} 발생: {exc} -> {wait_time}초 후 다시 시도합니다.")

@retry(
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=2, min=5, max=60), # 서버 재부팅(모델 로딩) 시간을 고려해 최대 대기 60초로 연장
    retry=retry_if_exception_type((
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.APIStatusError, # 500뿐만 아니라 서버 크래시로 인한 502, 503 등을 포괄적으로 감지
        openai.RateLimitError
    )),
    before_sleep=log_retry_to_terminal,
    reraise=True
)
async def analyze_with_qwen(source_code, is_chunk=False, chunk_info=""):
    """
    Qwen 모델(OpenAI 호환)을 사용하여 코드 분석을 요청합니다.
    Timeout, 500 내부 서버 오류, Rate Limit 등의 예외 발생 시 tenacity 패키지를 통해 최대 5번 지수 백오프 재시도를 합니다.
    """
    if is_chunk:
        prompt = f"""
        당신은 MSA 아키텍트입니다. 다음 코드는 원본 파일이 너무 커서 AST 파서를 통해 메서드 단위로 쪼갠 파일의 일부분(Part {chunk_info})입니다.
        이 코드 조각을 바탕으로 다음을 수행해주세요.
        1. 이 코드 조각이 포함하는 핵심 로직 및 도메인 식별
        2. 강결합된 객체/DB 조회 등 리팩토링이 필요한 부분 지적
        3. 의존성 관계가 있다면 반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 다이어그램 작성 (없으면 생략)
        
        [소스 코드 조각]
        {source_code}
        """
    else:
        prompt = f"""
        당신은 MSA 아키텍트입니다. 다음 소스 코드(Java 또는 XML 매퍼)를 분석하여 MSA 전환을 위한 가이드를 제공해주세요.
        1. 도메인 (Domain) 분류
        2. 타 도메인과의 강결합 부분 분석
        3. 리팩토링 제안
        4. 의존성 관계 다이어그램 (반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것)

        [소스 코드]
        {source_code}
        """

    response = await llm_client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a senior software architect specializing in Microservices Architecture (MSA)."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1 # 분석 결과의 일관성을 위해 temperature를 낮게 설정
    )
    
    return response.choices[0].message.content

@retry(
    stop=stop_after_attempt(5), 
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.APIStatusError,
        openai.RateLimitError
    )),
    before_sleep=log_retry_to_terminal,
    reraise=True
)
async def summarize_chunks_with_qwen(chunk_results_text, file_name):
    """분할 분석된 청크 결과들을 하나로 병합(Reduce)하여 최종 요약 리포트를 생성합니다."""
    if len(chunk_results_text) > 40000:
        chunk_results_text = chunk_results_text[:40000] + "\n\n... (중략: 토큰 보호를 위해 잘림) ..."
        
    prompt = f"""
    당신은 MSA 아키텍트입니다. 다음은 대용량 파일 '{file_name}'을(를) 여러 청크로 나누어 개별 분석한 결과들의 모음입니다.
    이 파편화된 결과들을 종합하여, 이 파일에 대한 **하나의 통합된 MSA 분석 리포트**를 작성해 주세요.
    
    [필수 포함 항목]
    1. 시스템의 핵심 로직 및 도메인 식별 (전체적인 관점에서)
    2. 타 도메인과의 강결합 부분 및 문제점 (종합)
    3. 리팩토링 제안 (종합)
    4. 전체 파일 수준의 의존성 관계 다이어그램 (반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것)

    [개별 청크 분석 결과 모음]
    {chunk_results_text}
    """
    
    response = await llm_client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a senior software architect specializing in Microservices Architecture (MSA)."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content

async def generate_summary_with_qwen(combined_text):
    """전체 파일들의 분석 결과를 종합하여 최종 요약 아키텍처 가이드를 생성합니다."""
    prompt = f"""
    당신은 수석 MSA 아키텍트입니다. 다음은 기존 모놀리식 시스템의 각 파일별 MSA 분석 리포트들입니다.
    이 내용들을 종합하여 전체 시스템에 대한 '전체 요약 아키텍처 가이드'를 마크다운 형식으로 작성해 주세요.
    1. 시스템의 핵심 도메인 식별 요약
    2. 주요 결합 문제(DB 조인, 직접 참조 등) 및 공통 리팩토링 전략
    3. 성공적인 MSA 전환을 위한 단계별 추천 로드맵
    4. 전체 시스템의 마이크로서비스 도메인 간 통신 및 의존성 다이어그램 (반드시 ```dot ... ``` 블록으로 작성)

    [개별 분석 리포트 종합 내용]
    {combined_text}
    """
    
    response = await llm_client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a senior software architect specializing in Microservices Architecture (MSA)."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content