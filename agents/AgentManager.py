from agents.agentClass import DataAnalyzerAgent,DictionaryLookupAgent,SQLGeneratorAgent,SQLExecutorAgent,ResponseGeneratorAgent
import time

class AgentResult:
    def __init__(self, task_id, status, output, elapsed_time, error=None, schema_errors=None):
        self.task_id = task_id
        self.status = status
        self.output = output
        self.error = error
        self.elapsed_time = elapsed_time
        self.schema_errors = schema_errors
        
    def to_dict(self):  # Convert object to dictionary
        return {
            "task_id": self.task_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "elapsed_time": self.elapsed_time,
            "schema_errors": self.schema_errors
        }            
class AgentManager:
    def __init__(self, session, ARCH_DB, ARCH_SCHEMA, DI_STAGE, data_dictionary, processed_input,user_input):
        self.session = session
        self.arch_db = ARCH_DB
        self.arch_schema = ARCH_SCHEMA
        self.di_stage = DI_STAGE
        self.data_dictionary = data_dictionary
        self.processed_input = processed_input
        self.user_input = user_input


    def create_agent(self, agent_type):
        print(f"🤖 Execution started for AI agent: {agent_type}")
        if agent_type == "DictionaryLookup":
            return DictionaryLookupAgent(self.data_dictionary)
        elif agent_type == "DataAnalyzer":
            return DataAnalyzerAgent(self.processed_input,self.di_stage, self.data_dictionary, self.session, self.arch_db, self.arch_schema)
        elif agent_type == "SQLGenerator":
            return SQLGeneratorAgent(self.session, self.di_stage, self.data_dictionary,self.processed_input,self.user_input)
        elif agent_type == "SQLExecutor":
            return SQLExecutorAgent(self.session)
        elif agent_type == "ResponseGenerator":
            return ResponseGeneratorAgent(self.session, self.di_stage, self.user_input)
        else:
            raise ValueError(f"Invalid agent type: {agent_type}")

    def execute_task(self, task, shared_context):
        agent = self.create_agent(task.agent_type)
        start_time = time.perf_counter()
        result = agent.execute(task.parameters, shared_context)
        end_time = time.perf_counter()
        elapsed_time = end_time - start_time
        return AgentResult(task.task_id, result["status"], result.get("output"), elapsed_time=elapsed_time, error=result.get("error"))  # Pass task_id to AgentResult