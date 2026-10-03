def run_agent(agent_id, uploaded_files):
    results = []

    for file in uploaded_files:
        results.append({
            "agent_id": agent_id,
            "file_name": file.name
        })

    return results