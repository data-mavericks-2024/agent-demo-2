class SharedContext:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key):
        return self.data.get(key)
    def get_all(self):
        return self.data
class ResultAggregator:
    def __init__(self):
        self.results = {}

    def store_result(self, result):
        self.results[result.task_id] = result

    def get_result(self, task_id):
        return self.results.get(task_id)

    def get_results(self):
        return self.results
class Task:
    def __init__(self, description, agent_type, parameters, task_id, dependencies=None, output_schema=None):
        self.task_id = task_id
        self.description = description
        self.agent_type = agent_type
        self.parameters = parameters
        self.dependencies = dependencies or []
        self.output_schema = output_schema
        self.status = "Pending"
        self.result = None
        self.next_task_on_success = None
        self.next_task_on_failure = None

    def __repr__(self):
        return f"Task(id={self.task_id}, status={self.status}, agent={self.agent_type})"


class Planner:
    def __init__(self, strategy, agent_manager, result_aggregator, shared_context):
        self.strategy = strategy
        self.agent_manager = agent_manager
        self.result_aggregator = result_aggregator
        self.tasks = self.create_tasks()
        self.shared_context = shared_context

    def create_tasks(self):
        tasks = {}
        for task_data in self.strategy["tasks"]:            
            task = Task(
                description=task_data.get("description"),
                agent_type=task_data["agent_type"],
                parameters=task_data["parameters"],
                task_id=task_data["task_id"],
                dependencies=task_data.get("dependencies",),
                output_schema=task_data.get("output_schema")
            )
            task.next_task_on_success = task_data.get("next_task_on_success")  # Add this line
            task.next_task_on_failure = task_data.get("next_task_on_failure")  # Add this line
            tasks[task.task_id] = task
        return tasks

    def run(self):
        completed_tasks = set()
        task_results = {}
        # Find the starting task, which has no dependencies
        current_task = next((task for task in self.tasks.values() if not task.dependencies), None)
        while current_task:
            # Execute the task
            result = self.agent_manager.execute_task(current_task, self.shared_context)
            # result.set("agent_type",current_task.agent_type)
            task_results[current_task.task_id] = result.to_dict()
            self.shared_context.set("task-results",task_results)
            
            
            self.result_aggregator.store_result(result)

            # Update task status
            current_task.status = "Completed" if result.status == "Success" else "Failed"
            current_task.result = result.output
            last_task_output = result.output

            # Determine the next task based on success or failure
            next_task_id = current_task.next_task_on_success if result.status == "Success" else current_task.next_task_on_failure
            completed_tasks.add(current_task.task_id)

            # Find the next task that has its dependencies met
            # print(current_task.print_task())
            # print(self.tasks.values())
            current_task = None  # Initialize current_task to None
           
            for task in self.tasks.values():
                if task.dependencies is None:
                    task.dependencies =[]
                if task.task_id == next_task_id and all(dep in completed_tasks for dep in task.dependencies):
                    current_task = task  # Assign the task to current_task if conditions are met
                    break  # Exit the loop once a matching task is found

        # Return the final result
        return self.result_aggregator.get_results(),last_task_output,self.shared_context
