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
async def analyze_with_qwen(source_code, is_chunk=False, chunk_info="", file_name="", global_context=""):
    """
    Qwen 모델(OpenAI 호환)을 사용하여 코드 분석을 요청합니다.
    Timeout, 500 내부 서버 오류, Rate Limit 등의 예외 발생 시 tenacity 패키지를 통해 최대 5번 지수 백오프 재시도를 합니다.
    """
    if file_name.endswith(".sql"):
        # [DDL 전용 프롬프트] 데이터 모델링 및 스키마 분석에 집중
        if is_chunk:
            prompt = f"""
            당신은 데이터베이스 및 MSA 데이터 모델링 전문가입니다. 다음 코드는 원본 DDL 파일이 너무 커서 분할된 일부분(Part {chunk_info})입니다.
            이 DDL 조각을 바탕으로 MSA 전환을 위한 데이터베이스 분리 가이드를 제공해주세요.
            1. 식별된 데이터베이스 객체(테이블, 뷰, 프로시저, 트리거 등)와 추천 도메인(마이크로서비스)을 반드시 마크다운 표(Table) 형식으로 정리할 것 (헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
            2. 테이블 간의 외래 키(FK) 등 강결합 요소를 파악하되, **애그리거트 루트와 그 하위 종속 테이블은 절대 다른 도메인으로 찢어지지 않도록 동일 도메인으로 묶을 것**. (주의: 분할된 파일이므로, 현재 코드 조각에 존재하지 않는 '외부 테이블'을 참조하는 FK가 발견되더라도 누락 없이 반드시 기록할 것).
            3. 강결합 분리 시, 단순한 API 조회를 넘어서 **이벤트 기반 결과적 일관성(Eventual Consistency), Saga 패턴, CQRS 등 구체적인 MSA 데이터 동기화 아키텍처 패턴**을 제시할 것.
            4. 의존성 관계 다이어그램이 필요하다면 반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것.
            {global_context}
            
            [DDL 소스 코드 조각]
            {source_code}
            """
        else:
            prompt = f"""
            당신은 데이터베이스 및 MSA 데이터 모델링 전문가입니다. 다음 SQL DDL 코드를 분석하여 MSA 전환을 위한 데이터베이스 분리 가이드를 제공해주세요.
            1. 식별된 데이터베이스 객체(테이블, 뷰, 프로시저, 트리거 등)와 추천 도메인(마이크로서비스)을 반드시 마크다운 표(Table) 형식으로 정리할 것 (헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
            2. 테이블 간의 외래 키(FK) 등 강결합 요소를 파악하되, **애그리거트 루트와 그 하위 종속 테이블은 절대 다른 도메인으로 찢어지지 않도록 동일 도메인으로 묶을 것**.
            3. 강결합 분리 시, 단순한 API 조회를 넘어서 **이벤트 기반 결과적 일관성(Eventual Consistency), Saga 패턴, CQRS 등 구체적인 MSA 데이터 동기화 아키텍처 패턴**을 제시할 것.
            4. 의존성 관계 다이어그램 (반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것).

            [DDL 소스 코드]
            {source_code}
            """
    else:
        # [Java/XML 전용 프롬프트] 비즈니스 로직 및 객체/서비스 의존성 분석에 집중
        if is_chunk:
            prompt = f"""
            당신은 MSA 아키텍트입니다. 다음 코드는 원본 파일이 너무 커서 분할된 파일의 일부분(Part {chunk_info})입니다.
            이 코드 조각을 바탕으로 다음을 수행해주세요.
            1. 이 코드 조각이 포함하는 핵심 비즈니스 로직, 도메인, 그리고 **DDD 애그리거트(Aggregate) 단위 및 루트(Root)** 식별 (기준에 따라 분석 후, 식별된 객체/도메인 정보를 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
            2. 강결합된 객체/서비스 호출 등 리팩토링이 필요한 부분 지적 (의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것).
            3. 의존성 관계가 있다면 반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 다이어그램 작성 (없으면 생략).
            4. 만약 REST API(Controller 등) 엔드포인트가 포함되어 있다면, API 엔드포인트, HTTP Method, 설명/상세를 마크다운 표(Table) 형식으로 추가 정리할 것.
            {global_context}
            
            [소스 코드 조각]
            {source_code}
            """
        else:
            prompt = f"""
            당신은 MSA 아키텍트입니다. 다음 소스 코드(Java 또는 XML 매퍼)를 분석하여 MSA 전환을 위한 가이드를 제공해주세요.
            1. 도메인 (Domain) 분류 및 **DDD 애그리거트(Aggregate) 단위와 루트(Root)** 식별 (기준에 따라 분석 후, 식별된 객체/도메인 정보를 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
            2. 타 도메인과의 강결합 부분 분석 (의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것).
            3. 리팩토링 제안.
            4. 의존성 관계 다이어그램 (반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것).
            5. 만약 REST API(Controller 등) 엔드포인트가 포함되어 있다면, API 엔드포인트, HTTP Method, 설명/상세를 마크다운 표(Table) 형식으로 추가 정리할 것.

            [소스 코드]
            {source_code}
            """

    # DDL 파일(.sql)인 경우 스키마 분석의 정확도를 높이고 환각(Hallucination)을 막기 위해 Temperature를 0에 가깝게 설정
    # 일반 코드(.java, .xml)는 문맥 추론을 위해 0.1로 유지
    req_temperature = 0.01 if file_name.endswith(".sql") else 0.1
    
    # DDL 분석 시 마크다운 표 출력이 길어질 수 있으므로 최대 토큰 수를 넉넉하게 할당합니다.
    req_max_tokens = 4096 if file_name.endswith(".sql") else 2048

    response = await llm_client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {"role": "system", "content": "You are a senior software architect specializing in Microservices Architecture (MSA)."},
            {"role": "user", "content": prompt}
        ],
        temperature=req_temperature,
        max_tokens=req_max_tokens
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
    1. 시스템의 핵심 로직, 도메인 및 **DDD 애그리거트(Aggregate)** 식별 (전체적인 관점에서, 식별된 도메인과 데이터베이스 객체 매핑은 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세)
    2. 타 도메인과의 강결합 부분(FK 포함) 및 문제점 종합 (개별 청크에서 파편화되어 식별된 외부 참조 FK 관계들을 하나로 연결하여 전체 시스템의 테이블 간 연관 관계를 복원하고, 의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것)
    3. 데이터 마이그레이션 우선순위(Phase 1, 2, 3) 및 MSA 데이터 아키텍처 리팩토링 제안 (Saga, CQRS, 이벤트 기반 동기화 등 활용)
    4. 전체 파일 수준의 의존성 관계 다이어그램 (반드시 ```dot ... ``` 마크다운 코드 블록 안에 Graphviz DOT 문법으로 작성할 것)
    5. 발견된 REST API 엔드포인트가 있다면 모두 취합하여 마크다운 표(Table) 형식으로 정리할 것 (헤더: API Endpoint, Method, 설명/상세)

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
    1. 시스템의 핵심 도메인 및 **DDD 애그리거트(Aggregate)** 식별 요약 (식별된 도메인/애그리거트와 주요 데이터베이스 객체 매핑 결과를 반드시 마크다운 표(Table) 형식으로 종합하여 정리할 것. 헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세)
    2. 주요 결합 문제(DB 조인, 직접 참조 등) 및 공통 리팩토링 전략
    3. 성공적인 MSA 전환을 위한 데이터 마이그레이션 우선순위 및 단계별 추천 로드맵 (단순 분리가 아닌 Saga, Eventual Consistency 등 아키텍처 패턴 명시)
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