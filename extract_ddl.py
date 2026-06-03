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
                
        print(f"\n✨ DDL 추출이 성공적으로 완료되었습니다!")
        print(f"👉 추출된 파일 경로: {output_file}")
        
    except Exception as e:
        print(f"\n❌ DDL 추출 중 오류가 발생했습니다: {e}")
        print("팁: 데이터베이스 종류에 맞는 드라이버가 설치되어 있는지 확인해주세요.")
        print("- MySQL: pip install pymysql")
        print("- PostgreSQL: pip install psycopg2-binary")
        print("- Oracle: pip install cx_Oracle 또는 oracledb")

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
        help="데이터베이스 접속 URL (예: oracle+cx_oracle://user:pass@localhost:1521/?service_name=orcl)"
    )
    parser.add_argument(
        "--schema", 
        type=str, 
        default=None,
        help="추출할 대상 스키마 이름 (Oracle 등에서 유용함)"
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
        print("사용법: python extract_ddl.py --url 'oracle+cx_oracle://user:pass@localhost:1521/?service_name=orcl' --schema 'MY_SCHEMA'")
        print("또는 .env 파일에 DB_URL=... 을 설정해주세요.")
        exit(1)

    extract_ddl(args.url, args.output, args.schema)
