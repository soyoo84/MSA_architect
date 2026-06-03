# 🚀 Legacy-to-MSA Automator (레거시 to MSA 자동 분석 파이프라인)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/LLM-Qwen_3.5_(OpenAI_API)-412991?logo=openai&logoColor=white)
![Asyncio](https://img.shields.io/badge/Architecture-Asyncio_%2B_Multiprocessing-FFca28)

## 📖 프로젝트 소개 (About the Project)
**Legacy-to-MSA Automator**는 방대한 레거시 모놀리식(Monolithic) 시스템의 소스 코드(Java, XML)와 데이터베이스 스키마(DDL)를 AI가 자동으로 분석하여, **마이크로서비스 아키텍처(MSA) 전환을 위한 도메인 설계도와 물리적 분리 가이드를 제공하는 엔터프라이즈급 AI 자동화 파이프라인**입니다.

이 도구는 단순한 코드 분석을 넘어 다음과 같은 심층적인 아키텍처 가이드를 제공합니다:
- **도메인 주도 설계(DDD) 기반 Bounded Context 정의**: 비즈니스 프로세스(LV1~LV5)에 따라 코드를 분류하고 Aggregate Root를 식별합니다.
- **물리적 DB 분리 및 정합성 전략**: MSA의 핵심인 데이터베이스의 물리적 분리를 위해 FK(외래 키) 단절 전략을 제시하고, Saga 패턴 및 트랜잭셔널 아웃박스(Transactional Outbox) 등을 활용한 데이터 정합성 보장 방안을 가이드합니다.
- **To-Be MSA API (Event Storming) 자동 추출**: 레거시의 단순한 호출 로직을 그대로 가져오지 않고, Event Storming 관점(Command, Query 분리)에서 식별된 Bounded Context에 맞춰 재설계된 **To-Be REST API 명세서(Swagger/OpenAPI)**를 자동 생성합니다.
- **UML 표준 시각화**: 텍스트 형태의 요약을 넘어, 추출된 Bounded Context 내의 엔티티(Entity) 및 연관관계를 **UML 클래스 다이어그램** 형태로 브라우저에서 바로 확인할 수 있도록 자동 시각화(Mermaid.js)합니다.

---

## ✨ 핵심 파이프라인 프로세스 (How it Works)

본 프로그램은 사용자가 실행 버튼을 누르는 순간부터 결과물을 압축하기까지 다음과 같은 고도화된 체계(Map-Reduce)로 작동합니다.

1. **지능형 파일 청킹 (Parser & Chunker)**
   * 수천 줄이 넘는 Java 코드나 XML 매퍼, 거대한 DDL 파일을 그대로 LLM에 던지면 컨텍스트 한도 초과(OOM)가 발생합니다.
   * `parser.py`가 AST(추상 구문 트리)와 정규식을 이용해 Java는 '메서드' 단위로, XML은 '쿼리 태그' 단위로, DDL은 '테이블' 단위로 쪼개어(Chunking) 토큰 오버플로우를 원천 차단합니다.
2. **하이브리드 병렬 LLM 분석 (Map)**
   * `main.py`는 `Pebble` 멀티프로세싱을 통해 파일 단위로 CPU 워커를 띄우고, 각 파일 내의 잘게 쪼개진 청크(Chunk)들은 `asyncio`를 통해 비동기로 사내 LLM에 동시 전송됩니다.
   * 네트워크 병목을 최소화하여 분석 속도를 극대화합니다.
3. **토큰 압축 병합 (Reduce)**
   * 분석된 파편화 조각들을 모아 해당 파일의 단일 마크다운 리포트로 통합합니다.
   * **글로벌 요약 최적화**: 1,700여 개가 넘는 대규모 파일을 전체 요약할 때 텍스트를 무식하게 합치지 않습니다. 개별 파일에서 도출된 정보(프로세스 레벨, 도메인, Aggregate Root)를 **CSV 형태(`domain_table_mapping.csv`)로 먼저 추출한 뒤, 트리 맵 형태로 극도로 압축**하여 LLM에 전달합니다. 이를 통해 초대규모 프로젝트도 거시적인 MSA 글로벌 요약 다이어그램을 성공적으로 그려냅니다.
4. **산출물 및 시각화 자동화 (Reporting)**
   * 생성된 마크다운을 하나로 합치고(`merge_reports.py`), 웹 브라우저에서 UML 클래스 다이어그램을 인터랙티브하게 볼 수 있는 HTML 리포트(`generate_report.py`)를 렌더링합니다.
   * 분석된 API 엔드포인트를 모아 Swagger 규격 파일(`generate_swagger.py`)까지 만들어 낸 후, 이 모든 것을 `msa_analysis_output.zip`으로 압축합니다.

---

## 📁 프로젝트 구조 (Directory Structure)

본 프로그램을 실행하기 전과 후의 전체적인 폴더 및 파일 구조는 다음과 같습니다. (분석을 시작하면 필요한 디렉토리들은 자동으로 생성됩니다.)

```text
MSA_architect/
├── .env                        # 환경 변수 설정 파일 (DB 접속, LLM 키 등)
├── requirements.txt            # 파이썬 라이브러리 의존성 목록
├── main.py                     # 🚀 메인 실행 스크립트 (파이프라인 시작점)
├── llm_service.py              # LLM 비동기 호출 및 프롬프트 관리
├── parser.py                   # AST/정규식 기반 대용량 소스 분할기
├── extract_ddl.py              # DB 스키마 자동 추출 스크립트
├── generate_report.py          # 브라우저용 HTML 리포트 렌더링 스크립트
├── merge_reports.py            # 파편화된 리포트 마크다운 통합 스크립트
├── extract_csv.py              # 프로세스/도메인 매핑 CSV 데이터 추출 스크립트
├── generate_swagger.py         # To-Be API Swagger 생성 스크립트
├── analyze_single.py           # 단일 파일 지정 분석 스크립트
├── retry_server_errors.py      # 에러/누락 파일 재처리 스크립트
├── clean.py                    # 산출물 및 로그 초기화 스크립트
├── config.py                   # 환경 변수 로드 및 공통 설정
├── templates/                  # 📂 (자동생성)
│   └── report_template.html    # 웹 리포트 렌더링용 HTML 템플릿
├── monolith_source/            # 📂 (자동생성) 분석할 레거시 소스 코드를 넣는 곳
│   └── schema.sql              # (자동추출) DB 스키마 파일
├── analysis_results/           # 📂 (자동생성) 개별 분석 마크다운 결과물 저장소
└── msa_analysis_output.zip     # 📦 (최종결과) 모든 분석 산출물이 압축된 공유용 파일
```

---

## 🚀 처음 오신 분들을 위한 시작 가이드 (Getting Started)

처음 파이썬 프로그램을 다루시는 분들도 쉽게 따라 하실 수 있도록 구성했습니다.

### Step 1. 사전 준비물 확인
- **Python 3.9 이상**이 설치되어 있어야 합니다.
- 터미널(또는 명령 프롬프트)을 열고 아래 명령어를 입력하여 필요한 파이썬 라이브러리를 모두 설치합니다.
  ```bash
  pip install -r requirements.txt
  ```

### Step 2. 환경 변수(`.env`) 셋팅
프로그램이 코드를 읽어올 위치와 DB에 접속할 정보, 사내 LLM 접근 키를 알려주기 위해 프로젝트 최상단에 `.env` 파일을 생성하고 내용을 작성합니다.

```dotenv
# 1. MSA로 전환할 레거시 소스 코드가 들어있는 최상위 폴더 경로
SOURCE_DIRECTORY=C:/workspace/legacy_project/src

# 2. 데이터베이스 스키마(DDL) 자동 추출을 위한 DB 접속 URL (필수 아님, DB 연동 시에만)
# 형태: [DB종류]+[드라이버]://[아이디]:[비밀번호]@[주소]:[포트]/[DB명]
# MySQL 예시: mysql+pymysql://root:1234@localhost:3306/legacy_db
# Oracle 예시: oracle+cx_oracle://admin:1234@192.168.0.10:1521/?service_name=orcl
DB_URL=mysql+pymysql://root:1234@localhost:3306/legacy_db

# 3. 사내 AI(LLM) 접근 키
LLM_BASE_URL=http://your-internal-llm-server/v1
LLM_API_KEY=your_internal_llm_api_key
LLM_MODEL_NAME=qwen3.5

# 4. 분석에서 제외할 폴더 지정 (쉼표로 구분)
EXCLUDE_PATHS=com/example/common,src/test

# 5. 성능 조절 (※ OOM 오류가 잦다면 LLM_MAX_WORKERS 숫자를 2~3으로 줄이세요)
LLM_MAX_WORKERS=5
WORKER_TIMEOUT_SECONDS=300
ASYNC_CHUNK_CONCURRENCY=3
ASYNC_CHUNK_CONCURRENCY_SQL=1
```

### Step 3. (권장) DB 스키마 자동 추출하기
MSA 전환 시 데이터베이스 분리 설계는 가장 중요합니다. 프로그램이 DB를 분석할 수 있도록 코드가 있는 폴더(`SOURCE_DIRECTORY`) 안에 `.sql` 파일을 만들어 주어야 합니다.

`.env`에 `DB_URL`을 설정해 두었다면, 터미널에서 명령어 한 줄로 DB에 직접 접속해 자동으로 `.sql` 파일을 만들어낼 수 있습니다.
*(DB 종류에 따라 `pip install pymysql` 또는 `pip install cx_Oracle`이 선행되어야 합니다.)*

```bash
# 기본 실행 (.env의 DB_URL 설정값을 읽어서 소스 폴더에 schema.sql을 자동 생성)
python extract_ddl.py

# 오라클 등에서 특정 스키마만 콕 집어서 추출하고 싶은 경우
python extract_ddl.py --schema "MY_SCHEMA"
```

### Step 4. 본격적인 AI 분석 파이프라인 가동!
준비가 끝났습니다. 아래 명령어를 실행하고 커피 한 잔 드시고 오시면 됩니다.
```bash
python main.py
```
* **이어하기 기능**: 파일이 너무 많아 중간에 컴퓨터를 끄더라도 걱정 마세요. 다시 실행하면 이미 분석이 완료된 파일은 1초 만에 `[SKIP]` 처리되며 남은 파일부터 이어서 분석합니다.

---

## 🎁 결과물 확인하기 (Outputs)

파이프라인이 100% 완료되면 화면에 성공률이 뜨면서 프로젝트 폴더에 `msa_analysis_output.zip` 이라는 압축 파일이 생성됩니다. 이 파일을 압축 해제하면 다음의 보물 같은 산출물들을 확인할 수 있습니다.

1. **`msa_analysis_report.html` (가장 중요 ⭐)**
   * 마우스를 더블 클릭하여 웹 브라우저(Chrome 등)로 여세요.
   * 왼쪽 목차를 클릭하여 개별 파일의 분석 결과를 볼 수 있으며, 화면에 **UML 클래스 다이어그램**이 예쁘게 그려진 것을 볼 수 있습니다.
2. **`domain_table_mapping.csv` 외 CSV 파일 3종**
   * 엑셀로 열어보시면 전체 소스 코드가 어떤 비즈니스 프로세스(LV1~LV5)와 도메인(Bounded Context)으로 맵핑되어 있는지 표 형태로 깔끔하게 정리되어 있습니다. (마이그레이션 우선순위 도출용)
3. **`swagger.json`**
   * 레거시 코드 내부에 숨어있던 API 호출 엔드포인트들을 찾아내어 OpenAPI(Swagger) 규격으로 만들어 줍니다. Swagger UI에 드래그 앤 드롭해서 시각적으로 확인하세요.

---

## 🚑 장애 복구 및 관리 (Recovery & Cleanup)

**1. 누락된 파일만 재분석하기**
서버 네트워크가 잠시 끊겼거나 사내 LLM VRAM 부족으로 몇몇 파일 분석이 `[TIMEOUT]`으로 실패했나요? 
처음부터 다시 할 필요 없이 아래 명령어만 치면, 실패한 파일만 쏙쏙 찾아내어 재시도합니다.
```bash
python retry_server_errors.py
```

**2. 단일 파일만 콕 집어서 다시 분석하기**
특정 소스 파일의 내용이 변경되었거나, 전체를 돌리지 않고 딱 한 파일만 다시 분석해보고 싶을 때 사용합니다. `--force` 옵션을 주면 기존 결과를 덮어씁니다.
```bash
python analyze_single.py --file "monolith_source/src/main/java/com/example/UserController.java" --force
```

**3. 초기화하기 (새 프로젝트 시작)**
다른 프로젝트의 소스 코드를 분석하고 싶거나, 결과를 싹 지우고 처음부터 다시 하고 싶다면 아래 명령어를 입력하세요. 깔끔하게 모든 로그와 결과물을 청소해 줍니다.
```bash
python clean.py
```