RETRY_PROMPT = """你上一次输出不符合要求，请严格根据原始任务重新输出。

原始任务：
{start_prompt}

你上一次的错误输出：
{bad_output}

错误原因：
{error_message}
"""
