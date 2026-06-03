import os
import markdown
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from jinja2 import Environment, FileSystemLoader
from config import SOURCE_DIRECTORY

RESULT_DIR = "./analysis_results"
TEMPLATE_DIR = "./templates"
OUTPUT_FILE = "msa_analysis_report.html"

def main(stats: Optional[Dict[str, Any]] = None) -> None:
    if stats is None:
        stats = {}
    if not os.path.exists(RESULT_DIR):
        print(f"[{RESULT_DIR}] 디렉토리가 없습니다. 먼저 분석(main.py)을 실행해주세요.")
        return

    reports = []
    summary_content = ""
    summary_file_path = os.path.join(RESULT_DIR, "_architecture_summary.md")
    
    if os.path.exists(summary_file_path):
        with open(summary_file_path, "r", encoding="utf-8") as f:
            summary_content = f.read()

    # 생성된 .md 파일들을 읽어서 리스트에 추가
    # os.listdir 대신 os.scandir를 사용하여 메모리 오버헤드 방지
    with os.scandir(RESULT_DIR) as it:
        entries = [entry for entry in it if entry.is_file() and entry.name.endswith(".md") and entry.name != "_architecture_summary.md"]
    
    for entry in sorted(entries, key=lambda e: e.name):
        with open(entry.path, "r", encoding="utf-8") as f:
            reports.append({
                "name": entry.name,
                "content": f.read()
            })

    if not reports:
        print("생성된 Markdown 리포트 파일이 없습니다.")
        return

    print(f"총 {len(reports)}개의 리포트를 취합하여 HTML 리포트를 생성합니다...")

    analysis_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Jinja2 환경 구성 및 HTML 렌더링
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("report_template.html")
    html_content = template.render(
        reports=reports, 
        summary_content=summary_content,
        analysis_date=analysis_date,
        source_directory=SOURCE_DIRECTORY,
        stats=stats
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"✨ 통합 HTML 리포트 생성이 완료되었습니다: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
