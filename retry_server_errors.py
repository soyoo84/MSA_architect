import os
import concurrent.futures
import logging
from tqdm import tqdm
from pebble import ProcessPool

# 기존 파이프라인의 모듈들을 재사용합니다.
from config import SOURCE_DIRECTORY, LLM_MAX_WORKERS, WORKER_TIMEOUT_SECONDS
from parser import get_target_files
from main import process_file, generate_architecture_summary, create_zip_archive
import generate_report
import merge_reports

LOG_FILE = "skipped_files.log"

def main():
    if not os.path.exists(LOG_FILE):
        print(f"[{LOG_FILE}] 파일이 존재하지 않습니다. 스킵된 파일이 없습니다.")
        return

    print("로그에서 서버 장애(VRAM OOM) 및 타임아웃으로 스킵된 파일 목록을 추출합니다...")

    # 1. 로그 파일에서 [SKIP-SERVER-ERROR] 또는 [TIMEOUT]이 기록된 파일명 추출
    failed_filenames = set()
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if "[SKIP-SERVER-ERROR]" in line or "[TIMEOUT]" in line:
                # 라인 형식: [SKIP-SERVER-ERROR] LLM 서버 장애로 분석 보류: UserMapper.xml 또는 [TIMEOUT] ... : UserMapper.xml
                # 마지막 ':' 이후의 텍스트가 순수 파일명입니다.
                filename = line.split(":")[-1].strip()
                if filename:
                    failed_filenames.add(filename)

    if not failed_filenames:
        print("[SKIP-SERVER-ERROR] 또는 [TIMEOUT] 상태로 기록된 파일이 없습니다. 모두 정상 처리되었거나 다른 사유로 스킵되었습니다.")
        return

    print(f"총 {len(failed_filenames)}개의 복구 대상(서버 장애/타임아웃) 파일명을 찾았습니다.")

    # 2. 전체 대상 파일 목록에서 해당 파일명과 일치하는 실제 절대 경로 수집
    all_files = get_target_files(SOURCE_DIRECTORY)
    retry_target_files = [f for f in all_files if os.path.basename(f) in failed_filenames]

    print(f"실제 경로가 매핑된 재시도 대상 파일: {len(retry_target_files)}개\n")

    if not retry_target_files:
        return

    print(f"[{LLM_MAX_WORKERS}]개의 워커(Worker)로 복구 분석을 시작합니다...\n")

    # 3. 기존 main.py의 분석 로직을 100% 활용하여 재시도 파이프라인 가동
    with ProcessPool(max_workers=LLM_MAX_WORKERS) as pool:
        future_to_file = {}
        for file_path in retry_target_files:
            future = pool.schedule(process_file, args=(file_path,), timeout=WORKER_TIMEOUT_SECONDS)
            future_to_file[future] = file_path
            
        for future in tqdm(concurrent.futures.as_completed(future_to_file), total=len(retry_target_files), desc="재시도 진행률"):
            file_path = future_to_file[future]
            try:
                result_msg = future.result()
                tqdm.write(result_msg)
            except concurrent.futures.TimeoutError:
                file_name = os.path.basename(file_path)
                timeout_msg = f"[TIMEOUT] 분석 시간 초과 ({WORKER_TIMEOUT_SECONDS}초) - 워커를 교체합니다: {file_name}"
                tqdm.write(timeout_msg)
                logging.error(f"재시도 분석 중 타임아웃 발생 ({WORKER_TIMEOUT_SECONDS}초 초과): {file_path}")
                with open(LOG_FILE, "a", encoding="utf-8") as log_file:
                    log_file.write(timeout_msg + "\n")
            except Exception as exc:
                tqdm.write(f"[ERROR] 재시도 분석 중 치명적인 오류 발생: {exc}")
                logging.error(f"재시도 워커(Worker) 중 치명적인 오류 발생: {exc}", exc_info=True)

    print("\n🎉 복구(재시도) 작업이 완료되었습니다. 결과물을 갱신합니다...")
    generate_architecture_summary()
    generate_report.main()
    merge_reports.main()
    create_zip_archive()
    print("✨ 리포트 갱신 및 ZIP 압축이 모두 완료되었습니다!")

if __name__ == "__main__":
    main()