import os
import argparse
from sqlalchemy import create_engine, MetaData
from sqlalchemy.schema import CreateTable
from dotenv import load_dotenv

def extract_ddl(db_url: str, output_file: str, db_schema: str = None):
    """
    지정된 데이터베이스 URL에 접속하여 DDL(CREATE TABLE 문)을 추출하고 파일로 저장합니다.
    """
    print(f"[{db_url}] 데이터베이스에 접속 중...")
    try:
        engine = create_engine(db_url)
        metadata = MetaData()
        
        try:
            if db_schema:
                print(f"[{db_schema}] 스키마 정보를 불러오는 중 (Reflection)...")
                metadata.reflect(bind=engine, schema=db_schema)
            else:
                print("데이터베이스 스키마 정보를 불러오는 중 (Reflection)...")
                metadata.reflect(bind=engine)
            
            # 출력 디렉토리 확인 및 생성
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                
            with open(output_file, 'w', encoding='utf-8') as f:
                for table in metadata.sorted_tables:
                    print(f"테이블 추출 중: {table.name}")
                    # 각 테이블의 DDL 생성
                    ddl = str(CreateTable(table).compile(engine)).strip()
                    
                    f.write(f"-- ==========================================\n")
                    f.write(f"-- Table: {table.name}\n")
                    f.write(f"-- ==========================================\n")
                    f.write(f"{ddl};\n\n")
                    
        except Exception as reflection_error:
            print(f"\n⚠️ 기본 스키마 매핑(Reflection) 방식 실패: {reflection_error}")
            print("🛡️ [방어 로직 가동] 오라클 전용 데이터 딕셔너리(DBMS_METADATA)를 통한 직접 DDL 추출을 시도합니다.")
            
            from sqlalchemy import text
            output_dir = os.path.dirname(output_file)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                
            with engine.connect() as conn:
                # 스키마 지정 여부에 따라 조회 뷰 변경 (all_tables 또는 user_tables)
                table_query = f"SELECT table_name FROM all_tables WHERE owner = '{db_schema.upper()}'" if db_schema else "SELECT table_name FROM user_tables"
                tables = conn.execute(text(table_query)).fetchall()
                
                if not tables:
                    print("❌ 해당 스키마/계정에서 테이블을 찾을 수 없습니다.")
                    return
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    for (table_name,) in tables:
                        print(f"테이블 DDL 직접 추출 중 (DBMS_METADATA): {table_name}")
                        try:
                            # DBMS_METADATA.GET_DDL을 사용하여 원본 DDL 텍스트 호출
                            ddl_query = f"SELECT DBMS_METADATA.GET_DDL('TABLE', '{table_name}') FROM DUAL"
                            ddl_result = conn.execute(text(ddl_query)).scalar()
                            
                            f.write(f"-- ==========================================\n")
                            f.write(f"-- Table: {table_name}\n")
                            f.write(f"-- ==========================================\n")
                            if ddl_result:
                                f.write(f"{ddl_result.read() if hasattr(ddl_result, 'read') else str(ddl_result).strip()};\n\n")
                            else:
                                f.write("-- DDL 추출 결과 없음\n\n")
                        except Exception as ddl_e:
                            print(f"  -> ❌ {table_name} DDL 텍스트 추출 실패: {ddl_e}")
                            
        print(f"\n✨ DDL 추출이 성공적으로 완료되었습니다!")
        print(f"👉 추출된 파일 경로: {output_file}")
        
    except Exception as e:
        print(f"\n❌ DDL 추출 중 오류가 발생했습니다: {e}")
        print("팁: 데이터베이스 스키마 및 접속 정보를 확인해주세요.")
        print("- Oracle 드라이버는 'oracledb'를 사용합니다.")

if __name__ == "__main__":
    load_dotenv()
    
    # 환경변수 DB_URL이 있으면 기본값으로 사용
    default_db_url = os.getenv("DB_URL")
    default_output = os.getenv("SOURCE_DIRECTORY", "./monolith_source") + "/schema.sql"

    parser = argparse.ArgumentParser(description="데이터베이스에 직접 접속하여 DDL을 추출하는 도구입니다.")
    parser.add_argument(
        "--url", 
        type=str, 
        default=default_db_url,
        help="데이터베이스 접속 URL (예: oracle+oracledb://user:pass@localhost:1521/?service_name=orcl)"
    )
    parser.add_argument(
        "--schema", 
        type=str, 
        default=None,
        help="추출할 대상 스키마 이름 (Oracle 전용 필수옵션 권장)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default=default_output,
        help=f"추출할 DDL 파일 경로 (기본값: {default_output})"
    )

    args = parser.parse_args()

    if not args.url:
        print("❌ 데이터베이스 접속 URL이 제공되지 않았습니다.")
        print("사용법: python extract_ddl.py --url 'oracle+oracledb://user:pass@localhost:1521/?service_name=orcl' --schema 'MY_SCHEMA'")
        print("또는 .env 파일에 DB_URL=... 을 설정해주세요.")
        exit(1)

    extract_ddl(args.url, args.output, args.schema)
