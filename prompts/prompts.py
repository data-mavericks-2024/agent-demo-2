SQL_GENRATION_PROMPT1 = """
Task: You are an expert in SQL query development with deep knowledge of insurance industry terminology.

I need you to create a SQL query that answers this question: {user_query}

The query must follow these conditions:
{conditions}

Available tables and columns:
{tables}

Data Dictionary:
{data_dictionary}

Important: Verify column and table names against the data dictionary. If there's any mismatch between provided tables/columns and the data dictionary, prioritize using the names from the data dictionary.

Create a clean, syntax-error-free SQL query that will execute successfully on the first attempt.

Example user queries and their corresponding SQL solutions:
{sql_cached_example}

Response format:
- Provide only the SQL query without any explanations, comments, or backticks
- Ensure the query is formatted with proper indentation for readability
- Don't include any unnecessary text before or after the query"""


SQL_GENRATION_PROMPT = """
Task: You are an expert in SQLite query development with deep knowledge of insurance industry terminology.

I need you to create a SQLite query that with this information: {user_query}

Important: Verify column and table names against the data dictionary. If there's any mismatch between provided tables/columns and the data dictionary, prioritize using the names from the data dictionary.

Create a clean, syntax-error-free SQL query that will execute successfully on the first attempt.
Response format:
- Provide only the SQL query without any explanations, comments, or backticks
- Ensure the query is formatted with proper indentation for readability
- Don't include any unnecessary text before or after the query
- Provide output in ```sql  {{sql_query}} ```
"""


ERROR_HANDLING_PROMPT = """
As an SQL expert specializing in insurance data, please fix this query:

I'm trying to {user_query} in my insurance database using SQLite, but I'm getting:
Error: {error}

Data Dictionary : {data_dictionary}
Confirm the columns name from the data daictionary is this  provided column names provided in the user querie are correct or not


Please provide ONLY the corrected sql query with no explanations.(```sql)

"""


SQL_CACHE_MAPING = """
# Insurance Analytics Comprehensive Analyzer

You are an expert in insurance analytics with deep knowledge of a commercial property insurance data dictionary. Your task is to analyze a given natural language query and provide three distinct outputs:

## Task 1: Generate Metadata Object in YAML
First, generate a metadata object in YAML format that captures:
- The key data entities (domains) involved (using standard names from the data dictionary)
- The key columns explicitly mentioned or logically inferred from the query
- The necessary join conditions (relationships) required to connect these entities
- Any relevant notes or assumptions explaining your reasoning

## Task 2: Determine Composite Narrow Intent
Next, generate a composite narrow intent that combines:
1. The primary data domain(s) involved (as identified from the data dictionary)
2. The specific analytical operation being requested (aggregation, counting, averaging, trend analysis, etc.)

Format this as: "[Analytical Operation] ([Primary Data Domain(s)])"

## Task 3: Determine Overall Business Function (Broad Intent)
Finally, determine the overall business function that the query supports, selecting ONE of these categories:
- "Performance Analysis" (premium, policy program, revenue, renewal, volume)
- "Risk Identification" (claims, loss, risk, severity, frequency)
- "Underwriting Improvement" (underwriting, policyholder evaluation, pricing, eligibility, credit)
- "Operations Optimization" (processing, cancellations, renewal process, operations, efficiency)
- "Decision Support" (market share, competitive positioning, investment, benchmarking, strategic decision-making)
- "General" (if no clear mapping is found)

## Instructions for Analysis:
1. Review the data dictionary provided with the query (includes entities like PLC, CLM, INS, LOC, BRKR, ADJ and their synonyms)
2. Analyze the query carefully to understand its context and requirements
3. For each task, follow the specific guidelines outlined above
4. Provide your analysis in the following structured format:

```
## Metadata Object (YAML)
```yaml
broad_intent:''
narrow_intent: ''
metadata:
  tables:
    - [list of relevant data entities]
  columns:
    - [list of key columns required]
  join_conditions:
    - [list of join conditions as strings]
  notes: [explanation of reasoning and assumptions]
```

## Composite Narrow Intent
[Analytical Operation] ([Primary Data Domain(s)])

## Broad Intent
[Single business function label]
```

Query: "{user_input}"

Data Dictionary:{data_dictionary}
"""