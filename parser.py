import os
import re
import logging
from typing import List, Optional

# XML 태그 분할용 정규식을 모듈 레벨에서 한 번만 컴파일하여 반복 호출 시 CPU 부하 감소
XML_TAG_PATTERN = re.compile(r'^\s*<(select|insert|update|delete|sql|resultMap)\b', re.IGNORECASE)

# DDL(SQL) 테이블 분할용 정규식 컴파일
SQL_TAG_PATTERN = re.compile(r'^\s*(CREATE\s+(OR\s+REPLACE\s+)?(UNIQUE\s+)?(TABLE|VIEW|PROCEDURE|FUNCTION|TRIGGER|INDEX)|ALTER\s+TABLE)\b', re.IGNORECASE)

# DDL 객체명 추출용 정규식 컴파일 (멀티라인 적용)
SQL_OBJECT_PATTERN = re.compile(r'^\s*(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:UNIQUE\s+)?(?:TABLE|VIEW|PROCEDURE|FUNCTION|TRIGGER|INDEX)|ALTER\s+TABLE)\s+([a-zA-Z0-9_`"\'\.]+)', re.IGNORECASE | re.MULTILINE)

# javalang 패키지 로드 여부를 모듈 로드 시 1회만 체크하여 반복적인 import 오버헤드 제거
try:
    import javalang
    HAS_JAVALANG = True
except ImportError:
    HAS_JAVALANG = False
    logging.warning("javalang 패키지가 없습니다. 단순 라인 단위로 분할합니다.")


def get_target_files(directory: str, exclude_paths: Optional[List[str]] = None) -> List[str]:
    """지정된 경로 하위의 모든 대상 파일의 절대 경로를 수집하며, 특정 경로는 제외합니다."""
    target_files = []
    if exclude_paths is None:
        exclude_paths = []
    
    # os.walk 대신 제너레이터 기반의 os.scandir를 사용하여 파일 탐색 속도와 메모리 최적화
    def scan_dir(path):
        try:
            for entry in os.scandir(path):
                entry_path_normalized = entry.path.replace('\\', '/')
                
                # 제외할 경로 키워드가 포함되어 있으면 하위 탐색 생략
                if any(ex_path in entry_path_normalized for ex_path in exclude_paths):
                    continue
                    
                if entry.is_file() and entry.name.endswith(('.java', '.xml', '.sql')): # 튜플 검사로 속도 향상
                    target_files.append(entry.path)
                elif entry.is_dir():
                    scan_dir(entry.path)
        except PermissionError:
            pass
            
    scan_dir(directory)
    return target_files


def chunk_java_code(source_code: str, max_lines: int = 1500) -> List[str]:
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


def chunk_xml_code(source_code: str, max_lines: int = 1500) -> List[str]:
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


def extract_sql_object_names(source_code: str) -> List[str]:
    """SQL DDL 코드에서 생성되거나 변경되는 전체 테이블/객체명 목록을 추출합니다."""
    matches = SQL_OBJECT_PATTERN.findall(source_code)
    
    # 스키마명.테이블명 형태 정제 및 빈 문자열 필터링 (Generator Expression)
    names = (match.split('.')[-1].strip('`"\'') for match in matches)
    
    # 파이썬 3.7+ dict를 활용하여 순서 유지 및 중복 제거 O(N) 최적화 적용
    return list(dict.fromkeys(filter(None, names)))


def chunk_sql_code(source_code: str, max_lines: int = 1500) -> List[str]:
    """SQL DDL 코드를 주요 구문(CREATE TABLE/VIEW/PROCEDURE/FUNCTION/TRIGGER/INDEX, ALTER TABLE 등) 경계 단위로 잘게 쪼갭니다."""
    lines = source_code.split('\n')
    statement_start_lines = []
    
    for i, line in enumerate(lines):
        if SQL_TAG_PATTERN.search(line):
            statement_start_lines.append(i)
            
    if not statement_start_lines:
        return ['\n'.join(lines[i:i+max_lines]) for i in range(0, len(lines), max_lines)]
        
    chunks = []
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