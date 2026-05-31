import os
import re
import uuid
import logging
from graphviz import Source

RESULT_DIR = "./analysis_results"

# 다이어그램 정규식을 모듈 레벨에서 한 번만 컴파일
DOT_PATTERN = re.compile(r'```(?:dot|graphviz)\n(.*?)```', re.DOTALL)

def render_graphviz_to_svg(markdown_text: str, file_prefix: str) -> str:
    """마크다운 내의 dot/graphviz 코드 블록을 추출하여 로컬에서 SVG 이미지로 렌더링합니다."""
    try:
        def replacer(match):
            dot_code = match.group(1).strip()
            diagram_id = uuid.uuid4().hex[:6]
            file_base = f"{file_prefix}_diagram_{diagram_id}"
            file_path_base = os.path.join(RESULT_DIR, file_base)
            
            try:
                # Graphviz 객체 생성 및 SVG 렌더링
                src = Source(dot_code, format='svg')
                # cleanup=True 시 중간 생성되는 소스 파일(.gv)을 삭제하고 svg만 남깁니다.
                src.render(filename=file_path_base, cleanup=True)
                
                # HTML 리포트(루트 디렉토리)에서 SVG 이미지를 찾을 수 있도록 마크다운 이미지 문법으로 반환
                svg_rel_path = f"{RESULT_DIR}/{file_base}.svg"
                return f"![Architecture Diagram]({svg_rel_path})"
            except Exception as e:
                logging.error(f"Graphviz 다이어그램 렌더링 실패: {e}", exc_info=True)
                error_msg = str(e).lower()
                if "executable" in error_msg or "not found" in error_msg:
                    return f"> ⚠️ 다이어그램 렌더링 실패: OS에 Graphviz가 설치되어 있는지 확인해주세요.\n\n```dot\n{dot_code}\n```"
                else:
                    return f"> ⚠️ 다이어그램 문법 오류: LLM이 작성한 DOT 코드에 오류가 있습니다. ({e})\n\n```dot\n{dot_code}\n```"
                    
        return DOT_PATTERN.sub(replacer, markdown_text)
    except Exception as e:
        logging.error(f"Graphviz 처리 중 예기치 않은 치명적 오류 발생: {e}", exc_info=True)
        # 파싱 자체가 실패하더라도 귀중한 LLM 분석 결과(원본 텍스트)를 날리지 않도록 그대로 반환합니다.
        return markdown_text