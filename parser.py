import os
import re
import logging

# XML 태그 분할용 정규식을 모듈 레벨에서 한 번만 컴파일하여 반복 호출 시 CPU 부하 감소
XML_TAG_PATTERN = re.compile(r'^\s*<(select|insert|update|delete|sql|resultMap)\b', re.IGNORECASE)

# javalang 패키지 로드 여부를 모듈 로드 시 1회만 체크하여 반복적인 import 오버헤드 제거
try:
    import javalang
    HAS_JAVALANG = True
except ImportError:
    HAS_JAVALANG = False
    logging.warning("javalang 패키지가 없습니다. 단순 라인 단위로 분할합니다.")

def get_target_files(directory):
    """지정된 경로 하위의 모든 .java 및 .xml 파일의 절대 경로를 수집합니다."""
    target_files = []
    
    # os.walk 대신 제너레이터 기반의 os.scandir를 사용하여 파일 탐색 속도와 메모리 최적화
    def scan_dir(path):
        try:
            for entry in os.scandir(path):
                if entry.is_file() and entry.name.endswith(('.java', '.xml')): # 튜플 검사로 속도 향상
                    target_files.append(entry.path)
                elif entry.is_dir():
                    scan_dir(entry.path)
        except PermissionError:
            pass
            
    scan_dir(directory)
    return target_files

def chunk_java_code(source_code, max_lines=1500):
    """javalang을 활용하여 Java 코드를 클래스 필드와 메서드 경계 단위로 잘게 쪼갭니다."""
    if not HAS_JAVALANG:
        lines = source_code.split('\n')
        return ['\n'.join(lines[i:i+max_lines]) for i in range(0, len(lines), max_lines)]

    try:
        tree = javalang.parse.parse(source_code)
        method_start_lines = []
        
        # 메서드 선언부의 시작 라인 추출
        for path, node in tree.filter(javalang.tree.MethodDeclaration):
            if node.position:
                method_start_lines.append(node.position.line - 1) # position.line은 1부터 시작하므로 0-indexed 변환
                
        method_start_lines.sort()
        lines = source_code.split('\n')
        
        if not method_start_lines:
            return [source_code]
            
        chunks = []
        # 첫 번째 청크: 패키지, 임포트, 클래스 선언부 및 전역 변수들 (첫 메서드 전까지)
        current_chunk_lines = lines[:method_start_lines[0]]
        
        for i in range(len(method_start_lines)):
            start = method_start_lines[i]
            end = method_start_lines[i+1] if i + 1 < len(method_start_lines) else len(lines)
            method_lines = lines[start:end]
            
            if len(current_chunk_lines) + len(method_lines) > max_lines and current_chunk_lines:
                chunks.append('\n'.join(current_chunk_lines))
                current_chunk_lines = method_lines
            else:
                current_chunk_lines.extend(method_lines)
                
        if current_chunk_lines:
            chunks.append('\n'.join(current_chunk_lines))
            
        return chunks
    except Exception as e:
        logging.warning(f"AST 파싱 중 오류 발생. 단순 분할로 대체합니다: {e}")
        lines = source_code.split('\n')
        return ['\n'.join(lines[i:i+max_lines]) for i in range(0, len(lines), max_lines)]

def chunk_xml_code(source_code, max_lines=1500):
    """MyBatis XML 코드를 주요 태그(<select>, <insert> 등) 경계 단위로 잘게 쪼갭니다."""
    lines = source_code.split('\n')
    statement_start_lines = []
    
    # 주요 쿼리/매퍼 태그 시작 라인 추출 (대소문자 구분 없이 감지)
    for i, line in enumerate(lines):
        if XML_TAG_PATTERN.search(line):
            statement_start_lines.append(i)
            
    if not statement_start_lines:
        # 태그를 찾지 못한 경우 단순 라인 분할
        return ['\n'.join(lines[i:i+max_lines]) for i in range(0, len(lines), max_lines)]
        
    chunks = []
    # 첫 번째 청크: XML 선언부, DOCTYPE, <mapper> 태그 등
    current_chunk_lines = lines[:statement_start_lines[0]]
    
    for i in range(len(statement_start_lines)):
        start = statement_start_lines[i]
        end = statement_start_lines[i+1] if i + 1 < len(statement_start_lines) else len(lines)
        statement_lines = lines[start:end]
        
        if len(current_chunk_lines) + len(statement_lines) > max_lines and current_chunk_lines:
            chunks.append('\n'.join(current_chunk_lines))
            current_chunk_lines = statement_lines
        else:
            current_chunk_lines.extend(statement_lines)
            
    if current_chunk_lines:
        chunks.append('\n'.join(current_chunk_lines))
        
    return chunks