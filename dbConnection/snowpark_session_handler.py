
from snowflake.snowpark import Session


deepsight_connection_parameters = {
    "account": "TTB91148",
    "user": "angshuman.deb@saama.com",
    "password": "$n0wP@rk@$@@m@",
    "role": "ACCOUNTADMIN",
    "warehouse": "DEEPINSIGHTS_WH",
    "database": "DEEPINSIGHT",
    "schema": "DI_SCHEMA"
}

archdb_connection_parameters = {
    "account": "TTB91148",
    "user": "angshuman.deb@saama.com",
    "password": "$n0wP@rk@$@@m@",
    "role": "ACCOUNTADMIN",
    "warehouse": "DEEPINSIGHTS_WH",
    "database": "SAAMA_ARCH_DEMO_DB",
    "schema": "DEMO_SCHEMA"
}

def get_snowpark_session(database):
    session = None
    if database.lower().find("deepinsight") != -1:
        session = Session.builder.configs(deepsight_connection_parameters).create()
    elif database.lower().find("arch") != -1:
        session = Session.builder.configs(archdb_connection_parameters).create()
    return session

# STAGE_DIR='@"DEEPINSIGHT"."DI_SCHEMA"."DI_STAGE"'
# session = get_snowpark_session("arch")
# df_table = session.table("BRKR")
# df_table.show()
# # stream = session.file.get_stream(STAGE_DIR + "/prompts/query_normalization_prompt.yaml")
# # prompt_yaml_str = stream.read().decode('utf-8')
# # print(prompt_yaml_str)
# session.close()
