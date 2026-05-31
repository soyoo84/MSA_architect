import os
import csv
import json
import re

ENDPOINT_CSV = "api_endpoints.csv"
SWAGGER_OUTPUT = "swagger.json"


def main() -> None:
    if not os.path.exists(ENDPOINT_CSV):
        print(f"[{ENDPOINT_CSV}] 파일이 없습니다. API 추출 결과가 있는지 확인해주세요.")
        return

    print("추출된 API 엔드포인트 CSV를 바탕으로 Swagger(OpenAPI 3.0) 규격 파일을 생성합니다...")

    openapi_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Legacy to MSA API Specification",
            "version": "1.0.0",
            "description": "자동 분석 파이프라인을 통해 레거시 소스에서 추출된 API 엔드포인트 명세서입니다."
        },
        "servers": [{"url": "/api/v1"}],
        "tags": [],
        "paths": {},
        "components": {
            "schemas": {},
            "requestBodies": {},
            "securitySchemes": {}
        }
    }

    tags_set = set()
    count = 0
    
    with open(ENDPOINT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            endpoint = row.get("API Endpoint", "").strip()
            method_raw = row.get("Method", "").strip().lower()
            description = row.get("Description / Details", "").strip()
            source_file = row.get("Source File", "")

            # LLM이 "GET (조회)" 또는 "GET, POST" 등으로 응답할 경우를 대비해 유효한 HTTP 메서드만 추출
            valid_methods = ['get', 'post', 'put', 'delete', 'patch', 'options', 'head']
            extracted_methods = [m for m in valid_methods if m in method_raw]

            if not endpoint or not extracted_methods:
                continue
            
            if not endpoint.startswith("/"):
                endpoint = "/" + endpoint

            if endpoint not in openapi_spec["paths"]:
                openapi_spec["paths"][endpoint] = {}

            # 태그(Tag) 자동 생성: 소스 파일명 기준 그룹핑 (예: UserController.java -> UserController)
            tag_name = source_file.split('.')[0] if source_file else "default"
            if tag_name not in tags_set:
                tags_set.add(tag_name)
                openapi_spec["tags"].append({
                    "name": tag_name,
                    "description": f"Operations related to {tag_name}"
                })

            # 경로 파라미터(Path Parameter) 자동 추출 (예: /users/{id} -> id 추출)
            path_params = re.findall(r'\{([^}]+)\}', endpoint)
            parameters = []
            for param in path_params:
                parameters.append({
                    "name": param,
                    "in": "path",
                    "required": True,
                    "schema": { "type": "string" }
                })

            # 추출된 각각의 유효한 HTTP 메서드에 대해 Swagger Path 추가
            for method in extracted_methods:
                # 고유한 Operation ID 생성
                operation_id = f"{method}_{endpoint.strip('/').replace('/', '_').replace('{', '').replace('}', '')}"
                if not operation_id or operation_id == method + "_":
                    operation_id = f"{method}_root"

                openapi_spec["paths"][endpoint][method] = {
                    "tags": [tag_name],
                    "summary": f"[{source_file}]",
                    "description": description,
                    "operationId": operation_id,
                    "parameters": parameters,
                    "responses": {
                        "200": { 
                            "description": "Successful operation",
                            "content": {
                                "application/json": {
                                    "schema": { "type": "object" }
                                }
                            }
                        }
                    }
                }
            count += 1

    if count > 0:
        with open(SWAGGER_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(openapi_spec, f, indent=2, ensure_ascii=False)
        print(f"✨ 총 {count}개의 API가 등록된 Swagger 파일 생성이 완료되었습니다: {SWAGGER_OUTPUT}")
        print("👉 이 파일을 Swagger Editor(https://editor.swagger.io/)에 드래그하여 시각적으로 확인해보세요!")
    else:
        print("CSV 파일에 유효한 API 엔드포인트 데이터가 없어 Swagger 파일을 생성하지 않았습니다.")

if __name__ == "__main__":
    main()