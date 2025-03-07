import json
import pandas as pd
import os
import yaml
import math
import sys
import traceback
from agents.AgentManager import AgentManager
from helper import  create_strategy   #, load_sample_data, load_enriched_data, store_in_chromadb, query_chromadb
from llmModels.llm_utils import LLMCaller
from helperClass import SharedContext, ResultAggregator, Planner
import streamlit_mermaid as stmd
import streamlit as st
from datetime import datetime
import logging
import time
from dbConnection.snowpark_session_handler import get_snowpark_session
from helper import load_file, write_to_stage, read_from_stage
from snowflake.snowpark.context import get_active_session

# Configure logging
# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.FileHandler("app.log"),
#         logging.StreamHandler()
#     ]
# )

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logger = logging.getLogger(__name__)


# Constants
#DB_FILEPATH = './data/insurance_db.sqlite'
ARCH_DB = "SAAMA_ARCH_DEMO_DB"
ARCH_SCHEMA = "DEMO_SCHEMA"

DI_DB = "DEEPINSIGHT"
DI_SCHEMA = "DI_SCHEMA"
DI_STAGE="@DEEPINSIGHT.DI_SCHEMA.DI_STAGE"
#ARCH_STAGE='@"SAAMA_ARCH_DEMO_DB"."DEMO_SCHEMA"."DI_STAGE"'
ARCH_STAGE="@SAAMA_ARCH_DEMO_DB.DEMO_SCHEMA.DI_STAGE"
#CHAT_HISTORY_FILE = DI_STAGE + "/chat_history.json"

CHAT_HISTORY_FILE =  "chat_history.json"



#session = get_active_session()
session = get_snowpark_session("arch")





def load_chat(session, file_path):
    """Load chat history from JSON file"""
    try:
         stream = session.file.get_stream(file_path)
         prompt_json_str = stream.read().decode('utf-8')
         if prompt_json_str is None or  len(prompt_json_str) ==0:
             prompt_json_str = {}

         return prompt_json_str
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning(f"Could not load chat history: {e}")
        return {}


def save_chat(session, DI_STAGE, CHAT_HISTORY_FILE, chat_history):
   try:
        # Create a temporary table
        session.sql("CREATE OR REPLACE TABLE json_stage_table (data VARIANT)").collect()

        # Insert JSON data into the table
        session.sql(f"INSERT INTO json_stage_table SELECT '{chat_history}'").collect()

        # Copy JSON data from table to Snowflake stage
        copy_query = f"""
        COPY INTO {DI_STAGE}/{CHAT_HISTORY_FILE}
        FROM json_stage_table
        FILE_FORMAT = (TYPE = 'JSON')
        OVERWRITE = TRUE
        """
        session.sql(copy_query).collect()
        print(f"File {CHAT_HISTORY_FILE} overwritten in stage {DI_STAGE}.")

   except Exception as ex:
        logger.error(f"Error normalizing query: {ex}")
        #raise

    


def create_normalized_query(SESSION, DI_STAGE, user_query, enriched_dict, cached_normalised_query):
    try:
        prompt_yaml = json.dumps(load_file(SESSION, DI_STAGE + "/prompts/query_normalization_prompt.yaml"))
        prompt_yaml = prompt_yaml.replace('enriched_data_dictionary', str(enriched_dict))
        prompt_yaml = prompt_yaml.replace('user_query', user_query)
        prompt_yaml = prompt_yaml.replace('cached_normalised_query', str(cached_normalised_query))
        normalised_query = LLMCaller.call_llm(SESSION,prompt_yaml)
        logger.info("Successfully normalized user query --> " + json.dumps(normalised_query))
        return normalised_query
    except Exception as e:
        logger.error(f"Error normalizing query: {e}")
        raise


def json_to_mermaid(workflow_json):
    """
    Convert a workflow JSON to Mermaid flowchart syntax.
    
    Args:
        workflow_json (dict): The workflow JSON object
        
    Returns:
        str: Mermaid flowchart syntax as a string
    """
    try:
        # Extract workflow information
        workflow_name = workflow_json.get("name", "Workflow")
        tasks = workflow_json.get("tasks", [])
        
        if not tasks:
            return "flowchart TD\n    Start([Start]) --> End([End])"
        
        # Start building the mermaid code
        mermaid_code = "flowchart TD\n"
        mermaid_code += f"    Start([Start]) --> Task{tasks[0]['task_id']}[Task {tasks[0]['task_id']}: {tasks[0]['agent_type']}]\n"
        
        # Create a task lookup dictionary for easy reference
        task_dict = {task["task_id"]: task for task in tasks}
        
        # Generate main flow connections
        for task in tasks:
            task_id = task["task_id"]
            
            # Handle success path
            next_task_id = task.get("next_task_on_success")
            if next_task_id and next_task_id in task_dict:
                next_agent_type = task_dict[next_task_id]["agent_type"]
                mermaid_code += f"    Task{task_id} --> Task{next_task_id}[Task {next_task_id}: {next_agent_type}]\n"
            elif next_task_id:  # Next task ID exists but not found in task_dict
                mermaid_code += f"    Task{task_id} --> Task{next_task_id}[Task {next_task_id}: Unknown]\n"
            else:  # No next task, go to End
                mermaid_code += f"    Task{task_id} --> End([End])\n"
            
            # Handle failure path
            next_task_failure = task.get("next_task_on_failure")
            if next_task_failure and next_task_failure in task_dict:
                next_agent_type = task_dict[next_task_failure]["agent_type"]
                mermaid_code += f"    Task{task_id} -- \"on failure\" --> Task{next_task_failure}[Task {next_task_failure}: {next_agent_type}]\n"
            elif next_task_failure:  # Next task ID exists but not found in task_dict
                mermaid_code += f"    Task{task_id} -- \"on failure\" --> Task{next_task_failure}[Task {next_task_failure}: Unknown]\n"
            else:  # No failure path defined, go to End
                mermaid_code += f"    Task{task_id} -- \"on failure\" --> End([End])\n"
        
        # Add Task Details subgraph
        mermaid_code += "\n    subgraph Task Details\n"
        
        for task in tasks:
            task_id = task["task_id"]
            agent_type = task["agent_type"]
            
            # Generate task description based on agent type
            details = ""
            
            if agent_type == "DictionaryLookup":
                tables = task.get("parameters", {}).get("tables", {})
                if tables:
                    tables_info = []
                    for table, columns in tables.items():
                        tables_info.append(f"{table}: [{', '.join(columns)}]")
                    details = "Looks up tables:<br/>" + "<br/>".join(tables_info)
                else:
                    details = "Dictionary lookup operation"
                    
            elif agent_type == "SQLGenerator":
                task_desc = task.get("parameters", {}).get("task_description", "")
                user_query = task.get("parameters", {}).get("user_query", "")
                
                if task_desc:
                    # Truncate long descriptions
                    if len(task_desc) > 70:
                        task_desc = task_desc[:67] + "..."
                    details = f"Generates SQL to<br/>{task_desc}"
                elif user_query:
                    if len(user_query) > 70:
                        user_query = user_query[:67] + "..."
                    details = f"Generates SQL for:<br/>{user_query}"
                else:
                    details = "Generates SQL query"
                    
            elif agent_type == "SQLExecutor":
                details = "Executes SQL query"
                
            elif agent_type == "ResponseGenerator":
                hypotheses = task.get("parameters", {}).get("hypotheses", [])
                if hypotheses:
                    details = "Generates response with<br/>insights and hypotheses"
                else:
                    details = "Generates final response"
                    
            else:
                details = f"{agent_type} operation"
            
            # Add connection with details
            next_task_id = task.get("next_task_on_success")
            if next_task_id and next_task_id in task_dict:
                mermaid_code += f"        Task{task_id} -- \"{details}\" --> Task{next_task_id}\n"
            else:
                mermaid_code += f"        Task{task_id} -- \"{details}\" --> End\n"
        
        mermaid_code += "    end\n"
        
        # Add styling
        mermaid_code += """    
        classDef default fill:#f9f9f9,stroke:#333,stroke-width:1px;
        classDef task fill:#d4f1f9,stroke:#333,stroke-width:1px;
        classDef endpoint fill:#e6e6e6,stroke:#333,stroke-width:1px,stroke-dasharray: 5 5;
        
        class """
        
        # Add task classes
        task_ids = [task["task_id"] for task in tasks]
        task_class_list = ",".join([f"Task{task_id}" for task_id in task_ids])
        mermaid_code += f"{task_class_list} task;\n"
        mermaid_code += "    class Start,End endpoint;"
        
        logger.info("Successfully generated Mermaid flowchart")
        return mermaid_code
    except Exception as e:
        logger.error(f"Error generating Mermaid flowchart: {e}")
        raise

def calculate_stepwise_latency(normalization_latency, strategy_create_latency, task_results):
    latency_results  = {}
    total_time = 0
    latency_results["Normalizae Query Latency"] =  math.ceil(normalization_latency)
    total_time = math.ceil(normalization_latency)
    latency_results["Strategy Create Latency"] =  math.ceil(strategy_create_latency)
    total_time = total_time + math.ceil(strategy_create_latency)
    for step_key, step_result in task_results.items():
        task_id = step_result['task_id']
        elapsed_time = math.ceil(step_result['elapsed_time'])
        total_time = total_time + elapsed_time
        latency_results[task_id] = elapsed_time

    latency_results["Total time taken"] = total_time

    return latency_results

    


def agent_main(user_input):
    try:
        logger.info("Into agent_main function" + "DEBUG_1")
        if user_input:
            try:
                # session.sql("USE DATABASE "+ ARCH_DB).collect()
                # session.sql("USE SCHEMA " + ARCH_SCHEMA)  
                stream = session.file.get_stream(ARCH_STAGE + "/schema/enriched_data_dict.yaml")
                dict_yaml_string = stream.read().decode('utf-8')
                enriched_dict = yaml.safe_load(dict_yaml_string)
                logger.info("Successfully read enriched data dict")
                logger.info("Data Dict --> " + json.dumps(enriched_dict))
                
            except Exception as e:
                logger.error(f"Error in accessing data sdict: {e}")
                # logger.error("Error in accessing data dict:", str(e))
                # logger.error("Full Exception Traceback:")
                # logger.error("".join(traceback.format_exception(*sys.exc_info())))
                # Preserving the existing try-except logic while adding proper logging
                return last_task_output, strategy
            
            try:
                stream = session.file.get_stream(ARCH_STAGE + "/sample_data/sample_data.yaml")
                sample_yaml_string = stream.read().decode('utf-8')
                sample_data = yaml.safe_load(sample_yaml_string)
                logger.info("Successfully read sample_data.yaml file")
                logger.info("Sample Data --> " + json.dumps(sample_data))
            except Exception as e:
                logger.error(f"Error in accessing sample dataset: {e}")
           

            #cached_normalised_query = query_chromadb(collection_name="cached_normalised_query", search_text=user_input)
            cached_normalised_query=None
            start_time = time.perf_counter()
            processed_input = create_normalized_query(session, DI_STAGE, user_input, enriched_dict, cached_normalised_query)
            end_time = time.perf_counter()
            elapsed_time_normalization = end_time-start_time

            logger.info("Normalized query: " +  json.dumps(processed_input))

            # processed_input="""
            # {"normalized_query":"identify locations with highest frequency of insurance claims","decomposed_steps":[{"step_id":"STEP1","description":"Join claims data with policy and insured location information to connect claims to physical locations","hints":{"tables":["CLM","PLC","INS","LOC"],"columns":["CLM.CLM_ID","CLM.PLC_ID","PLC.INS_ID","INS.INS_LOC","LOC.LOC_ID"],"joins":["CLM.PLC_ID-JOINS-PLC.PLC_ID","PLC.INS_ID-JOINS-INS.INS_ID","INS.INS_LOC-JOINS-LOC.LOC_ID"]}},{"step_id":"STEP2","description":"Group claims by location and count frequency of claims per location","hints":{"tables":["LOC"],"columns":["LOC.LOC_ID","LOC.LOC_ADDR","LOC.LOC_CITY","LOC.LOC_STATE"],"joins":[]}},{"step_id":"STEP3","description":"Order locations by claim count to identify highest frequency locations","hints":{"tables":["LOC"],"columns":["LOC.LOC_ID","LOC.LOC_ADDR","LOC.LOC_CITY","LOC.LOC_STATE"],"joins":[]}}],"unresolved":""}
            # """
            # processed_input = json.loads(processed_input)
            # logger.info("Normalized query: " +  json.dumps(processed_input))
            
            #processed_input = json.loads(processed_input)
            #cached_strategy_example = query_chromadb(collection_name="cached_strategy", search_text=user_input)
            cached_strategy_example=None
            start_time = time.perf_counter()
            strategy = create_strategy(session, DI_STAGE, processed_input, enriched_dict, sample_data, cached_strategy_example)
            end_time = time.perf_counter()
            elapsed_time_strategy_create = end_time-start_time
            agent_manager = AgentManager(session, ARCH_DB,ARCH_SCHEMA, DI_STAGE, enriched_dict, processed_input, user_input)
            result_aggregator = ResultAggregator()
            shared_context = SharedContext()
            planner = Planner(strategy, agent_manager, result_aggregator, shared_context)
            results = planner.run()
            _, last_task_output, shared_context_final = results
            try:
                sql_query = shared_context_final.get('sql_generation_results')['output']
            except Exception as e:
                logger.warning(f'No SQL Found for Query: {e}')
                sql_query = 'No SQL Query'
            logger.info("Successfully processed user query")

            latency_results = calculate_stepwise_latency(elapsed_time_normalization, elapsed_time_strategy_create, shared_context.get_all().get("task-results"))
            return last_task_output, strategy, processed_input, sql_query, latency_results
    except Exception as e:
        logger.error(f"Error in agent_main: {e}")
        # Preserving the existing try-except logic while adding proper logging
        return last_task_output, strategy


def main():
    try:
        #chat_history_str = read_from_stage(session, DI_STAGE, CHAT_HISTORY_FILE)
        chat_history_str = load_chat(session, DI_STAGE + "/" + CHAT_HISTORY_FILE)
        chat_history = json.loads(chat_history_str)
        st.title("Q A Agentic Approach")
        logger.info("INTO MAIN")


        # Display chat history
        if chat_history is not None:
            for message in chat_history:
                if message["role"] == "assistant" and "strategy" in message:
                    with st.expander("Show Strategy"):
                        st.json(message["strategy"])
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            logger.info("Loaded Chat messages")
                
        # Handle user input
        if user_input := st.chat_input("Type your question..."):
            logger.info(f"New user input received: {user_input[:50]}...")
            user_message = {"role": "user", "content": user_input}
            if chat_history is None or len(chat_history)==0:
                chat_history = [user_message]
            else:
                chat_history.append(user_message)
            
            with st.chat_message("user"):
                st.markdown(user_input)
            
            logger.info("About to call agent_main function")
            response, strategy, processed_input, sql_query, latency_results = agent_main(user_input)
            
            assistant_message = {"role": "assistant", "content": response, "strategy": strategy}
            if chat_history is  None or len(chat_history)==0:
                chat_history = [assistant_message]
            else:           
                chat_history.append(assistant_message)
            
            with st.expander("Show Strategy"):
                st.json(strategy)
            
            with st.chat_message("assistant"):
                st.markdown(response)

            with st.expander("Total time taken"):
                st.json(latency_results)
            
            sql_query_entity = {'user_query': user_input, 'sql_query': sql_query}
            strategy_entity = {'user_query': user_input, 'strategy': strategy}
            processed_input_entity = {
                'user_query': user_input,
                'decomposed_steps': processed_input['decomposed_steps'],
                'normalized_query': processed_input['normalized_query']
            }        

            # try:
            #     store_in_chromadb(collection_name='cached_strategy', document=json.dumps(strategy_entity))
            #     store_in_chromadb(collection_name='sql_cached_memory', document=json.dumps(sql_query_entity))
            #     store_in_chromadb(collection_name='cached_normalised_query', document=json.dumps(processed_input_entity))
            #     logger.info("Successfully stored data in ChromaDB")
            #     st.success("Feedback stored successfully!")
            # except Exception as e:
            #     logger.error(f"Error storing data in ChromaDB: {e}")
            #     st.error("Failed to store feedback.")
            logger.info("About to persist chat messages to chat history")
            save_chat(session, DI_STAGE, CHAT_HISTORY_FILE, json.dumps(chat_history))
    except Exception as e:
        logger.error(f"Error in user interface: {e}")
        st.error(f"An error occurred: {str(e)}")




if __name__ == "__main__":
    logger = logging.getLogger(f"{__name__}.app.py")
    logger.info("Starting application app.py")
    main()
    #agent_main("Which locations have the highest claim frequency?")