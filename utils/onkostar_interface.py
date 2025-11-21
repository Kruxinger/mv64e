from sqlalchemy import create_engine, text

host_test="srvonkostart.srv.med.uni-muenchen.de"
port=3306
name="onkostar"
user="ccc_ro"
password_t="rjge0ntv"

test_engine_string = f"mariadb://{user}:{password_t}@{host_test}:{port}/{name}"
engine = create_engine(test_engine_string)

def get_query_res_as_dict(query: str):
    with engine.begin() as conn:
        result = conn.execute(text(query))
        return [row for row in result.mappings()]

def get_anamnese_procedures_for_pat(pat_id: str):
    return get_query_res_as_dict("SELECT id, beginndatum FROM prozedur WHERE patient_id=0 AND html_schnipsel_detailiert LIKE '%DNPM Klinik/Anamnese%' AND geloescht=0")