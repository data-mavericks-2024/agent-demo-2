data_analyzer_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Success", "Failure"]},
        "output": {"type": "array", "items": {"type": "object"}},  # Change "object" to "array" with "items"
        "error": {"type": "string"}
    },
    "required": ["status"]
}

dictionary_lookup_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Success", "Failure"]},
        "output": {"type": "object"},
        "error": {"type": "string"}
    },
    "required": ["status"]
}

sql_generator_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Success", "Failure"]},
        "output": {"type": "object", "properties": {"sql_query": {"type": "string"}}},
        "error": {"type": "string"}
    },
    "required": ["status", "output"]
}

sql_executor_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Success", "Failure"]},
        "output": {"type": "array"},
        "error": {"type": "string"}
    },
    "required": ["status"]
}

response_generator_schema = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["Success", "Failure"]},
        "output": {"type": "object", "properties": {"response_json": {"type": "object"}}},
        "error": {"type": "string"}
    },
    "required": ["status", "output"]
}