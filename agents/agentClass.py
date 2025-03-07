import pandas as pd
import numpy as np
import jsonschema
import traceback
import logging
import re
import json
from llmModels.llm_utils import LLMCaller
from dbConnection.data_access import DataAccess
from helper import load_file
from helper import get_data_analysis_results, generate_sql_query

from agents.schemas import (
    data_analyzer_schema, 
    dictionary_lookup_schema, 
    sql_generator_schema, 
    sql_executor_schema, 
    response_generator_schema
)
# from helper import query_chromadb, extract_query,extract_yaml
from helper import extract_query

from prompts.prompts import SQL_GENRATION_PROMPT, ERROR_HANDLING_PROMPT,SQL_CACHE_MAPING

logger = logging.getLogger(__name__)




class DataAnalyzerAgent:
    def __init__(self, processed_input, di_stage, data_dictionary, session, arch_db, arch_schema):
        self.session = session
        self.arch_db = arch_db
        self.arch_schema = arch_schema
        self.di_stage = di_stage
        self.processed_input = processed_input
        self.data_dictionary = data_dictionary
        self.logger = logging.getLogger(f"{__name__}.DataAnalyzerAgent")


    def execute(self, parameters, shared_context):
        # Updated parameter format: "tables": { table_name: [column1, column2, ...], ... }
        tables = parameters["tables"]
        try:
            data_access = DataAccess(self.session)
            all_dfs = {}
            for table_name, column_names in tables.items():

                sql_query = f"SELECT * FROM {table_name} LIMIT 50"
             
                results = data_access.execute_query(sql_query)
           
                if results.status != "Success":
                    self.logger.error(f"Failed to fetch data from table {fq_table_name}")
                    return {
                        "status": "Failure",
                        "error": f"Failed to fetch data from table {fq_table_name}"
                    }
                
                # Create a DataFrame from the query results
                df = pd.DataFrame(results.output, columns=results.columns)
                all_dfs[table_name] = df
          
            # Build a combined prompt for the LLM using the data from all tables
            sample_data=""
            for table, df in all_dfs.items():
                sample_data += f"Table: {table}\n"
                sample_data += df.to_csv(index=False) + "\n\n"

            # get data dictionary specific to tables involved, if available from prior stage, else the entire data dict
            # this is bad design - replace this, since this makes one agent's execution dependent on another
          
            data = shared_context.get_all()
            #print(data)

           
            if data.get("dictionary_lookup_results") is not None:
                if data.get("dictionary_lookup_results").get("output") is not None:
                    self.data_dictionary = data.get("dictionary_lookup_results").get("output") 

            insights = get_data_analysis_results(self.session,
                                                 self.di_stage,
                                                 self.processed_input["normalized_query"],
                                                 self.data_dictionary,
                                                 sample_data,
                                                 None)
            
            result = {"status": "Success", "output": insights}
            shared_context.set('data_analysis_results', result)
            self.logger.info("DataAnalyzerAgent successfully analyzed the dataset and generated insights.")
            return result

        except Exception as e:
            import sys
            self.logger.error(f"DataAnalyzerAgent execution failed:: {e}\n{traceback.format_exc()}")
            self.logger.error("Full Exception Traceback:")
            self.logger.error("".join(traceback.format_exception(*sys.exc_info())))

            return {"status": "Failure", "error": str(e)}


class DictionaryLookupAgent:
    def __init__(self, data_dictionary):
        self.data_dictionary = data_dictionary
        self.logger = logging.getLogger(f"{__name__}.DictionaryLookupAgent")

    def execute(self, parameters, shared_context):
        tables = parameters["tables"]  # New parameter format
        try:
            output = {}
            # Iterate over each table and its columns
            for table_name, column_names in tables.items():
            #for table_name in tables:
                table_found = False
                # Search for the table in the data dictionary
                for table_info in self.data_dictionary:
                    if table_info["table_name"] == table_name:
                        table_found = True
                        output[table_name] = {}
                        output[table_name]["description"] = table_info["description"]
                        output[table_name]["keys"] = table_info["keys"]
                        output[table_name]["synonyms"] = table_info["synonyms"]
                        output[table_name]["possible_joins"] = table_info["join_conditions"]
                        # Iterate over each column in the provided list
                        for column_name in column_names:
                            column_found = False
                            # Search for the column in the table's columns
                            for column in table_info["columns"]:
                                if column["column_name"] == column_name:
                                    output[table_name][column_name] = {
                                        "description": column.get("description"),
                                        "data_type": column.get("data_type"),
                                        "potential_correlations": column.get("potential_correlations"),
                                        "inferred_business_rules": column.get("inferred_business_rules"),
                                    }
                                    column_found = True
                                    break  # Column found, exit inner loop
                            if not column_found:
                                self.logger.error(f"Column {column_name} or table {table_name} not found")
                                return {
                                    "status": "Failure",
                                    "error": f"Column {column_name} or table {table_name} not found",
                                    "error_code": "NOT_FOUND",
                                }
                        break  # Table found, no need to check further tables
                if not table_found:
                    self.logger.error(f"Table {table_name} not found")
                    return {
                        "status": "Failure",
                        "error": f"Table {table_name} not found",
                        "error_code": "NOT_FOUND",
                    }

            result = {"status": "Success", "output": output}
            shared_context.set('dictionary_lookup_results', result)

            try:
                jsonschema.validate(instance=result, schema=dictionary_lookup_schema)
                self.logger.info("DictionaryLookupAgent successfully retrieved metadata and insights from the data dictionary.")
                self.logger.info("Retrived data dict: " + json.dumps(output))
                return result
            except jsonschema.exceptions.ValidationError as e:
                self.logger.error(f"Schema validation failed: {e.message}")
                return {
                    "status": "Failure",
                    "error": f"Schema validation failed: {e.message}",
                    "error_code": "SCHEMA_VALIDATION_ERROR",
                }

        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
            return {
                "status": "Failure",
                "error": f"An unexpected error occurred: {e}\n{traceback.format_exc()}",
                "error_code": "UNEXPECTED_ERROR",
            }


class SQLGeneratorAgent:
    def __init__(self,  di_db_session, di_stage, data_dictionary, processed_input, user_input):
        self.session = di_db_session
        self.stage = di_stage
        self.data_dictionary = data_dictionary
        self.processed_input = processed_input
        self.user_input = user_input
        self.logger = logging.getLogger(f"{__name__}.SQLGeneratorAgent")
        
    def execute(self, parameters, shared_context):
        task_description = parameters["task_description"]
        tables = parameters["tables"]
        conditions = parameters.get("conditions", {})
        
        data = shared_context.get_all()
        if data.get("data_analysis_results") is not None:
            if data.get("data_analysis_results").get("output") is not None:
                self.data_dictionary = data.get("data_analysis_results").get("output") 

        data_dictionary = self.data_dictionary

        try:

            sql_query = generate_sql_query(self.session, self.stage, 
                                        self.processed_input.get("normalized_query"),
                                        self.processed_input.get("decomposed_steps"),
                                        data_dictionary, tables, conditions
                                        )
            
            # try:
            #     data_access = DataAccess(self.db_filepath)        
            #     results = data_access.execute_query(sql_query)
            #     if results.status == 'Success':
            #         result = {
            #             "status": "Success",
            #             "output": {"sql_query": sql_query}
            #         }
            #     else:
            #         self.logger.warning(f"First SQL execution attempt failed: {str(results.error)}")
            #         error_handling_prompt = ERROR_HANDLING_PROMPT.format(user_query=self.processed_input, error=results.error,data_dictionary = self.data_dictionary)
            #         corrected_query = LLMCaller.call_llm(error_handling_prompt, "GENERATE SQL TASK", None)
            #         sql_query = extract_query(corrected_query)
            #         data_access = DataAccess(self.db_filepath)        
            #         results= data_access.execute_query(sql_query)
            #         if results.status == 'Success':
            #             result = {
            #                 "status": "Success",
            #                 "output": {"sql_query": sql_query}
            #             }
            #         else:
            #             self.logger.warning(f"Second SQL execution attempt failed: {str(results.error)}")
            #             error_handling_prompt = ERROR_HANDLING_PROMPT.format(user_query=self.processed_input, error=results.error,data_dictionary = self.data_dictionary)
            #             corrected_query = LLMCaller.call_llm(error_handling_prompt, "GENERATE SQL TASK", None)
            #             sql_query = extract_query(corrected_query)
            #             result = {
            #                 "status": "Success",
            #                 "output": {"sql_query": sql_query}
            #             }
                        
            # except Exception as e:
            #     self.logger.error(f"Exception Occured while generating SQL Query: {e}")
            # shared_context.set('sql_generation_results', result)
            
            try:
               
                result = {"status": "Success", "output": sql_query}
                jsonschema.validate(instance=result, schema=sql_generator_schema)
                self.logger.info(f"SQLGeneratorAgent successfully generated the SQL query: {sql_query}")
                shared_context.set('sql_generation_results', result)
                
                return result
            except jsonschema.exceptions.ValidationError as e:
                self.logger.error(f"Schema validation failed: {e.message}")
                return {
                    "status": "Failure",
                    "error": f"Schema validation failed: {e.message}",
                    "error_code": "SCHEMA_VALIDATION_ERROR"
                }

        except Exception as e:
            self.logger.error(f"An unexpected error occurred during SQL generation: {e}\n{traceback.format_exc()}")
            return {
                "status": "Failure",
                "error": f"An unexpected error occurred during SQL generation: {e}\n{traceback.format_exc()}",
                "error_code": "SQL_GENERATION_ERROR"
            }


class SQLExecutorAgent:
    def __init__(self, session):
        self.session = session
        self.logger = logging.getLogger(f"{__name__}.SQLExecutorAgent")
        
    def execute(self, parameters, shared_context):
        try:
            sql_query = shared_context.get("sql_generation_results")['output']['sql_query']
            if not sql_query:
                self.logger.error("No SQL query provided in parameters.")
                return {"status": "Failure", "error": "No SQL query provided in parameters."}
            
            # Create a DataAccess instance to execute the query
    
            data_access = DataAccess( self.session)        
            results = data_access.execute_query(sql_query)
            if results.status == 'Success':
                result = {"status": "Success", "output": results.output[:1000]}
                print("length of result ",len(results.output))
                self.logger.info(f"SQL query execution response: {results.status}")
            else:
                self.logger.error(f"Exception occurred while executing SQL query: {str(results.error)}")
                result = {"status": "Success", "output": ["Execution Failed of user Query try to analyze some other data"]}
                
            shared_context.set("sql_execution_results", result)
            try:
                self.logger.debug("Validating output against schema")
                jsonschema.validate(instance=result, schema=sql_executor_schema)
                self.logger.info("SQLExecutor successfully executed the generated SQL query.")
                return result
            except jsonschema.exceptions.ValidationError as e:
                self.logger.error(f"Schema validation failed: {e.message}")
                return {"status": "Failure", "error": f"Schema validation failed: {e.message}", "error_code": "SCHEMA_VALIDATION_ERROR"}
        except Exception as e:
            self.logger.error(f"An unexpected error occurred: {e}\n{traceback.format_exc()}")
            return {"status": "Failure", "error": f"An unexpected error occurred: {e}\n{traceback.format_exc()}", "error_code": "UNEXPECTED_ERROR"}


class ResponseGeneratorAgent:
    def __init__(self, di_db_session, di_stage, user_input):
        self.user_input = user_input
        self.session = di_db_session
        self.stage = di_stage
        self.logger = logging.getLogger(f"{__name__}.ResponseGeneratorAgent")
        
    def execute(self, parameters, shared_context):
        try:
            user_query = parameters['user_query']
            #agent_outputs = shared_context.get_all()
            task_results = shared_context.get_all().get("task-results")

            prompt_yaml = load_file(self.session, self.stage + "/prompts/response_generator_prompt.yaml")
       
            prompt_yaml["dynamic_input"] = {
                "user_question": user_query,
                "agent_outputs": task_results
            }
            
            response = LLMCaller.call_llm(self.session,json.dumps(prompt_yaml), output_tag="response_streamlit")
            response = response.get("response_streamlit")
            try:
                self.logger.info("Response from ResponseGenerator --> " + response)
            except Exception as ex:
                 self.logger.error("Error in printing the response from Response Generator -> " + ex.message)
            
            result = {"status": "Success", "output": response}
        
            shared_context.set('response_generation_results', result)

            # Validate the response against the schema
            try:
                #jsonschema.validate(instance=result, schema=response_generator_schema)
                self.logger.info("ResponseGeneratorAgent successfully executed.")
                return result
            except jsonschema.exceptions.ValidationError as e:
                self.logger.error(f"Schema validation failed: {e.message}")
                return {"status": "Failure", "error": f"Schema validation failed: {e.message}", "error_code": "SCHEMA_VALIDATION_ERROR"}

        except Exception as e:
            self.logger.error(f"An unexpected error occurred during response generation: {e}\n{traceback.format_exc()}")
            return {"status": "Failure", "error": f"An unexpected error occurred during response generation: {e}\n{traceback.format_exc()}", "error_code": "RESPONSE_GENERATION_ERROR"}