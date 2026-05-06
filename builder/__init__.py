"""
Builder — Project Builder Execution System.

Transforms natural language project requests into real, running code:
  goal_parser      → parse user intent
  project_planner  → generate file/command plan
  file_executor    → create real files on disk
  terminal_runner  → run real shell commands (sandboxed)
  result_checker   → detect errors from real stdout/stderr
  repair_loop      → iterative LLM-guided fixing with rollback
  builder_controller → orchestrate end-to-end pipeline
"""
