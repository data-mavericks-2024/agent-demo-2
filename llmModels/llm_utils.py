# llm_utils.py

import io
import sys
import yaml
import re
import os
import json
import logging
from dbConnection.snowpark_session_handler import get_snowpark_session
import time
#import google.generativeai as gemini_genai



from dotenv import load_dotenv
load_dotenv()
#CORTEX_LLM_MODEL = "claude-3-5-sonnet"
CORTEX_LLM_MODEL = "llama3.3-70b"
GEMINI_MODEL_NAME="gemini-2.0-flash-lite"
GEMINI_API_KEY="AIzaSyDdd72Vck8jLBsljuan7Iytv-swH6fO21w"
SCHEMA_NAME = 'DEMO_SCHEMA'
STAGE_DIR='@"DEEPINSIGHT"."DI_SCHEMA"."DI_STAGE"'
PROMPT_DIR= STAGE_DIR + "/prompt"
SCHEMA_DIR = '@"DEEPINSIGHT.DI_SCHEMA.DI_STAGE"' + "/schema"


LLM_PROVIDER="CORTEX"
#LLM_PROVIDER="GEMINI"

#gemini_genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


logger = logging.getLogger(__name__)


class LLMCaller:
    @staticmethod
    def cleanse_raw_output(json_string):

        # Special handling for markdown content
        if "```md" in json_string and "```" in json_string:
            start_idx = json_string.find("```json") + 6  # Move past ````md`
            end_idx = json_string.find("```", start_idx)  # Find closing backticks
            if end_idx > start_idx:
                json_string = json_string[start_idx:end_idx].strip()
            return json_string


        # 1. Remove control characters (except tab, newline, carriage return)
        json_string = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", json_string)
        json_string = json_string.replace("\\", "\\\\")
        # 2. Replace non-breaking spaces and similar with regular spaces
        json_string = json_string.replace("\xa0", " ").replace("\xc2\xa0", " ").replace('\xb0', ' ')
        # 3. Handle escaped characters. Decode unicode escapes and then re-encode any remaining backslashes that are not part of valid JSON escape sequences.
        try:
            json_string = json_string.encode('utf-8').decode('unicode_escape')
        except UnicodeDecodeError: #handle cases where there are invalid unicode escape sequences
            json_string = json_string.encode('utf-8', 'ignore').decode('utf-8')
        json_string = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', '', json_string) #Remove backslashes that are not part of valid JSON escape sequences.
        # 4. Handle lone surrogates (can cause UnicodeDecodeError in json.loads)
        json_string = re.sub(r"[\ud800-\udfff]", "", json_string)


        # 5. Remove any leading/trailing whitespace
        json_string = json_string.strip()

    
          # Look for the `json` block enclosed by triple backticks
        if "```json" in json_string and "```" in json_string:
            start_idx = json_string.find("```json") + 7  # Move past ````json`
            end_idx = json_string.find("```", start_idx)  # Find closing backticks
            if end_idx > start_idx:
                json_string = json_string[start_idx:end_idx].strip()
        elif "```sql" in json_string and "```" in json_string:
            start_idx = json_string.find("```sql") + 7  # Move past ````sql`
            end_idx = json_string.find("```", start_idx)  # Find closing backticks
            if end_idx > start_idx:
                json_string =  json_string[start_idx:end_idx].strip()
        
        # finally replace new lines with spaces
        json_string = re.sub(r"\n", " ", json_string)
        
        return json_string
    
   
    @staticmethod    
    def call_Cortex_llm(session, prompt, output_tag=None):


        # prompt_file_path=PROMPT_DIR+"/"+prompt_file
        
        # # Load the prompt file from the stage into a bytes stream and decode it to a string
        # stream = session.file.get_stream(prompt_file_path)
        # prompt_yaml_str = stream.read().decode('utf-8')

        # #print("prompt_yaml_str:", prompt_yaml_str)

        # for key, value in params.items():
        #     prompt_yaml_str = prompt_yaml_str.replace(key, value)
        
    
        # final_prompt = prompt_yaml_str  # or use final_prompt_dict if your integration expects a dict
        cmd = """
            SELECT snowflake.cortex.complete(?, ?) AS response
        """
        df_response = session.sql(cmd, params=[CORTEX_LLM_MODEL, prompt]).collect()
        # Extract and display the result.
        response_text = df_response[0]["RESPONSE"]

        logger.info("Response text from LLM -->>  " + response_text)


        
        try:
            cleansed_response = LLMCaller.cleanse_raw_output(response_text)
        except Exception as exp:
            logger.error("encountered error in converting LLM output: \n" + response_text)
            cleansed_response = response_text
        
        if output_tag is not None:
            response = {}
            response[output_tag] = cleansed_response
            return response

        response = json.loads(cleansed_response)

        return response
        


    # @staticmethod
    # def call_gemini_llm(contents, output_tag=None):
    #     """
    #     Makes an API call to the Gemini LLM with retry logic in case of rate limiting errors.

    #     Args:
    #         contents (list): The data to be sent to the LLM.
    #     """
    #     #print("Gemini Prompt:\n", contents)
    #     try:
    #         #print("Calling Gemini with:\n",contents)
    #         start_time = time.perf_counter()
    #         model = gemini_genai.GenerativeModel(GEMINI_MODEL_NAME)
    #         response = model.generate_content(contents)
           
    #         response.resolve()
    #         response_text = response.text
    #         # print("\n\n ********* GEMINI response: ", response_text)
            
    #         if response_text is None:
    #           print("Null response from Gemini, trying again after 15 seconds")
    #           time.sleep(15) 
    #           response = model.generate_content(contents)
    #           response.resolve()
    #           response = LLMCaller.cleanse_raw_output(response.text)
    #           #print("GEMINI RESPONSE - SECOND TRY:", response)
    #           end_time = time.perf_counter()
    #           duration = round(end_time - start_time)
    #           #print(f"Second Try: Time taken by Gemini LLM: {duration} seconds")
    #           return response
    #         else:
    #           #print("GEMINI RESPONSE:", response_text)

    #           cleansed_response = LLMCaller.cleanse_raw_output(response_text)
    #           end_time = time.perf_counter()
    #           duration = round(end_time - start_time)
    #           #print(f"First Try: Time taken by Gemini LLM: {duration} seconds")
    #           if output_tag is not None:
    #             response = {}
    #             response[output_tag] = cleansed_response
    #             return response
              
    #           response = json.loads(cleansed_response)

    #           return response
    #     except Exception as e:
    #         print(f"Error from Gemini API: {e}")
    #         try:
    #           print("Gemini call failed ... trying again in 15 seconds")
    #           time.sleep(15) 
    #           start_time = time.perf_counter()
    #           response = model.generate_content(contents)
    #           response.resolve()
    #           cleansed_response = LLMCaller.cleanse_raw_output(response.text)
    #           end_time = time.perf_counter()
    #           duration = round(end_time - start_time)
    #           #print(f"Exception/Second Try: Time taken by Gemini LLM: {duration} seconds")
    #           if output_tag is not None:
    #             response = {}
    #             response[output_tag] = cleansed_response
    #             return response
              
    #           response = json.loads(cleansed_response)

    #           return response
    #         except Exception as e:
    #            print(f"After Second Try - Error from Gemini API: {e}")
    #         return None   


# session = get_snowpark_session("arch")
# prompt_dir = ""
# response = LLMCaller.call_llm(session,CORTEX_LLM_MODEL, "tell me a koke")
# print (response)

    @staticmethod    
    def call_llm(session, prompt, output_tag=None):
        if LLM_PROVIDER == "CORTEX":
            return LLMCaller.call_Cortex_llm(session, prompt, output_tag)
        # elif LLM_PROVIDER == "GEMINI":
        #      return LLMCaller.call_gemini_llm(prompt, output_tag)


