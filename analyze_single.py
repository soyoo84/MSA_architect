import argparse
import os
from main import process_file
from config import SOURCE_DIRECTORY

RESULT_DIR = "./analysis_results"

def main():
    parser = argparse.ArgumentParser(description="지정된 단일 파일만 독립적으로 MSA 분석을 수행합니다.")
    parser.add_argument(
        "--file", 
        type=str, 
        required=True, 
        help="분석할 소스 파일의 상대 경로나 절대 경로 (예: monolith_source/src/main/java/User.java)"
    )
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="기존에 분석된 마크다운 결과가 존재하더라도 삭제하고 처음부터 다시 분석합니다."
    )
    
    args = parser.parse_args()
    file_path = args.file
    
    if not os.path.exists(file_path):
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
        return
        
    # main.py 와 동일한 결과물 파일명 생성 로직
    rel_path = os.path.relpath(file_path, SOURCE_DIRECTORY)
    safe_file_name = rel_path.replace(os.sep, "_")
    result_file = os.path.join(RESULT_DIR, f"{safe_file_name}_analysis.md")
    
    # 디렉토리 확인 및 생성
    os.makedirs(RESULT_DIR, exist_ok=True)
    
    # --force 옵션이 주어졌고 결과 파일이 있다면 삭제
    if args.force and os.path.exists(result_file):
        print(f"♻️ [Force] 기존 분석 결과를 삭제하고 강제로 재분석합니다: {result_file}")
        try:
            os.remove(result_file)
        except Exception as e:
            print(f"❌ 파일 삭제 실패: {e}")
            return
            
    print(f"🚀 단일 파일 분석 시작: {file_path}")
    print("AI 모델이 코드를 분석 중입니다. 잠시만 기다려주세요...")
    
    try:
        # main.py의 분석 핵심 워커 함수 재사용
        result_msg = process_file(file_path)
        print(f"\n✨ 완료 메시지: {result_msg}")
        
        if "[SUCCESS]" in result_msg:
            print(f"👉 분석 결과가 저장되었습니다: {result_file}")
            print(f"팁: 전체 요약 리포트에 반영하려면 'python main.py'를 한 번 더 실행하세요 (새로 추가된 내용만 병합됩니다).")
            
    except Exception as e:
        print(f"\n❌ 분석 중 치명적 오류가 발생했습니다: {e}")

if __name__ == "__main__":
    main()
