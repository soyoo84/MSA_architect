import openai
from typing import Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from tqdm import tqdm
from config import llm_client, LLM_MODEL_NAME


def log_retry_to_terminal(retry_state: Any) -> None:
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
async def analyze_with_qwen(source_code: str, is_chunk: bool = False, chunk_info: str = "", file_name: str = "", global_context: str = "") -> str:
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
            1. 식별된 데이터베이스 객체(테이블, 뷰, 프로시저, 트리거 등)와 추천 도메인(마이크로서비스)을 마크다운 표(Table)로 정리할 것 (헤더: 구분, 객체명, 프로세스 체계(LV1~LV5), 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세). 
               - **프로세스 체계 (LV1~LV5)**: 테이블이 지원하는 업무를 비즈니스 프로세스 관점(LV1: 밸류체인/대분류, LV2: 메가프로세스/중분류, LV3: 주요프로세스/소분류, LV4: 서브프로세스, LV5: 단위업무/액티비티)으로 분류하여 명시할 것.
            2. **Bounded Context 정의 및 물리적 DB 분리**: 테이블 간의 외래 키(FK) 등 강결합 요소를 파악하되, 서로 다른 Bounded Context(도메인) 간의 물리적 FK 제약조건은 완전히 끊어내는(제거하는) 아키텍처를 지향할 것. 단, 동일한 **애그리거트 루트(Aggregate Root)**와 하위 종속 테이블은 절대 다른 도메인으로 찢어지지 않도록 묶을 것. (주의: 분할된 파일이므로, 현재 코드 조각에 존재하지 않는 '외부 테이블'을 참조하는 FK가 발견되더라도 누락 없이 기록).
            3. **데이터 정합성(Consistency) 및 동기화 가이드**: 서로 다른 DB로 물리적 분리 시 발생하는 데이터 정합성 문제를 해결하기 위해, 단순 API 조회를 넘어 **트랜잭셔널 아웃박스(Transactional Outbox), Saga 패턴(보상 트랜잭션), 이벤트 기반 결과적 일관성(Eventual Consistency)** 등 구체적인 데이터 정합성 보장 방안을 가이드할 것.
            4. **UML 도메인 모델 다이어그램**: 도메인 주요 개념, Aggregate Root, 그리고 객체 간의 연관관계를 표준화된 UML 클래스 다이어그램 형태로 시각화할 것 (반드시 ```mermaid\nclassDiagram\n...``` 형태의 Mermaid 문법을 사용할 것).
            5. [스키마 검증 및 리팩토링 가이드] 다음 항목을 심층 분석할 것:
               - **정규화**: 데이터 중복 최소화 여부, 기본키(PK) 및 식별자 명확성 점검
               - **확장성 및 유지보수성**: 대용량 트래픽 처리 및 MSA 확장에 유리한 구조인지 평가
               - **비즈니스 목적 명확화**: 테이블 설계가 비즈니스 로직(XML 쿼리 등) 목적에 부합하는지 점검
            {global_context}
            
            [DDL 소스 코드 조각]
            {source_code}
            """
        else:
            prompt = f"""
            당신은 데이터베이스 및 MSA 데이터 모델링 전문가입니다. 다음 SQL DDL 코드를 분석하여 MSA 전환을 위한 데이터베이스 분리 가이드를 제공해주세요.
            1. 식별된 데이터베이스 객체(테이블, 뷰, 프로시저, 트리거 등)와 추천 도메인(마이크로서비스)을 반드시 마크다운 표(Table) 형식으로 정리할 것 (헤더: 구분, 객체명, 도메인, 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
            2. **Bounded Context 정의 및 물리적 DB 분리**: 테이블 간의 외래 키(FK) 등 강결합 요소를 파악하되, 서로 다른 Bounded Context(도메인) 간의 물리적 FK 제약조건은 완전히 끊어내는(제거하는) 아키텍처를 지향할 것. 단, 동일한 **애그리거트 루트(Aggregate Root)**와 하위 종속 테이블은 절대 다른 도메인으로 찢어지지 않도록 묶을 것.
            3. **데이터 정합성(Consistency) 및 동기화 가이드**: 서로 다른 DB로 물리적 분리 시 발생하는 데이터 정합성 문제를 해결하기 위해, 단순 API 조회를 넘어 **트랜잭셔널 아웃박스(Transactional Outbox), Saga 패턴(보상 트랜잭션), 이벤트 기반 결과적 일관성(Eventual Consistency)** 등 구체적인 데이터 정합성 보장 방안을 가이드할 것.
            4. **UML 도메인 모델 다이어그램**: 도메인 주요 개념, Aggregate Root, 그리고 객체 간의 연관관계를 표준화된 UML 클래스 다이어그램 형태로 시각화할 것 (반드시 ```mermaid\nclassDiagram\n...``` 형태의 Mermaid 문법을 사용할 것).
            5. [스키마 검증 및 리팩토링 가이드] 다음 항목을 심층 분석할 것:
               - **정규화**: 데이터 중복 최소화 여부, 기본키(PK) 및 식별자 명확성 점검
               - **확장성 및 유지보수성**: 대용량 트래픽 처리 및 MSA 확장에 유리한 구조인지 평가
               - **비즈니스 목적 명확화**: 테이블 설계가 비즈니스 로직(XML 쿼리 등) 목적에 부합하는지 점검

            [DDL 소스 코드]
            {source_code}
            """
    else:
        # [Java/XML 전용 프롬프트] 비즈니스 로직 및 객체/서비스 의존성 분석에 집중
        if is_chunk:
            prompt = f"""
            당신은 MSA 아키텍트입니다. 다음 코드는 원본 파일이 너무 커서 분할된 파일의 일부분(Part {chunk_info})입니다.
            이 코드 조각을 바탕으로 다음을 수행해주세요.
            1. **Bounded Context 정의 및 DDD 설계**: 이 코드 조각이 포함하는 핵심 비즈니스 로직을 바탕으로 명확한 **Bounded Context**를 정의하고, 도메인 및 **DDD 애그리거트(Aggregate) 단위와 루트(Root)**를 식별할 것 (기준에 따라 분석 후, 식별된 객체/도메인 정보를 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 프로세스 체계(LV1~LV5), 도메인(Bounded Context), 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
               - **프로세스 체계 (LV1~LV5)**: 해당 클래스나 쿼리가 지원하는 업무를 비즈니스 프로세스 관점(LV1: 밸류체인/대분류, LV2: 메가프로세스/중분류, LV3: 주요프로세스/소분류, LV4: 서브프로세스, LV5: 단위업무/액티비티)으로 분류하여 명시할 것.
            2. **물리적 분리를 위한 컨텍스트 디커플링**: 서로 다른 Bounded Context 간의 강결합된 객체 참조나 서비스 호출, DB 조인 등을 찾아내어, 독립적인 마이크로서비스로 완전히 분리하기 위한 리팩토링 방안 지적 (의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것).
            3. **데이터 정합성 보장 방안**: 분리된 서비스 간 트랜잭션 처리를 위해 API 호출 대신 Saga 패턴, 트랜잭셔널 아웃박스, 이벤트 발행/구독(Pub/Sub) 등을 활용하는 방안 제시.
            4. 의존성 관계가 있다면 반드시 ```mermaid ... ``` 마크다운 코드 블록 안에 Mermaid 문법으로 다이어그램 작성 (없으면 생략).
            5. **To-Be MSA API 설계 (Event Storming 관점)**: 현재 모놀리식 소스의 호출 및 비즈니스 로직을 바탕으로, 단순 As-Is 추출이 아닌 식별된 Bounded Context에 맞춰 도메인 주도(To-Be MSA) REST API 엔드포인트를 재설계하여 마크다운 표(Table)로 제시할 것 (Command/Query 분리, 이벤트 등 이벤트 스토밍 관점 반영. 헤더: API Endpoint, Method, 설명/상세).
            {global_context}
            
            [소스 코드 조각]
            {source_code}
            """
        else:
            prompt = f"""
            당신은 MSA 아키텍트입니다. 다음 소스 코드(Java 또는 XML 매퍼)를 분석하여 MSA 전환을 위한 가이드를 제공해주세요.
            1. **Bounded Context 정의 및 DDD 설계**: 도메인 (Domain) 분류 및 **DDD 애그리거트(Aggregate) 단위와 루트(Root)** 식별 (기준에 따라 분석 후, 식별된 객체/도메인 정보를 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 프로세스 체계(LV1~LV5), 도메인(Bounded Context), 애그리거트 루트, 마이그레이션 우선순위, 설명/상세).
               - **프로세스 체계 (LV1~LV5)**: 해당 클래스나 쿼리가 지원하는 업무를 비즈니스 프로세스 관점(LV1: 밸류체인/대분류, LV2: 메가프로세스/중분류, LV3: 주요프로세스/소분류, LV4: 서브프로세스, LV5: 단위업무/액티비티)으로 분류하여 명시할 것.
            2. **물리적 분리를 위한 컨텍스트 디커플링**: 서로 다른 Bounded Context 간의 강결합된 객체 참조나 서비스 호출, DB 조인 등 타 도메인과의 강결합 부분 분석 (의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것).
            3. **데이터 정합성 보장 방안 및 리팩토링 제안**: 분리된 서비스 간 트랜잭션 처리를 위해 API 조회를 넘어 Saga 패턴, 트랜잭셔널 아웃박스, 이벤트 발행/구독(Pub/Sub) 패턴 등을 활용하는 방안 제시.
            4. **UML 도메인 모델 다이어그램**: 도메인 주요 개념, Aggregate Root, 그리고 객체 간의 연관관계를 표준화된 UML 클래스 다이어그램 형태로 시각화할 것 (반드시 ```mermaid\nclassDiagram\n...``` 형태의 Mermaid 문법을 사용할 것).
            5. **To-Be MSA API 설계 (Event Storming 관점)**: 현재 모놀리식 소스의 호출 및 비즈니스 로직을 바탕으로, 단순 As-Is 추출이 아닌 식별된 Bounded Context에 맞춰 도메인 주도(To-Be MSA) REST API 엔드포인트를 재설계하여 마크다운 표(Table)로 제시할 것 (Command/Query 분리, 이벤트 등 이벤트 스토밍 관점 반영. 헤더: API Endpoint, Method, 설명/상세).

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
async def summarize_chunks_with_qwen(chunk_results_text: str, file_name: str) -> str:
    """분할 분석된 청크 결과들을 하나로 병합(Reduce)하여 최종 요약 리포트를 생성합니다."""
    if len(chunk_results_text) > 40000:
        chunk_results_text = chunk_results_text[:40000] + "\n\n... (중략: 토큰 보호를 위해 잘림) ..."
        
    prompt = f"""
    당신은 MSA 아키텍트입니다. 다음은 대용량 파일 '{file_name}'을(를) 여러 청크로 나누어 개별 분석한 결과들의 모음입니다.
    이 파편화된 결과들을 종합하여, 이 파일에 대한 **하나의 통합된 MSA 분석 리포트**를 작성해 주세요.
    
    [필수 포함 항목]
    1. 시스템의 핵심 로직, 도메인 및 **DDD 애그리거트(Aggregate)** 식별 (전체적인 관점에서, 식별된 도메인(Bounded Context)과 데이터베이스 객체 매핑은 마크다운 표(Table) 형식으로 정리할 것. 헤더: 구분, 객체명, 프로세스 체계(LV1~LV5), 도메인(Bounded Context), 애그리거트 루트, 마이그레이션 우선순위, 설명/상세)
    2. **물리적 DB 분리 전략**: 타 도메인과의 강결합 부분(FK 포함) 및 문제점 종합 (개별 청크에서 식별된 외부 참조 FK 관계들을 연결하여 복원하되, 서로 다른 Bounded Context 간의 물리적 FK 제약조건은 제거하는 방향으로 아키텍처를 제시하고 의존 대상, 대상 도메인, 의존 사유를 마크다운 표(Table) 형식으로 정리할 것)
    3. **데이터 마이그레이션 및 정합성 보장 제안**: 마이그레이션 우선순위(Phase 1, 2, 3) 및 물리적 분리 이후의 데이터 일관성을 위한 MSA 아키텍처 리팩토링 제안 (트랜잭셔널 아웃박스, Saga, CQRS, 이벤트 기반 동기화 등 구체적 패턴 제시)
    4. 전체 파일 수준의 의존성 관계 다이어그램 (반드시 ```mermaid ... ``` 마크다운 코드 블록 안에 Mermaid 문법으로 작성할 것)
    5. **To-Be MSA API 설계 (Event Storming 관점)**: 개별 청크에서 발견된 API/비즈니스 호출을 모두 취합하여, 식별된 Bounded Context에 맞춘 To-Be REST API로 재정규화하여 마크다운 표(Table)로 제시할 것 (Command/Query 분리, 이벤트 등 이벤트 스토밍 관점 반영. 헤더: API Endpoint, Method, 설명/상세).

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


async def generate_summary_with_qwen(combined_text: str) -> str:
    """추출된 CSV 데이터를 기반으로 전체 시스템의 요약 아키텍처 가이드를 생성합니다."""
    prompt = f"""
    당신은 수석 MSA 아키텍트입니다. 다음은 1,700여 개의 대규모 모놀리식 시스템 파일을 분석하여 추출해 낸 '프로세스 체계(LV1~LV5) 및 도메인 맵핑'과 '타 도메인 간 강결합(Coupling) 현황' 데이터입니다. 
    이 압축된 구조화 데이터를 바탕으로, 전체 시스템을 한눈에 조망할 수 있는 'To-Be MSA 아키텍처 가이드'를 마크다운 형식으로 작성해 주세요.
    
    [필수 포함 항목]
    1. **To-Be MSA 프로세스 및 도메인 맵 (Process & Domain Map)**: 제공된 데이터를 바탕으로, 비즈니스 프로세스(LV1~LV5)에 따라 도메인과 애그리거트 루트(Aggregate Root)들이 어떻게 묶여 있는지 체계적으로 보여주는 종합 표(Table) 또는 계층 구조(Tree)를 작성할 것.
    2. **물리적 DB 분리 및 정합성 전략 (핵심)**: 제공된 [타 Bounded Context 간 강결합 현황] 데이터를 반드시 분석하여, 도메인 간 물리적 DB 분리 시 어떤 제약조건(FK, JOIN 등)을 끊어내야 하는지 구체적으로 명시할 것. 끊어낸 후 분산 환경에서의 데이터 정합성 유지를 위해 **어떤 도메인 간에 트랜잭셔널 아웃박스(Transactional Outbox)나 Saga 패턴이 적용되어야 하는지** 실질적인 아키텍처 대안을 제시할 것.
    3. **글로벌 UML 도메인 모델 다이어그램**: 핵심 도메인(Bounded Context) 간의 관계와 그 내부의 주요 Aggregate Root들을 보여주는 거시적인 아키텍처 다이어그램을 작성 (반드시 ```mermaid\nclassDiagram\n...``` 형태의 Mermaid 문법 사용).

    [프로세스 체계, 도메인 및 의존성 압축 데이터]
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
    return response.choices[0].message.content.message.contentt