import os
import shutil
import glob

def main():
    print("🧹 분석 산출물 정리를 시작합니다...")

    # 삭제할 단일 파일 및 패턴 목록
    files_to_remove = [
        "msa_analysis_report.html",
        "msa_analysis_report.pdf",
        "merged_msa_report.md",
        "domain_table_mapping.csv",
        "service_dependencies.csv",
        "api_endpoints.csv",
        "swagger.json",
        "msa_analysis_output.zip",
        "skipped_files.log"
    ]

    # error.log, error.log.1 등 순환 로그 파일 찾기
    for log_file in glob.glob("error.log*"):
        files_to_remove.append(log_file)

    # 파일 삭제 실행
    for file_path in set(files_to_remove):
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"  - 삭제 완료: {file_path}")
            except Exception as e:
                print(f"  - 삭제 실패 ({file_path}): {e}")

    # 분석 결과 디렉토리 삭제 실행
    result_dir = "./analysis_results"
    if os.path.exists(result_dir):
        try:
            shutil.rmtree(result_dir)
            print(f"  - 디렉토리 삭제 완료: {result_dir}/")
        except Exception as e:
            print(f"  - 디렉토리 삭제 실패 ({result_dir}): {e}")

    print("✨ 모든 산출물이 정리되었습니다! 깨끗한 상태에서 다시 분석을 시작할 수 있습니다.")

if __name__ == "__main__":
    main()