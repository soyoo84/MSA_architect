import os

RESULT_DIR = "./analysis_results"
OUTPUT_FILE = "merged_msa_report.md"

def main():
    if not os.path.exists(RESULT_DIR):
        print(f"[{RESULT_DIR}] 디렉토리가 없습니다. 먼저 분석(main.py)을 실행해주세요.")
        return

    print("여러 개의 마크다운 분석 결과를 하나의 파일로 병합합니다...")
    
    merged_parts = ["# 🚀 MSA 전환 분석 통합 리포트\n\n"]
    
    # 1. 전체 요약본(_architecture_summary.md)이 존재한다면 가장 맨 위에 배치
    summary_file = os.path.join(RESULT_DIR, "_architecture_summary.md")
    if os.path.exists(summary_file):
        with open(summary_file, "r", encoding="utf-8") as f:
            merged_parts.append(f"{f.read()}\n\n---\n\n")
            
    merged_parts.append("## 📂 개별 파일 분석 상세 내역\n\n")

    # 2. 나머지 모든 개별 분석 마크다운 파일을 순회하며 내용 이어붙이기
    count = 0
    # os.scandir를 활용해 파일 탐색 최적화
    with os.scandir(RESULT_DIR) as it:
        entries = [entry for entry in it if entry.is_file() and entry.name.endswith(".md") and entry.name not in ["_architecture_summary.md", OUTPUT_FILE]]
    
    for entry in sorted(entries, key=lambda e: e.name):
        with open(entry.path, "r", encoding="utf-8") as f:
            # 구분선과 함께 파일의 내용 병합
            merged_parts.append(f"### 📄 {entry.name}\n\n{f.read()}\n\n<br>\n\n---\n\n")
        count += 1

    if count == 0:
        print("병합할 개별 Markdown 리포트 파일이 없습니다.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("".join(merged_parts))

    print(f"✨ 총 {count}개의 개별 리포트가 하나의 파일({OUTPUT_FILE})로 성공적으로 병합되었습니다.")

if __name__ == "__main__":
    main()