import os
import markdown
import pdfkit
import logging
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from config import SOURCE_DIRECTORY

RESULT_DIR = "./analysis_results"
TEMPLATE_DIR = "./templates"
OUTPUT_FILE = "msa_analysis_report.html"
PDF_OUTPUT_FILE = "msa_analysis_report.pdf"

# wkhtmltopdf 실행 파일 경로 (OS 환경변수 PATH에 추가하지 않은 경우 직접 지정)
# 본인의 실제 설치 경로에 맞게 수정해주세요. (예: Mac/Linux의 경우 '/usr/local/bin/wkhtmltopdf')
WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"

def generate_pdf(reports, summary_content):
    """마크다운 결과물들을 모아 하나의 정적 PDF 파일로 추출합니다."""
    print("PDF 리포트를 생성하는 중입니다 (시간이 다소 소요될 수 있습니다)...")
    
    md_parts = []
    if summary_content:
        # 전체 요약본 삽입 및 페이지 나누기
        md_parts.append(summary_content + "\n\n<div style='page-break-after: always;'></div>\n\n")
        
    for report in reports:
        md_parts.append(f"{report['content']}\n\n<div style='page-break-after: always;'></div>\n\n")
        
    full_md = "".join(md_parts)
        
    # SVG 이미지 로드를 위해 로컬 상대 경로(./analysis_results)를 절대 경로로 변환
    abs_result_dir = os.path.abspath(RESULT_DIR).replace('\\', '/')
    full_md = full_md.replace(RESULT_DIR, abs_result_dir)

    # 마크다운을 파이썬 내부에서 정적 HTML로 파싱 (코드 블록, 표 확장 기능 활성화)
    html_body = markdown.markdown(full_md, extensions=['fenced_code', 'tables'])

    # PDF 전용 정적 HTML 템플릿
    pdf_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/github-markdown-css/5.5.1/github-markdown.min.css">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; padding: 40px; }}
            img {{ max-width: 100%; }}
            pre {{ background-color: #f6f8fa; padding: 16px; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; }}
        </style>
    </head>
    <body class="markdown-body">
        {html_body}
    </body>
    </html>
    """
    
    # 로컬 파일(SVG) 접근 허용 옵션
    options = {'enable-local-file-access': None, 'encoding': 'UTF-8', 'quiet': ''}
    
    # 지정한 wkhtmltopdf 경로 적용
    config = None
    if os.path.exists(WKHTMLTOPDF_PATH):
        config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
        
    try:
        pdfkit.from_string(pdf_html, PDF_OUTPUT_FILE, options=options, configuration=config)
        print(f"✨ 통합 PDF 리포트 생성이 완료되었습니다: {PDF_OUTPUT_FILE}")
    except Exception as e:
        print(f"\n[⚠️ PDF 생성 실패] wkhtmltopdf 경로가 올바른지 확인해주세요. ({WKHTMLTOPDF_PATH})\n상세 오류: {e}\n")
        logging.error(f"PDF 리포트 생성 실패: {e}", exc_info=True)

def main(stats=None):
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
        
    # HTML 생성 완료 후 PDF 생성 함수 호출
    generate_pdf(reports, summary_content)

    print(f"✨ 통합 HTML 리포트 생성이 완료되었습니다: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()