import os
import csv
from typing import Iterable, List

RESULT_DIR = "./analysis_results"
MAPPING_CSV = "domain_table_mapping.csv"
DEPENDENCY_CSV = "service_dependencies.csv"
ENDPOINT_CSV = "api_endpoints.csv"


def extract_markdown_tables(lines_iterable: Iterable[str]) -> List[List[str]]:
    """파일 객체 등 순회 가능한(Iterable) 라인 묶음에서 표 데이터를 메모리 효율적으로(Lazy) 추출합니다."""
    tables = []
    current_table = []
    for line in lines_iterable:
        line = line.strip()
        if line.startswith('|') and line.endswith('|'):
            current_table.append(line)
        else:
            if current_table:
                tables.append(current_table)
                current_table = []
    if current_table:
        tables.append(current_table)
    return tables


def main() -> None:
    if not os.path.exists(RESULT_DIR):
        return

    print("분석 결과에서 표(Table) 데이터를 추출하여 CSV로 통합 저장합니다...")
    
    all_mappings = []
    mapping_headers = ["Source File", "Type", "Object Name", "Domain", "Aggregate Root", "Migration Priority", "Description / Details"]
    
    all_dependencies = []
    dependency_headers = ["Source File", "Dependency Target", "Target Domain", "Reason / Details"]
    
    all_endpoints = []
    endpoint_headers = ["Source File", "API Endpoint", "Method", "Description / Details"]
    
    # 단 한 번의 파일 순회(O(N))로 두 가지 종류의 표를 동시에 추출합니다.
    # os.scandir 컨텍스트 매니저를 사용하여 시스템 자원(Resource)을 안전하게 즉시 반환
    with os.scandir(RESULT_DIR) as it:
        for entry in it:
            if entry.is_file() and entry.name.endswith(".md") and entry.name != "_architecture_summary.md":
                file_name = entry.name
                # 파일 전체를 메모리에 올리지 않고 스트리밍 방식으로 한 줄씩 읽어 파싱 (O(1) 메모리)
                with open(entry.path, "r", encoding="utf-8") as f:
                    tables = extract_markdown_tables(f)
                
                for table in tables:
                    if not table or len(table) < 3:
                        continue
                        
                    header_row = table[0].lower()
                    
                    # 테이블 종류 판별 조건
                    is_mapping = ('구분' in header_row or 'type' in header_row) and ('객체' in header_row or '테이블' in header_row or 'object' in header_row or 'table' in header_row) and ('도메인' in header_row or 'domain' in header_row)
                    is_dependency = ('의존' in header_row or '대상' in header_row) and ('도메인' in header_row or 'domain' in header_row) and not ('테이블' in header_row and 'table' in header_row)
                    is_endpoint = ('엔드포인트' in header_row or 'endpoint' in header_row) or ('api' in header_row and ('method' in header_row or '메서드' in header_row))
                    
                    if is_mapping or is_dependency or is_endpoint:
                        for data_row in table[2:]:
                            cells = [cell.strip() for cell in data_row.split('|')[1:-1]]
                            if not any(cells):
                                continue
                                
                            if is_mapping:
                                normalized_cells = cells[:5]  # Type, Object Name, Domain, Aggregate Root, Migration Priority (5개 추출)
                                if len(cells) > 5:
                                    normalized_cells.append(" / ".join(cells[5:])) # 나머지는 Description에 병합
                                else:
                                    normalized_cells.extend([""] * (6 - len(cells))) # 부족한 열 채우기
                                all_mappings.append([file_name] + normalized_cells)
                            elif is_dependency:
                                normalized_cells = cells[:3]
                                if len(cells) > 3:
                                    normalized_cells.append(" / ".join(cells[3:]))
                                else:
                                    normalized_cells.extend([""] * (3 - len(cells)))
                                all_dependencies.append([file_name] + normalized_cells)
                            elif is_endpoint:
                                normalized_cells = cells[:3]
                                if len(cells) > 3:
                                    normalized_cells.append(" / ".join(cells[3:]))
                                else:
                                    normalized_cells.extend([""] * (3 - len(cells)))
                                all_endpoints.append([file_name] + normalized_cells)

    # 엑셀에서 분석하기 편하도록 데이터 정렬(Sorting) 최적화
    all_mappings.sort(key=lambda x: (x[3], x[0], x[2]))  # Domain -> Source File -> Object Name
    all_dependencies.sort(key=lambda x: (x[2], x[0], x[1]))  # Target Domain -> Source File -> Target
    all_endpoints.sort(key=lambda x: (x[0], x[1]))  # Source File -> Endpoint

    with open(MAPPING_CSV, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(mapping_headers)
        writer.writerows(all_mappings)

    with open(DEPENDENCY_CSV, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(dependency_headers)
        writer.writerows(all_dependencies)

    with open(ENDPOINT_CSV, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(endpoint_headers)
        writer.writerows(all_endpoints)

if __name__ == "__main__":
    main()