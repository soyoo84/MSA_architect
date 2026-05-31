import os
import concurrent.futures
import asyncio
import logging
import openai
from typing import Dict, Any
from tqdm import tqdm
from pebble import ProcessPool

# 작성해둔 config.py에서 설정값과 초기화된 LLM 클라이언트를 가져옵니다.
from config import SOURCE_DIRECTORY, LLM_MAX_WORKERS, WORKER_TIMEOUT_SECONDS, ASYNC_CHUNK_CONCURRENCY, ASYNC_CHUNK_CONCURRENCY_SQL, EXCLUDE_PATHS
from parser import get_target_files, chunk_java_code, chunk_xml_code, chunk_sql_code, extract_sql_object_names
from llm_service import analyze_with_qwen, summarize_chunks_with_qwen, generate_summary_with_qwen
from diagram import render_graphviz_to_svg
import generate_report
import merge_reports
import extract_csv
import generate_swagger
import zipfile

RESULT_DIR = "./analysis_results"

# 분석 결과를 저장할 디렉토리 생성
os.makedirs(RESULT_DIR, exist_ok=True)


def process_file(file_path: str) -> str:
    """단일 파일을 분석하고 결과를 저장하는 워커 함수입니다."""
    # 1. 파일 이름 충돌 방지: 패키지(디렉토리) 경로를 언더스코어로 결합하여 고유한 파일명 생성 (예: src_main_java_User.java)
    rel_path = os.path.relpath(file_path, SOURCE_DIRECTORY)
    safe_file_name = rel_path.replace(os.sep, "_")
    
    file_name = os.path.basename(file_path) # 로깅/리포트 타이틀용 원본 이름
    result_file = os.path.join(RESULT_DIR, f"{safe_file_name}_analysis.md")
    
    # [체크포인트] 이미 분석 완료된 파일은 건너뜁니다.
    if os.path.exists(result_file):
        return f"[SKIP] 이미 분석됨: {file_name}"

    with open(file_path, 'r', encoding='utf-8') as f:
        source_code = f.read()
        
    line_count = source_code.count('\n') + 1
    needs_chunking = False
    
    # [사전 감지] 파일 라인 수가 3000줄 이상인 경우 사전에 분할 로직으로 우회
    if line_count >= 3000:
        logging.warning(f"파일이 너무 큽니다 ({line_count}줄). 분할 분석을 시도합니다: {file_name}")
        needs_chunking = True
        
    result_text = ""
    
    if not needs_chunking:
        try:
            # LLM 분석 요청 (단일 파일 비동기 호출, 파일명 전달)
            result_text = asyncio.run(analyze_with_qwen(source_code, file_name=file_name))
        except openai.BadRequestError as e:
            # 토큰 한도 초과 등 400 에러 발생 시
            logging.warning(f"토큰 한도 초과 ({file_name}). 분할 분석을 시도합니다: {e}")
            needs_chunking = True
        except (openai.APIConnectionError, openai.APIStatusError, openai.APITimeoutError) as e:
            # VRAM OOM 등으로 서버가 완전히 터진 경우 (조기 포기)
            logging.error(f"🚨 사내 LLM 서버 다운 의심 (VRAM OOM 등) ({file_name}): {e}", exc_info=True)
            return f"[SKIP-SERVER-ERROR] LLM 서버 장애로 분석 보류: {file_name}"
        except Exception as e:
            logging.error(f"분석 중 에러 발생 ({file_name}): {e}", exc_info=True)
            return f"[ERROR] 분석 실패: {file_name} ({e})"
            
    # needs_chunking이 True가 된 경우 분할 분석 수행
    if needs_chunking:
        global_context = ""
        
        if file_name.endswith(".xml"):
            chunks = chunk_xml_code(source_code, max_lines=1500)
            chunk_type = "쿼리(태그)"
        elif file_name.endswith(".sql"):
            chunks = chunk_sql_code(source_code, max_lines=1500)
            chunk_type = "테이블(DDL)"
            
            # SQL 파일인 경우 전체 테이블/객체 목록을 추출하여 Global Context로 생성
            object_names = extract_sql_object_names(source_code)
            if object_names:
                global_context = f"\n[전체 시스템 데이터베이스 객체 목록 (참고용: 현재 청크에 없는 객체와의 외부 FK 연관 관계 식별 시 활용)]\n{', '.join(object_names)}\n"
        else:
            chunks = chunk_java_code(source_code, max_lines=1500)
            chunk_type = "메서드"
            
        raw_chunk_parts = []
        
        # 청크 조각들을 비동기로 동시에 요청합니다.
        async def process_all_chunks():
            # 사내 LLM 서버 보호를 위해 Semaphore 적용 (SQL 파일은 별도의 엄격한 제한 적용)
            concurrency_limit = ASYNC_CHUNK_CONCURRENCY_SQL if file_name.endswith(".sql") else ASYNC_CHUNK_CONCURRENCY
            sem = asyncio.Semaphore(concurrency_limit)
            
            async def bounded_analyze(chunk, i):
                async with sem:
                    return await analyze_with_qwen(chunk, is_chunk=True, chunk_info=f"{i+1}/{len(chunks)}", file_name=file_name, global_context=global_context)
                    
            tasks = [bounded_analyze(chunk, i) for i, chunk in enumerate(chunks)]
            return await asyncio.gather(*tasks, return_exceptions=True)
            
        chunk_responses = asyncio.run(process_all_chunks())
        
        for i, result in enumerate(chunk_responses):
            if isinstance(result, Exception):
                e = result
                if isinstance(e, (openai.APIConnectionError, openai.APIStatusError, openai.APITimeoutError)):
                    logging.error(f"🚨 청크 분석 중 서버 다운 의심 ({file_name} - {i+1}): {e}", exc_info=e)
                    raw_chunk_parts.append(f"### 🧩 Part {i+1}/{len(chunks)}\n> 🚨 LLM 서버 장애 (VRAM OOM 등)로 분석 실패\n\n")
                else:
                    logging.error(f"청크 분석 실패 ({file_name} - {i+1}): {e}", exc_info=e)
                    raw_chunk_parts.append(f"### 🧩 Part {i+1}/{len(chunks)}\n> ⚠️ LLM 분석 실패 (토큰 초과 또는 오류): {e}\n\n")
            else:
                raw_chunk_parts.append(f"### 🧩 Part {i+1}/{len(chunks)}\n{result}\n\n")
                
        raw_chunk_results = "".join(raw_chunk_parts)
                
        try:
            # Map-Reduce의 Reduce 단계: 모인 청크 결과들을 하나로 요약
            merged_result = asyncio.run(summarize_chunks_with_qwen(raw_chunk_results, file_name))
            result_text = f"> ⚠️ **대용량 파일 분할 분석 (Map-Reduce 적용)**\n> 원본 파일이 너무 커서 {len(chunks)}개의 청크({chunk_type} 단위)로 나누어 분석한 후, 하나의 리포트로 병합한 결과입니다.\n\n"
            result_text += merged_result
            
            # 상세 파편화 내역은 접기/펴기로 하단에 첨부
            result_text += f"\n\n<br><details><summary><b>🔍 개별 청크 분석 상세 보기 (클릭하여 펴기)</b></summary>\n\n---\n\n{raw_chunk_results}\n</details>"
        except Exception as e:
            logging.error(f"청크 결과 병합 실패 ({file_name}): {e}", exc_info=True)
            result_text = f"> ⚠️ **대용량 파일 분할 분석 (병합 실패)**\n> 요약 병합 중 오류가 발생하여 개별 청크 분석 결과를 그대로 출력합니다: {e}\n\n" + raw_chunk_results
    
    # Graphviz 로컬 렌더링 적용 및 이미지 경로로 치환
    result_text = render_graphviz_to_svg(result_text, file_name)
    
    with open(result_file, 'w', encoding='utf-8') as rf:
        rf.write(f"# {file_name} MSA 분석 리포트\n\n{result_text}")
        
    if needs_chunking:
        return f"[SUCCESS] 분할 분석 완료 (총 {len(chunks)}개 청크): {file_name}"
    else:
        return f"[SUCCESS] 분석 완료: {file_name}"


def generate_architecture_summary() -> None:
    """모든 개별 분석 결과를 모아 하나의 전체 요약 아키텍처 가이드를 생성합니다."""
    summary_file = os.path.join(RESULT_DIR, "_architecture_summary.md")
    
    if os.path.exists(summary_file):
        print("\n[SKIP] 전체 요약 아키텍처 가이드가 이미 존재합니다.")
        return

    print("\n전체 분석 결과를 종합하여 요약 아키텍처 가이드를 생성합니다 (시간이 다소 소요될 수 있습니다)...")
    
    combined_texts = []
    with os.scandir(RESULT_DIR) as it:
        for entry in it:
            if entry.is_file() and entry.name.endswith(".md") and entry.name != "_architecture_summary.md":
                with open(entry.path, "r", encoding="utf-8") as f:
                    combined_texts.append(f"--- {entry.name} ---\n{f.read()}\n\n")
                
    if not combined_texts:
        return
        
    combined_text = "".join(combined_texts)
        
    # LLM 토큰 한도를 보호하기 위해 최대 50,000자(약 1.5만~2만 토큰)로 텍스트 제한
    if len(combined_text) > 50000:
        combined_text = combined_text[:50000] + "\n\n... (중략: 토큰 한도 제한으로 일부 결과만 요약에 반영됨) ..."
        
    try:
        # llm_service를 통해 요약본 생성 (비동기 호출)
        summary_content = asyncio.run(generate_summary_with_qwen(combined_text))
        
        # 전체 요약 가이드에도 Graphviz 로컬 렌더링 적용
        summary_content = render_graphviz_to_svg(summary_content, "summary")
        
        with open(summary_file, 'w', encoding='utf-8') as rf:
            rf.write(f"# 🌟 전체 요약 아키텍처 가이드\n\n{summary_content}")
        print("✨ 전체 요약 아키텍처 가이드 생성이 완료되었습니다.")
    except Exception as e:
        print(f"[ERROR] 요약 가이드 생성 중 오류 발생: {e}")
        logging.error("전체 요약 아키텍처 가이드 생성 중 오류 발생", exc_info=True)


def create_zip_archive() -> None:
    """최종 분석 결과물과 리포트 파일들을 팀원 공유용 ZIP 파일로 압축합니다."""
    zip_filename = "msa_analysis_output.zip"
    print(f"\n최종 결과물들을 팀원 공유용 파일({zip_filename})로 압축합니다...")
    
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 1. 개별 분석 결과 마크다운 및 SVG 다이어그램 포함 (os.walk 대신 os.scandir 사용으로 속도 최적화)
            with os.scandir(RESULT_DIR) as it:
                for entry in it:
                    if entry.is_file():
                        arcname = os.path.relpath(entry.path, ".")
                        zipf.write(entry.path, arcname)
            # 2. 루트 디렉토리의 생성된 리포트 및 로그 파일들 포함
            for report in ["msa_analysis_report.html", "msa_analysis_report.pdf", "merged_msa_report.md", "domain_table_mapping.csv", "service_dependencies.csv", "api_endpoints.csv", "swagger.json", "error.log", "skipped_files.log"]:
                if os.path.exists(report):
                    zipf.write(report)
        print(f"✨ 압축 완료: {zip_filename} (이 파일을 팀원들과 공유하세요!)")
    except Exception as e:
        print(f"[ERROR] ZIP 압축 중 오류 발생: {e}")
        logging.error("ZIP 파일 생성 중 오류 발생", exc_info=True)


def main() -> None:
    print(f"소스 코드 디렉토리 '{SOURCE_DIRECTORY}'에서 분석을 시작합니다...\n")
    
    target_files = get_target_files(SOURCE_DIRECTORY, exclude_paths=EXCLUDE_PATHS)
    if not target_files:
        print("분석할 .java, .xml, .sql 파일이 존재하지 않습니다. 경로를 확인해주세요.")
        return

    print(f"총 {len(target_files)}개의 분석 대상(Java, XML, SQL) 파일을 찾았습니다.\n")

    print(f"[{LLM_MAX_WORKERS}]개의 워커(Worker)로 병렬 분석을 시작합니다...\n")

    total_files = len(target_files)
    success_count = 0
    skip_count = 0
    error_count = 0

    # Pebble ProcessPool을 사용하여 개별 작업 타임아웃(Timeout) 및 좀비 프로세스 방지 적용
    with ProcessPool(max_workers=LLM_MAX_WORKERS) as pool:
        # pool.schedule을 통해 개별 작업에 timeout 강제 지정
        future_to_file = {}
        for file_path in target_files:
            future = pool.schedule(process_file, args=(file_path,), timeout=WORKER_TIMEOUT_SECONDS)
            future_to_file[future] = file_path
        
        # tqdm을 적용하여 진행률 바 표시 (as_completed 결과가 나올 때마다 게이지가 올라감)
        for future in tqdm(concurrent.futures.as_completed(future_to_file), total=len(target_files), desc="분석 진행률"):
            file_path = future_to_file[future]
            try:
                result_msg = future.result()
                tqdm.write(result_msg)  # 프로그레스 바가 깨지지 않도록 일반 print 대신 tqdm.write 사용
                
                # 상태별 카운트 증가
                if "[SUCCESS]" in result_msg:
                    success_count += 1
                elif "[SKIP" in result_msg:
                    skip_count += 1
                else:
                    error_count += 1

                # [SKIP] 상태(크기 초과, 토큰 초과, 서버 장애)인 경우 로그 파일에 추가 저장
                if "[SKIP-LARGE]" in result_msg or "[SKIP-TOKEN-LIMIT]" in result_msg or "[SKIP-SERVER-ERROR]" in result_msg:
                    with open("skipped_files.log", "a", encoding="utf-8") as log_file:
                        log_file.write(result_msg + "\n")
            except concurrent.futures.TimeoutError:
                error_count += 1
                file_name = os.path.basename(file_path)
                timeout_msg = f"[TIMEOUT] 분석 시간 초과 ({WORKER_TIMEOUT_SECONDS}초) - 워커를 교체합니다: {file_name}"
                tqdm.write(timeout_msg)
                logging.error(f"파일 분석 중 타임아웃 발생 ({WORKER_TIMEOUT_SECONDS}초 초과): {file_path}")
                with open("skipped_files.log", "a", encoding="utf-8") as log_file:
                    log_file.write(timeout_msg + "\n")
            except Exception as exc:
                error_count += 1
                tqdm.write(f"[ERROR] 분석 중 치명적인 오류 발생: {exc}")
                logging.error(f"파일 분석 워커(Worker) 중 치명적인 오류 발생: {exc}", exc_info=True)

    # 결과 요약 출력
    print("\n" + "="*40)
    print("📊 MSA 분석 작업 완료 요약")
    print("="*40)
    print(f"전체 대상 파일 : {total_files}개")
    print(f"✅ 성공       : {success_count}개")
    print(f"⏭️ 스킵       : {skip_count}개")
    print(f"❌ 실패/오류  : {error_count}개")
    
    success_rate = 0.0
    if total_files > 0:
        success_rate = (success_count / total_files) * 100
        print(f"📈 전체 성공률 : {success_rate:.1f}%")
    print("="*40 + "\n")

    stats = {
        "total": total_files,
        "success": success_count,
        "skip": skip_count,
        "error": error_count,
        "rate": f"{success_rate:.1f}"
    }

    # 통합 아키텍처 요약본 생성
    generate_architecture_summary()
    
    # HTML/PDF 리포트 및 통합 마크다운 문서 생성
    generate_report.main(stats)
    merge_reports.main()
    
    # 도메인-테이블 및 서비스 의존성 CSV 통합 추출
    extract_csv.main()
    
    # API 엔드포인트로 Swagger 파일 자동 생성
    generate_swagger.main()
    
    # 모든 결과물을 ZIP으로 압축
    create_zip_archive()

if __name__ == "__main__":
    main()