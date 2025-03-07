import yaml, io,json, pandas as pd
from ruamel.yaml import YAML
from llmModels.llm_utils import LLMCaller  # Import the LLMCaller class
#import chromadb
import json
import uuid
import logging
from dbConnection.data_access import DataAccess


#logger = logging.getLogger(f"{__name__}.SQLExecutorAgent")


def load_file(session, file_path):
    try:
        stream = session.file.get_stream(file_path)
        prompt_yaml_str = stream.read().decode('utf-8')
        return yaml.safe_load(prompt_yaml_str)
    except Exception as ex:
        return None

    
# Function to load sample data; here we simulate sample tables using pandas DataFrames.
# def load_sample_data():
#     sample_data_file = "./data/sample_data.yaml"
#     return load_file(sample_data_file)

# def load_enriched_data():
#     filename = "./schema/enriched_data_dictionary.yaml"
#     return load_file(filename)

import io
import os

def write_to_stage(session, file_path, file_name, content):
    logger = logging.getLogger(f"{__name__}.read_from_stage")
    with open(file_name, "w") as f:
        f.write(content)
    try:
        put_command = f"PUT file://{file_name} {file_path} OVERWRITE=TRUE AUTO_COMPRESS=FALSE"
        session.sql(put_command).collect()
        os.remove(file_name)
    except Exception as ex:
        logger.error(f"Error in writing to file in stage: {ex}")
    print(f"File {file_name} uploaded to stage {file_path}.")


def read_from_stage(session, stage_name, file_path):
    logger = logging.getLogger(f"{__name__}.read_from_stage")
    try:
        get_command = f"GET {stage_name}/{file_path} file://./"
        session.sql(get_command).collect()
    except Exception as ex:
        logger.error(f"Error in reading from file in stage: {ex}")

    
    local_file_path = file_path.split('/')[-1]
    with open(local_file_path, "r") as f:
        content = f.read()
    os.remove(local_file_path)
    if content is None or len(content) == 0:
        content = []
    return content


def format_prompt(prompt_yaml):
     # Initialize the YAML object
    ruamel_yaml = YAML()
    ruamel_yaml.default_flow_style = False  # Ensure block formatting
    ruamel_yaml.indent(mapping=2, sequence=4, offset=2)

    # Dump to a string
    output_stream = io.StringIO()
    ruamel_yaml.dump(prompt_yaml, output_stream)
    customized_prompt = output_stream.getvalue()

    contents = [customized_prompt]

    return contents

def create_strategy(SESSION, STAGE, normalization_output, enriched_dict, sample_data,cached_strategy_example = None):
    logger = logging.getLogger(f"{__name__}.create_strategy")

    prompt_yaml = load_file(SESSION, STAGE + "/prompts/query_answering_strategy_v1.yaml")
    prompt_yaml['dynamic_input'] = {
                "`user_question`": normalization_output["normalized_query"],
                "`decomposed_steps`": normalization_output["decomposed_steps"],
                "`sample_dataset`": sample_data,
                "`enhanced_database_dictionary`": enriched_dict,
                "`Examples`":cached_strategy_example
                
        }

    prompt_yaml = format_prompt(prompt_yaml)
    strategy =  LLMCaller.call_llm( SESSION, prompt_yaml)
    logger.info("Strategy generated -->" + json.dumps(strategy))
    # strategy_str="""
    # {"workflow_type":"insurance_claim_analysis","name":"Commercial Property Insurance Claim Analysis","description":"This workflow analyzes commercial property insurance claims to identify locations with the highest frequency of claims.","tasks":[{"task_id":"1","agent_type":"DictionaryLookup","parameters":{"tables":{"CLM":["CLM_ID","PLC_ID","ADJ_ID","LOSS_TYPE"],"PLC":["PLC_ID","INS_ID","BRKR_ID","PLC_DIV"],"LOC":["LOC_ID","LOC_ADDR","LOC_CITY","LOC_STATE"]}},"output_schema":["description","hidden_insights"],"next_task_on_success":"2","next_task_on_failure":null},{"task_id":"2","agent_type":"DataAnalyzer","parameters":{"tables":{"CLM":["CLM_ID","PLC_ID","ADJ_ID","LOSS_TYPE"],"PLC":["PLC_ID","INS_ID","BRKR_ID","PLC_DIV"],"LOC":["LOC_ID","LOC_ADDR","LOC_CITY","LOC_STATE"]}},"output_schema":["description","hidden_insights"],"next_task_on_success":"3","next_task_on_failure":null},{"task_id":"3","agent_type":"SQLGenerator","parameters":{"task_description":"Generate SQL query to join claims data with policy and insured location information","user_query":"identify locations with highest frequency of insurance claims","tables":{"CLM":["CLM_ID","PLC_ID","ADJ_ID","LOSS_TYPE"],"PLC":["PLC_ID","INS_ID","BRKR_ID","PLC_DIV"],"LOC":["LOC_ID","LOC_ADDR","LOC_CITY","LOC_STATE"]},"conditions":{"where_clause":"CLM.PLC_ID = PLC.PLC_ID AND PLC.INS_ID = INS.INS_ID AND INS.INS_LOC = LOC.LOC_ID","groupby_clause":"LOC.LOC_ID","aggregate_function":"COUNT","aggregate_column":"CLM.CLM_ID","orderby_clause":"COUNT(CLM.CLM_ID) DESC"}},"output_schema":["sql_query"],"next_task_on_success":"4","next_task_on_failure":null},{"task_id":"4","agent_type":"SQLExecutor","parameters":{"sql_query":"${tasks.3.output.sql_query}"},"output_schema":["results"],"next_task_on_success":"5","next_task_on_failure":null},{"task_id":"5","agent_type":"ResponseGenerator","parameters":{"hypotheses":["High claim frequency locations are likely to be in areas with high crime rates or natural disaster-prone zones"],"reasoning":["The analysis of claims data and location information reveals patterns of high claim frequency in certain areas"],"next_steps":["Further investigation into the causes of high claim frequency in these areas is necessary"],"task_results":"${tasks.*.output}","user_query":"identify locations with highest frequency of insurance claims"}}]}
    # """
    # strategy = json.loads(strategy_str)
    try:
        if isinstance(strategy, str):
            strategy = json.loads(str(strategy))
    except Exception as e:
        print("Exception Occured whiling loading JSon")
        strategy = eval(str(strategy))
        
    return strategy


def get_data_analysis_results(SESSION, DI_STAGE, user_query, data_dict, sample_data, cached_normalised_query=None):
        logger = logging.getLogger(f"{__name__}.get_data_analysis_results")
        try:
            if isinstance(data_dict, dict):
                data_dict = json.dumps(data_dict)
            prompt_yaml = load_file(SESSION, DI_STAGE + "/prompts/data_analysis_insights.yaml")
            prompt_yaml["`dynamic_input`"] = {
                "`user_question`": user_query,
                "`sample_dataset`": sample_data,
                "`enhanced_database_dictionary`": data_dict,
                "`Examples`":None
             }   
            analysis_results = LLMCaller.call_llm(SESSION,json.dumps(prompt_yaml))
            logger.info(f"Analysis_results: {json.dumps(analysis_results)}")
            
            # analysis_results_str = '{"CLM":{"description":"The Claims table stores information about insurance claims filed against commercial property policies. It captures claim details including claim numbers, dates, loss types, amounts, status, and assigned adjusters. Based on sample data, it appears to handle various types of property losses including fire, water damage, theft and auto-related claims. The table shows a clear workflow progression through different claim statuses and maintains traceability through claim numbers and dates.","keys":{"primary_key":"CLM_ID","foreign_keys":["CLM.PLC_ID references PLC.PLC_ID","CLM.ADJ_ID references ADJ.ADJ_ID"]},"synonyms":"Claims, Loss Records, Claim Register","possible_joins":["CLM.PLC_ID-JOINS-PLC.PLC_ID","CLM.ADJ_ID-JOINS-ADJ.ADJ_ID","PLC.INS_ID-JOINS-INS.INS_ID","PLC.BRKR_ID-JOINS-BRKR.BRKR_ID"],"key_insights":["Locations with the highest frequency of insurance claims can be identified by analyzing the PLC_ID and LOC_ID columns in the CLM and LOC tables respectively.","The most common types of claims are Water Damage, Fire, and Auto, which could indicate areas where policyholders are most at risk.","Claims with higher amounts tend to be associated with certain types of losses, such as Fire and Water Damage, suggesting a potential correlation between loss type and claim amount."],"CLM_ID":{"description":"Unique identifier for each claim record","data_type":"numerical","potential_correlations":[],"inferred_business_rules":["Must be unique","Must be positive integer","Cannot be null"]},"PLC_ID":{"description":"Reference to the policy under which the claim is filed","data_type":"numerical","potential_correlations":["PLC.PLC_COVLMT","PLC.PLC_PREM"],"inferred_business_rules":["Must reference valid policy","Policy must be active when claim is filed","One policy can have multiple claims"]},"ADJ_ID":{"description":"Reference to adjuster assigned to handle claim","data_type":"numerical","potential_correlations":["ADJ.ADJ_SPCL","LOSS_TYPE"],"inferred_business_rules":["Must reference valid adjuster","Adjuster specialty should match loss type","Cannot be null for active claims"]},"LOSS_TYPE":{"description":"Category of loss/damage that occurred","data_type":"categorical [Fire, Water Damage, Auto, Theft, Other]","potential_correlations":["PLC_COV.COV_ID","CLM_AMT"],"inferred_business_rules":["Must match coverage types on policy","Certain loss types may have specific handling requirements"]}},"PLC":{"description":"The Policy (PLC) table is the central entity in the commercial property insurance database that stores core policy information. It captures policy details including identifiers, effective/expiration dates, premiums, coverage limits, and status. Based on sample data, it manages diverse commercial policies across different divisions (Auto, Life, Health, etc) with varying premium amounts and coverage limits. The data suggests policies are issued through different channels (Agent, Online, ThirdParty) and can have different statuses (Active, Expired, Cancelled).","keys":{"primary_key":"PLC_ID","foreign_keys":["BRKR_ID references BRKR.BRKR_ID","INS_ID references INS.INS_ID"]},"synonyms":"Policy, Insurance Policy, Contract, Coverage Agreement","possible_joins":["PLC.PLC_ID-JOINS-CLM.PLC_ID","PLC.PLC_ID-JOINS-FEE.PLC_ID","PLC.PLC_ID-JOINS-DISC.PLC_ID","PLC.PLC_ID-JOINS-SUR.PLC_ID","PLC.PLC_ID-JOINS-PLC_COV.PLC_ID","PLC.BRKR_ID-JOINS-BRKR.BRKR_ID","PLC.INS_ID-JOINS-INS.INS_ID"],"key_insights":["Policies with higher coverage limits tend to have higher premiums, indicating a potential correlation between coverage and cost.","The most common policy divisions are Auto, Life, and Health, suggesting areas where the company has a strong presence.","Policies issued through agents tend to have higher premiums than those issued online, potentially indicating a difference in target markets or sales strategies."],"PLC_ID":{"description":"Unique identifier for each insurance policy","data_type":"numerical","potential_correlations":["CLM.PLC_ID","FEE.PLC_ID","DISC.PLC_ID","SUR.PLC_ID","PLC_COV.PLC_ID"],"inferred_business_rules":["Must be unique","Cannot be null"]},"INS_ID":{"description":"Reference to the insured entity","data_type":"numerical","potential_correlations":["INS.INS_ID","INS.INS_TYPE","INS.INS_INDC"],"inferred_business_rules":["Must reference valid INS.INS_ID"]},"BRKR_ID":{"description":"Reference to the broker managing the policy","data_type":"numerical","potential_correlations":["BRKR.BRKR_ID","BRKR.BRKR_SPCL"],"inferred_business_rules":["Must reference valid BRKR.BRKR_ID"]},"PLC_DIV":{"description":"Business division or line of insurance","data_type":"categorical [Life, Health, Property, Financial, Auto]","potential_correlations":["INS.INS_INDC","BRKR.BRKR_SPCL"],"inferred_business_rules":["Must be one of valid divisions"]}},"LOC":{"description":"Location table storing details of insured commercial properties including address, building characteristics, and safety features. Contains property-specific information critical for risk assessment and underwriting in commercial property insurance.","keys":{"primary_key":"LOC_ID","foreign_keys":"No direct foreign keys identified, but likely referenced by other tables through LOC_ID"},"synonyms":"Property Location, Risk Location, Insured Property, Building Location","possible_joins":"INS.INS_LOC-JOINS-LOC.LOC_ID","key_insights":["Locations in certain states (e.g. TX, IL, NY) tend to have a higher frequency of claims, potentially indicating areas of higher risk.","Properties with certain types of buildings (e.g. Office, Hospital) tend to have different claim patterns, suggesting a potential correlation between building type and risk.","Locations with higher safety features (e.g. fire protection, security) tend to have lower claim amounts, indicating a potential correlation between safety and loss severity."],"LOC_ID":{"description":"Unique identifier for each property location","data_type":"numerical","potential_correlations":["INS.INS_LOC"],"inferred_business_rules":["Must be unique","Must be positive integer"]},"LOC_ADDR":{"description":"Street address of the insured property","data_type":"text","potential_correlations":["LOC_CITY","LOC_STATE","LOC_ZIP"],"inferred_business_rules":["Cannot be null","Must be valid US address format"]},"LOC_CITY":{"description":"City where the insured property is located","data_type":"text","potential_correlations":["LOC_STATE","LOC_ZIP"],"inferred_business_rules":["Must be valid US city name"]},"LOC_STATE":{"description":"US state where the insured property is located","data_type":"categorical [\\"TX\\", \\"IL\\", \\"NY\\", \\"CA\\", \\"MD\\"]","potential_correlations":["LOC_CITY","LOC_ZIP","BRKR.BRKR_RG"],"inferred_business_rules":["Must be valid US state code","Must be 2 characters"]}}}'
            # analysis_results = json.loads(analysis_results_str)

            print("Successfully completed data analysis of related tables")
            
            return analysis_results
        except Exception as e:
            print(f"Error data analysis: {e}")
            raise

def generate_sql_query(SESSION, DI_STAGE, user_query, decomposed_steps, data_dict, tables, conditions, cached_normalised_query=None):
        
        logger = logging.getLogger(f"{__name__}.generate_sql_query")

        prompt_yaml = load_file(SESSION, DI_STAGE + "/prompts/sql_generation_prompt.yaml")
       
        prompt_yaml["dynamic_input"] = {
            "user_query": user_query,
            "decomposed_steps": decomposed_steps,
            "enhanced_database_dictionary": data_dict,
            "table_column_condition_hints": {
                "tables": tables,
                "conditions": conditions
            }
        }
        results = LLMCaller.call_llm(SESSION,json.dumps(prompt_yaml))
        logger.info(f"Generated query: {json.dumps(results)}")
        # analysis_results = {'sql_query':'SELECT LOC.LOC_STATE, COUNT(CLM.CLM_ID) AS claim_count FROM CLM JOIN PLC ON CLM.PLC_ID = PLC.PLC_ID JOIN INS ON PLC.INS_ID = INS.INS_ID JOIN LOC ON INS.INS_LOC = LOC.LOC_ID GROUP BY LOC.LOC_STATE ORDER BY claim_count DESC LIMIT 5;','query_explanation':'This SQL query identifies the top 5 states with the highest claim frequency. It joins the CLM, PLC, INS, and LOC tables to link claims to locations. It groups the results by state and counts the number of claims per state, ordering them in descending order to find the states with the most claims. Finally, it limits the output to the top 5 states.','pre_validation_status':'Decomposition and hints deemed valid and consistent with user query and data dictionary.','post_validation_status':'SQL query passed both syntax and data dictionary validation. No errors or warnings detected.'}
        generated_sql = json.loads(json.dumps(results))
        
        print("Successfully generated SQL from strategy")
        return generated_sql


def get_few_shot_examples(session, db_name, schema_name, process_step, current_input):
    
    logger = logging.getLogger(f"{__name__}.get_few_shot_examples")

    table_name = "FEW_SHOT_EXAMPLES"
    few_shot_table = db_name + "." + schema_name + "." + table_name
    data_access = DataAccess(session)
    sql_query = sql_query =     f"SELECT * FROM {few_shot_table} \
                                WHERE STEP = '{process_step}' \
                                AND INPUT = '{current_input}' LIMIT 50"
    try:
        results = data_access.execute_query(sql_query)
           
        if results.status != "Success":
            logger.error(f"Failed to fetch data from table {few_shot_table}")
            return {
                "status": "Failure",
                "error": f"Failed to fetch data from table {few_shot_table}"
            }
        # Create a DataFrame from the query results
        df = pd.DataFrame(results.output, columns=results.columns)

    except Exception as ex:
        logger.error("ERROR: encountered while retrieving few-shot examples for: " + process_step)


def log_query(query, answer, explanation):
        log_line = f"Query: {query}\nAnswer: {answer}\nExplanation: {explanation}\n\n"
        with open("query_log.txt", "a") as f:
            f.write(log_line)
        
# def store_in_chromadb(document,collection_name):
#     client = chromadb.PersistentClient(path="./chroma_db")  # Change path as needed
#     collection = client.get_or_create_collection(name=collection_name)
#     id = str(uuid.uuid4())
    
#     # Create a single entity combining user_query and strategy
#     collection.add(
#         ids=[id],
#         documents=[document]
#     )
#     print(f"Data stored successfully in ChromaDB with ID: {id} in collection {collection_name}")
    

# def query_chromadb(collection_name, search_text,n_results=2):
#     try:
        
#     # Initialize ChromaDB client
#         client = chromadb.PersistentClient(path="./chroma_db")
#         # Get collection
#         collection = client.get_collection(name=collection_name)
#         # Perform similarity search
#         results = collection.query(query_texts=search_text, n_results=n_results)
#         return results.get("documents")[0]
#     except Exception as e:
#         print("Exception error Retriving the document",e)
#         return None

def extract_query(response: str) -> str:
    try:
        start = response.find("```sql")
        end = response.rfind("```")
        query = (
            response[start + len("```sql") : end].strip()
            if start != -1 and end != -1
            else response.strip()
        )
        print("Query extracted successfully")
        return query
    except Exception as e:
        print(f"Error extracting SQL query: {e}")
        return ""
    
def extract_yaml(response: str) -> str:
    try:
        start = response.find("```yaml")
        end = response.rfind("```")
        query = (
            response[start + len("```sql") : end].strip()
            if start != -1 and end != -1
            else response.strip()
        )
        print("Query extracted successfully")
        return query
    except Exception as e:
        print(f"Error extracting SQL query: {e}")
        return ""

