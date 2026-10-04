# MILES — LANTERN HARNESS HANDOFF

Generated: `2026-10-04T20:07:03.238888+00:00`

This report was generated directly from the current repository.

**Repository contents are the source of truth.**

Static analysis was performed without executing the application.


## 1. REPOSITORY MAP

```text
ODYSSEUS_INTEGRATION.md
PEACEMAKER.md
README.md
RELEASE.md
config/config.json
examples/demo_operating_loop.py
export_for_miles.py
lantern_harness/__init__.py
lantern_harness/bootstrap.py
lantern_harness/bridge.py
lantern_harness/confidence_field.py
lantern_harness/config.py
lantern_harness/decision_state_machine.py
lantern_harness/harness_status.py
lantern_harness/mcp_server.py
lantern_harness/operating_loop.py
lantern_harness/permission_authority.py
lantern_harness/perspective_differential.py
lantern_harness/prompt_compiler.py
lantern_harness/reality_boundary.py
lantern_harness/reasoning/__init__.py
lantern_harness/reasoning/api_provider.py
lantern_harness/reasoning/base.py
lantern_harness/reasoning/ollama_provider.py
lantern_harness/self_model.py
lantern_harness/spine.py
lantern_harness/tools/__init__.py
lantern_harness/tools/boundary.py
lantern_harness/transfer_manifest.py
main.py
prompts/system.md
prompts/tool_use.md
pyproject.toml
tests/test_bootstrap.py
tests/test_bridge.py
tests/test_confidence_field.py
tests/test_config.py
tests/test_conversation_loop.py
tests/test_decision_state_machine.py
tests/test_harness_status.py
tests/test_mcp_server.py
tests/test_mcp_server_live_stdio.py
tests/test_operating_loop.py
tests/test_permission_authority.py
tests/test_perspective_differential.py
tests/test_prompt_compiler.py
tests/test_reality_boundary.py
tests/test_reasoning.py
tests/test_self_model.py
tests/test_spine.py
tests/test_tool_boundary.py
tests/test_transfer_manifest.py
```


## 2. DISCOVERED EXECUTION MODEL

The following execution model is a STATIC ANALYSIS HYPOTHESIS.

It must be checked against the call graph above.

`main.py` appears to be an application entrypoint.
`lantern_harness/bridge.py` appears to contain the Lantern integration boundary.
`lantern_harness/operating_loop.py` appears to contain structured execution behavior.
`lantern_harness/permission_authority.py` appears to contain authorization logic.
`lantern_harness/reality_boundary.py` appears to contain claim/evidence boundary logic.
`lantern_harness/spine.py` appears to contain persistence/commitment logic.


## 3. DISCOVERED ENTRY POINTS

- `examples/demo_operating_loop.py`: main() at line 36
- `export_for_miles.py`: main() at line 809
- `lantern_harness/bootstrap.py`: bootstrap() at line 42
- `lantern_harness/mcp_server.py`: main() at line 223
- `lantern_harness/operating_loop.py`: OperatingLoop.run() at line 102
- `lantern_harness/reasoning/api_provider.py`: OpenAIEngine.respond() at line 32
- `lantern_harness/reasoning/api_provider.py`: AnthropicEngine.respond() at line 77
- `lantern_harness/reasoning/api_provider.py`: GoogleEngine.respond() at line 128
- `lantern_harness/reasoning/base.py`: ReasoningEngine.respond() at line 36
- `lantern_harness/reasoning/ollama_provider.py`: OllamaEngine.respond() at line 36
- `main.py`: run_repl() at line 204
- `main.py`: main() at line 247
- `tests/test_conversation_loop.py`: test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.respond() at line 69


## 4. CLASSES AND FUNCTIONS

### `examples/demo_operating_loop.py`
- FUNCTION `main()` — line 36

### `export_for_miles.py`
- CLASS `PythonAnalysis` — line 136
- CLASS `ASTVisitor` extends ast.NodeVisitor — line 171
- FUNCTION `redact()` — line 99
- FUNCTION `should_skip()` — line 112
- FUNCTION `relative()` — line 114
- FUNCTION `read_text()` — line 116
- FUNCTION `all_files()` — line 123
- FUNCTION `python_files()` — line 129
- FUNCTION `PythonAnalysis.__init__()` — line 137
- FUNCTION `PythonAnalysis.parse()` — line 149
- FUNCTION `ASTVisitor.__init__()` — line 172
- FUNCTION `ASTVisitor.visit_Import()` — line 178
- FUNCTION `ASTVisitor.visit_ImportFrom()` — line 184
- FUNCTION `ASTVisitor.visit_FunctionDef()` — line 198
- FUNCTION `ASTVisitor.visit_AsyncFunctionDef()` — line 225
- FUNCTION `ASTVisitor.visit_ClassDef()` — line 242
- FUNCTION `ASTVisitor.visit_Call()` — line 265
- FUNCTION `ASTVisitor.visit_Constant()` — line 303
- FUNCTION `analyze_repository()` — line 321
- FUNCTION `repository_map()` — line 331
- FUNCTION `configuration_report()` — line 341
- FUNCTION `language_for()` — line 395
- FUNCTION `source_block()` — line 405
- FUNCTION `call_graph()` — line 428
- FUNCTION `symbol_report()` — line 446
- FUNCTION `import_report()` — line 481
- FUNCTION `entrypoint_report()` — line 496
- FUNCTION `security_report()` — line 509
- FUNCTION `marker_report()` — line 530
- FUNCTION `test_report()` — line 547
- FUNCTION `verification_questions()` — line 564
- FUNCTION `execution_model()` — line 599
- FUNCTION `build_report()` — line 647
- FUNCTION `main()` — line 809

### `lantern_harness/bootstrap.py`
- FUNCTION `check_python()` — line 19
- FUNCTION `check_lantern_importable()` — line 24
- FUNCTION `ensure_directories()` — line 32
- FUNCTION `bootstrap()` — line 42
- FUNCTION `format_bootstrap_report()` — line 83

### `lantern_harness/bridge.py`
- CLASS `LanternBridge` — line 20
- FUNCTION `LanternBridge.__init__()` — line 31
- FUNCTION `LanternBridge.ensure_identity()` — line 45
- FUNCTION `LanternBridge.identity_status()` — line 60
- FUNCTION `LanternBridge.startup()` — line 73
- FUNCTION `LanternBridge.observe()` — line 80
- FUNCTION `LanternBridge.add_evidence()` — line 83
- FUNCTION `LanternBridge.resolve()` — line 90
- FUNCTION `LanternBridge.belief()` — line 93
- FUNCTION `LanternBridge.latest_contradiction()` — line 96
- FUNCTION `LanternBridge.save_snapshot()` — line 101
- FUNCTION `LanternBridge.status()` — line 104
- FUNCTION `LanternBridge.create_scar()` — line 110
- FUNCTION `LanternBridge.persist_scar()` — line 113
- FUNCTION `LanternBridge.branches()` — line 120
- FUNCTION `LanternBridge.witness_integrity()` — line 127

### `lantern_harness/confidence_field.py`
- CLASS `ConfidenceFieldReading` — line 27
- CLASS `ConfidenceField` — line 72
- FUNCTION `ConfidenceFieldReading.to_dict()` — line 48
- FUNCTION `ConfidenceField.__init__()` — line 90
- FUNCTION `ConfidenceField.evaluate()` — line 98

### `lantern_harness/config.py`
- FUNCTION `load_config()` — line 17

### `lantern_harness/decision_state_machine.py`
- CLASS `DecisionReading` — line 30
- CLASS `DecisionStateMachine` — line 63
- FUNCTION `DecisionReading.to_dict()` — line 45
- FUNCTION `DecisionStateMachine.recommend()` — line 68

### `lantern_harness/harness_status.py`
- FUNCTION `_mcp_server_status()` — line 12
- FUNCTION `lantern_version()` — line 20
- FUNCTION `status_report()` — line 45
- FUNCTION `format_status_report()` — line 85

### `lantern_harness/mcp_server.py`
- CLASS `LanternMCPContext` — line 69
- FUNCTION `LanternMCPContext.__init__()` — line 74
- FUNCTION `build_server()` — line 88
- FUNCTION `build_server.lantern_observe()` — line 107
- FUNCTION `build_server.lantern_add_evidence()` — line 112
- FUNCTION `build_server.lantern_confidence()` — line 117
- FUNCTION `build_server.lantern_decide()` — line 122
- FUNCTION `build_server.lantern_compile()` — line 128
- FUNCTION `build_server.lantern_self_model()` — line 133
- FUNCTION `build_server.lantern_branch_open()` — line 137
- FUNCTION `build_server.lantern_spine_read()` — line 142
- FUNCTION `build_server.lantern_witness_integrity()` — line 147
- FUNCTION `build_server.lantern_evaluate_intent()` — line 160
- FUNCTION `build_server.lantern_transfer_manifest()` — line 186
- FUNCTION `build_server.lantern_permissions()` — line 205
- FUNCTION `main()` — line 223

### `lantern_harness/operating_loop.py`
- CLASS `LoopResult` — line 44
- CLASS `OperatingLoop` — line 89
- FUNCTION `LoopResult.to_dict()` — line 54
- FUNCTION `LoopResult.format()` — line 66
- FUNCTION `OperatingLoop.__init__()` — line 93
- FUNCTION `OperatingLoop.run()` — line 102

### `lantern_harness/permission_authority.py`
- CLASS `PermissionGrant` — line 110
- CLASS `AlignmentResult` — line 151
- CLASS `PermissionCheckResult` — line 178
- CLASS `PermissionAuthority` — line 229
- FUNCTION `PermissionGrant.to_dict()` — line 127
- FUNCTION `PermissionGrant.is_active()` — line 141
- FUNCTION `AlignmentResult.to_dict()` — line 165
- FUNCTION `PermissionCheckResult.to_dict()` — line 195
- FUNCTION `PermissionCheckResult.format()` — line 208
- FUNCTION `PermissionAuthority.__init__()` — line 245
- FUNCTION `PermissionAuthority.grant()` — line 249
- FUNCTION `PermissionAuthority.revoke()` — line 291
- FUNCTION `PermissionAuthority.active_grants()` — line 322
- FUNCTION `PermissionAuthority.all_grants()` — line 325
- FUNCTION `PermissionAuthority._find_active_grant()` — line 331
- FUNCTION `PermissionAuthority.check()` — line 337
- FUNCTION `PermissionAuthority.format_new_authority_request()` — line 386
- FUNCTION `PermissionAuthority.format_action_complete()` — line 418

### `lantern_harness/perspective_differential.py`
- CLASS `Perspective` — line 27
- CLASS `DifferentialReading` — line 52
- CLASS `PerspectiveDifferentialEngine` — line 75
- FUNCTION `Perspective.to_dict()` — line 40
- FUNCTION `DifferentialReading.to_dict()` — line 62
- FUNCTION `PerspectiveDifferentialEngine.compare()` — line 79

### `lantern_harness/prompt_compiler.py`
- CLASS `FieldStatus` — line 27
- CLASS `CompiledPrompt` — line 54
- CLASS `PromptCompiler` — line 77
- FUNCTION `_looks_consequential()` — line 48
- FUNCTION `CompiledPrompt.to_dict()` — line 64
- FUNCTION `PromptCompiler.__init__()` — line 86
- FUNCTION `PromptCompiler.compile()` — line 89
- FUNCTION `PromptCompiler._read_bridge_state()` — line 182
- FUNCTION `PromptCompiler._default_desired_output()` — line 255
- FUNCTION `PromptCompiler._epistemic_status()` — line 265
- FUNCTION `PromptCompiler._render()` — line 279

### `lantern_harness/reality_boundary.py`
- CLASS `ActionProposal` — line 42
- CLASS `ActionRecord` — line 68
- CLASS `RealityBoundary` — line 100
- FUNCTION `ActionProposal.to_dict()` — line 56
- FUNCTION `ActionRecord.to_dict()` — line 80
- FUNCTION `ActionRecord.is_real_success()` — line 91
- FUNCTION `RealityBoundary.propose()` — line 108
- FUNCTION `RealityBoundary.act()` — line 127
- FUNCTION `RealityBoundary.simulate()` — line 166

### `lantern_harness/reasoning/__init__.py`
- FUNCTION `build_engine()` — line 25

### `lantern_harness/reasoning/api_provider.py`
- CLASS `OpenAIEngine` extends ReasoningEngine — line 17
- CLASS `AnthropicEngine` extends ReasoningEngine — line 62
- CLASS `GoogleEngine` extends ReasoningEngine — line 113
- FUNCTION `OpenAIEngine.__init__()` — line 20
- FUNCTION `OpenAIEngine._api_key()` — line 24
- FUNCTION `OpenAIEngine.detect()` — line 27
- FUNCTION `OpenAIEngine.respond()` — line 32
- FUNCTION `OpenAIEngine.describe()` — line 57
- FUNCTION `AnthropicEngine.__init__()` — line 65
- FUNCTION `AnthropicEngine._api_key()` — line 69
- FUNCTION `AnthropicEngine.detect()` — line 72
- FUNCTION `AnthropicEngine.respond()` — line 77
- FUNCTION `AnthropicEngine.describe()` — line 108
- FUNCTION `GoogleEngine.__init__()` — line 116
- FUNCTION `GoogleEngine._api_key()` — line 120
- FUNCTION `GoogleEngine.detect()` — line 123
- FUNCTION `GoogleEngine.respond()` — line 128
- FUNCTION `GoogleEngine.describe()` — line 163

### `lantern_harness/reasoning/base.py`
- CLASS `ReasoningResponse` — line 14
- CLASS `ReasoningEngineUnavailable` extends RuntimeError — line 21
- CLASS `ReasoningEngine` — line 26
- FUNCTION `ReasoningEngine.respond()` — line 36
- FUNCTION `ReasoningEngine.describe()` — line 39

### `lantern_harness/reasoning/ollama_provider.py`
- CLASS `OllamaEngine` extends ReasoningEngine — line 14
- FUNCTION `OllamaEngine.__init__()` — line 17
- FUNCTION `OllamaEngine.detect()` — line 21
- FUNCTION `OllamaEngine.respond()` — line 36
- FUNCTION `OllamaEngine.describe()` — line 58

### `lantern_harness/self_model.py`
- CLASS `SelfModelReading` — line 77
- CLASS `SelfModel` — line 120
- FUNCTION `SelfModelReading.to_dict()` — line 87
- FUNCTION `SelfModelReading.format()` — line 99
- FUNCTION `SelfModel.__init__()` — line 124
- FUNCTION `SelfModel.describe()` — line 128

### `lantern_harness/spine.py`
- CLASS `Branch` — line 54
- CLASS `SpineEntry` — line 83
- CLASS `CommitResult` — line 113
- CLASS `BranchStore` — line 126
- CLASS `SpineCommitter` — line 185
- FUNCTION `_uid()` — line 49
- FUNCTION `Branch.to_dict()` — line 69
- FUNCTION `SpineEntry.to_dict()` — line 97
- FUNCTION `CommitResult.to_dict()` — line 118
- FUNCTION `BranchStore.__init__()` — line 132
- FUNCTION `BranchStore.open_branch()` — line 135
- FUNCTION `BranchStore.get()` — line 146
- FUNCTION `BranchStore.add_note()` — line 149
- FUNCTION `BranchStore.link_observation()` — line 154
- FUNCTION `BranchStore.link_evidence()` — line 160
- FUNCTION `BranchStore.abandon()` — line 166
- FUNCTION `BranchStore._require()` — line 173
- FUNCTION `BranchStore.all()` — line 181
- FUNCTION `SpineCommitter.__init__()` — line 190
- FUNCTION `SpineCommitter.commit()` — line 193
- FUNCTION `SpineCommitter.read_spine()` — line 286
- FUNCTION `branch_to_scar()` — line 318

### `lantern_harness/tools/boundary.py`
- CLASS `ToolDescriptor` — line 16
- CLASS `ToolResult` — line 24
- CLASS `ToolBoundary` — line 31
- FUNCTION `ToolBoundary.__init__()` — line 43
- FUNCTION `ToolBoundary.register()` — line 47
- FUNCTION `ToolBoundary.discover()` — line 50
- FUNCTION `ToolBoundary.authorize()` — line 53
- FUNCTION `ToolBoundary.is_authorized()` — line 60
- FUNCTION `ToolBoundary.execute()` — line 63

### `lantern_harness/transfer_manifest.py`
- CLASS `TransferManifest` — line 121
- FUNCTION `_git_commit()` — line 84
- FUNCTION `_lantern_core_commit()` — line 100
- FUNCTION `_protocol_info()` — line 111
- FUNCTION `TransferManifest.to_dict()` — line 143
- FUNCTION `TransferManifest.format()` — line 176
- FUNCTION `build_manifest()` — line 221

### `main.py`
- FUNCTION `load_system_prompt()` — line 35
- FUNCTION `handle_command()` — line 41
- FUNCTION `handle_stateful_command()` — line 100
- FUNCTION `run_repl()` — line 204
- FUNCTION `main()` — line 247

### `tests/test_bootstrap.py`
- FUNCTION `test_check_python_reports_actual_version()` — line 9
- FUNCTION `test_bootstrap_returns_bridge_when_lantern_importable()` — line 15
- FUNCTION `test_bootstrap_reasoning_engine_not_configured_by_default()` — line 21
- FUNCTION `test_ensure_directories_creates_all_required()` — line 28

### `tests/test_bridge.py`
- FUNCTION `_new_bridge()` — line 10
- FUNCTION `test_identity_starts_uninitialized()` — line 15
- FUNCTION `test_ensure_identity_creates_real_node_identity()` — line 20
- FUNCTION `test_identity_persists_across_bridge_instances()` — line 28
- FUNCTION `test_observe_and_belief_flow()` — line 39
- FUNCTION `test_startup_with_no_prior_state()` — line 48
- FUNCTION `test_witness_integrity_valid_on_fresh_chronicle()` — line 55
- FUNCTION `test_branches_not_implemented_honestly()` — line 62
- FUNCTION `test_snapshot_and_restart_recovery()` — line 71

### `tests/test_confidence_field.py`
- FUNCTION `_fresh_bridge()` — line 12
- FUNCTION `_add_evidence()` — line 22
- FUNCTION `test_high_state_with_strong_independent_support()` — line 27
- FUNCTION `test_medium_state_boundary_exact_threshold()` — line 37
- FUNCTION `test_low_state_with_empty_evidence()` — line 45
- FUNCTION `test_blocked_state_on_integrity_failure()` — line 54
- FUNCTION `test_blocked_is_more_severe_than_low()` — line 65
- FUNCTION `test_contradictory_evidence_increases_pressure_and_lowers_confidence()` — line 78
- FUNCTION `test_assumption_pressure_raises_investigation_need()` — line 87
- FUNCTION `test_perspective_divergence_is_signal_not_falsehood()` — line 95
- FUNCTION `test_repeated_observations_do_not_count_as_independent_sources()` — line 110
- FUNCTION `test_integrity_recovery_reenables_non_blocked_reading()` — line 119
- FUNCTION `test_scars_add_caution_but_not_permanent_punishment()` — line 133
- FUNCTION `test_compass_reading_is_included_read_only()` — line 149
- FUNCTION `test_malformed_concept_rejected()` — line 157

### `tests/test_config.py`
- FUNCTION `test_load_config_defaults_when_missing()` — line 9
- FUNCTION `test_load_real_config_file()` — line 14
- FUNCTION `test_config_never_stores_raw_api_key()` — line 20

### `tests/test_conversation_loop.py`
- CLASS `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine` — line 66
- FUNCTION `_run_main()` — line 12
- FUNCTION `test_first_launch_reaches_lantern_ready()` — line 23
- FUNCTION `test_message_without_reasoning_engine_reports_not_configured_not_fabricated()` — line 30
- FUNCTION `test_status_command_available_from_conversation_loop()` — line 36
- FUNCTION `test_graceful_shutdown_via_exit_command()` — line 41
- FUNCTION `test_graceful_shutdown_via_eof()` — line 46
- FUNCTION `test_system_prompt_is_actually_sent_to_the_reasoning_engine()` — line 50
- FUNCTION `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.respond()` — line 69
- FUNCTION `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.describe()` — line 73
- FUNCTION `test_compile_command_produces_structured_prompt_not_fabricated()` — line 91
- FUNCTION `test_compile_command_with_no_request_shows_usage()` — line 98
- FUNCTION `test_compile_command_lightweight_for_ordinary_question()` — line 103
- FUNCTION `test_self_command_reports_seven_sections()` — line 107
- FUNCTION `test_branch_command_opens_a_real_branch()` — line 115
- FUNCTION `test_branch_command_without_double_colon_shows_usage()` — line 121
- FUNCTION `test_spine_command_with_no_entries_reports_zero()` — line 126
- FUNCTION `test_spine_command_never_authorizes_a_commit_from_the_repl()` — line 131
- FUNCTION `test_run_command_executes_the_full_operating_loop()` — line 137
- FUNCTION `test_run_command_with_no_intent_shows_usage()` — line 144
- FUNCTION `test_permissions_command_reports_zero_active_grants_by_default()` — line 150
- FUNCTION `test_grant_command_requires_explicit_granting_authority()` — line 158
- FUNCTION `test_grant_then_permissions_shows_the_new_grant()` — line 163
- FUNCTION `test_grant_rejects_unknown_capability_from_the_repl()` — line 174
- FUNCTION `test_revoke_command_removes_an_active_grant()` — line 179

### `tests/test_decision_state_machine.py`
- FUNCTION `_fresh_bridge()` — line 12
- FUNCTION `_add_evidence()` — line 22
- FUNCTION `test_high_maps_to_proceed()` — line 27
- FUNCTION `test_medium_maps_to_preserve_gather()` — line 37
- FUNCTION `test_low_maps_to_branch_investigate()` — line 47
- FUNCTION `test_blocked_maps_to_stop_repair()` — line 55
- FUNCTION `test_illegal_transition_rejected()` — line 66
- FUNCTION `test_blocked_to_high_allowed_only_after_explicit_recovery_event()` — line 78
- FUNCTION `test_authorization_boundary_explicitly_preserved()` — line 88
- FUNCTION `test_decision_explanation_contains_pipeline()` — line 98
- FUNCTION `test_prompt_compiler_compatibility_path()` — line 105
- FUNCTION `test_blocked_never_silently_becomes_low()` — line 114

### `tests/test_harness_status.py`
- FUNCTION `test_status_report_reflects_actual_bridge_state()` — line 12
- FUNCTION `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions()` — line 25
- FUNCTION `test_status_report_self_model_and_operating_loop_reported_as_implemented()` — line 38
- FUNCTION `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh()` — line 46
- FUNCTION `test_status_report_prompt_compiler_reported_as_implemented()` — line 57
- FUNCTION `test_format_status_report_produces_readable_text()` — line 64
- FUNCTION `test_status_report_mcp_server_status_reflects_real_sdk_availability()` — line 74
- FUNCTION `test_status_report_transfer_manifest_reported_as_implemented()` — line 86
- FUNCTION `test_status_report_permission_authority_reported_as_implemented()` — line 95

### `tests/test_mcp_server.py`
- FUNCTION `_fresh_context()` — line 16
- FUNCTION `_call()` — line 23
- FUNCTION `test_server_exposes_expected_tool_names()` — line 30
- FUNCTION `test_lantern_observe_records_a_real_observation()` — line 44
- FUNCTION `test_lantern_confidence_reflects_real_evidence_state()` — line 54
- FUNCTION `test_lantern_decide_never_reports_authorization()` — line 64
- FUNCTION `test_lantern_compile_never_fabricates_missing_fields()` — line 71
- FUNCTION `test_lantern_self_model_lists_authorized_tools_from_real_boundary()` — line 79
- FUNCTION `test_lantern_branch_open_creates_a_real_branch()` — line 87
- FUNCTION `test_lantern_spine_read_reflects_real_committed_entries()` — line 97
- FUNCTION `test_lantern_witness_integrity_reports_real_chronicle_status()` — line 110
- FUNCTION `test_server_exposes_no_tool_capable_of_external_action()` — line 117
- FUNCTION `test_build_server_raises_clear_error_when_sdk_unavailable()` — line 129
- FUNCTION `test_lantern_evaluate_intent_runs_the_real_operating_loop()` — line 139
- FUNCTION `test_lantern_evaluate_intent_has_no_tool_name_parameter()` — line 158
- FUNCTION `test_lantern_transfer_manifest_reports_real_state_and_no_secrets()` — line 172
- FUNCTION `test_lantern_permissions_reports_zero_grants_by_default()` — line 187
- FUNCTION `test_lantern_permissions_reflects_a_real_in_process_grant()` — line 198
- FUNCTION `test_server_exposes_no_grant_or_revoke_tool_over_mcp()` — line 214

### `tests/test_mcp_server_live_stdio.py`
- FUNCTION `_fresh_target()` — line 30
- FUNCTION `test_real_stdio_subprocess_lists_all_expected_tools()` — line 41
- FUNCTION `test_real_stdio_subprocess_records_a_real_observation()` — line 54
- FUNCTION `test_real_stdio_subprocess_never_authorizes_a_decision()` — line 72

### `tests/test_operating_loop.py`
- FUNCTION `_fresh_bridge()` — line 13
- FUNCTION `test_run_records_a_real_observation()` — line 23
- FUNCTION `test_run_without_tool_name_does_not_attempt_action()` — line 34
- FUNCTION `test_run_with_unauthorized_tool_never_reports_real_success()` — line 42
- FUNCTION `test_run_with_authorized_tool_produces_real_result()` — line 53
- FUNCTION `test_run_produces_confidence_and_decision_for_every_call()` — line 64
- FUNCTION `test_open_branch_creates_a_real_branch_linked_to_the_observation()` — line 73
- FUNCTION `test_open_branch_without_concept_is_skipped_not_fabricated()` — line 83
- FUNCTION `test_run_uses_perspective_differential_when_multiple_perspectives_given()` — line 92
- FUNCTION `test_integrity_failure_propagates_to_blocked_decision_end_to_end()` — line 105
- FUNCTION `test_empty_intent_rejected()` — line 118
- FUNCTION `test_format_produces_readable_summary()` — line 129

### `tests/test_permission_authority.py`
- FUNCTION `_passed()` — line 22
- FUNCTION `_failed()` — line 36
- FUNCTION `test_grant_requires_explicit_granting_authority()` — line 52
- FUNCTION `test_permission_authority_cannot_self_grant()` — line 64
- FUNCTION `test_grant_rejects_unknown_capability_category()` — line 82
- FUNCTION `test_grant_rejects_empty_scope()` — line 94
- FUNCTION `test_grant_and_active_grants_round_trip()` — line 106
- FUNCTION `test_revoke_requires_explicit_granting_authority()` — line 121
- FUNCTION `test_revoke_marks_grant_revoked_and_it_stops_matching()` — line 131
- FUNCTION `test_expired_grant_does_not_match_at_or_after_expiry_step()` — line 145
- FUNCTION `test_authorized_and_aligned_is_act()` — line 158
- FUNCTION `test_authorized_but_misaligned_is_stop_and_reassess()` — line 173
- FUNCTION `test_aligned_but_not_authorized_is_ask_operator()` — line 189
- FUNCTION `test_neither_authorized_nor_aligned_is_refuse()` — line 200
- FUNCTION `test_unknown_capability_is_flagged_as_new_capability_and_cannot_be_authorized()` — line 211
- FUNCTION `test_file_modification_grant_does_not_authorize_external_communication()` — line 225
- FUNCTION `test_release_publication_grant_does_not_authorize_wallet_or_payment_authority()` — line 240
- FUNCTION `test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service()` — line 254
- FUNCTION `test_never_inherits_categories_are_flagged_even_when_unauthorized()` — line 268
- FUNCTION `test_permission_authority_grants_do_not_persist_across_instances()` — line 283
- FUNCTION `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one()` — line 301
- FUNCTION `test_new_authority_request_format_matches_directive_example_shape()` — line 319
- FUNCTION `test_action_complete_format_is_informational_not_a_request()` — line 338
- FUNCTION `test_check_result_to_dict_answers_auditability_questions()` — line 358

### `tests/test_perspective_differential.py`
- FUNCTION `test_none_input_rejected()` — line 13
- FUNCTION `test_single_perspective_is_not_applicable_not_fabricated()` — line 20
- FUNCTION `test_empty_list_is_not_applicable()` — line 28
- FUNCTION `test_two_identical_perspectives_have_zero_variance()` — line 34
- FUNCTION `test_diverging_perspectives_identify_primary_divergence_dimension()` — line 44
- FUNCTION `test_does_not_select_a_winner()` — line 54
- FUNCTION `test_three_perspectives_variance_computed()` — line 67
- FUNCTION `test_to_dict_round_trips()` — line 79

### `tests/test_prompt_compiler.py`
- FUNCTION `_fresh_bridge()` — line 12
- FUNCTION `test_rejects_empty_request()` — line 20
- FUNCTION `test_lightweight_mode_for_ordinary_request()` — line 29
- FUNCTION `test_heavyweight_mode_triggered_by_consequential_keyword()` — line 37
- FUNCTION `test_consequential_override_forces_heavyweight()` — line 45
- FUNCTION `test_consequential_override_forces_lightweight()` — line 51
- FUNCTION `test_missing_information_marked_not_provided_not_fabricated()` — line 57
- FUNCTION `test_prove_x_pattern_is_reframed_not_assumed()` — line 69
- FUNCTION `test_no_concept_supplied_means_evidence_fields_not_provided_not_fabricated()` — line 79
- FUNCTION `test_concept_with_no_recorded_evidence_is_unknown_not_fabricated()` — line 86
- FUNCTION `test_real_evidence_and_contradiction_are_surfaced_when_present()` — line 94
- FUNCTION `test_contradiction_detection_surfaces_when_kernel_actually_detects_one()` — line 113
- FUNCTION `test_secrets_never_enter_compiled_prompt()` — line 134
- FUNCTION `test_malformed_input_types_rejected_not_silently_coerced()` — line 145
- FUNCTION `test_epistemic_status_field_present_and_labels_output_as_observation()` — line 152
- FUNCTION `test_lightweight_still_surfaces_real_evidence_if_present()` — line 160
- FUNCTION `test_compiled_prompt_to_dict_round_trips()` — line 172
- FUNCTION `test_blocked_when_chronicle_integrity_check_fails()` — line 179

### `tests/test_reality_boundary.py`
- FUNCTION `_fresh_bridge()` — line 14
- FUNCTION `_decision()` — line 24
- FUNCTION `test_propose_never_touches_external_world()` — line 29
- FUNCTION `test_propose_requires_non_empty_intent()` — line 39
- FUNCTION `test_act_denied_when_tool_not_authorized()` — line 50
- FUNCTION `test_act_real_success_only_after_explicit_authorization()` — line 63
- FUNCTION `test_act_with_no_tool_name_is_not_executed()` — line 78
- FUNCTION `test_simulate_can_never_report_success()` — line 90
- FUNCTION `test_simulate_requires_reason()` — line 103
- FUNCTION `test_tool_error_is_never_reported_as_success()` — line 115
- FUNCTION `test_tool_error_is_never_reported_as_success.boom()` — line 118

### `tests/test_reasoning.py`
- CLASS `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse` — line 60
- FUNCTION `test_build_engine_returns_none_when_no_provider()` — line 13
- FUNCTION `test_build_engine_returns_none_for_unknown_provider()` — line 18
- FUNCTION `test_build_engine_returns_ollama_instance()` — line 22
- FUNCTION `test_ollama_detect_reports_absence_honestly()` — line 28
- FUNCTION `test_openai_detect_reports_missing_key()` — line 35
- FUNCTION `test_anthropic_detect_never_exposes_key_value()` — line 43
- FUNCTION `test_google_engine_forwards_system_message_as_system_instruction()` — line 50
- FUNCTION `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse.__enter__()` — line 61
- FUNCTION `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse.__exit__()` — line 64
- FUNCTION `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse.read()` — line 67
- FUNCTION `test_google_engine_forwards_system_message_as_system_instruction.fake_urlopen()` — line 70

### `tests/test_self_model.py`
- FUNCTION `_fresh_bridge()` — line 12
- FUNCTION `test_describe_returns_all_seven_sections()` — line 22
- FUNCTION `test_authorized_tools_reflect_real_tool_boundary_state()` — line 35
- FUNCTION `test_self_model_is_read_only()` — line 47
- FUNCTION `test_self_model_cannot_self_authorize()` — line 63
- FUNCTION `test_operator_boundaries_always_listed()` — line 74
- FUNCTION `test_format_produces_readable_text_with_all_headers()` — line 84

### `tests/test_spine.py`
- FUNCTION `_fresh_bridge()` — line 11
- FUNCTION `_add_evidence()` — line 21
- FUNCTION `test_open_branch_requires_concept_and_hypothesis()` — line 27
- FUNCTION `test_branch_cannot_commit_itself_without_explicit_authorization()` — line 39
- FUNCTION `test_commit_succeeds_with_explicit_authorization_and_no_contradictions()` — line 50
- FUNCTION `test_commit_refused_on_open_contradiction_unless_acknowledged()` — line 66
- FUNCTION `test_commit_refused_when_integrity_fails()` — line 89
- FUNCTION `test_committed_branch_cannot_be_recommitted_or_abandoned()` — line 103
- FUNCTION `test_read_spine_reconstructs_from_real_chronicle_replay()` — line 122
- FUNCTION `test_abandoned_branch_becomes_a_real_scar_not_discarded()` — line 137
- FUNCTION `test_child_branch_requires_known_parent()` — line 151
- FUNCTION `test_confidence_score_alone_never_authorizes_commit()` — line 163

### `tests/test_tool_boundary.py`
- FUNCTION `test_discovery_does_not_imply_authorization()` — line 9
- FUNCTION `test_authorized_tool_executes()` — line 20
- FUNCTION `test_unregistered_tool_execution_errors()` — line 30
- FUNCTION `test_handler_exception_becomes_error_result_not_crash()` — line 36
- FUNCTION `test_handler_exception_becomes_error_result_not_crash.bad_handler()` — line 39
- FUNCTION `test_authorize_unknown_tool_returns_false()` — line 50

### `tests/test_transfer_manifest.py`
- FUNCTION `_fresh_bridge()` — line 11
- FUNCTION `test_manifest_reports_real_identity_not_a_placeholder()` — line 19
- FUNCTION `test_manifest_never_contains_a_private_key_or_signing_material()` — line 28
- FUNCTION `test_manifest_state_summary_reflects_real_observations()` — line 37
- FUNCTION `test_manifest_reports_real_witness_integrity_not_assumed_valid()` — line 46
- FUNCTION `test_manifest_lists_reauthorization_required_items()` — line 53
- FUNCTION `test_manifest_does_not_transfer_reasoning_engine_api_key_value()` — line 62
- FUNCTION `test_manifest_reuses_self_model_capability_and_gap_lists()` — line 79
- FUNCTION `test_manifest_records_real_provenance_commit_hashes()` — line 91
- FUNCTION `test_manifest_protocol_version_matches_lantern_protocol_module()` — line 100
- FUNCTION `test_manifest_is_read_only_no_state_mutation()` — line 108
- FUNCTION `test_manifest_to_dict_and_format_round_trip_without_error()` — line 117
- FUNCTION `test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model()` — line 127



## 5. IMPORT GRAPH

### `examples/demo_operating_loop.py`
- `from __future__ import annotations`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.operating_loop import OperatingLoop`
- `from lantern_harness.self_model import SelfModel`
- `from lantern_harness.spine import BranchStore, SpineCommitter`
- `from lantern_harness.tools.boundary import ToolBoundary`
- `from pathlib import Path`
- `import sys`
- `import tempfile`

### `export_for_miles.py`
- `from __future__ import annotations`
- `from collections import defaultdict`
- `from datetime import datetime, timezone`
- `from pathlib import Path`
- `import ast`
- `import re`

### `lantern_harness/bootstrap.py`
- `from .bridge import LanternBridge`
- `from .config import load_config`
- `from .harness_status import lantern_version`
- `from .reasoning import build_engine`
- `from __future__ import annotations`
- `from pathlib import Path`
- `import lantern`
- `import sys`

### `lantern_harness/bridge.py`
- `from __future__ import annotations`
- `from lantern.agent import LanternAgent`
- `from lantern.core import Lantern`
- `from lantern.identity import NodeIdentity, default_identity_dir, load_or_create`
- `from pathlib import Path`
- `from typing import Any, Optional`

### `lantern_harness/confidence_field.py`
- `from .bridge import LanternBridge`
- `from .perspective_differential import Perspective, PerspectiveDifferentialEngine`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from lantern import compass`
- `from typing import Any, Optional, Sequence`

### `lantern_harness/config.py`
- `from __future__ import annotations`
- `from pathlib import Path`
- `import json`

### `lantern_harness/decision_state_machine.py`
- `from .confidence_field import ConfidenceFieldReading`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Optional`

### `lantern_harness/harness_status.py`
- `from .bridge import LanternBridge`
- `from .reasoning.base import ReasoningEngine`
- `from __future__ import annotations`
- `import importlib.metadata`
- `import lantern`
- `import mcp`

### `lantern_harness/mcp_server.py`
- `from .bridge import LanternBridge`
- `from .confidence_field import ConfidenceField`
- `from .decision_state_machine import DecisionStateMachine`
- `from .operating_loop import OperatingLoop`
- `from .permission_authority import PermissionAuthority`
- `from .prompt_compiler import PromptCompiler`
- `from .self_model import SelfModel`
- `from .spine import BranchStore, SpineCommitter`
- `from .tools.boundary import ToolBoundary`
- `from .transfer_manifest import build_manifest`
- `from __future__ import annotations`
- `from mcp.server.mcpserver import MCPServer`
- `from pathlib import Path`
- `from typing import Optional`
- `import os`

### `lantern_harness/operating_loop.py`
- `from .bridge import LanternBridge`
- `from .confidence_field import ConfidenceField, ConfidenceFieldReading`
- `from .decision_state_machine import DecisionStateMachine, DecisionReading`
- `from .perspective_differential import Perspective`
- `from .prompt_compiler import CompiledPrompt, PromptCompiler`
- `from .reality_boundary import ActionRecord, RealityBoundary`
- `from .spine import Branch, BranchStore`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Optional, Sequence`

### `lantern_harness/permission_authority.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Optional`

### `lantern_harness/perspective_differential.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from statistics import pvariance`
- `from typing import Optional`

### `lantern_harness/prompt_compiler.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Optional`
- `import re`

### `lantern_harness/reality_boundary.py`
- `from .decision_state_machine import DecisionReading`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Optional`

### `lantern_harness/reasoning/__init__.py`
- `from .api_provider import AnthropicEngine, GoogleEngine, OpenAIEngine`
- `from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse`
- `from .ollama_provider import OllamaEngine`
- `from __future__ import annotations`
- `from typing import Optional`

### `lantern_harness/reasoning/api_provider.py`
- `from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse`
- `from __future__ import annotations`
- `from typing import Optional`
- `import json`
- `import os`
- `import urllib.error`
- `import urllib.request`

### `lantern_harness/reasoning/base.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass`
- `from typing import Any, Optional`

### `lantern_harness/reasoning/ollama_provider.py`
- `from .base import ReasoningEngine, ReasoningEngineUnavailable, ReasoningResponse`
- `from __future__ import annotations`
- `from typing import Optional`
- `import json`
- `import urllib.error`
- `import urllib.request`

### `lantern_harness/self_model.py`
- `from .bridge import LanternBridge`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Optional`

### `lantern_harness/spine.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from lantern.core import KernelEvent`
- `from typing import Any, Optional`
- `import uuid`

### `lantern_harness/tools/boundary.py`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from typing import Any, Callable, Optional`

### `lantern_harness/transfer_manifest.py`
- `from .bridge import LanternBridge`
- `from .harness_status import HARNESS_VERSION, lantern_version`
- `from .self_model import KNOWN_CAPABILITIES, KNOWN_GAPS, STANDING_OPERATOR_BOUNDARIES`
- `from __future__ import annotations`
- `from dataclasses import dataclass, field`
- `from lantern.protocol import PROTOCOL_VERSION`
- `from pathlib import Path`
- `from typing import Any, Optional`
- `import importlib.metadata`
- `import lantern`
- `import platform`
- `import subprocess`

### `main.py`
- `from __future__ import annotations`
- `from lantern_harness.bootstrap import bootstrap, format_bootstrap_report`
- `from lantern_harness.confidence_field import ConfidenceField`
- `from lantern_harness.decision_state_machine import DecisionStateMachine`
- `from lantern_harness.harness_status import format_status_report, status_report`
- `from lantern_harness.operating_loop import OperatingLoop`
- `from lantern_harness.permission_authority import PermissionAuthority, CAPABILITY_CATEGORIES`
- `from lantern_harness.prompt_compiler import PromptCompiler`
- `from lantern_harness.reasoning.base import ReasoningEngineUnavailable`
- `from lantern_harness.self_model import SelfModel`
- `from lantern_harness.spine import BranchStore, SpineCommitter`
- `from lantern_harness.tools.boundary import ToolBoundary`
- `from lantern_harness.transfer_manifest import build_manifest`
- `from pathlib import Path`
- `import sys`

### `tests/test_bootstrap.py`
- `from lantern_harness.bootstrap import bootstrap, check_python, ensure_directories`
- `from pathlib import Path`
- `import lantern_harness.bootstrap`
- `import sys`

### `tests/test_bridge.py`
- `from lantern_harness.bridge import LanternBridge`
- `from pathlib import Path`
- `import sys`
- `import tempfile`

### `tests/test_confidence_field.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.confidence_field import ConfidenceField, HIGH_THRESHOLD, MEDIUM_THRESHOLD`
- `from lantern_harness.perspective_differential import Perspective`
- `from pathlib import Path`
- `import shutil`

### `tests/test_config.py`
- `from lantern_harness.config import load_config`
- `from pathlib import Path`
- `import sys`

### `tests/test_conversation_loop.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.operating_loop import OperatingLoop`
- `from lantern_harness.permission_authority import PermissionAuthority`
- `from lantern_harness.reasoning.base import ReasoningResponse`
- `from lantern_harness.spine import BranchStore`
- `from lantern_harness.tools.boundary import ToolBoundary`
- `from pathlib import Path`
- `import io`
- `import main`
- `import subprocess`
- `import sys`
- `import tempfile`

### `tests/test_decision_state_machine.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.confidence_field import ConfidenceField`
- `from lantern_harness.decision_state_machine import DecisionStateMachine`
- `from lantern_harness.prompt_compiler import PromptCompiler`
- `from pathlib import Path`
- `import shutil`

### `tests/test_harness_status.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.harness_status import format_status_report, status_report`
- `from lantern_harness.tools.boundary import ToolBoundary`
- `from pathlib import Path`
- `import mcp`
- `import sys`
- `import tempfile`

### `tests/test_mcp_server.py`
- `from lantern_harness.mcp_server import LanternMCPContext, build_server`
- `from pathlib import Path`
- `import asyncio`
- `import json`
- `import lantern_harness.mcp_server`
- `import pytest`
- `import shutil`

### `tests/test_mcp_server_live_stdio.py`
- `from lantern.mcp_client import MCP_SDK_AVAILABLE, StdioMCPClient, StdioServerTarget`
- `from lantern.mcp_integration import MCPExecutionRequest`
- `from pathlib import Path`
- `import json`
- `import pytest`
- `import shutil`
- `import sys`
- `import tempfile`

### `tests/test_operating_loop.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.operating_loop import OperatingLoop`
- `from lantern_harness.perspective_differential import Perspective`
- `from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor`
- `from pathlib import Path`
- `import shutil`

### `tests/test_permission_authority.py`
- `from lantern_harness.permission_authority import PermissionAuthority, AlignmentResult, CAPABILITY_CATEGORIES, NEVER_INHERITS, RESULT_ACT, RESULT_STOP_AND_REASSESS, RESULT_ASK_OPERATOR, RESULT_REFUSE, GRANT_STATUS_ACTIVE, GRANT_STATUS_REVOKED`
- `from pathlib import Path`
- `import pytest`
- `import sys`

### `tests/test_perspective_differential.py`
- `from lantern_harness.perspective_differential import DifferentialReading, Perspective, PerspectiveDifferentialEngine`
- `from pathlib import Path`
- `import pytest`
- `import sys`

### `tests/test_prompt_compiler.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.prompt_compiler import CompiledPrompt, FieldStatus, PromptCompiler`
- `from pathlib import Path`
- `import os`
- `import pytest`
- `import sys`
- `import tempfile`

### `tests/test_reality_boundary.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.confidence_field import ConfidenceField`
- `from lantern_harness.decision_state_machine import DecisionStateMachine`
- `from lantern_harness.reality_boundary import RealityBoundary, EXECUTION_MODE_REAL, EXECUTION_MODE_SIMULATED`
- `from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor`
- `from pathlib import Path`
- `import shutil`

### `tests/test_reasoning.py`
- `from lantern_harness.reasoning import build_engine`
- `from lantern_harness.reasoning.api_provider import AnthropicEngine, GoogleEngine, OpenAIEngine`
- `from lantern_harness.reasoning.ollama_provider import OllamaEngine`
- `from pathlib import Path`
- `import json`
- `import lantern_harness.reasoning.api_provider`
- `import os`
- `import sys`

### `tests/test_self_model.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.self_model import SelfModel`
- `from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor`
- `from pathlib import Path`
- `import shutil`

### `tests/test_spine.py`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.confidence_field import ConfidenceField`
- `from lantern_harness.spine import BranchStore, SpineCommitter, branch_to_scar`
- `from pathlib import Path`
- `import shutil`

### `tests/test_tool_boundary.py`
- `from lantern_harness.tools.boundary import ToolBoundary, ToolDescriptor`
- `from pathlib import Path`
- `import sys`

### `tests/test_transfer_manifest.py`
- `from lantern.protocol import PROTOCOL_VERSION`
- `from lantern_harness.bridge import LanternBridge`
- `from lantern_harness.self_model import KNOWN_CAPABILITIES, KNOWN_GAPS`
- `from lantern_harness.transfer_manifest import build_manifest, TransferManifest`
- `from pathlib import Path`
- `import os`
- `import sys`
- `import tempfile`



## 6. STATIC CALL GRAPH

### `examples/demo_operating_loop.py`
- line 27: `<module>` → `sys.path.insert`
- line 27: `<module>` → `str`
- line 27: `<module>` → `Path(__file__).resolve`
- line 27: `<module>` → `Path`
- line 37: `main` → `Path`
- line 37: `main` → `tempfile.mkdtemp`
- line 38: `main` → `print`
- line 40: `main` → `LanternBridge`
- line 41: `main` → `bridge.ensure_identity`
- line 42: `main` → `print`
- line 43: `main` → `bridge.startup`
- line 45: `main` → `ToolBoundary`
- line 46: `main` → `OperatingLoop`
- line 48: `main` → `print`
- line 49: `main` → `loop.run`
- line 50: `main` → `print`
- line 50: `main` → `result.format`
- line 51: `main` → `print`
- line 53: `main` → `print`
- line 54: `main` → `bridge.observe`
- line 55: `main` → `bridge.add_evidence`
- line 56: `main` → `bridge.observe`
- line 57: `main` → `bridge.add_evidence`
- line 59: `main` → `loop.run`
- line 60: `main` → `print`
- line 60: `main` → `result2.format`
- line 61: `main` → `print`
- line 63: `main` → `print`
- line 64: `main` → `loop.run`
- line 65: `main` → `print`
- line 65: `main` → `result3.format`
- line 66: `main` → `print`
- line 68: `main` → `print`
- line 69: `main` → `SpineCommitter`
- line 70: `main` → `committer.commit`
- line 74: `main` → `print`
- line 76: `main` → `committer.commit`
- line 80: `main` → `print`
- line 82: `main` → `print`
- line 84: `main` → `print`
- line 85: `main` → `SelfModel`
- line 86: `main` → `print`
- line 86: `main` → `self_model.describe().format`
- line 86: `main` → `self_model.describe`
- line 90: `<module>` → `main`

### `export_for_miles.py`
- line 40: `<module>` → `Path(__file__).resolve`
- line 40: `<module>` → `Path`
- line 75: `<module>` → `re.compile`
- line 78: `<module>` → `re.compile`
- line 81: `<module>` → `re.compile`
- line 84: `<module>` → `re.compile`
- line 87: `<module>` → `re.compile`
- line 90: `<module>` → `re.compile`
- line 95: `<module>` → `re.compile`
- line 96: `<module>` → `re.compile`
- line 97: `<module>` → `re.compile`
- line 102: `redact` → `pattern.sub`
- line 103: `redact` → `match.group`
- line 107: `redact` → `pattern.sub`
- line 113: `should_skip` → `any`
- line 115: `relative` → `str`
- line 115: `relative` → `path.relative_to`
- line 118: `read_text` → `path.stat`
- line 120: `read_text` → `path.read_text`
- line 124: `all_files` → `sorted`
- line 124: `all_files` → `ROOT.rglob`
- line 125: `all_files` → `should_skip`
- line 127: `all_files` → `path.is_file`
- line 130: `python_files` → `all_files`
- line 148: `PythonAnalysis.__init__` → `self.parse`
- line 150: `PythonAnalysis.parse` → `read_text`
- line 155: `PythonAnalysis.parse` → `ast.parse`
- line 157: `PythonAnalysis.parse` → `str`
- line 160: `PythonAnalysis.parse` → `self.markers.append`
- line 164: `PythonAnalysis.parse` → `ASTVisitor`
- line 166: `PythonAnalysis.parse` → `visitor.visit`
- line 168: `PythonAnalysis.parse` → `self.markers.append`
- line 169: `PythonAnalysis.parse` → `type`
- line 180: `ASTVisitor.visit_Import` → `self.analysis.imports.append`
- line 183: `ASTVisitor.visit_Import` → `self.generic_visit`
- line 186: `ASTVisitor.visit_ImportFrom` → `', '.join`
- line 191: `ASTVisitor.visit_ImportFrom` → `self.analysis.imports.append`
- line 194: `ASTVisitor.visit_ImportFrom` → `self.generic_visit`
- line 199: `ASTVisitor.visit_FunctionDef` → `'.'.join`
- line 202: `ASTVisitor.visit_FunctionDef` → `self.analysis.functions.append`
- line 219: `ASTVisitor.visit_FunctionDef` → `self.analysis.entrypoints.append`
- line 222: `ASTVisitor.visit_FunctionDef` → `self.current_scope.append`
- line 223: `ASTVisitor.visit_FunctionDef` → `self.generic_visit`
- line 224: `ASTVisitor.visit_FunctionDef` → `self.current_scope.pop`
- line 226: `ASTVisitor.visit_AsyncFunctionDef` → `'.'.join`
- line 229: `ASTVisitor.visit_AsyncFunctionDef` → `self.analysis.functions.append`
- line 236: `ASTVisitor.visit_AsyncFunctionDef` → `self.current_scope.append`
- line 237: `ASTVisitor.visit_AsyncFunctionDef` → `self.generic_visit`
- line 238: `ASTVisitor.visit_AsyncFunctionDef` → `self.current_scope.pop`
- line 243: `ASTVisitor.visit_ClassDef` → `'.'.join`
- line 249: `ASTVisitor.visit_ClassDef` → `bases.append`
- line 249: `ASTVisitor.visit_ClassDef` → `ast.unparse`
- line 251: `ASTVisitor.visit_ClassDef` → `bases.append`
- line 252: `ASTVisitor.visit_ClassDef` → `self.analysis.classes.append`
- line 259: `ASTVisitor.visit_ClassDef` → `self.current_scope.append`
- line 260: `ASTVisitor.visit_ClassDef` → `self.generic_visit`
- line 261: `ASTVisitor.visit_ClassDef` → `self.current_scope.pop`
- line 267: `ASTVisitor.visit_Call` → `ast.unparse`
- line 271: `ASTVisitor.visit_Call` → `'.'.join`
- line 275: `ASTVisitor.visit_Call` → `self.analysis.calls.append`
- line 296: `ASTVisitor.visit_Call` → `self.analysis.security_calls.append`
- line 299: `ASTVisitor.visit_Call` → `self.generic_visit`
- line 304: `ASTVisitor.visit_Constant` → `isinstance`
- line 316: `ASTVisitor.visit_Constant` → `marker.lower`
- line 316: `ASTVisitor.visit_Constant` → `value.lower`
- line 317: `ASTVisitor.visit_Constant` → `self.analysis.markers.append`
- line 320: `ASTVisitor.visit_Constant` → `self.generic_visit`
- line 323: `analyze_repository` → `python_files`
- line 324: `analyze_repository` → `analyses.append`
- line 325: `analyze_repository` → `PythonAnalysis`
- line 333: `repository_map` → `all_files`
- line 334: `repository_map` → `path.suffix.lower`
- line 336: `repository_map` → `lines.append`
- line 336: `repository_map` → `relative`
- line 337: `repository_map` → `'\n'.join`
- line 358: `configuration_report` → `path.exists`
- line 360: `configuration_report` → `read_text`
- line 363: `configuration_report` → `output.append`
- line 366: `configuration_report` → `redact`
- line 371: `configuration_report` → `'\n'.join`
- line 396: `language_for` → `{'.py': 'python', '.toml': 'toml', '.json': 'json', '.md': 'markdown', '.yaml': 'yaml', '.yml': 'yaml', '.sh': 'bash'}.get`
- line 404: `language_for` → `path.suffix.lower`
- line 407: `source_block` → `path.exists`
- line 412: `source_block` → `read_text`
- line 418: `source_block` → `redact`
- line 421: `source_block` → `language_for`
- line 433: `call_graph` → `output.append`
- line 434: `call_graph` → `relative`
- line 437: `call_graph` → `output.append`
- line 441: `call_graph` → `output.append`
- line 442: `call_graph` → `'\n'.join`
- line 451: `symbol_report` → `output.append`
- line 452: `symbol_report` → `relative`
- line 459: `symbol_report` → `', '.join`
- line 461: `symbol_report` → `output.append`
- line 472: `symbol_report` → `output.append`
- line 476: `symbol_report` → `output.append`
- line 477: `symbol_report` → `'\n'.join`
- line 486: `import_report` → `output.append`
- line 487: `import_report` → `relative`
- line 489: `import_report` → `sorted`
- line 489: `import_report` → `set`
- line 490: `import_report` → `output.append`
- line 491: `import_report` → `output.append`
- line 492: `import_report` → `'\n'.join`
- line 500: `entrypoint_report` → `output.append`
- line 501: `entrypoint_report` → `relative`
- line 505: `entrypoint_report` → `'\n'.join`
- line 514: `security_report` → `output.append`
- line 515: `security_report` → `relative`
- line 518: `security_report` → `output.append`
- line 521: `security_report` → `output.append`
- line 526: `security_report` → `'\n'.join`
- line 535: `marker_report` → `output.append`
- line 536: `marker_report` → `relative`
- line 539: `marker_report` → `output.append`
- line 540: `marker_report` → `redact`
- line 542: `marker_report` → `output.append`
- line 543: `marker_report` → `'\n'.join`
- line 549: `test_report` → `tests_dir.exists`
- line 552: `test_report` → `sorted`
- line 553: `test_report` → `tests_dir.rglob`
- line 555: `test_report` → `tests.append`
- line 556: `test_report` → `relative`
- line 560: `test_report` → `'\n'.join`
- line 605: `execution_model` → `relative`
- line 615: `execution_model` → `output.append`
- line 619: `execution_model` → `output.append`
- line 624: `execution_model` → `output.append`
- line 629: `execution_model` → `output.append`
- line 634: `execution_model` → `output.append`
- line 639: `execution_model` → `output.append`
- line 643: `execution_model` → `'\n'.join`
- line 648: `build_report` → `analyze_repository`
- line 649: `build_report` → `datetime.now(timezone.utc).isoformat`
- line 649: `build_report` → `datetime.now`
- line 653: `build_report` → `parts.append`
- line 660: `build_report` → `parts.append`
- line 663: `build_report` → `repository_map`
- line 666: `build_report` → `parts.append`
- line 668: `build_report` → `execution_model`
- line 671: `build_report` → `parts.append`
- line 673: `build_report` → `entrypoint_report`
- line 676: `build_report` → `parts.append`
- line 678: `build_report` → `symbol_report`
- line 681: `build_report` → `parts.append`
- line 683: `build_report` → `import_report`
- line 686: `build_report` → `parts.append`
- line 688: `build_report` → `call_graph`
- line 691: `build_report` → `parts.append`
- line 693: `build_report` → `security_report`
- line 696: `build_report` → `parts.append`
- line 698: `build_report` → `configuration_report`
- line 701: `build_report` → `parts.append`
- line 703: `build_report` → `test_report`
- line 706: `build_report` → `parts.append`
- line 708: `build_report` → `marker_report`
- line 711: `build_report` → `parts.append`
- line 713: `build_report` → `'\n'.join`
- line 714: `build_report` → `source_block`
- line 718: `build_report` → `parts.append`
- line 720: `build_report` → `verification_questions`
- line 722: `build_report` → `parts.append`
- line 805: `build_report` → `'\n'.join`
- line 810: `main` → `build_report`
- line 811: `main` → `OUT.write_text`
- line 815: `main` → `print`
- line 816: `main` → `print`
- line 817: `main` → `print`
- line 818: `main` → `print`
- line 819: `main` → `print`
- line 820: `main` → `print`
- line 821: `main` → `print`
- line 822: `main` → `print`
- line 822: `main` → `len`
- line 823: `main` → `print`
- line 824: `main` → `print`
- line 825: `main` → `print`
- line 826: `main` → `print`
- line 827: `main` → `print`
- line 828: `main` → `print`
- line 829: `main` → `print`
- line 830: `main` → `print`
- line 832: `<module>` → `main`

### `lantern_harness/bootstrap.py`
- line 14: `<module>` → `Path(__file__).resolve`
- line 14: `<module>` → `Path`
- line 36: `ensure_directories` → `d.exists`
- line 37: `ensure_directories` → `d.mkdir`
- line 38: `ensure_directories` → `created.append`
- line 45: `bootstrap` → `check_python`
- line 48: `bootstrap` → `check_lantern_importable`
- line 51: `bootstrap` → `ensure_directories`
- line 54: `bootstrap` → `load_config`
- line 62: `bootstrap` → `config.get`
- line 63: `bootstrap` → `LanternBridge`
- line 63: `bootstrap` → `config.get`
- line 65: `bootstrap` → `bridge.ensure_identity`
- line 66: `bootstrap` → `identity_result.get`
- line 68: `bootstrap` → `bridge.startup`
- line 69: `bootstrap` → `startup_result.get`
- line 71: `bootstrap` → `build_engine`
- line 71: `bootstrap` → `config.get`
- line 73: `bootstrap` → `engine.detect`
- line 95: `format_bootstrap_report` → `checks.get`
- line 97: `format_bootstrap_report` → `lines.append`
- line 99: `format_bootstrap_report` → `lines.append`
- line 100: `format_bootstrap_report` → `result.get`
- line 101: `format_bootstrap_report` → `result.get`
- line 104: `format_bootstrap_report` → `lines.append`
- line 104: `format_bootstrap_report` → `lantern_version`
- line 106: `format_bootstrap_report` → `engine.detect`
- line 107: `format_bootstrap_report` → `lines.append`
- line 109: `format_bootstrap_report` → `lines.append`
- line 110: `format_bootstrap_report` → `lines.append`
- line 110: `format_bootstrap_report` → `checks['identity']['detail'].get`
- line 111: `format_bootstrap_report` → `lines.append`
- line 111: `format_bootstrap_report` → `checks['memory']['detail'].get`
- line 112: `format_bootstrap_report` → `lines.append`
- line 113: `format_bootstrap_report` → `lines.append`
- line 115: `format_bootstrap_report` → `lines.append`
- line 117: `format_bootstrap_report` → `lines.append`
- line 118: `format_bootstrap_report` → `'\n'.join`

### `lantern_harness/bridge.py`
- line 32: `LanternBridge.__init__` → `Path`
- line 33: `LanternBridge.__init__` → `self.data_dir.mkdir`
- line 37: `LanternBridge.__init__` → `Lantern`
- line 37: `LanternBridge.__init__` → `str`
- line 38: `LanternBridge.__init__` → `LanternAgent`
- line 49: `LanternBridge.ensure_identity` → `default_identity_dir`
- line 50: `LanternBridge.ensure_identity` → `load_or_create`
- line 54: `LanternBridge.ensure_identity` → `self._identity.verify_key_hex`
- line 57: `LanternBridge.ensure_identity` → `str`
- line 58: `LanternBridge.ensure_identity` → `str`
- line 65: `LanternBridge.identity_status` → `self._identity.verify_key_hex`
- line 76: `LanternBridge.startup` → `self.agent.startup`
- line 81: `LanternBridge.observe` → `self.agent.observe`
- line 88: `LanternBridge.add_evidence` → `self.agent.add_evidence`
- line 91: `LanternBridge.resolve` → `self.agent.resolve`
- line 94: `LanternBridge.belief` → `self.agent.ask_belief`
- line 97: `LanternBridge.latest_contradiction` → `self.lantern.kernel.latest_contradiction`
- line 102: `LanternBridge.save_snapshot` → `self.lantern.save_snapshot`
- line 106: `LanternBridge.status` → `self.agent.status`
- line 111: `LanternBridge.create_scar` → `self.lantern.create_scar`
- line 114: `LanternBridge.persist_scar` → `self.lantern.persist_scar`
- line 121: `LanternBridge.branches` → `NotImplementedError`
- line 135: `LanternBridge.witness_integrity` → `chronicle.verify`
- line 138: `LanternBridge.witness_integrity` → `str`

### `lantern_harness/confidence_field.py`
- line 38: `ConfidenceFieldReading` → `field`
- line 39: `ConfidenceFieldReading` → `field`
- line 40: `ConfidenceFieldReading` → `field`
- line 41: `ConfidenceFieldReading` → `field`
- line 42: `ConfidenceFieldReading` → `field`
- line 45: `ConfidenceFieldReading` → `field`
- line 60: `ConfidenceFieldReading.to_dict` → `list`
- line 61: `ConfidenceFieldReading.to_dict` → `list`
- line 62: `ConfidenceFieldReading.to_dict` → `list`
- line 63: `ConfidenceFieldReading.to_dict` → `list`
- line 64: `ConfidenceFieldReading.to_dict` → `dict`
- line 67: `ConfidenceFieldReading.to_dict` → `list`
- line 26: `ConfidenceFieldReading` → `dataclass`
- line 96: `ConfidenceField.__init__` → `PerspectiveDifferentialEngine`
- line 108: `ConfidenceField.evaluate` → `isinstance`
- line 109: `ConfidenceField.evaluate` → `ValueError`
- line 117: `ConfidenceField.evaluate` → `self.bridge.witness_integrity`
- line 118: `ConfidenceField.evaluate` → `integrity.get`
- line 121: `ConfidenceField.evaluate` → `ConfidenceFieldReading`
- line 167: `ConfidenceField.evaluate` → `sum`
- line 168: `ConfidenceField.evaluate` → `e.decayed_weight`
- line 172: `ConfidenceField.evaluate` → `sum`
- line 173: `ConfidenceField.evaluate` → `e.decayed_weight`
- line 178: `ConfidenceField.evaluate` → `min`
- line 178: `ConfidenceField.evaluate` → `max`
- line 180: `ConfidenceField.evaluate` → `min`
- line 182: `ConfidenceField.evaluate` → `sum`
- line 182: `ConfidenceField.evaluate` → `max`
- line 186: `ConfidenceField.evaluate` → `sum`
- line 186: `ConfidenceField.evaluate` → `len`
- line 188: `ConfidenceField.evaluate` → `min`
- line 188: `ConfidenceField.evaluate` → `len`
- line 192: `ConfidenceField.evaluate` → `min`
- line 194: `ConfidenceField.evaluate` → `max`
- line 196: `ConfidenceField.evaluate` → `min`
- line 203: `ConfidenceField.evaluate` → `min`
- line 203: `ConfidenceField.evaluate` → `len`
- line 206: `ConfidenceField.evaluate` → `len`
- line 207: `ConfidenceField.evaluate` → `self.perspective_engine.compare`
- line 207: `ConfidenceField.evaluate` → `list`
- line 208: `ConfidenceField.evaluate` → `min`
- line 210: `ConfidenceField.evaluate` → `max`
- line 218: `ConfidenceField.evaluate` → `len`
- line 225: `ConfidenceField.evaluate` → `len`
- line 233: `ConfidenceField.evaluate` → `getattr`
- line 233: `ConfidenceField.evaluate` → `getattr`
- line 234: `ConfidenceField.evaluate` → `getattr`
- line 234: `ConfidenceField.evaluate` → `getattr`
- line 236: `ConfidenceField.evaluate` → `min`
- line 238: `ConfidenceField.evaluate` → `scar_reasons.append`
- line 240: `ConfidenceField.evaluate` → `scar_reasons.append`
- line 241: `ConfidenceField.evaluate` → `min`
- line 248: `ConfidenceField.evaluate` → `max`
- line 250: `ConfidenceField.evaluate` → `min`
- line 263: `ConfidenceField.evaluate` → `max`
- line 269: `ConfidenceField.evaluate` → `len`
- line 285: `ConfidenceField.evaluate` → `reasons.append`
- line 286: `ConfidenceField.evaluate` → `len`
- line 289: `ConfidenceField.evaluate` → `reasons.append`
- line 290: `ConfidenceField.evaluate` → `missing_information.append`
- line 291: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 294: `ConfidenceField.evaluate` → `reasons.append`
- line 295: `ConfidenceField.evaluate` → `len`
- line 295: `ConfidenceField.evaluate` → `len`
- line 297: `ConfidenceField.evaluate` → `len`
- line 298: `ConfidenceField.evaluate` → `missing_information.append`
- line 299: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 301: `ConfidenceField.evaluate` → `missing_information.append`
- line 302: `ConfidenceField.evaluate` → `blockers.append`
- line 303: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 306: `ConfidenceField.evaluate` → `reasons.append`
- line 306: `ConfidenceField.evaluate` → `len`
- line 307: `ConfidenceField.evaluate` → `blockers.append`
- line 308: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 310: `ConfidenceField.evaluate` → `reasons.append`
- line 310: `ConfidenceField.evaluate` → `len`
- line 313: `ConfidenceField.evaluate` → `reasons.append`
- line 313: `ConfidenceField.evaluate` → `len`
- line 314: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 317: `ConfidenceField.evaluate` → `missing_information.append`
- line 319: `ConfidenceField.evaluate` → `reasons.append`
- line 320: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 321: `ConfidenceField.evaluate` → `len`
- line 322: `ConfidenceField.evaluate` → `reasons.append`
- line 325: `ConfidenceField.evaluate` → `blockers.append`
- line 326: `ConfidenceField.evaluate` → `what_would_change_state.append`
- line 328: `ConfidenceField.evaluate` → `blockers.append`
- line 330: `ConfidenceField.evaluate` → `reasons.append`
- line 332: `ConfidenceField.evaluate` → `reasons.extend`
- line 336: `ConfidenceField.evaluate` → `compass.orient(kernel=kernel, concepts_of_interest=(concept,) if concept else ()).to_dict`
- line 336: `ConfidenceField.evaluate` → `compass.orient`
- line 341: `ConfidenceField.evaluate` → `ConfidenceFieldReading`
- line 343: `ConfidenceField.evaluate` → `round`
- line 344: `ConfidenceField.evaluate` → `round`
- line 345: `ConfidenceField.evaluate` → `round`
- line 346: `ConfidenceField.evaluate` → `round`
- line 347: `ConfidenceField.evaluate` → `round`
- line 348: `ConfidenceField.evaluate` → `round`
- line 352: `ConfidenceField.evaluate` → `tuple`
- line 353: `ConfidenceField.evaluate` → `tuple`
- line 353: `ConfidenceField.evaluate` → `dict.fromkeys`
- line 354: `ConfidenceField.evaluate` → `tuple`
- line 354: `ConfidenceField.evaluate` → `dict.fromkeys`
- line 355: `ConfidenceField.evaluate` → `tuple`
- line 355: `ConfidenceField.evaluate` → `dict.fromkeys`
- line 358: `ConfidenceField.evaluate` → `round`
- line 359: `ConfidenceField.evaluate` → `round`
- line 360: `ConfidenceField.evaluate` → `round`
- line 361: `ConfidenceField.evaluate` → `len`
- line 362: `ConfidenceField.evaluate` → `sorted`
- line 363: `ConfidenceField.evaluate` → `round`
- line 364: `ConfidenceField.evaluate` → `list`
- line 365: `ConfidenceField.evaluate` → `len`
- line 366: `ConfidenceField.evaluate` → `len`
- line 367: `ConfidenceField.evaluate` → `differential.to_dict`
- line 377: `ConfidenceField.evaluate` → `band.lower`

### `lantern_harness/config.py`
- line 14: `<module>` → `Path(__file__).resolve`
- line 14: `<module>` → `Path`
- line 18: `load_config` → `Path`
- line 19: `load_config` → `path.exists`
- line 26: `load_config` → `json.loads`
- line 26: `load_config` → `path.read_text`

### `lantern_harness/decision_state_machine.py`
- line 43: `DecisionReading` → `field`
- line 49: `DecisionReading.to_dict` → `list`
- line 50: `DecisionReading.to_dict` → `list`
- line 51: `DecisionReading.to_dict` → `list`
- line 59: `DecisionReading.to_dict` → `dict`
- line 29: `DecisionReading` → `dataclass`
- line 77: `DecisionStateMachine.recommend` → `ValueError`
- line 79: `DecisionStateMachine.recommend` → `ALLOWED_TRANSITIONS.get`
- line 79: `DecisionStateMachine.recommend` → `set`
- line 81: `DecisionStateMachine.recommend` → `ValueError`
- line 82: `DecisionStateMachine.recommend` → `sorted`
- line 82: `DecisionStateMachine.recommend` → `ALLOWED_TRANSITIONS.get`
- line 82: `DecisionStateMachine.recommend` → `set`
- line 94: `DecisionStateMachine.recommend` → `DecisionReading`

### `lantern_harness/harness_status.py`
- line 30: `lantern_version` → `getattr`
- line 32: `lantern_version` → `str`
- line 37: `lantern_version` → `importlib.metadata.version`
- line 46: `status_report` → `bridge.status`
- line 47: `status_report` → `bridge.identity_status`
- line 48: `status_report` → `bridge.witness_integrity`
- line 50: `status_report` → `engine.describe`
- line 53: `status_report` → `lantern_version`
- line 58: `status_report` → `lantern_status.get`
- line 59: `status_report` → `lantern_status.get`
- line 60: `status_report` → `lantern_status.get`
- line 61: `status_report` → `lantern_status.get`
- line 62: `status_report` → `lantern_status.get`
- line 66: `status_report` → `tool_boundary.discover`
- line 67: `status_report` → `sorted`
- line 70: `status_report` → `_mcp_server_status`
- line 91: `format_status_report` → `report['node_identity'].get`
- line 94: `format_status_report` → `engine.get`
- line 95: `format_status_report` → `lines.append`
- line 95: `format_status_report` → `engine.get`
- line 96: `format_status_report` → `lines.append`
- line 96: `format_status_report` → `engine.get`
- line 98: `format_status_report` → `lines.append`
- line 99: `format_status_report` → `lines.append`
- line 101: `format_status_report` → `lines.append`
- line 102: `format_status_report` → `lines.append`
- line 102: `format_status_report` → `report['witness_integrity'].get`
- line 103: `format_status_report` → `lines.append`
- line 104: `format_status_report` → `lines.append`
- line 105: `format_status_report` → `lines.append`
- line 106: `format_status_report` → `lines.append`
- line 107: `format_status_report` → `lines.append`
- line 108: `format_status_report` → `lines.append`
- line 109: `format_status_report` → `lines.append`
- line 110: `format_status_report` → `lines.append`
- line 111: `format_status_report` → `lines.append`
- line 112: `format_status_report` → `lines.append`
- line 113: `format_status_report` → `lines.append`
- line 114: `format_status_report` → `lines.append`
- line 115: `format_status_report` → `lines.append`
- line 116: `format_status_report` → `lines.append`
- line 117: `format_status_report` → `'\n'.join`

### `lantern_harness/mcp_server.py`
- line 64: `<module>` → `Path`
- line 65: `<module>` → `os.getenv`
- line 65: `<module>` → `str`
- line 65: `<module>` → `Path.home`
- line 75: `LanternMCPContext.__init__` → `LanternBridge`
- line 76: `LanternMCPContext.__init__` → `self.bridge.ensure_identity`
- line 77: `LanternMCPContext.__init__` → `self.bridge.startup`
- line 78: `LanternMCPContext.__init__` → `ToolBoundary`
- line 79: `LanternMCPContext.__init__` → `PromptCompiler`
- line 80: `LanternMCPContext.__init__` → `ConfidenceField`
- line 81: `LanternMCPContext.__init__` → `DecisionStateMachine`
- line 82: `LanternMCPContext.__init__` → `BranchStore`
- line 83: `LanternMCPContext.__init__` → `SpineCommitter`
- line 84: `LanternMCPContext.__init__` → `OperatingLoop`
- line 85: `LanternMCPContext.__init__` → `PermissionAuthority`
- line 90: `build_server` → `RuntimeError`
- line 94: `build_server` → `LanternMCPContext`
- line 95: `build_server` → `MCPServer`
- line 108: `build_server.lantern_observe` → `ctx.bridge.observe`
- line 106: `build_server.lantern_observe` → `server.tool`
- line 113: `build_server.lantern_add_evidence` → `ctx.bridge.add_evidence`
- line 111: `build_server.lantern_add_evidence` → `server.tool`
- line 118: `build_server.lantern_confidence` → `ctx.confidence_field.evaluate`
- line 119: `build_server.lantern_confidence` → `reading.to_dict`
- line 116: `build_server.lantern_confidence` → `server.tool`
- line 123: `build_server.lantern_decide` → `ctx.confidence_field.evaluate`
- line 124: `build_server.lantern_decide` → `ctx.decision_machine.recommend`
- line 125: `build_server.lantern_decide` → `decision.to_dict`
- line 121: `build_server.lantern_decide` → `server.tool`
- line 129: `build_server.lantern_compile` → `ctx.compiler.compile`
- line 130: `build_server.lantern_compile` → `compiled.to_dict`
- line 127: `build_server.lantern_compile` → `server.tool`
- line 134: `build_server.lantern_self_model` → `SelfModel(ctx.bridge, ctx.tool_boundary).describe().to_dict`
- line 134: `build_server.lantern_self_model` → `SelfModel(ctx.bridge, ctx.tool_boundary).describe`
- line 134: `build_server.lantern_self_model` → `SelfModel`
- line 132: `build_server.lantern_self_model` → `server.tool`
- line 138: `build_server.lantern_branch_open` → `ctx.branch_store.open_branch`
- line 139: `build_server.lantern_branch_open` → `branch.to_dict`
- line 136: `build_server.lantern_branch_open` → `server.tool`
- line 143: `build_server.lantern_spine_read` → `ctx.spine_committer.read_spine`
- line 144: `build_server.lantern_spine_read` → `e.to_dict`
- line 141: `build_server.lantern_spine_read` → `server.tool`
- line 148: `build_server.lantern_witness_integrity` → `ctx.bridge.witness_integrity`
- line 146: `build_server.lantern_witness_integrity` → `server.tool`
- line 166: `build_server.lantern_evaluate_intent` → `ctx.loop.run`
- line 172: `build_server.lantern_evaluate_intent` → `result.to_dict`
- line 150: `build_server.lantern_evaluate_intent` → `server.tool`
- line 187: `build_server.lantern_transfer_manifest` → `build_manifest(ctx.bridge).to_dict`
- line 187: `build_server.lantern_transfer_manifest` → `build_manifest`
- line 174: `build_server.lantern_transfer_manifest` → `server.tool`
- line 206: `build_server.lantern_permissions` → `ctx.permission_authority.active_grants`
- line 208: `build_server.lantern_permissions` → `len`
- line 189: `build_server.lantern_permissions` → `server.tool`
- line 224: `main` → `build_server`
- line 225: `main` → `server.run`
- line 229: `<module>` → `main`

### `lantern_harness/operating_loop.py`
- line 52: `LoopResult` → `field`
- line 58: `LoopResult.to_dict` → `self.compiled_prompt.to_dict`
- line 59: `LoopResult.to_dict` → `self.confidence.to_dict`
- line 60: `LoopResult.to_dict` → `self.decision.to_dict`
- line 61: `LoopResult.to_dict` → `self.action_record.to_dict`
- line 62: `LoopResult.to_dict` → `self.branch.to_dict`
- line 63: `LoopResult.to_dict` → `list`
- line 75: `LoopResult.format` → `lines.append`
- line 78: `LoopResult.format` → `self.action_record.is_real_success`
- line 81: `LoopResult.format` → `lines.append`
- line 83: `LoopResult.format` → `lines.append`
- line 85: `LoopResult.format` → `lines.append`
- line 86: `LoopResult.format` → `'\n'.join`
- line 96: `OperatingLoop.__init__` → `PromptCompiler`
- line 97: `OperatingLoop.__init__` → `ConfidenceField`
- line 98: `OperatingLoop.__init__` → `DecisionStateMachine`
- line 99: `OperatingLoop.__init__` → `RealityBoundary`
- line 100: `OperatingLoop.__init__` → `BranchStore`
- line 116: `OperatingLoop.run` → `intent.strip`
- line 117: `OperatingLoop.run` → `ValueError`
- line 121: `OperatingLoop.run` → `self.bridge.observe`
- line 124: `OperatingLoop.run` → `self.compiler.compile`
- line 127: `OperatingLoop.run` → `list`
- line 128: `OperatingLoop.run` → `list`
- line 131: `OperatingLoop.run` → `self.confidence_field.evaluate`
- line 138: `OperatingLoop.run` → `self.decision_machine.recommend`
- line 142: `OperatingLoop.run` → `self.reality_boundary.propose`
- line 145: `OperatingLoop.run` → `self.reality_boundary.act`
- line 146: `OperatingLoop.run` → `action_record.is_real_success`
- line 147: `OperatingLoop.run` → `notes.append`
- line 155: `OperatingLoop.run` → `notes.append`
- line 157: `OperatingLoop.run` → `self.branch_store.open_branch`
- line 158: `OperatingLoop.run` → `self.branch_store.link_observation`
- line 159: `OperatingLoop.run` → `notes.append`
- line 161: `OperatingLoop.run` → `LoopResult`
- line 162: `OperatingLoop.run` → `intent.strip`
- line 169: `OperatingLoop.run` → `tuple`

### `lantern_harness/permission_authority.py`
- line 125: `PermissionGrant` → `field`
- line 138: `PermissionGrant.to_dict` → `list`
- line 109: `PermissionGrant` → `dataclass`
- line 168: `AlignmentResult.to_dict` → `list`
- line 169: `AlignmentResult.to_dict` → `list`
- line 170: `AlignmentResult.to_dict` → `list`
- line 171: `AlignmentResult.to_dict` → `list`
- line 150: `AlignmentResult` → `dataclass`
- line 193: `PermissionCheckResult` → `field`
- line 200: `PermissionCheckResult.to_dict` → `self.matched_grant.to_dict`
- line 201: `PermissionCheckResult.to_dict` → `self.alignment.to_dict`
- line 204: `PermissionCheckResult.to_dict` → `list`
- line 205: `PermissionCheckResult.to_dict` → `list`
- line 210: `PermissionCheckResult.format` → `lines.append`
- line 211: `PermissionCheckResult.format` → `lines.append`
- line 212: `PermissionCheckResult.format` → `lines.append`
- line 214: `PermissionCheckResult.format` → `lines.append`
- line 219: `PermissionCheckResult.format` → `lines.append`
- line 221: `PermissionCheckResult.format` → `lines.append`
- line 221: `PermissionCheckResult.format` → `'; '.join`
- line 222: `PermissionCheckResult.format` → `lines.append`
- line 223: `PermissionCheckResult.format` → `lines.append`
- line 223: `PermissionCheckResult.format` → `', '.join`
- line 225: `PermissionCheckResult.format` → `lines.append`
- line 226: `PermissionCheckResult.format` → `'\n'.join`
- line 177: `PermissionCheckResult` → `dataclass`
- line 268: `PermissionAuthority.grant` → `ValueError`
- line 271: `PermissionAuthority.grant` → `granting_authority.strip`
- line 272: `PermissionAuthority.grant` → `ValueError`
- line 273: `PermissionAuthority.grant` → `scope.strip`
- line 274: `PermissionAuthority.grant` → `ValueError`
- line 276: `PermissionAuthority.grant` → `PermissionGrant`
- line 278: `PermissionAuthority.grant` → `scope.strip`
- line 279: `PermissionAuthority.grant` → `boundary.strip`
- line 280: `PermissionAuthority.grant` → `granting_authority.strip`
- line 281: `PermissionAuthority.grant` → `provenance.strip`
- line 285: `PermissionAuthority.grant` → `tuple`
- line 288: `PermissionAuthority.grant` → `self._grants.append`
- line 296: `PermissionAuthority.revoke` → `granting_authority.strip`
- line 297: `PermissionAuthority.revoke` → `ValueError`
- line 302: `PermissionAuthority.revoke` → `updated.append`
- line 303: `PermissionAuthority.revoke` → `PermissionGrant`
- line 318: `PermissionAuthority.revoke` → `updated.append`
- line 323: `PermissionAuthority.active_grants` → `tuple`
- line 323: `PermissionAuthority.active_grants` → `g.is_active`
- line 329: `PermissionAuthority.all_grants` → `tuple`
- line 332: `PermissionAuthority._find_active_grant` → `reversed`
- line 333: `PermissionAuthority._find_active_grant` → `grant.is_active`
- line 350: `PermissionAuthority.check` → `action.strip`
- line 351: `PermissionAuthority.check` → `ValueError`
- line 354: `PermissionAuthority.check` → `self._find_active_grant`
- line 359: `PermissionAuthority.check` → `notes.append`
- line 368: `PermissionAuthority.check` → `notes.append`
- line 374: `PermissionAuthority.check` → `PermissionCheckResult`
- line 375: `PermissionAuthority.check` → `action.strip`
- line 382: `PermissionAuthority.check` → `tuple`
- line 383: `PermissionAuthority.check` → `tuple`
- line 402: `PermissionAuthority.format_new_authority_request` → `check_result.matched_grant.to_dict`
- line 411: `PermissionAuthority.format_new_authority_request` → `', '.join`
- line 416: `PermissionAuthority.format_new_authority_request` → `'\n'.join`
- line 439: `PermissionAuthority.format_action_complete` → `', '.join`
- line 443: `PermissionAuthority.format_action_complete` → `'\n'.join`

### `lantern_harness/perspective_differential.py`
- line 26: `Perspective` → `dataclass`
- line 59: `DifferentialReading` → `field`
- line 70: `DifferentialReading.to_dict` → `p.to_dict`
- line 51: `DifferentialReading` → `dataclass`
- line 81: `PerspectiveDifferentialEngine.compare` → `ValueError`
- line 82: `PerspectiveDifferentialEngine.compare` → `len`
- line 83: `PerspectiveDifferentialEngine.compare` → `DifferentialReading`
- line 85: `PerspectiveDifferentialEngine.compare` → `tuple`
- line 87: `PerspectiveDifferentialEngine.compare` → `len`
- line 100: `PerspectiveDifferentialEngine.compare` → `pvariance`
- line 101: `PerspectiveDifferentialEngine.compare` → `pvariance`
- line 102: `PerspectiveDifferentialEngine.compare` → `pvariance`
- line 103: `PerspectiveDifferentialEngine.compare` → `pvariance`
- line 105: `PerspectiveDifferentialEngine.compare` → `max`
- line 107: `PerspectiveDifferentialEngine.compare` → `DifferentialReading`
- line 114: `PerspectiveDifferentialEngine.compare` → `tuple`

### `lantern_harness/prompt_compiler.py`
- line 37: `<module>` → `re.compile`
- line 49: `_looks_consequential` → `user_request.lower`
- line 50: `_looks_consequential` → `any`
- line 56: `CompiledPrompt` → `field`
- line 58: `CompiledPrompt` → `field`
- line 60: `CompiledPrompt` → `field`
- line 61: `CompiledPrompt` → `field`
- line 71: `CompiledPrompt.to_dict` → `p.to_dict`
- line 72: `CompiledPrompt.to_dict` → `list`
- line 106: `PromptCompiler.compile` → `user_request.strip`
- line 107: `PromptCompiler.compile` → `ValueError`
- line 111: `PromptCompiler.compile` → `user_request.strip`
- line 112: `PromptCompiler.compile` → `_PROVE_PATTERN.search`
- line 116: `PromptCompiler.compile` → `user_request.strip`
- line 118: `PromptCompiler.compile` → `notes.append`
- line 125: `PromptCompiler.compile` → `_looks_consequential`
- line 126: `PromptCompiler.compile` → `notes.append`
- line 133: `PromptCompiler.compile` → `self._read_bridge_state`
- line 135: `PromptCompiler.compile` → `notes.append`
- line 138: `PromptCompiler.compile` → `user_request.strip`
- line 140: `PromptCompiler.compile` → `self._default_desired_output`
- line 141: `PromptCompiler.compile` → `self._epistemic_status`
- line 141: `PromptCompiler.compile` → `bool`
- line 145: `PromptCompiler.compile` → `fields.update`
- line 170: `PromptCompiler.compile` → `self._render`
- line 171: `PromptCompiler.compile` → `CompiledPrompt`
- line 177: `PromptCompiler.compile` → `tuple`
- line 178: `PromptCompiler.compile` → `tuple`
- line 192: `PromptCompiler._read_bridge_state` → `self.bridge.witness_integrity`
- line 193: `PromptCompiler._read_bridge_state` → `integrity.get`
- line 198: `PromptCompiler._read_bridge_state` → `integrity.get`
- line 231: `PromptCompiler._read_bridge_state` → `kernel.observations.items`
- line 232: `PromptCompiler._read_bridge_state` → `any`
- line 251: `PromptCompiler._read_bridge_state` → `len`
- line 268: `PromptCompiler._epistemic_status` → `status.append`
- line 269: `PromptCompiler._epistemic_status` → `status.append`
- line 270: `PromptCompiler._epistemic_status` → `repr`
- line 272: `PromptCompiler._epistemic_status` → `status.append`
- line 281: `PromptCompiler._render` → `fields.items`
- line 282: `PromptCompiler._render` → `lines.append`
- line 283: `PromptCompiler._render` → `lines.append`
- line 284: `PromptCompiler._render` → `isinstance`
- line 286: `PromptCompiler._render` → `lines.append`
- line 289: `PromptCompiler._render` → `lines.append`
- line 291: `PromptCompiler._render` → `lines.append`
- line 293: `PromptCompiler._render` → `lines.append`
- line 294: `PromptCompiler._render` → `lines.append`
- line 295: `PromptCompiler._render` → `lines.append`
- line 296: `PromptCompiler._render` → `lines.append`
- line 297: `PromptCompiler._render` → `lines.append`
- line 298: `PromptCompiler._render` → `lines.append`
- line 299: `PromptCompiler._render` → `lines.append`
- line 300: `PromptCompiler._render` → `lines.append`
- line 301: `PromptCompiler._render` → `'\n'.join`

### `lantern_harness/reality_boundary.py`
- line 54: `ActionProposal` → `field`
- line 63: `ActionProposal.to_dict` → `dict`
- line 41: `ActionProposal` → `dataclass`
- line 78: `ActionRecord` → `field`
- line 82: `ActionRecord.to_dict` → `self.proposal.to_dict`
- line 88: `ActionRecord.to_dict` → `list`
- line 67: `ActionRecord` → `dataclass`
- line 116: `RealityBoundary.propose` → `intent.strip`
- line 117: `RealityBoundary.propose` → `ValueError`
- line 118: `RealityBoundary.propose` → `ActionProposal`
- line 119: `RealityBoundary.propose` → `intent.strip`
- line 124: `RealityBoundary.propose` → `dict`
- line 132: `RealityBoundary.act` → `ActionRecord`
- line 140: `RealityBoundary.act` → `tool_boundary.is_authorized`
- line 141: `RealityBoundary.act` → `ActionRecord`
- line 149: `RealityBoundary.act` → `tool_boundary.execute`
- line 151: `RealityBoundary.act` → `ActionRecord`
- line 158: `RealityBoundary.act` → `ActionRecord`
- line 172: `RealityBoundary.simulate` → `reason.strip`
- line 173: `RealityBoundary.simulate` → `ValueError`
- line 174: `RealityBoundary.simulate` → `ActionRecord`
- line 180: `RealityBoundary.simulate` → `reason.strip`

### `lantern_harness/reasoning/__init__.py`
- line 31: `build_engine` → `config.get`
- line 34: `build_engine` → `_PROVIDERS.get`
- line 46: `build_engine` → `cls`

### `lantern_harness/reasoning/api_provider.py`
- line 25: `OpenAIEngine._api_key` → `os.environ.get`
- line 28: `OpenAIEngine.detect` → `self._api_key`
- line 33: `OpenAIEngine.respond` → `self._api_key`
- line 35: `OpenAIEngine.respond` → `ReasoningEngineUnavailable`
- line 38: `OpenAIEngine.respond` → `json.dumps(payload).encode`
- line 38: `OpenAIEngine.respond` → `json.dumps`
- line 39: `OpenAIEngine.respond` → `urllib.request.Request`
- line 49: `OpenAIEngine.respond` → `urllib.request.urlopen`
- line 50: `OpenAIEngine.respond` → `json.loads`
- line 50: `OpenAIEngine.respond` → `resp.read().decode`
- line 50: `OpenAIEngine.respond` → `resp.read`
- line 52: `OpenAIEngine.respond` → `ReasoningEngineUnavailable`
- line 54: `OpenAIEngine.respond` → `data.get('choices', [{}])[0].get('message', {}).get`
- line 54: `OpenAIEngine.respond` → `data.get('choices', [{}])[0].get`
- line 54: `OpenAIEngine.respond` → `data.get`
- line 55: `OpenAIEngine.respond` → `ReasoningResponse`
- line 58: `OpenAIEngine.describe` → `self.detect`
- line 70: `AnthropicEngine._api_key` → `os.environ.get`
- line 73: `AnthropicEngine.detect` → `self._api_key`
- line 78: `AnthropicEngine.respond` → `self._api_key`
- line 80: `AnthropicEngine.respond` → `ReasoningEngineUnavailable`
- line 82: `AnthropicEngine.respond` → `'\n'.join`
- line 82: `AnthropicEngine.respond` → `m.get`
- line 83: `AnthropicEngine.respond` → `m.get`
- line 87: `AnthropicEngine.respond` → `json.dumps(payload).encode`
- line 87: `AnthropicEngine.respond` → `json.dumps`
- line 88: `AnthropicEngine.respond` → `urllib.request.Request`
- line 99: `AnthropicEngine.respond` → `urllib.request.urlopen`
- line 100: `AnthropicEngine.respond` → `json.loads`
- line 100: `AnthropicEngine.respond` → `resp.read().decode`
- line 100: `AnthropicEngine.respond` → `resp.read`
- line 102: `AnthropicEngine.respond` → `ReasoningEngineUnavailable`
- line 104: `AnthropicEngine.respond` → `data.get`
- line 105: `AnthropicEngine.respond` → `''.join`
- line 105: `AnthropicEngine.respond` → `b.get`
- line 105: `AnthropicEngine.respond` → `b.get`
- line 106: `AnthropicEngine.respond` → `ReasoningResponse`
- line 109: `AnthropicEngine.describe` → `self.detect`
- line 121: `GoogleEngine._api_key` → `os.environ.get`
- line 124: `GoogleEngine.detect` → `self._api_key`
- line 129: `GoogleEngine.respond` → `self._api_key`
- line 131: `GoogleEngine.respond` → `ReasoningEngineUnavailable`
- line 133: `GoogleEngine.respond` → `'\n'.join`
- line 133: `GoogleEngine.respond` → `m.get`
- line 135: `GoogleEngine.respond` → `m.get`
- line 137: `GoogleEngine.respond` → `m.get`
- line 142: `GoogleEngine.respond` → `json.dumps(payload).encode`
- line 142: `GoogleEngine.respond` → `json.dumps`
- line 147: `GoogleEngine.respond` → `urllib.request.Request`
- line 151: `GoogleEngine.respond` → `urllib.request.urlopen`
- line 152: `GoogleEngine.respond` → `json.loads`
- line 152: `GoogleEngine.respond` → `resp.read().decode`
- line 152: `GoogleEngine.respond` → `resp.read`
- line 154: `GoogleEngine.respond` → `ReasoningEngineUnavailable`
- line 156: `GoogleEngine.respond` → `data.get`
- line 159: `GoogleEngine.respond` → `candidates[0].get('content', {}).get`
- line 159: `GoogleEngine.respond` → `candidates[0].get`
- line 160: `GoogleEngine.respond` → `''.join`
- line 160: `GoogleEngine.respond` → `p.get`
- line 161: `GoogleEngine.respond` → `ReasoningResponse`
- line 164: `GoogleEngine.describe` → `self.detect`

### `lantern_harness/reasoning/ollama_provider.py`
- line 19: `OllamaEngine.__init__` → `host.rstrip`
- line 24: `OllamaEngine.detect` → `urllib.request.Request`
- line 25: `OllamaEngine.detect` → `urllib.request.urlopen`
- line 26: `OllamaEngine.detect` → `json.loads`
- line 26: `OllamaEngine.detect` → `resp.read().decode`
- line 26: `OllamaEngine.detect` → `resp.read`
- line 27: `OllamaEngine.detect` → `m.get`
- line 27: `OllamaEngine.detect` → `data.get`
- line 28: `OllamaEngine.detect` → `any`
- line 29: `OllamaEngine.detect` → `m.startswith`
- line 29: `OllamaEngine.detect` → `self.model.split`
- line 37: `OllamaEngine.respond` → `self.detect`
- line 39: `OllamaEngine.respond` → `ReasoningEngineUnavailable`
- line 42: `OllamaEngine.respond` → `json.dumps(payload).encode`
- line 42: `OllamaEngine.respond` → `json.dumps`
- line 43: `OllamaEngine.respond` → `urllib.request.Request`
- line 50: `OllamaEngine.respond` → `urllib.request.urlopen`
- line 51: `OllamaEngine.respond` → `json.loads`
- line 51: `OllamaEngine.respond` → `resp.read().decode`
- line 51: `OllamaEngine.respond` → `resp.read`
- line 53: `OllamaEngine.respond` → `ReasoningEngineUnavailable`
- line 55: `OllamaEngine.respond` → `data.get('message', {}).get`
- line 55: `OllamaEngine.respond` → `data.get`
- line 56: `OllamaEngine.respond` → `ReasoningResponse`
- line 59: `OllamaEngine.describe` → `self.detect`

### `lantern_harness/self_model.py`
- line 85: `SelfModelReading` → `field`
- line 89: `SelfModelReading.to_dict` → `list`
- line 90: `SelfModelReading.to_dict` → `list`
- line 91: `SelfModelReading.to_dict` → `list`
- line 92: `SelfModelReading.to_dict` → `list`
- line 93: `SelfModelReading.to_dict` → `list`
- line 94: `SelfModelReading.to_dict` → `list`
- line 95: `SelfModelReading.to_dict` → `list`
- line 96: `SelfModelReading.to_dict` → `list`
- line 111: `SelfModelReading.format` → `lines.append`
- line 112: `SelfModelReading.format` → `lines.append`
- line 114: `SelfModelReading.format` → `lines.append`
- line 116: `SelfModelReading.format` → `lines.append`
- line 117: `SelfModelReading.format` → `'\n'.join`
- line 76: `SelfModelReading` → `dataclass`
- line 129: `SelfModel.describe` → `self.bridge.identity_status`
- line 130: `SelfModel.describe` → `self.bridge.witness_integrity`
- line 131: `SelfModel.describe` → `self.bridge.status`
- line 134: `SelfModel.describe` → `identity.get`
- line 135: `SelfModel.describe` → `integrity.get`
- line 136: `SelfModel.describe` → `status.get`
- line 136: `SelfModel.describe` → `status.get`
- line 137: `SelfModel.describe` → `status.get`
- line 137: `SelfModel.describe` → `status.get`
- line 141: `SelfModel.describe` → `integrity.get`
- line 142: `SelfModel.describe` → `what_i_infer.append`
- line 146: `SelfModel.describe` → `status.get`
- line 146: `SelfModel.describe` → `status.get`
- line 147: `SelfModel.describe` → `what_i_infer.append`
- line 148: `SelfModel.describe` → `status.get`
- line 158: `SelfModel.describe` → `list`
- line 159: `SelfModel.describe` → `list`
- line 161: `SelfModel.describe` → `sorted`
- line 168: `SelfModel.describe` → `SelfModelReading`
- line 169: `SelfModel.describe` → `tuple`
- line 170: `SelfModel.describe` → `tuple`
- line 171: `SelfModel.describe` → `tuple`
- line 172: `SelfModel.describe` → `tuple`
- line 173: `SelfModel.describe` → `tuple`
- line 174: `SelfModel.describe` → `tuple`

### `lantern_harness/spine.py`
- line 50: `_uid` → `str`
- line 50: `_uid` → `uuid.uuid4`
- line 64: `Branch` → `field`
- line 65: `Branch` → `field`
- line 66: `Branch` → `field`
- line 75: `Branch.to_dict` → `list`
- line 76: `Branch.to_dict` → `list`
- line 77: `Branch.to_dict` → `list`
- line 103: `SpineEntry.to_dict` → `dict`
- line 104: `SpineEntry.to_dict` → `list`
- line 82: `SpineEntry` → `dataclass`
- line 122: `CommitResult.to_dict` → `self.entry.to_dict`
- line 112: `CommitResult` → `dataclass`
- line 136: `BranchStore.open_branch` → `concept.strip`
- line 137: `BranchStore.open_branch` → `ValueError`
- line 138: `BranchStore.open_branch` → `hypothesis.strip`
- line 139: `BranchStore.open_branch` → `ValueError`
- line 141: `BranchStore.open_branch` → `ValueError`
- line 142: `BranchStore.open_branch` → `Branch`
- line 142: `BranchStore.open_branch` → `_uid`
- line 142: `BranchStore.open_branch` → `concept.strip`
- line 142: `BranchStore.open_branch` → `hypothesis.strip`
- line 147: `BranchStore.get` → `self._branches.get`
- line 150: `BranchStore.add_note` → `self._require`
- line 151: `BranchStore.add_note` → `branch.notes.append`
- line 155: `BranchStore.link_observation` → `self._require`
- line 157: `BranchStore.link_observation` → `branch.observation_ids.append`
- line 161: `BranchStore.link_evidence` → `self._require`
- line 163: `BranchStore.link_evidence` → `branch.evidence_ids.append`
- line 167: `BranchStore.abandon` → `self._require`
- line 169: `BranchStore.abandon` → `ValueError`
- line 174: `BranchStore._require` → `self._branches.get`
- line 176: `BranchStore._require` → `ValueError`
- line 178: `BranchStore._require` → `ValueError`
- line 182: `BranchStore.all` → `list`
- line 182: `BranchStore.all` → `self._branches.values`
- line 203: `SpineCommitter.commit` → `CommitResult`
- line 206: `SpineCommitter.commit` → `CommitResult`
- line 214: `SpineCommitter.commit` → `authorized_by.strip`
- line 215: `SpineCommitter.commit` → `CommitResult`
- line 217: `SpineCommitter.commit` → `self.bridge.witness_integrity`
- line 218: `SpineCommitter.commit` → `integrity.get`
- line 219: `SpineCommitter.commit` → `CommitResult`
- line 221: `SpineCommitter.commit` → `integrity.get`
- line 232: `SpineCommitter.commit` → `CommitResult`
- line 235: `SpineCommitter.commit` → `len`
- line 241: `SpineCommitter.commit` → `len`
- line 245: `SpineCommitter.commit` → `_uid`
- line 249: `SpineCommitter.commit` → `list`
- line 261: `SpineCommitter.commit` → `list`
- line 265: `SpineCommitter.commit` → `KernelEvent`
- line 266: `SpineCommitter.commit` → `self.bridge.lantern.bus.publish`
- line 272: `SpineCommitter.commit` → `SpineEntry`
- line 278: `SpineCommitter.commit` → `tuple`
- line 284: `SpineCommitter.commit` → `CommitResult`
- line 297: `SpineCommitter.read_spine` → `chronicle.replay`
- line 298: `SpineCommitter.read_spine` → `record.get`
- line 301: `SpineCommitter.read_spine` → `entries.append`
- line 302: `SpineCommitter.read_spine` → `SpineEntry`
- line 308: `SpineCommitter.read_spine` → `tuple`
- line 326: `branch_to_scar` → `ValueError`
- line 327: `branch_to_scar` → `bridge.create_scar`
- line 334: `branch_to_scar` → `list`
- line 336: `branch_to_scar` → `bridge.persist_scar`

### `lantern_harness/tools/boundary.py`
- line 45: `ToolBoundary.__init__` → `set`
- line 51: `ToolBoundary.discover` → `sorted`
- line 51: `ToolBoundary.discover` → `self._tools.keys`
- line 57: `ToolBoundary.authorize` → `self._authorized.add`
- line 64: `ToolBoundary.execute` → `self._tools.get`
- line 66: `ToolBoundary.execute` → `ToolResult`
- line 68: `ToolBoundary.execute` → `self.is_authorized`
- line 69: `ToolBoundary.execute` → `ToolResult`
- line 72: `ToolBoundary.execute` → `descriptor.handler`
- line 73: `ToolBoundary.execute` → `ToolResult`
- line 75: `ToolBoundary.execute` → `ToolResult`
- line 75: `ToolBoundary.execute` → `str`

### `lantern_harness/transfer_manifest.py`
- line 86: `_git_commit` → `subprocess.run`
- line 88: `_git_commit` → `str`
- line 94: `_git_commit` → `result.stdout.strip`
- line 104: `_lantern_core_commit` → `Path(lantern.__file__).resolve`
- line 104: `_lantern_core_commit` → `Path`
- line 106: `_lantern_core_commit` → `_git_commit`
- line 140: `TransferManifest` → `field`
- line 140: `TransferManifest` → `dict`
- line 141: `TransferManifest` → `field`
- line 163: `TransferManifest.to_dict` → `list`
- line 164: `TransferManifest.to_dict` → `list`
- line 165: `TransferManifest.to_dict` → `list`
- line 166: `TransferManifest.to_dict` → `list`
- line 173: `TransferManifest.to_dict` → `list`
- line 178: `TransferManifest.format` → `lines.append`
- line 179: `TransferManifest.format` → `lines.append`
- line 180: `TransferManifest.format` → `lines.append`
- line 181: `TransferManifest.format` → `lines.append`
- line 182: `TransferManifest.format` → `lines.append`
- line 183: `TransferManifest.format` → `lines.append`
- line 184: `TransferManifest.format` → `lines.append`
- line 185: `TransferManifest.format` → `lines.append`
- line 186: `TransferManifest.format` → `lines.append`
- line 186: `TransferManifest.format` → `self.lineage.get`
- line 186: `TransferManifest.format` → `self.lineage.get`
- line 187: `TransferManifest.format` → `lines.append`
- line 188: `TransferManifest.format` → `lines.append`
- line 189: `TransferManifest.format` → `lines.append`
- line 190: `TransferManifest.format` → `lines.append`
- line 191: `TransferManifest.format` → `self.state_summary.items`
- line 192: `TransferManifest.format` → `lines.append`
- line 193: `TransferManifest.format` → `lines.append`
- line 194: `TransferManifest.format` → `lines.append`
- line 194: `TransferManifest.format` → `self.witness_integrity.get`
- line 195: `TransferManifest.format` → `lines.append`
- line 196: `TransferManifest.format` → `lines.append`
- line 198: `TransferManifest.format` → `lines.append`
- line 199: `TransferManifest.format` → `lines.append`
- line 200: `TransferManifest.format` → `lines.append`
- line 202: `TransferManifest.format` → `lines.append`
- line 203: `TransferManifest.format` → `lines.append`
- line 204: `TransferManifest.format` → `lines.append`
- line 206: `TransferManifest.format` → `lines.append`
- line 207: `TransferManifest.format` → `lines.append`
- line 208: `TransferManifest.format` → `lines.append`
- line 209: `TransferManifest.format` → `lines.append`
- line 210: `TransferManifest.format` → `lines.append`
- line 211: `TransferManifest.format` → `lines.append`
- line 212: `TransferManifest.format` → `lines.append`
- line 214: `TransferManifest.format` → `lines.append`
- line 215: `TransferManifest.format` → `lines.append`
- line 217: `TransferManifest.format` → `lines.append`
- line 218: `TransferManifest.format` → `'\n'.join`
- line 120: `TransferManifest` → `dataclass`
- line 225: `build_manifest` → `bridge.identity_status`
- line 226: `build_manifest` → `bridge.status`
- line 227: `build_manifest` → `bridge.witness_integrity`
- line 228: `build_manifest` → `_protocol_info`
- line 232: `build_manifest` → `bridge.branches`
- line 233: `build_manifest` → `len`
- line 237: `build_manifest` → `notes.append`
- line 240: `build_manifest` → `status.get`
- line 241: `build_manifest` → `status.get`
- line 242: `build_manifest` → `status.get`
- line 243: `build_manifest` → `status.get`
- line 244: `build_manifest` → `status.get`
- line 251: `build_manifest` → `engine.describe`
- line 252: `build_manifest` → `described.get`
- line 253: `build_manifest` → `getattr`
- line 255: `build_manifest` → `Path(__file__).resolve`
- line 255: `build_manifest` → `Path`
- line 257: `build_manifest` → `TransferManifest`
- line 259: `build_manifest` → `identity.get`
- line 260: `build_manifest` → `identity.get`
- line 261: `build_manifest` → `lantern_version`
- line 272: `build_manifest` → `_git_commit`
- line 273: `build_manifest` → `_lantern_core_commit`
- line 274: `build_manifest` → `platform.python_version`
- line 275: `build_manifest` → `platform.platform`
- line 276: `build_manifest` → `dict`
- line 277: `build_manifest` → `tuple`

### `main.py`
- line 15: `<module>` → `sys.path.insert`
- line 15: `<module>` → `str`
- line 15: `<module>` → `Path(__file__).resolve`
- line 15: `<module>` → `Path`
- line 32: `<module>` → `Path(__file__).resolve`
- line 32: `<module>` → `Path`
- line 36: `load_system_prompt` → `SYSTEM_PROMPT_PATH.exists`
- line 38: `load_system_prompt` → `SYSTEM_PROMPT_PATH.read_text`
- line 43: `handle_command` → `status_report`
- line 44: `handle_command` → `format_status_report`
- line 45: `handle_command` → `command.startswith`
- line 46: `handle_command` → `command[len('/decide'):].strip`
- line 46: `handle_command` → `len`
- line 49: `handle_command` → `PromptCompiler`
- line 50: `handle_command` → `ConfidenceField`
- line 51: `handle_command` → `DecisionStateMachine`
- line 52: `handle_command` → `compiler.compile`
- line 53: `handle_command` → `field.evaluate`
- line 54: `handle_command` → `machine.recommend`
- line 58: `handle_command` → `'\n'.join`
- line 68: `handle_command` → `command.startswith`
- line 69: `handle_command` → `command[len('/compile'):].strip`
- line 69: `handle_command` → `len`
- line 72: `handle_command` → `PromptCompiler`
- line 74: `handle_command` → `compiler.compile`
- line 79: `handle_command` → `'; '.join`
- line 82: `handle_command` → `str`
- line 82: `handle_command` → `bridge.identity_status`
- line 84: `handle_command` → `tool_boundary.discover`
- line 84: `handle_command` → `sorted`
- line 86: `handle_command` → `bridge.status`
- line 90: `handle_command` → `bridge.branches`
- line 106: `handle_stateful_command` → `SelfModel`
- line 107: `handle_stateful_command` → `model.describe().format`
- line 107: `handle_stateful_command` → `model.describe`
- line 109: `handle_stateful_command` → `command.startswith`
- line 110: `handle_stateful_command` → `command[len('/branch'):].strip`
- line 110: `handle_stateful_command` → `len`
- line 112: `handle_stateful_command` → `branch_store.all`
- line 116: `handle_stateful_command` → `part.strip`
- line 116: `handle_stateful_command` → `request.split`
- line 117: `handle_stateful_command` → `branch_store.open_branch`
- line 120: `handle_stateful_command` → `command.startswith`
- line 121: `handle_stateful_command` → `command[len('/spine'):].strip`
- line 121: `handle_stateful_command` → `len`
- line 123: `handle_stateful_command` → `SpineCommitter`
- line 124: `handle_stateful_command` → `committer.read_spine`
- line 127: `handle_stateful_command` → `len`
- line 129: `handle_stateful_command` → `lines.append`
- line 130: `handle_stateful_command` → `'\n'.join`
- line 138: `handle_stateful_command` → `command.startswith`
- line 139: `handle_stateful_command` → `command[len('/run'):].strip`
- line 139: `handle_stateful_command` → `len`
- line 142: `handle_stateful_command` → `loop.run`
- line 143: `handle_stateful_command` → `result.format`
- line 146: `handle_stateful_command` → `build_manifest`
- line 147: `handle_stateful_command` → `manifest.format`
- line 152: `handle_stateful_command` → `permission_authority.active_grants`
- line 155: `handle_stateful_command` → `len`
- line 157: `handle_stateful_command` → `lines.append`
- line 158: `handle_stateful_command` → `'\n'.join`
- line 160: `handle_stateful_command` → `command.startswith`
- line 161: `handle_stateful_command` → `command[len('/grant'):].strip`
- line 161: `handle_stateful_command` → `len`
- line 165: `handle_stateful_command` → `', '.join`
- line 167: `handle_stateful_command` → `p.strip`
- line 167: `handle_stateful_command` → `request.split`
- line 168: `handle_stateful_command` → `len`
- line 174: `handle_stateful_command` → `permission_authority.grant`
- line 185: `handle_stateful_command` → `command.startswith`
- line 186: `handle_stateful_command` → `command[len('/revoke'):].strip`
- line 186: `handle_stateful_command` → `len`
- line 189: `handle_stateful_command` → `p.strip`
- line 189: `handle_stateful_command` → `request.split`
- line 190: `handle_stateful_command` → `len`
- line 196: `handle_stateful_command` → `permission_authority.revoke`
- line 205: `run_repl` → `load_system_prompt`
- line 208: `run_repl` → `print`
- line 210: `run_repl` → `line.strip`
- line 212: `run_repl` → `print`
- line 215: `run_repl` → `line.startswith`
- line 216: `run_repl` → `handle_stateful_command`
- line 218: `run_repl` → `print`
- line 219: `run_repl` → `print`
- line 221: `run_repl` → `handle_command`
- line 224: `run_repl` → `print`
- line 225: `run_repl` → `print`
- line 228: `run_repl` → `bridge.observe`
- line 231: `run_repl` → `print`
- line 232: `run_repl` → `print`
- line 235: `run_repl` → `history.append`
- line 237: `run_repl` → `engine.respond`
- line 238: `run_repl` → `print`
- line 239: `run_repl` → `history.append`
- line 241: `run_repl` → `print`
- line 242: `run_repl` → `history.pop`
- line 244: `run_repl` → `print`
- line 248: `main` → `bootstrap`
- line 249: `main` → `print`
- line 249: `main` → `format_bootstrap_report`
- line 253: `main` → `print`
- line 257: `main` → `ToolBoundary`
- line 258: `main` → `BranchStore`
- line 259: `main` → `OperatingLoop`
- line 260: `main` → `PermissionAuthority`
- line 262: `main` → `print`
- line 263: `main` → `run_repl`
- line 268: `<module>` → `SystemExit`
- line 268: `<module>` → `main`

### `tests/test_bootstrap.py`
- line 4: `<module>` → `sys.path.insert`
- line 4: `<module>` → `str`
- line 4: `<module>` → `Path(__file__).resolve`
- line 4: `<module>` → `Path`
- line 10: `test_check_python_reports_actual_version` → `check_python`
- line 16: `test_bootstrap_returns_bridge_when_lantern_importable` → `bootstrap`
- line 22: `test_bootstrap_reasoning_engine_not_configured_by_default` → `bootstrap`
- line 31: `test_ensure_directories_creates_all_required` → `monkeypatch.setattr`
- line 32: `test_ensure_directories_creates_all_required` → `ensure_directories`
- line 34: `test_ensure_directories_creates_all_required` → `(tmp_path / name).exists`

### `tests/test_bridge.py`
- line 5: `<module>` → `sys.path.insert`
- line 5: `<module>` → `str`
- line 5: `<module>` → `Path(__file__).resolve`
- line 5: `<module>` → `Path`
- line 11: `_new_bridge` → `Path`
- line 11: `_new_bridge` → `tempfile.mkdtemp`
- line 12: `_new_bridge` → `LanternBridge`
- line 16: `test_identity_starts_uninitialized` → `_new_bridge`
- line 17: `test_identity_starts_uninitialized` → `bridge.identity_status`
- line 21: `test_ensure_identity_creates_real_node_identity` → `_new_bridge`
- line 22: `test_ensure_identity_creates_real_node_identity` → `bridge.ensure_identity`
- line 25: `test_ensure_identity_creates_real_node_identity` → `len`
- line 29: `test_identity_persists_across_bridge_instances` → `Path`
- line 29: `test_identity_persists_across_bridge_instances` → `tempfile.mkdtemp`
- line 30: `test_identity_persists_across_bridge_instances` → `LanternBridge`
- line 31: `test_identity_persists_across_bridge_instances` → `bridge1.ensure_identity`
- line 33: `test_identity_persists_across_bridge_instances` → `LanternBridge`
- line 34: `test_identity_persists_across_bridge_instances` → `bridge2.ensure_identity`
- line 40: `test_observe_and_belief_flow` → `_new_bridge`
- line 41: `test_observe_and_belief_flow` → `bridge.observe`
- line 42: `test_observe_and_belief_flow` → `bridge.add_evidence`
- line 44: `test_observe_and_belief_flow` → `bridge.belief`
- line 49: `test_startup_with_no_prior_state` → `_new_bridge`
- line 50: `test_startup_with_no_prior_state` → `bridge.startup`
- line 56: `test_witness_integrity_valid_on_fresh_chronicle` → `_new_bridge`
- line 57: `test_witness_integrity_valid_on_fresh_chronicle` → `bridge.observe`
- line 58: `test_witness_integrity_valid_on_fresh_chronicle` → `bridge.witness_integrity`
- line 63: `test_branches_not_implemented_honestly` → `_new_bridge`
- line 65: `test_branches_not_implemented_honestly` → `bridge.branches`
- line 68: `test_branches_not_implemented_honestly` → `str`
- line 72: `test_snapshot_and_restart_recovery` → `Path`
- line 72: `test_snapshot_and_restart_recovery` → `tempfile.mkdtemp`
- line 73: `test_snapshot_and_restart_recovery` → `LanternBridge`
- line 74: `test_snapshot_and_restart_recovery` → `bridge1.observe`
- line 75: `test_snapshot_and_restart_recovery` → `bridge1.add_evidence`
- line 76: `test_snapshot_and_restart_recovery` → `bridge1.save_snapshot`
- line 78: `test_snapshot_and_restart_recovery` → `LanternBridge`
- line 79: `test_snapshot_and_restart_recovery` → `bridge2.startup`
- line 81: `test_snapshot_and_restart_recovery` → `bridge2.belief`

### `tests/test_confidence_field.py`
- line 9: `<module>` → `Path`
- line 14: `_fresh_bridge` → `path.exists`
- line 15: `_fresh_bridge` → `shutil.rmtree`
- line 16: `_fresh_bridge` → `LanternBridge`
- line 17: `_fresh_bridge` → `bridge.ensure_identity`
- line 18: `_fresh_bridge` → `bridge.startup`
- line 23: `_add_evidence` → `bridge.observe`
- line 24: `_add_evidence` → `bridge.add_evidence`
- line 28: `test_high_state_with_strong_independent_support` → `_fresh_bridge`
- line 29: `test_high_state_with_strong_independent_support` → `_add_evidence`
- line 30: `test_high_state_with_strong_independent_support` → `_add_evidence`
- line 31: `test_high_state_with_strong_independent_support` → `ConfidenceField`
- line 32: `test_high_state_with_strong_independent_support` → `field.evaluate`
- line 38: `test_medium_state_boundary_exact_threshold` → `_fresh_bridge`
- line 39: `test_medium_state_boundary_exact_threshold` → `_add_evidence`
- line 40: `test_medium_state_boundary_exact_threshold` → `ConfidenceField`
- line 41: `test_medium_state_boundary_exact_threshold` → `field.evaluate`
- line 46: `test_low_state_with_empty_evidence` → `_fresh_bridge`
- line 47: `test_low_state_with_empty_evidence` → `ConfidenceField`
- line 48: `test_low_state_with_empty_evidence` → `field.evaluate`
- line 55: `test_blocked_state_on_integrity_failure` → `_fresh_bridge`
- line 56: `test_blocked_state_on_integrity_failure` → `_add_evidence`
- line 57: `test_blocked_state_on_integrity_failure` → `open`
- line 58: `test_blocked_state_on_integrity_failure` → `f.write`
- line 59: `test_blocked_state_on_integrity_failure` → `ConfidenceField`
- line 60: `test_blocked_state_on_integrity_failure` → `field.evaluate`
- line 66: `test_blocked_is_more_severe_than_low` → `_fresh_bridge`
- line 67: `test_blocked_is_more_severe_than_low` → `ConfidenceField(bridge_ok).evaluate`
- line 67: `test_blocked_is_more_severe_than_low` → `ConfidenceField`
- line 68: `test_blocked_is_more_severe_than_low` → `_fresh_bridge`
- line 69: `test_blocked_is_more_severe_than_low` → `_add_evidence`
- line 70: `test_blocked_is_more_severe_than_low` → `open`
- line 71: `test_blocked_is_more_severe_than_low` → `f.write`
- line 72: `test_blocked_is_more_severe_than_low` → `ConfidenceField(bridge_bad).evaluate`
- line 72: `test_blocked_is_more_severe_than_low` → `ConfidenceField`
- line 79: `test_contradictory_evidence_increases_pressure_and_lowers_confidence` → `_fresh_bridge`
- line 80: `test_contradictory_evidence_increases_pressure_and_lowers_confidence` → `_add_evidence`
- line 81: `test_contradictory_evidence_increases_pressure_and_lowers_confidence` → `_add_evidence`
- line 82: `test_contradictory_evidence_increases_pressure_and_lowers_confidence` → `ConfidenceField(bridge).evaluate`
- line 82: `test_contradictory_evidence_increases_pressure_and_lowers_confidence` → `ConfidenceField`
- line 88: `test_assumption_pressure_raises_investigation_need` → `_fresh_bridge`
- line 89: `test_assumption_pressure_raises_investigation_need` → `_add_evidence`
- line 90: `test_assumption_pressure_raises_investigation_need` → `ConfidenceField(bridge).evaluate`
- line 90: `test_assumption_pressure_raises_investigation_need` → `ConfidenceField`
- line 92: `test_assumption_pressure_raises_investigation_need` → `any`
- line 96: `test_perspective_divergence_is_signal_not_falsehood` → `_fresh_bridge`
- line 97: `test_perspective_divergence_is_signal_not_falsehood` → `_add_evidence`
- line 98: `test_perspective_divergence_is_signal_not_falsehood` → `_add_evidence`
- line 100: `test_perspective_divergence_is_signal_not_falsehood` → `Perspective`
- line 101: `test_perspective_divergence_is_signal_not_falsehood` → `Perspective`
- line 102: `test_perspective_divergence_is_signal_not_falsehood` → `Perspective`
- line 104: `test_perspective_divergence_is_signal_not_falsehood` → `ConfidenceField(bridge).evaluate`
- line 104: `test_perspective_divergence_is_signal_not_falsehood` → `ConfidenceField`
- line 107: `test_perspective_divergence_is_signal_not_falsehood` → `any`
- line 111: `test_repeated_observations_do_not_count_as_independent_sources` → `_fresh_bridge`
- line 112: `test_repeated_observations_do_not_count_as_independent_sources` → `_add_evidence`
- line 113: `test_repeated_observations_do_not_count_as_independent_sources` → `_add_evidence`
- line 114: `test_repeated_observations_do_not_count_as_independent_sources` → `ConfidenceField(bridge).evaluate`
- line 114: `test_repeated_observations_do_not_count_as_independent_sources` → `ConfidenceField`
- line 120: `test_integrity_recovery_reenables_non_blocked_reading` → `_fresh_bridge`
- line 121: `test_integrity_recovery_reenables_non_blocked_reading` → `_add_evidence`
- line 122: `test_integrity_recovery_reenables_non_blocked_reading` → `open`
- line 123: `test_integrity_recovery_reenables_non_blocked_reading` → `f.write`
- line 124: `test_integrity_recovery_reenables_non_blocked_reading` → `ConfidenceField(bridge_bad).evaluate`
- line 124: `test_integrity_recovery_reenables_non_blocked_reading` → `ConfidenceField`
- line 127: `test_integrity_recovery_reenables_non_blocked_reading` → `_fresh_bridge`
- line 128: `test_integrity_recovery_reenables_non_blocked_reading` → `_add_evidence`
- line 129: `test_integrity_recovery_reenables_non_blocked_reading` → `ConfidenceField(bridge_good).evaluate`
- line 129: `test_integrity_recovery_reenables_non_blocked_reading` → `ConfidenceField`
- line 134: `test_scars_add_caution_but_not_permanent_punishment` → `_fresh_bridge`
- line 135: `test_scars_add_caution_but_not_permanent_punishment` → `_add_evidence`
- line 136: `test_scars_add_caution_but_not_permanent_punishment` → `bridge.create_scar`
- line 144: `test_scars_add_caution_but_not_permanent_punishment` → `ConfidenceField(bridge).evaluate`
- line 144: `test_scars_add_caution_but_not_permanent_punishment` → `ConfidenceField`
- line 145: `test_scars_add_caution_but_not_permanent_punishment` → `any`
- line 150: `test_compass_reading_is_included_read_only` → `_fresh_bridge`
- line 151: `test_compass_reading_is_included_read_only` → `_add_evidence`
- line 152: `test_compass_reading_is_included_read_only` → `ConfidenceField(bridge).evaluate`
- line 152: `test_compass_reading_is_included_read_only` → `ConfidenceField`
- line 158: `test_malformed_concept_rejected` → `_fresh_bridge`
- line 159: `test_malformed_concept_rejected` → `ConfidenceField`
- line 161: `test_malformed_concept_rejected` → `field.evaluate`
- line 163: `test_malformed_concept_rejected` → `str`
- line 165: `test_malformed_concept_rejected` → `AssertionError`

### `tests/test_config.py`
- line 4: `<module>` → `sys.path.insert`
- line 4: `<module>` → `str`
- line 4: `<module>` → `Path(__file__).resolve`
- line 4: `<module>` → `Path`
- line 10: `test_load_config_defaults_when_missing` → `load_config`
- line 15: `test_load_real_config_file` → `load_config`
- line 21: `test_config_never_stores_raw_api_key` → `load_config`
- line 22: `test_config_never_stores_raw_api_key` → `config['reasoning_engine'].get`
- line 22: `test_config_never_stores_raw_api_key` → `str`
- line 22: `test_config_never_stores_raw_api_key` → `config['reasoning_engine'].get`
- line 23: `test_config_never_stores_raw_api_key` → `config['reasoning_engine'].values`
- line 24: `test_config_never_stores_raw_api_key` → `isinstance`
- line 25: `test_config_never_stores_raw_api_key` → `value.startswith`

### `tests/test_conversation_loop.py`
- line 7: `<module>` → `sys.path.insert`
- line 7: `<module>` → `str`
- line 7: `<module>` → `Path(__file__).resolve`
- line 7: `<module>` → `Path`
- line 9: `<module>` → `Path(__file__).resolve`
- line 9: `<module>` → `Path`
- line 13: `_run_main` → `subprocess.run`
- line 14: `_run_main` → `str`
- line 18: `_run_main` → `str`
- line 24: `test_first_launch_reaches_lantern_ready` → `_run_main`
- line 31: `test_message_without_reasoning_engine_reports_not_configured_not_fabricated` → `_run_main`
- line 37: `test_status_command_available_from_conversation_loop` → `_run_main`
- line 42: `test_graceful_shutdown_via_exit_command` → `_run_main`
- line 47: `test_graceful_shutdown_via_eof` → `_run_main`
- line 59: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `Path`
- line 59: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `tempfile.mkdtemp`
- line 60: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `LanternBridge`
- line 61: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `bridge.ensure_identity`
- line 62: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `bridge.startup`
- line 70: `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.respond` → `captured_messages.append`
- line 70: `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.respond` → `list`
- line 71: `test_system_prompt_is_actually_sent_to_the_reasoning_engine.FakeEngine.respond` → `ReasoningResponse`
- line 81: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `monkeypatch.setattr`
- line 81: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `io.StringIO`
- line 82: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `ToolBoundary`
- line 83: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `main_mod.run_repl`
- line 83: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `FakeEngine`
- line 83: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `BranchStore`
- line 83: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `OperatingLoop`
- line 83: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `PermissionAuthority`
- line 85: `test_system_prompt_is_actually_sent_to_the_reasoning_engine` → `len`
- line 92: `test_compile_command_produces_structured_prompt_not_fabricated` → `_run_main`
- line 99: `test_compile_command_with_no_request_shows_usage` → `_run_main`
- line 104: `test_compile_command_lightweight_for_ordinary_question` → `_run_main`
- line 108: `test_self_command_reports_seven_sections` → `_run_main`
- line 116: `test_branch_command_opens_a_real_branch` → `_run_main`
- line 122: `test_branch_command_without_double_colon_shows_usage` → `_run_main`
- line 127: `test_spine_command_with_no_entries_reports_zero` → `_run_main`
- line 132: `test_spine_command_never_authorizes_a_commit_from_the_repl` → `_run_main`
- line 138: `test_run_command_executes_the_full_operating_loop` → `_run_main`
- line 145: `test_run_command_with_no_intent_shows_usage` → `_run_main`
- line 154: `test_permissions_command_reports_zero_active_grants_by_default` → `_run_main`
- line 159: `test_grant_command_requires_explicit_granting_authority` → `_run_main`
- line 164: `test_grant_then_permissions_shows_the_new_grant` → `_run_main`
- line 175: `test_grant_rejects_unknown_capability_from_the_repl` → `_run_main`
- line 180: `test_revoke_command_removes_an_active_grant` → `_run_main`

### `tests/test_decision_state_machine.py`
- line 9: `<module>` → `Path`
- line 14: `_fresh_bridge` → `path.exists`
- line 15: `_fresh_bridge` → `shutil.rmtree`
- line 16: `_fresh_bridge` → `LanternBridge`
- line 17: `_fresh_bridge` → `bridge.ensure_identity`
- line 18: `_fresh_bridge` → `bridge.startup`
- line 23: `_add_evidence` → `bridge.observe`
- line 24: `_add_evidence` → `bridge.add_evidence`
- line 28: `test_high_maps_to_proceed` → `_fresh_bridge`
- line 29: `test_high_maps_to_proceed` → `_add_evidence`
- line 30: `test_high_maps_to_proceed` → `_add_evidence`
- line 31: `test_high_maps_to_proceed` → `ConfidenceField(bridge).evaluate`
- line 31: `test_high_maps_to_proceed` → `ConfidenceField`
- line 32: `test_high_maps_to_proceed` → `DecisionStateMachine().recommend`
- line 32: `test_high_maps_to_proceed` → `DecisionStateMachine`
- line 38: `test_medium_maps_to_preserve_gather` → `_fresh_bridge`
- line 39: `test_medium_maps_to_preserve_gather` → `_add_evidence`
- line 40: `test_medium_maps_to_preserve_gather` → `ConfidenceField(bridge).evaluate`
- line 40: `test_medium_maps_to_preserve_gather` → `ConfidenceField`
- line 41: `test_medium_maps_to_preserve_gather` → `DecisionStateMachine().recommend`
- line 41: `test_medium_maps_to_preserve_gather` → `DecisionStateMachine`
- line 48: `test_low_maps_to_branch_investigate` → `_fresh_bridge`
- line 49: `test_low_maps_to_branch_investigate` → `ConfidenceField(bridge).evaluate`
- line 49: `test_low_maps_to_branch_investigate` → `ConfidenceField`
- line 50: `test_low_maps_to_branch_investigate` → `DecisionStateMachine().recommend`
- line 50: `test_low_maps_to_branch_investigate` → `DecisionStateMachine`
- line 56: `test_blocked_maps_to_stop_repair` → `_fresh_bridge`
- line 57: `test_blocked_maps_to_stop_repair` → `_add_evidence`
- line 58: `test_blocked_maps_to_stop_repair` → `open`
- line 59: `test_blocked_maps_to_stop_repair` → `f.write`
- line 60: `test_blocked_maps_to_stop_repair` → `ConfidenceField(bridge).evaluate`
- line 60: `test_blocked_maps_to_stop_repair` → `ConfidenceField`
- line 61: `test_blocked_maps_to_stop_repair` → `DecisionStateMachine().recommend`
- line 61: `test_blocked_maps_to_stop_repair` → `DecisionStateMachine`
- line 67: `test_illegal_transition_rejected` → `_fresh_bridge`
- line 68: `test_illegal_transition_rejected` → `ConfidenceField(bridge).evaluate`
- line 68: `test_illegal_transition_rejected` → `ConfidenceField`
- line 69: `test_illegal_transition_rejected` → `DecisionStateMachine`
- line 71: `test_illegal_transition_rejected` → `machine.recommend`
- line 73: `test_illegal_transition_rejected` → `str`
- line 75: `test_illegal_transition_rejected` → `AssertionError`
- line 79: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `_fresh_bridge`
- line 80: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `_add_evidence`
- line 81: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `ConfidenceField(bridge).evaluate`
- line 81: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `ConfidenceField`
- line 82: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `DecisionStateMachine`
- line 83: `test_blocked_to_high_allowed_only_after_explicit_recovery_event` → `machine.recommend`
- line 89: `test_authorization_boundary_explicitly_preserved` → `_fresh_bridge`
- line 90: `test_authorization_boundary_explicitly_preserved` → `_add_evidence`
- line 91: `test_authorization_boundary_explicitly_preserved` → `ConfidenceField(bridge).evaluate`
- line 91: `test_authorization_boundary_explicitly_preserved` → `ConfidenceField`
- line 92: `test_authorization_boundary_explicitly_preserved` → `DecisionStateMachine().recommend`
- line 92: `test_authorization_boundary_explicitly_preserved` → `DecisionStateMachine`
- line 99: `test_decision_explanation_contains_pipeline` → `_fresh_bridge`
- line 100: `test_decision_explanation_contains_pipeline` → `ConfidenceField(bridge).evaluate`
- line 100: `test_decision_explanation_contains_pipeline` → `ConfidenceField`
- line 101: `test_decision_explanation_contains_pipeline` → `DecisionStateMachine().recommend`
- line 101: `test_decision_explanation_contains_pipeline` → `DecisionStateMachine`
- line 107: `test_prompt_compiler_compatibility_path` → `_fresh_bridge`
- line 108: `test_prompt_compiler_compatibility_path` → `PromptCompiler(bridge=bridge).compile`
- line 108: `test_prompt_compiler_compatibility_path` → `PromptCompiler`
- line 109: `test_prompt_compiler_compatibility_path` → `ConfidenceField(bridge).evaluate`
- line 109: `test_prompt_compiler_compatibility_path` → `ConfidenceField`
- line 110: `test_prompt_compiler_compatibility_path` → `DecisionStateMachine().recommend`
- line 110: `test_prompt_compiler_compatibility_path` → `DecisionStateMachine`
- line 115: `test_blocked_never_silently_becomes_low` → `_fresh_bridge`
- line 116: `test_blocked_never_silently_becomes_low` → `_add_evidence`
- line 117: `test_blocked_never_silently_becomes_low` → `open`
- line 118: `test_blocked_never_silently_becomes_low` → `f.write`
- line 119: `test_blocked_never_silently_becomes_low` → `ConfidenceField(bridge).evaluate`
- line 119: `test_blocked_never_silently_becomes_low` → `ConfidenceField`
- line 121: `test_blocked_never_silently_becomes_low` → `DecisionStateMachine().recommend`
- line 121: `test_blocked_never_silently_becomes_low` → `DecisionStateMachine`

### `tests/test_harness_status.py`
- line 5: `<module>` → `sys.path.insert`
- line 5: `<module>` → `str`
- line 5: `<module>` → `Path(__file__).resolve`
- line 5: `<module>` → `Path`
- line 13: `test_status_report_reflects_actual_bridge_state` → `Path`
- line 13: `test_status_report_reflects_actual_bridge_state` → `tempfile.mkdtemp`
- line 14: `test_status_report_reflects_actual_bridge_state` → `LanternBridge`
- line 15: `test_status_report_reflects_actual_bridge_state` → `bridge.ensure_identity`
- line 16: `test_status_report_reflects_actual_bridge_state` → `bridge.startup`
- line 17: `test_status_report_reflects_actual_bridge_state` → `bridge.observe`
- line 19: `test_status_report_reflects_actual_bridge_state` → `status_report`
- line 19: `test_status_report_reflects_actual_bridge_state` → `ToolBoundary`
- line 30: `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions` → `Path`
- line 30: `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions` → `tempfile.mkdtemp`
- line 31: `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions` → `LanternBridge`
- line 32: `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions` → `status_report`
- line 32: `test_status_report_labels_spine_and_reality_boundary_as_implemented_harness_additions` → `ToolBoundary`
- line 39: `test_status_report_self_model_and_operating_loop_reported_as_implemented` → `Path`
- line 39: `test_status_report_self_model_and_operating_loop_reported_as_implemented` → `tempfile.mkdtemp`
- line 40: `test_status_report_self_model_and_operating_loop_reported_as_implemented` → `LanternBridge`
- line 41: `test_status_report_self_model_and_operating_loop_reported_as_implemented` → `status_report`
- line 41: `test_status_report_self_model_and_operating_loop_reported_as_implemented` → `ToolBoundary`
- line 50: `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh` → `Path`
- line 50: `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh` → `tempfile.mkdtemp`
- line 51: `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh` → `LanternBridge`
- line 52: `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh` → `status_report`
- line 52: `test_status_report_perspective_engine_is_labeled_partial_not_full_mesh` → `ToolBoundary`
- line 58: `test_status_report_prompt_compiler_reported_as_implemented` → `Path`
- line 58: `test_status_report_prompt_compiler_reported_as_implemented` → `tempfile.mkdtemp`
- line 59: `test_status_report_prompt_compiler_reported_as_implemented` → `LanternBridge`
- line 60: `test_status_report_prompt_compiler_reported_as_implemented` → `status_report`
- line 60: `test_status_report_prompt_compiler_reported_as_implemented` → `ToolBoundary`
- line 65: `test_format_status_report_produces_readable_text` → `Path`
- line 65: `test_format_status_report_produces_readable_text` → `tempfile.mkdtemp`
- line 66: `test_format_status_report_produces_readable_text` → `LanternBridge`
- line 67: `test_format_status_report_produces_readable_text` → `status_report`
- line 67: `test_format_status_report_produces_readable_text` → `ToolBoundary`
- line 68: `test_format_status_report_produces_readable_text` → `format_status_report`
- line 75: `test_status_report_mcp_server_status_reflects_real_sdk_availability` → `Path`
- line 75: `test_status_report_mcp_server_status_reflects_real_sdk_availability` → `tempfile.mkdtemp`
- line 76: `test_status_report_mcp_server_status_reflects_real_sdk_availability` → `LanternBridge`
- line 77: `test_status_report_mcp_server_status_reflects_real_sdk_availability` → `status_report`
- line 77: `test_status_report_mcp_server_status_reflects_real_sdk_availability` → `ToolBoundary`
- line 87: `test_status_report_transfer_manifest_reported_as_implemented` → `Path`
- line 87: `test_status_report_transfer_manifest_reported_as_implemented` → `tempfile.mkdtemp`
- line 88: `test_status_report_transfer_manifest_reported_as_implemented` → `LanternBridge`
- line 89: `test_status_report_transfer_manifest_reported_as_implemented` → `status_report`
- line 89: `test_status_report_transfer_manifest_reported_as_implemented` → `ToolBoundary`
- line 91: `test_status_report_transfer_manifest_reported_as_implemented` → `format_status_report`
- line 96: `test_status_report_permission_authority_reported_as_implemented` → `Path`
- line 96: `test_status_report_permission_authority_reported_as_implemented` → `tempfile.mkdtemp`
- line 97: `test_status_report_permission_authority_reported_as_implemented` → `LanternBridge`
- line 98: `test_status_report_permission_authority_reported_as_implemented` → `status_report`
- line 98: `test_status_report_permission_authority_reported_as_implemented` → `ToolBoundary`
- line 101: `test_status_report_permission_authority_reported_as_implemented` → `format_status_report`

### `tests/test_mcp_server.py`
- line 8: `<module>` → `pytest.importorskip`
- line 13: `<module>` → `Path`
- line 18: `_fresh_context` → `path.exists`
- line 19: `_fresh_context` → `shutil.rmtree`
- line 20: `_fresh_context` → `LanternMCPContext`
- line 24: `_call` → `asyncio.run`
- line 24: `_call` → `server.call_tool`
- line 25: `_call` → `getattr`
- line 26: `_call` → `hasattr`
- line 27: `_call` → `isinstance`
- line 27: `_call` → `json.loads`
- line 31: `test_server_exposes_expected_tool_names` → `_fresh_context`
- line 32: `test_server_exposes_expected_tool_names` → `build_server`
- line 33: `test_server_exposes_expected_tool_names` → `asyncio.run`
- line 33: `test_server_exposes_expected_tool_names` → `server.list_tools`
- line 41: `test_server_exposes_expected_tool_names` → `expected.issubset`
- line 45: `test_lantern_observe_records_a_real_observation` → `_fresh_context`
- line 46: `test_lantern_observe_records_a_real_observation` → `build_server`
- line 47: `test_lantern_observe_records_a_real_observation` → `ctx.bridge.status`
- line 48: `test_lantern_observe_records_a_real_observation` → `_call`
- line 49: `test_lantern_observe_records_a_real_observation` → `ctx.bridge.status`
- line 55: `test_lantern_confidence_reflects_real_evidence_state` → `_fresh_context`
- line 56: `test_lantern_confidence_reflects_real_evidence_state` → `build_server`
- line 57: `test_lantern_confidence_reflects_real_evidence_state` → `_call`
- line 58: `test_lantern_confidence_reflects_real_evidence_state` → `_call`
- line 59: `test_lantern_confidence_reflects_real_evidence_state` → `_call`
- line 61: `test_lantern_confidence_reflects_real_evidence_state` → `isinstance`
- line 65: `test_lantern_decide_never_reports_authorization` → `_fresh_context`
- line 66: `test_lantern_decide_never_reports_authorization` → `build_server`
- line 67: `test_lantern_decide_never_reports_authorization` → `_call`
- line 72: `test_lantern_compile_never_fabricates_missing_fields` → `_fresh_context`
- line 73: `test_lantern_compile_never_fabricates_missing_fields` → `build_server`
- line 74: `test_lantern_compile_never_fabricates_missing_fields` → `_call`
- line 75: `test_lantern_compile_never_fabricates_missing_fields` → `json.dumps`
- line 80: `test_lantern_self_model_lists_authorized_tools_from_real_boundary` → `_fresh_context`
- line 81: `test_lantern_self_model_lists_authorized_tools_from_real_boundary` → `build_server`
- line 82: `test_lantern_self_model_lists_authorized_tools_from_real_boundary` → `_call`
- line 88: `test_lantern_branch_open_creates_a_real_branch` → `_fresh_context`
- line 89: `test_lantern_branch_open_creates_a_real_branch` → `build_server`
- line 90: `test_lantern_branch_open_creates_a_real_branch` → `_call`
- line 93: `test_lantern_branch_open_creates_a_real_branch` → `ctx.branch_store.get`
- line 98: `test_lantern_spine_read_reflects_real_committed_entries` → `_fresh_context`
- line 99: `test_lantern_spine_read_reflects_real_committed_entries` → `build_server`
- line 100: `test_lantern_spine_read_reflects_real_committed_entries` → `_call`
- line 103: `test_lantern_spine_read_reflects_real_committed_entries` → `ctx.branch_store.open_branch`
- line 104: `test_lantern_spine_read_reflects_real_committed_entries` → `ctx.spine_committer.commit`
- line 105: `test_lantern_spine_read_reflects_real_committed_entries` → `_call`
- line 106: `test_lantern_spine_read_reflects_real_committed_entries` → `len`
- line 111: `test_lantern_witness_integrity_reports_real_chronicle_status` → `_fresh_context`
- line 112: `test_lantern_witness_integrity_reports_real_chronicle_status` → `build_server`
- line 113: `test_lantern_witness_integrity_reports_real_chronicle_status` → `_call`
- line 120: `test_server_exposes_no_tool_capable_of_external_action` → `_fresh_context`
- line 121: `test_server_exposes_no_tool_capable_of_external_action` → `build_server`
- line 122: `test_server_exposes_no_tool_capable_of_external_action` → `asyncio.run`
- line 122: `test_server_exposes_no_tool_capable_of_external_action` → `server.list_tools`
- line 131: `test_build_server_raises_clear_error_when_sdk_unavailable` → `monkeypatch.setattr`
- line 133: `test_build_server_raises_clear_error_when_sdk_unavailable` → `mod.build_server`
- line 133: `test_build_server_raises_clear_error_when_sdk_unavailable` → `_fresh_context`
- line 134: `test_build_server_raises_clear_error_when_sdk_unavailable` → `AssertionError`
- line 136: `test_build_server_raises_clear_error_when_sdk_unavailable` → `str`
- line 143: `test_lantern_evaluate_intent_runs_the_real_operating_loop` → `_fresh_context`
- line 144: `test_lantern_evaluate_intent_runs_the_real_operating_loop` → `build_server`
- line 145: `test_lantern_evaluate_intent_runs_the_real_operating_loop` → `ctx.bridge.status`
- line 146: `test_lantern_evaluate_intent_runs_the_real_operating_loop` → `_call`
- line 150: `test_lantern_evaluate_intent_runs_the_real_operating_loop` → `ctx.bridge.status`
- line 163: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `_fresh_context`
- line 164: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `build_server`
- line 165: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `asyncio.run`
- line 165: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `server.list_tools`
- line 166: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `next`
- line 167: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `set`
- line 167: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `(tool.input_schema or {}).get('properties', {}).keys`
- line 167: `test_lantern_evaluate_intent_has_no_tool_name_parameter` → `(tool.input_schema or {}).get`
- line 173: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `_fresh_context`
- line 174: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `build_server`
- line 175: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `ctx.bridge.observe`
- line 176: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `_call`
- line 181: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `len`
- line 182: `test_lantern_transfer_manifest_reports_real_state_and_no_secrets` → `str`
- line 191: `test_lantern_permissions_reports_zero_grants_by_default` → `_fresh_context`
- line 192: `test_lantern_permissions_reports_zero_grants_by_default` → `build_server`
- line 193: `test_lantern_permissions_reports_zero_grants_by_default` → `_call`
- line 199: `test_lantern_permissions_reflects_a_real_in_process_grant` → `_fresh_context`
- line 200: `test_lantern_permissions_reflects_a_real_in_process_grant` → `build_server`
- line 201: `test_lantern_permissions_reflects_a_real_in_process_grant` → `ctx.permission_authority.grant`
- line 208: `test_lantern_permissions_reflects_a_real_in_process_grant` → `_call`
- line 218: `test_server_exposes_no_grant_or_revoke_tool_over_mcp` → `_fresh_context`
- line 219: `test_server_exposes_no_grant_or_revoke_tool_over_mcp` → `build_server`
- line 220: `test_server_exposes_no_grant_or_revoke_tool_over_mcp` → `asyncio.run`
- line 220: `test_server_exposes_no_grant_or_revoke_tool_over_mcp` → `server.list_tools`

### `tests/test_mcp_server_live_stdio.py`
- line 17: `<module>` → `pytest.importorskip`
- line 23: `<module>` → `pytest.mark.skipif`
- line 27: `<module>` → `Path(__file__).resolve`
- line 27: `<module>` → `Path`
- line 31: `_fresh_target` → `Path`
- line 31: `_fresh_target` → `tempfile.mkdtemp`
- line 32: `_fresh_target` → `StdioServerTarget`
- line 36: `_fresh_target` → `str`
- line 37: `_fresh_target` → `str`
- line 42: `test_real_stdio_subprocess_lists_all_expected_tools` → `_fresh_target`
- line 43: `test_real_stdio_subprocess_lists_all_expected_tools` → `StdioMCPClient`
- line 44: `test_real_stdio_subprocess_lists_all_expected_tools` → `client.discover`
- line 51: `test_real_stdio_subprocess_lists_all_expected_tools` → `expected.issubset`
- line 57: `test_real_stdio_subprocess_records_a_real_observation` → `_fresh_target`
- line 58: `test_real_stdio_subprocess_records_a_real_observation` → `StdioMCPClient`
- line 60: `test_real_stdio_subprocess_records_a_real_observation` → `client.execute`
- line 61: `test_real_stdio_subprocess_records_a_real_observation` → `MCPExecutionRequest`
- line 69: `test_real_stdio_subprocess_records_a_real_observation` → `result.get`
- line 69: `test_real_stdio_subprocess_records_a_real_observation` → `result.get`
- line 75: `test_real_stdio_subprocess_never_authorizes_a_decision` → `_fresh_target`
- line 76: `test_real_stdio_subprocess_never_authorizes_a_decision` → `StdioMCPClient`
- line 77: `test_real_stdio_subprocess_never_authorizes_a_decision` → `client.execute`
- line 78: `test_real_stdio_subprocess_never_authorizes_a_decision` → `MCPExecutionRequest`
- line 86: `test_real_stdio_subprocess_never_authorizes_a_decision` → `result.get`
- line 87: `test_real_stdio_subprocess_never_authorizes_a_decision` → `result.get`
- line 89: `test_real_stdio_subprocess_never_authorizes_a_decision` → `json.loads`
- line 90: `test_real_stdio_subprocess_never_authorizes_a_decision` → `payload.get`

### `tests/test_operating_loop.py`
- line 10: `<module>` → `Path`
- line 15: `_fresh_bridge` → `path.exists`
- line 16: `_fresh_bridge` → `shutil.rmtree`
- line 17: `_fresh_bridge` → `LanternBridge`
- line 18: `_fresh_bridge` → `bridge.ensure_identity`
- line 19: `_fresh_bridge` → `bridge.startup`
- line 24: `test_run_records_a_real_observation` → `_fresh_bridge`
- line 25: `test_run_records_a_real_observation` → `ToolBoundary`
- line 26: `test_run_records_a_real_observation` → `OperatingLoop`
- line 27: `test_run_records_a_real_observation` → `bridge.status`
- line 28: `test_run_records_a_real_observation` → `loop.run`
- line 29: `test_run_records_a_real_observation` → `bridge.status`
- line 35: `test_run_without_tool_name_does_not_attempt_action` → `_fresh_bridge`
- line 36: `test_run_without_tool_name_does_not_attempt_action` → `ToolBoundary`
- line 37: `test_run_without_tool_name_does_not_attempt_action` → `OperatingLoop`
- line 38: `test_run_without_tool_name_does_not_attempt_action` → `loop.run`
- line 43: `test_run_with_unauthorized_tool_never_reports_real_success` → `_fresh_bridge`
- line 44: `test_run_with_unauthorized_tool_never_reports_real_success` → `ToolBoundary`
- line 45: `test_run_with_unauthorized_tool_never_reports_real_success` → `tb.register`
- line 45: `test_run_with_unauthorized_tool_never_reports_real_success` → `ToolDescriptor`
- line 46: `test_run_with_unauthorized_tool_never_reports_real_success` → `OperatingLoop`
- line 47: `test_run_with_unauthorized_tool_never_reports_real_success` → `loop.run`
- line 49: `test_run_with_unauthorized_tool_never_reports_real_success` → `result.action_record.is_real_success`
- line 54: `test_run_with_authorized_tool_produces_real_result` → `_fresh_bridge`
- line 55: `test_run_with_authorized_tool_produces_real_result` → `ToolBoundary`
- line 56: `test_run_with_authorized_tool_produces_real_result` → `tb.register`
- line 56: `test_run_with_authorized_tool_produces_real_result` → `ToolDescriptor`
- line 57: `test_run_with_authorized_tool_produces_real_result` → `tb.authorize`
- line 58: `test_run_with_authorized_tool_produces_real_result` → `OperatingLoop`
- line 59: `test_run_with_authorized_tool_produces_real_result` → `loop.run`
- line 60: `test_run_with_authorized_tool_produces_real_result` → `result.action_record.is_real_success`
- line 65: `test_run_produces_confidence_and_decision_for_every_call` → `_fresh_bridge`
- line 66: `test_run_produces_confidence_and_decision_for_every_call` → `ToolBoundary`
- line 67: `test_run_produces_confidence_and_decision_for_every_call` → `OperatingLoop`
- line 68: `test_run_produces_confidence_and_decision_for_every_call` → `loop.run`
- line 74: `test_open_branch_creates_a_real_branch_linked_to_the_observation` → `_fresh_bridge`
- line 75: `test_open_branch_creates_a_real_branch_linked_to_the_observation` → `ToolBoundary`
- line 76: `test_open_branch_creates_a_real_branch_linked_to_the_observation` → `OperatingLoop`
- line 77: `test_open_branch_creates_a_real_branch_linked_to_the_observation` → `loop.run`
- line 84: `test_open_branch_without_concept_is_skipped_not_fabricated` → `_fresh_bridge`
- line 85: `test_open_branch_without_concept_is_skipped_not_fabricated` → `ToolBoundary`
- line 86: `test_open_branch_without_concept_is_skipped_not_fabricated` → `OperatingLoop`
- line 87: `test_open_branch_without_concept_is_skipped_not_fabricated` → `loop.run`
- line 89: `test_open_branch_without_concept_is_skipped_not_fabricated` → `any`
- line 93: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `_fresh_bridge`
- line 94: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `ToolBoundary`
- line 95: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `OperatingLoop`
- line 97: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `Perspective`
- line 98: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `Perspective`
- line 100: `test_run_uses_perspective_differential_when_multiple_perspectives_given` → `loop.run`
- line 106: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `_fresh_bridge`
- line 107: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `bridge.observe`
- line 108: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `open`
- line 109: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `f.write`
- line 110: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `ToolBoundary`
- line 111: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `OperatingLoop`
- line 112: `test_integrity_failure_propagates_to_blocked_decision_end_to_end` → `loop.run`
- line 119: `test_empty_intent_rejected` → `_fresh_bridge`
- line 120: `test_empty_intent_rejected` → `ToolBoundary`
- line 121: `test_empty_intent_rejected` → `OperatingLoop`
- line 123: `test_empty_intent_rejected` → `loop.run`
- line 124: `test_empty_intent_rejected` → `AssertionError`
- line 130: `test_format_produces_readable_summary` → `_fresh_bridge`
- line 131: `test_format_produces_readable_summary` → `ToolBoundary`
- line 132: `test_format_produces_readable_summary` → `OperatingLoop`
- line 133: `test_format_produces_readable_summary` → `loop.run`
- line 134: `test_format_produces_readable_summary` → `result.format`

### `tests/test_permission_authority.py`
- line 4: `<module>` → `sys.path.insert`
- line 4: `<module>` → `str`
- line 4: `<module>` → `Path(__file__).resolve`
- line 4: `<module>` → `Path`
- line 23: `_passed` → `dict`
- line 32: `_passed` → `defaults.update`
- line 33: `_passed` → `AlignmentResult`
- line 37: `_failed` → `dict`
- line 46: `_failed` → `defaults.update`
- line 47: `_failed` → `AlignmentResult`
- line 53: `test_grant_requires_explicit_granting_authority` → `PermissionAuthority`
- line 54: `test_grant_requires_explicit_granting_authority` → `pytest.raises`
- line 55: `test_grant_requires_explicit_granting_authority` → `authority.grant`
- line 70: `test_permission_authority_cannot_self_grant` → `PermissionAuthority`
- line 71: `test_permission_authority_cannot_self_grant` → `pytest.raises`
- line 72: `test_permission_authority_cannot_self_grant` → `authority.grant`
- line 79: `test_permission_authority_cannot_self_grant` → `authority.all_grants`
- line 83: `test_grant_rejects_unknown_capability_category` → `PermissionAuthority`
- line 84: `test_grant_rejects_unknown_capability_category` → `pytest.raises`
- line 85: `test_grant_rejects_unknown_capability_category` → `authority.grant`
- line 95: `test_grant_rejects_empty_scope` → `PermissionAuthority`
- line 96: `test_grant_rejects_empty_scope` → `pytest.raises`
- line 97: `test_grant_rejects_empty_scope` → `authority.grant`
- line 107: `test_grant_and_active_grants_round_trip` → `PermissionAuthority`
- line 108: `test_grant_and_active_grants_round_trip` → `authority.grant`
- line 116: `test_grant_and_active_grants_round_trip` → `authority.active_grants`
- line 117: `test_grant_and_active_grants_round_trip` → `len`
- line 122: `test_revoke_requires_explicit_granting_authority` → `PermissionAuthority`
- line 123: `test_revoke_requires_explicit_granting_authority` → `authority.grant`
- line 127: `test_revoke_requires_explicit_granting_authority` → `pytest.raises`
- line 128: `test_revoke_requires_explicit_granting_authority` → `authority.revoke`
- line 132: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `PermissionAuthority`
- line 133: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `authority.grant`
- line 137: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `authority.revoke`
- line 139: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `authority.active_grants`
- line 140: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `authority.all_grants`
- line 141: `test_revoke_marks_grant_revoked_and_it_stops_matching` → `len`
- line 146: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `PermissionAuthority`
- line 147: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `authority.grant`
- line 151: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `len`
- line 151: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `authority.active_grants`
- line 152: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `len`
- line 152: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `authority.active_grants`
- line 153: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `len`
- line 153: `test_expired_grant_does_not_match_at_or_after_expiry_step` → `authority.active_grants`
- line 159: `test_authorized_and_aligned_is_act` → `PermissionAuthority`
- line 160: `test_authorized_and_aligned_is_act` → `authority.grant`
- line 164: `test_authorized_and_aligned_is_act` → `authority.check`
- line 167: `test_authorized_and_aligned_is_act` → `_passed`
- line 174: `test_authorized_but_misaligned_is_stop_and_reassess` → `PermissionAuthority`
- line 175: `test_authorized_but_misaligned_is_stop_and_reassess` → `authority.grant`
- line 179: `test_authorized_but_misaligned_is_stop_and_reassess` → `authority.check`
- line 182: `test_authorized_but_misaligned_is_stop_and_reassess` → `_failed`
- line 186: `test_authorized_but_misaligned_is_stop_and_reassess` → `any`
- line 190: `test_aligned_but_not_authorized_is_ask_operator` → `PermissionAuthority`
- line 191: `test_aligned_but_not_authorized_is_ask_operator` → `authority.check`
- line 194: `test_aligned_but_not_authorized_is_ask_operator` → `_passed`
- line 201: `test_neither_authorized_nor_aligned_is_refuse` → `PermissionAuthority`
- line 202: `test_neither_authorized_nor_aligned_is_refuse` → `authority.check`
- line 205: `test_neither_authorized_nor_aligned_is_refuse` → `_failed`
- line 212: `test_unknown_capability_is_flagged_as_new_capability_and_cannot_be_authorized` → `PermissionAuthority`
- line 213: `test_unknown_capability_is_flagged_as_new_capability_and_cannot_be_authorized` → `authority.check`
- line 216: `test_unknown_capability_is_flagged_as_new_capability_and_cannot_be_authorized` → `_passed`
- line 226: `test_file_modification_grant_does_not_authorize_external_communication` → `PermissionAuthority`
- line 227: `test_file_modification_grant_does_not_authorize_external_communication` → `authority.grant`
- line 231: `test_file_modification_grant_does_not_authorize_external_communication` → `authority.check`
- line 234: `test_file_modification_grant_does_not_authorize_external_communication` → `_passed`
- line 241: `test_release_publication_grant_does_not_authorize_wallet_or_payment_authority` → `PermissionAuthority`
- line 242: `test_release_publication_grant_does_not_authorize_wallet_or_payment_authority` → `authority.grant`
- line 246: `test_release_publication_grant_does_not_authorize_wallet_or_payment_authority` → `authority.check`
- line 249: `test_release_publication_grant_does_not_authorize_wallet_or_payment_authority` → `_passed`
- line 255: `test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service` → `PermissionAuthority`
- line 256: `test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service` → `authority.grant`
- line 260: `test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service` → `authority.check`
- line 263: `test_one_mcp_server_authorization_does_not_authorize_unrelated_external_service` → `_passed`
- line 269: `test_never_inherits_categories_are_flagged_even_when_unauthorized` → `PermissionAuthority`
- line 271: `test_never_inherits_categories_are_flagged_even_when_unauthorized` → `authority.check`
- line 274: `test_never_inherits_categories_are_flagged_even_when_unauthorized` → `_passed`
- line 278: `test_never_inherits_categories_are_flagged_even_when_unauthorized` → `any`
- line 289: `test_permission_authority_grants_do_not_persist_across_instances` → `PermissionAuthority`
- line 290: `test_permission_authority_grants_do_not_persist_across_instances` → `first.grant`
- line 294: `test_permission_authority_grants_do_not_persist_across_instances` → `len`
- line 294: `test_permission_authority_grants_do_not_persist_across_instances` → `first.active_grants`
- line 296: `test_permission_authority_grants_do_not_persist_across_instances` → `PermissionAuthority`
- line 297: `test_permission_authority_grants_do_not_persist_across_instances` → `second.active_grants`
- line 298: `test_permission_authority_grants_do_not_persist_across_instances` → `second.all_grants`
- line 302: `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one` → `PermissionAuthority`
- line 303: `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one` → `first.grant`
- line 307: `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one` → `PermissionAuthority`
- line 308: `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one` → `receiving_operator_authority.check`
- line 311: `test_a_previously_authorized_capability_in_one_authority_instance_is_unauthorized_in_a_fresh_one` → `_passed`
- line 320: `test_new_authority_request_format_matches_directive_example_shape` → `PermissionAuthority`
- line 321: `test_new_authority_request_format_matches_directive_example_shape` → `authority.check`
- line 324: `test_new_authority_request_format_matches_directive_example_shape` → `_passed`
- line 327: `test_new_authority_request_format_matches_directive_example_shape` → `authority.format_new_authority_request`
- line 328: `test_new_authority_request_format_matches_directive_example_shape` → `text.startswith`
- line 339: `test_action_complete_format_is_informational_not_a_request` → `PermissionAuthority`
- line 340: `test_action_complete_format_is_informational_not_a_request` → `authority.grant`
- line 344: `test_action_complete_format_is_informational_not_a_request` → `authority.check`
- line 347: `test_action_complete_format_is_informational_not_a_request` → `_passed`
- line 350: `test_action_complete_format_is_informational_not_a_request` → `authority.format_action_complete`
- line 351: `test_action_complete_format_is_informational_not_a_request` → `text.startswith`
- line 359: `test_check_result_to_dict_answers_auditability_questions` → `PermissionAuthority`
- line 360: `test_check_result_to_dict_answers_auditability_questions` → `authority.grant`
- line 364: `test_check_result_to_dict_answers_auditability_questions` → `authority.check`
- line 367: `test_check_result_to_dict_answers_auditability_questions` → `_passed`
- line 370: `test_check_result_to_dict_answers_auditability_questions` → `result.to_dict`
- line 375: `test_check_result_to_dict_answers_auditability_questions` → `isinstance`

### `tests/test_perspective_differential.py`
- line 4: `<module>` → `sys.path.insert`
- line 4: `<module>` → `str`
- line 4: `<module>` → `Path(__file__).resolve`
- line 4: `<module>` → `Path`
- line 14: `test_none_input_rejected` → `PerspectiveDifferentialEngine`
- line 16: `test_none_input_rejected` → `__import__('pytest').raises`
- line 16: `test_none_input_rejected` → `__import__`
- line 17: `test_none_input_rejected` → `engine.compare`
- line 21: `test_single_perspective_is_not_applicable_not_fabricated` → `PerspectiveDifferentialEngine`
- line 22: `test_single_perspective_is_not_applicable_not_fabricated` → `Perspective`
- line 23: `test_single_perspective_is_not_applicable_not_fabricated` → `engine.compare`
- line 29: `test_empty_list_is_not_applicable` → `PerspectiveDifferentialEngine`
- line 30: `test_empty_list_is_not_applicable` → `engine.compare`
- line 35: `test_two_identical_perspectives_have_zero_variance` → `PerspectiveDifferentialEngine`
- line 36: `test_two_identical_perspectives_have_zero_variance` → `Perspective`
- line 37: `test_two_identical_perspectives_have_zero_variance` → `Perspective`
- line 38: `test_two_identical_perspectives_have_zero_variance` → `engine.compare`
- line 45: `test_diverging_perspectives_identify_primary_divergence_dimension` → `PerspectiveDifferentialEngine`
- line 46: `test_diverging_perspectives_identify_primary_divergence_dimension` → `Perspective`
- line 47: `test_diverging_perspectives_identify_primary_divergence_dimension` → `Perspective`
- line 48: `test_diverging_perspectives_identify_primary_divergence_dimension` → `engine.compare`
- line 57: `test_does_not_select_a_winner` → `PerspectiveDifferentialEngine`
- line 58: `test_does_not_select_a_winner` → `Perspective`
- line 59: `test_does_not_select_a_winner` → `Perspective`
- line 60: `test_does_not_select_a_winner` → `engine.compare`
- line 61: `test_does_not_select_a_winner` → `result.to_dict`
- line 68: `test_three_perspectives_variance_computed` → `PerspectiveDifferentialEngine`
- line 70: `test_three_perspectives_variance_computed` → `Perspective`
- line 71: `test_three_perspectives_variance_computed` → `Perspective`
- line 72: `test_three_perspectives_variance_computed` → `Perspective`
- line 74: `test_three_perspectives_variance_computed` → `engine.compare`
- line 76: `test_three_perspectives_variance_computed` → `len`
- line 80: `test_to_dict_round_trips` → `PerspectiveDifferentialEngine`
- line 81: `test_to_dict_round_trips` → `Perspective`
- line 82: `test_to_dict_round_trips` → `Perspective`
- line 83: `test_to_dict_round_trips` → `engine.compare`
- line 84: `test_to_dict_round_trips` → `result.to_dict`
- line 86: `test_to_dict_round_trips` → `len`

### `tests/test_prompt_compiler.py`
- line 6: `<module>` → `sys.path.insert`
- line 6: `<module>` → `str`
- line 6: `<module>` → `Path(__file__).resolve`
- line 6: `<module>` → `Path`
- line 13: `_fresh_bridge` → `Path`
- line 13: `_fresh_bridge` → `tempfile.mkdtemp`
- line 14: `_fresh_bridge` → `LanternBridge`
- line 15: `_fresh_bridge` → `bridge.ensure_identity`
- line 16: `_fresh_bridge` → `bridge.startup`
- line 21: `test_rejects_empty_request` → `PromptCompiler`
- line 23: `test_rejects_empty_request` → `__import__('pytest').raises`
- line 23: `test_rejects_empty_request` → `__import__`
- line 24: `test_rejects_empty_request` → `compiler.compile`
- line 25: `test_rejects_empty_request` → `__import__('pytest').raises`
- line 25: `test_rejects_empty_request` → `__import__`
- line 26: `test_rejects_empty_request` → `compiler.compile`
- line 30: `test_lightweight_mode_for_ordinary_request` → `PromptCompiler`
- line 31: `test_lightweight_mode_for_ordinary_request` → `compiler.compile`
- line 38: `test_heavyweight_mode_triggered_by_consequential_keyword` → `PromptCompiler`
- line 39: `test_heavyweight_mode_triggered_by_consequential_keyword` → `compiler.compile`
- line 46: `test_consequential_override_forces_heavyweight` → `PromptCompiler`
- line 47: `test_consequential_override_forces_heavyweight` → `compiler.compile`
- line 52: `test_consequential_override_forces_lightweight` → `PromptCompiler`
- line 53: `test_consequential_override_forces_lightweight` → `compiler.compile`
- line 58: `test_missing_information_marked_not_provided_not_fabricated` → `PromptCompiler`
- line 59: `test_missing_information_marked_not_provided_not_fabricated` → `compiler.compile`
- line 70: `test_prove_x_pattern_is_reframed_not_assumed` → `PromptCompiler`
- line 71: `test_prove_x_pattern_is_reframed_not_assumed` → `compiler.compile`
- line 74: `test_prove_x_pattern_is_reframed_not_assumed` → `any`
- line 80: `test_no_concept_supplied_means_evidence_fields_not_provided_not_fabricated` → `PromptCompiler`
- line 81: `test_no_concept_supplied_means_evidence_fields_not_provided_not_fabricated` → `compiler.compile`
- line 87: `test_concept_with_no_recorded_evidence_is_unknown_not_fabricated` → `_fresh_bridge`
- line 88: `test_concept_with_no_recorded_evidence_is_unknown_not_fabricated` → `PromptCompiler`
- line 89: `test_concept_with_no_recorded_evidence_is_unknown_not_fabricated` → `compiler.compile`
- line 95: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `_fresh_bridge`
- line 96: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `bridge.observe`
- line 97: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `bridge.add_evidence`
- line 98: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `bridge.observe`
- line 99: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `bridge.add_evidence`
- line 101: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `PromptCompiler`
- line 102: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `compiler.compile`
- line 108: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `len`
- line 109: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `any`
- line 110: `test_real_evidence_and_contradiction_are_surfaced_when_present` → `any`
- line 114: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `_fresh_bridge`
- line 117: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `bridge.observe`
- line 118: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `bridge.add_evidence`
- line 119: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `bridge.observe`
- line 120: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `bridge.add_evidence`
- line 122: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `PromptCompiler`
- line 123: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `compiler.compile`
- line 129: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `isinstance`
- line 130: `test_contradiction_detection_surfaces_when_kernel_actually_detects_one` → `isinstance`
- line 137: `test_secrets_never_enter_compiled_prompt` → `PromptCompiler`
- line 138: `test_secrets_never_enter_compiled_prompt` → `compiler.compile`
- line 140: `test_secrets_never_enter_compiled_prompt` → `str`
- line 146: `test_malformed_input_types_rejected_not_silently_coerced` → `PromptCompiler`
- line 148: `test_malformed_input_types_rejected_not_silently_coerced` → `__import__('pytest').raises`
- line 148: `test_malformed_input_types_rejected_not_silently_coerced` → `__import__`
- line 149: `test_malformed_input_types_rejected_not_silently_coerced` → `compiler.compile`
- line 153: `test_epistemic_status_field_present_and_labels_output_as_observation` → `PromptCompiler`
- line 154: `test_epistemic_status_field_present_and_labels_output_as_observation` → `compiler.compile`
- line 156: `test_epistemic_status_field_present_and_labels_output_as_observation` → `' '.join`
- line 161: `test_lightweight_still_surfaces_real_evidence_if_present` → `_fresh_bridge`
- line 162: `test_lightweight_still_surfaces_real_evidence_if_present` → `bridge.observe`
- line 163: `test_lightweight_still_surfaces_real_evidence_if_present` → `bridge.add_evidence`
- line 165: `test_lightweight_still_surfaces_real_evidence_if_present` → `PromptCompiler`
- line 166: `test_lightweight_still_surfaces_real_evidence_if_present` → `compiler.compile`
- line 169: `test_lightweight_still_surfaces_real_evidence_if_present` → `result.fields.get`
- line 173: `test_compiled_prompt_to_dict_round_trips` → `PromptCompiler`
- line 174: `test_compiled_prompt_to_dict_round_trips` → `compiler.compile`
- line 175: `test_compiled_prompt_to_dict_round_trips` → `result.to_dict`
- line 183: `test_blocked_when_chronicle_integrity_check_fails` → `_fresh_bridge`
- line 184: `test_blocked_when_chronicle_integrity_check_fails` → `bridge.observe`
- line 185: `test_blocked_when_chronicle_integrity_check_fails` → `bridge.add_evidence`
- line 188: `test_blocked_when_chronicle_integrity_check_fails` → `open`
- line 189: `test_blocked_when_chronicle_integrity_check_fails` → `f.write`
- line 191: `test_blocked_when_chronicle_integrity_check_fails` → `bridge.witness_integrity`
- line 194: `test_blocked_when_chronicle_integrity_check_fails` → `PromptCompiler`
- line 195: `test_blocked_when_chronicle_integrity_check_fails` → `compiler.compile`
- line 200: `test_blocked_when_chronicle_integrity_check_fails` → `any`

### `tests/test_reality_boundary.py`
- line 11: `<module>` → `Path`
- line 16: `_fresh_bridge` → `path.exists`
- line 17: `_fresh_bridge` → `shutil.rmtree`
- line 18: `_fresh_bridge` → `LanternBridge`
- line 19: `_fresh_bridge` → `bridge.ensure_identity`
- line 20: `_fresh_bridge` → `bridge.startup`
- line 25: `_decision` → `ConfidenceField(bridge).evaluate`
- line 25: `_decision` → `ConfidenceField`
- line 26: `_decision` → `DecisionStateMachine().recommend`
- line 26: `_decision` → `DecisionStateMachine`
- line 30: `test_propose_never_touches_external_world` → `_fresh_bridge`
- line 31: `test_propose_never_touches_external_world` → `_decision`
- line 32: `test_propose_never_touches_external_world` → `RealityBoundary`
- line 33: `test_propose_never_touches_external_world` → `rb.propose`
- line 40: `test_propose_requires_non_empty_intent` → `_fresh_bridge`
- line 41: `test_propose_requires_non_empty_intent` → `_decision`
- line 42: `test_propose_requires_non_empty_intent` → `RealityBoundary`
- line 44: `test_propose_requires_non_empty_intent` → `rb.propose`
- line 45: `test_propose_requires_non_empty_intent` → `AssertionError`
- line 51: `test_act_denied_when_tool_not_authorized` → `_fresh_bridge`
- line 52: `test_act_denied_when_tool_not_authorized` → `_decision`
- line 53: `test_act_denied_when_tool_not_authorized` → `ToolBoundary`
- line 54: `test_act_denied_when_tool_not_authorized` → `tb.register`
- line 54: `test_act_denied_when_tool_not_authorized` → `ToolDescriptor`
- line 55: `test_act_denied_when_tool_not_authorized` → `RealityBoundary`
- line 56: `test_act_denied_when_tool_not_authorized` → `rb.propose`
- line 57: `test_act_denied_when_tool_not_authorized` → `rb.act`
- line 60: `test_act_denied_when_tool_not_authorized` → `record.is_real_success`
- line 64: `test_act_real_success_only_after_explicit_authorization` → `_fresh_bridge`
- line 65: `test_act_real_success_only_after_explicit_authorization` → `_decision`
- line 66: `test_act_real_success_only_after_explicit_authorization` → `ToolBoundary`
- line 67: `test_act_real_success_only_after_explicit_authorization` → `tb.register`
- line 67: `test_act_real_success_only_after_explicit_authorization` → `ToolDescriptor`
- line 68: `test_act_real_success_only_after_explicit_authorization` → `tb.authorize`
- line 69: `test_act_real_success_only_after_explicit_authorization` → `RealityBoundary`
- line 70: `test_act_real_success_only_after_explicit_authorization` → `rb.propose`
- line 71: `test_act_real_success_only_after_explicit_authorization` → `rb.act`
- line 74: `test_act_real_success_only_after_explicit_authorization` → `record.is_real_success`
- line 79: `test_act_with_no_tool_name_is_not_executed` → `_fresh_bridge`
- line 80: `test_act_with_no_tool_name_is_not_executed` → `_decision`
- line 81: `test_act_with_no_tool_name_is_not_executed` → `ToolBoundary`
- line 82: `test_act_with_no_tool_name_is_not_executed` → `RealityBoundary`
- line 83: `test_act_with_no_tool_name_is_not_executed` → `rb.propose`
- line 84: `test_act_with_no_tool_name_is_not_executed` → `rb.act`
- line 87: `test_act_with_no_tool_name_is_not_executed` → `record.is_real_success`
- line 91: `test_simulate_can_never_report_success` → `_fresh_bridge`
- line 92: `test_simulate_can_never_report_success` → `_decision`
- line 93: `test_simulate_can_never_report_success` → `RealityBoundary`
- line 94: `test_simulate_can_never_report_success` → `rb.propose`
- line 95: `test_simulate_can_never_report_success` → `rb.simulate`
- line 99: `test_simulate_can_never_report_success` → `record.is_real_success`
- line 100: `test_simulate_can_never_report_success` → `any`
- line 104: `test_simulate_requires_reason` → `_fresh_bridge`
- line 105: `test_simulate_requires_reason` → `_decision`
- line 106: `test_simulate_requires_reason` → `RealityBoundary`
- line 107: `test_simulate_requires_reason` → `rb.propose`
- line 109: `test_simulate_requires_reason` → `rb.simulate`
- line 110: `test_simulate_requires_reason` → `AssertionError`
- line 116: `test_tool_error_is_never_reported_as_success` → `_fresh_bridge`
- line 117: `test_tool_error_is_never_reported_as_success` → `_decision`
- line 119: `test_tool_error_is_never_reported_as_success.boom` → `RuntimeError`
- line 120: `test_tool_error_is_never_reported_as_success` → `ToolBoundary`
- line 121: `test_tool_error_is_never_reported_as_success` → `tb.register`
- line 121: `test_tool_error_is_never_reported_as_success` → `ToolDescriptor`
- line 122: `test_tool_error_is_never_reported_as_success` → `tb.authorize`
- line 123: `test_tool_error_is_never_reported_as_success` → `RealityBoundary`
- line 124: `test_tool_error_is_never_reported_as_success` → `rb.propose`
- line 125: `test_tool_error_is_never_reported_as_success` → `rb.act`
- line 127: `test_tool_error_is_never_reported_as_success` → `record.is_real_success`

### `tests/test_reasoning.py`
- line 6: `<module>` → `sys.path.insert`
- line 6: `<module>` → `str`
- line 6: `<module>` → `Path(__file__).resolve`
- line 6: `<module>` → `Path`
- line 14: `test_build_engine_returns_none_when_no_provider` → `build_engine`
- line 15: `test_build_engine_returns_none_when_no_provider` → `build_engine`
- line 19: `test_build_engine_returns_none_for_unknown_provider` → `build_engine`
- line 23: `test_build_engine_returns_ollama_instance` → `build_engine`
- line 24: `test_build_engine_returns_ollama_instance` → `isinstance`
- line 29: `test_ollama_detect_reports_absence_honestly` → `OllamaEngine`
- line 30: `test_ollama_detect_reports_absence_honestly` → `engine.detect`
- line 36: `test_openai_detect_reports_missing_key` → `monkeypatch.delenv`
- line 37: `test_openai_detect_reports_missing_key` → `OpenAIEngine`
- line 38: `test_openai_detect_reports_missing_key` → `engine.detect`
- line 44: `test_anthropic_detect_never_exposes_key_value` → `monkeypatch.setenv`
- line 45: `test_anthropic_detect_never_exposes_key_value` → `AnthropicEngine`
- line 46: `test_anthropic_detect_never_exposes_key_value` → `engine.detect`
- line 55: `test_google_engine_forwards_system_message_as_system_instruction` → `monkeypatch.setenv`
- line 56: `test_google_engine_forwards_system_message_as_system_instruction` → `GoogleEngine`
- line 68: `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse.read` → `json.dumps({'candidates': [{'content': {'parts': [{'text': 'ok'}]}}]}).encode`
- line 68: `test_google_engine_forwards_system_message_as_system_instruction.FakeResponse.read` → `json.dumps`
- line 71: `test_google_engine_forwards_system_message_as_system_instruction.fake_urlopen` → `json.loads`
- line 71: `test_google_engine_forwards_system_message_as_system_instruction.fake_urlopen` → `req.data.decode`
- line 72: `test_google_engine_forwards_system_message_as_system_instruction.fake_urlopen` → `FakeResponse`
- line 76: `test_google_engine_forwards_system_message_as_system_instruction` → `monkeypatch.setattr`
- line 78: `test_google_engine_forwards_system_message_as_system_instruction` → `engine.respond`
- line 85: `test_google_engine_forwards_system_message_as_system_instruction` → `all`

### `tests/test_self_model.py`
- line 9: `<module>` → `Path`
- line 14: `_fresh_bridge` → `path.exists`
- line 15: `_fresh_bridge` → `shutil.rmtree`
- line 16: `_fresh_bridge` → `LanternBridge`
- line 17: `_fresh_bridge` → `bridge.ensure_identity`
- line 18: `_fresh_bridge` → `bridge.startup`
- line 23: `test_describe_returns_all_seven_sections` → `_fresh_bridge`
- line 24: `test_describe_returns_all_seven_sections` → `ToolBoundary`
- line 25: `test_describe_returns_all_seven_sections` → `SelfModel(bridge, tb).describe`
- line 25: `test_describe_returns_all_seven_sections` → `SelfModel`
- line 26: `test_describe_returns_all_seven_sections` → `reading.to_dict`
- line 32: `test_describe_returns_all_seven_sections` → `isinstance`
- line 36: `test_authorized_tools_reflect_real_tool_boundary_state` → `_fresh_bridge`
- line 37: `test_authorized_tools_reflect_real_tool_boundary_state` → `ToolBoundary`
- line 38: `test_authorized_tools_reflect_real_tool_boundary_state` → `tb.register`
- line 38: `test_authorized_tools_reflect_real_tool_boundary_state` → `ToolDescriptor`
- line 39: `test_authorized_tools_reflect_real_tool_boundary_state` → `SelfModel(bridge, tb).describe`
- line 39: `test_authorized_tools_reflect_real_tool_boundary_state` → `SelfModel`
- line 42: `test_authorized_tools_reflect_real_tool_boundary_state` → `tb.authorize`
- line 43: `test_authorized_tools_reflect_real_tool_boundary_state` → `SelfModel(bridge, tb).describe`
- line 43: `test_authorized_tools_reflect_real_tool_boundary_state` → `SelfModel`
- line 50: `test_self_model_is_read_only` → `_fresh_bridge`
- line 51: `test_self_model_is_read_only` → `ToolBoundary`
- line 52: `test_self_model_is_read_only` → `tb.register`
- line 52: `test_self_model_is_read_only` → `ToolDescriptor`
- line 53: `test_self_model_is_read_only` → `bridge.status`
- line 54: `test_self_model_is_read_only` → `set`
- line 55: `test_self_model_is_read_only` → `SelfModel(bridge, tb).describe`
- line 55: `test_self_model_is_read_only` → `SelfModel`
- line 56: `test_self_model_is_read_only` → `SelfModel(bridge, tb).describe`
- line 56: `test_self_model_is_read_only` → `SelfModel`
- line 57: `test_self_model_is_read_only` → `bridge.status`
- line 58: `test_self_model_is_read_only` → `set`
- line 66: `test_self_model_cannot_self_authorize` → `_fresh_bridge`
- line 67: `test_self_model_cannot_self_authorize` → `ToolBoundary`
- line 68: `test_self_model_cannot_self_authorize` → `SelfModel`
- line 70: `test_self_model_cannot_self_authorize` → `dir`
- line 70: `test_self_model_cannot_self_authorize` → `name.startswith`
- line 75: `test_operator_boundaries_always_listed` → `_fresh_bridge`
- line 76: `test_operator_boundaries_always_listed` → `ToolBoundary`
- line 77: `test_operator_boundaries_always_listed` → `SelfModel(bridge, tb).describe`
- line 77: `test_operator_boundaries_always_listed` → `SelfModel`
- line 78: `test_operator_boundaries_always_listed` → `' '.join`
- line 85: `test_format_produces_readable_text_with_all_headers` → `_fresh_bridge`
- line 86: `test_format_produces_readable_text_with_all_headers` → `ToolBoundary`
- line 87: `test_format_produces_readable_text_with_all_headers` → `SelfModel(bridge, tb).describe`
- line 87: `test_format_produces_readable_text_with_all_headers` → `SelfModel`
- line 88: `test_format_produces_readable_text_with_all_headers` → `reading.format`

### `tests/test_spine.py`
- line 8: `<module>` → `Path`
- line 13: `_fresh_bridge` → `path.exists`
- line 14: `_fresh_bridge` → `shutil.rmtree`
- line 15: `_fresh_bridge` → `LanternBridge`
- line 16: `_fresh_bridge` → `bridge.ensure_identity`
- line 17: `_fresh_bridge` → `bridge.startup`
- line 22: `_add_evidence` → `bridge.observe`
- line 23: `_add_evidence` → `bridge.add_evidence`
- line 28: `test_open_branch_requires_concept_and_hypothesis` → `BranchStore`
- line 29: `test_open_branch_requires_concept_and_hypothesis` → `store.open_branch`
- line 33: `test_open_branch_requires_concept_and_hypothesis` → `store.open_branch`
- line 34: `test_open_branch_requires_concept_and_hypothesis` → `AssertionError`
- line 40: `test_branch_cannot_commit_itself_without_explicit_authorization` → `_fresh_bridge`
- line 41: `test_branch_cannot_commit_itself_without_explicit_authorization` → `BranchStore`
- line 42: `test_branch_cannot_commit_itself_without_explicit_authorization` → `store.open_branch`
- line 43: `test_branch_cannot_commit_itself_without_explicit_authorization` → `SpineCommitter`
- line 44: `test_branch_cannot_commit_itself_without_explicit_authorization` → `committer.commit`
- line 51: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `_fresh_bridge`
- line 52: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `_add_evidence`
- line 53: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `BranchStore`
- line 54: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `store.open_branch`
- line 55: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `store.link_observation`
- line 56: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `store.link_evidence`
- line 57: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `SpineCommitter`
- line 58: `test_commit_succeeds_with_explicit_authorization_and_no_contradictions` → `committer.commit`
- line 67: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `_fresh_bridge`
- line 68: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `_add_evidence`
- line 69: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `_add_evidence`
- line 71: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `len`
- line 73: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `BranchStore`
- line 74: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `store.open_branch`
- line 75: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `SpineCommitter`
- line 77: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `committer.commit`
- line 81: `test_commit_refused_on_open_contradiction_unless_acknowledged` → `committer.commit`
- line 90: `test_commit_refused_when_integrity_fails` → `_fresh_bridge`
- line 91: `test_commit_refused_when_integrity_fails` → `_add_evidence`
- line 92: `test_commit_refused_when_integrity_fails` → `open`
- line 93: `test_commit_refused_when_integrity_fails` → `f.write`
- line 94: `test_commit_refused_when_integrity_fails` → `BranchStore`
- line 95: `test_commit_refused_when_integrity_fails` → `store.open_branch`
- line 96: `test_commit_refused_when_integrity_fails` → `SpineCommitter`
- line 97: `test_commit_refused_when_integrity_fails` → `committer.commit`
- line 99: `test_commit_refused_when_integrity_fails` → `result.reason.lower`
- line 104: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `_fresh_bridge`
- line 105: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `_add_evidence`
- line 106: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `BranchStore`
- line 107: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `store.open_branch`
- line 108: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `SpineCommitter`
- line 109: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `committer.commit`
- line 112: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `committer.commit`
- line 116: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `store.abandon`
- line 117: `test_committed_branch_cannot_be_recommitted_or_abandoned` → `AssertionError`
- line 123: `test_read_spine_reconstructs_from_real_chronicle_replay` → `_fresh_bridge`
- line 124: `test_read_spine_reconstructs_from_real_chronicle_replay` → `_add_evidence`
- line 125: `test_read_spine_reconstructs_from_real_chronicle_replay` → `BranchStore`
- line 126: `test_read_spine_reconstructs_from_real_chronicle_replay` → `store.open_branch`
- line 127: `test_read_spine_reconstructs_from_real_chronicle_replay` → `SpineCommitter`
- line 128: `test_read_spine_reconstructs_from_real_chronicle_replay` → `committer.commit`
- line 130: `test_read_spine_reconstructs_from_real_chronicle_replay` → `LanternBridge`
- line 131: `test_read_spine_reconstructs_from_real_chronicle_replay` → `SpineCommitter(fresh_bridge).read_spine`
- line 131: `test_read_spine_reconstructs_from_real_chronicle_replay` → `SpineCommitter`
- line 132: `test_read_spine_reconstructs_from_real_chronicle_replay` → `len`
- line 138: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `_fresh_bridge`
- line 139: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `_add_evidence`
- line 140: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `BranchStore`
- line 141: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `store.open_branch`
- line 142: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `store.link_evidence`
- line 143: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `store.abandon`
- line 146: `test_abandoned_branch_becomes_a_real_scar_not_discarded` → `branch_to_scar`
- line 152: `test_child_branch_requires_known_parent` → `BranchStore`
- line 153: `test_child_branch_requires_known_parent` → `store.open_branch`
- line 154: `test_child_branch_requires_known_parent` → `store.open_branch`
- line 157: `test_child_branch_requires_known_parent` → `store.open_branch`
- line 158: `test_child_branch_requires_known_parent` → `AssertionError`
- line 167: `test_confidence_score_alone_never_authorizes_commit` → `_fresh_bridge`
- line 168: `test_confidence_score_alone_never_authorizes_commit` → `_add_evidence`
- line 169: `test_confidence_score_alone_never_authorizes_commit` → `_add_evidence`
- line 171: `test_confidence_score_alone_never_authorizes_commit` → `ConfidenceField(bridge).evaluate`
- line 171: `test_confidence_score_alone_never_authorizes_commit` → `ConfidenceField`
- line 173: `test_confidence_score_alone_never_authorizes_commit` → `BranchStore`
- line 174: `test_confidence_score_alone_never_authorizes_commit` → `store.open_branch`
- line 175: `test_confidence_score_alone_never_authorizes_commit` → `SpineCommitter`
- line 176: `test_confidence_score_alone_never_authorizes_commit` → `committer.commit`

### `tests/test_tool_boundary.py`
- line 4: `<module>` → `sys.path.insert`
- line 4: `<module>` → `str`
- line 4: `<module>` → `Path(__file__).resolve`
- line 4: `<module>` → `Path`
- line 10: `test_discovery_does_not_imply_authorization` → `ToolBoundary`
- line 11: `test_discovery_does_not_imply_authorization` → `boundary.register`
- line 11: `test_discovery_does_not_imply_authorization` → `ToolDescriptor`
- line 13: `test_discovery_does_not_imply_authorization` → `boundary.discover`
- line 14: `test_discovery_does_not_imply_authorization` → `boundary.is_authorized`
- line 16: `test_discovery_does_not_imply_authorization` → `boundary.execute`
- line 21: `test_authorized_tool_executes` → `ToolBoundary`
- line 22: `test_authorized_tool_executes` → `boundary.register`
- line 22: `test_authorized_tool_executes` → `ToolDescriptor`
- line 23: `test_authorized_tool_executes` → `boundary.authorize`
- line 25: `test_authorized_tool_executes` → `boundary.execute`
- line 31: `test_unregistered_tool_execution_errors` → `ToolBoundary`
- line 32: `test_unregistered_tool_execution_errors` → `boundary.execute`
- line 37: `test_handler_exception_becomes_error_result_not_crash` → `ToolBoundary`
- line 40: `test_handler_exception_becomes_error_result_not_crash.bad_handler` → `ValueError`
- line 42: `test_handler_exception_becomes_error_result_not_crash` → `boundary.register`
- line 42: `test_handler_exception_becomes_error_result_not_crash` → `ToolDescriptor`
- line 43: `test_handler_exception_becomes_error_result_not_crash` → `boundary.authorize`
- line 45: `test_handler_exception_becomes_error_result_not_crash` → `boundary.execute`
- line 51: `test_authorize_unknown_tool_returns_false` → `ToolBoundary`
- line 52: `test_authorize_unknown_tool_returns_false` → `boundary.authorize`

### `tests/test_transfer_manifest.py`
- line 5: `<module>` → `sys.path.insert`
- line 5: `<module>` → `str`
- line 5: `<module>` → `Path(__file__).resolve`
- line 5: `<module>` → `Path`
- line 12: `_fresh_bridge` → `Path`
- line 12: `_fresh_bridge` → `tempfile.mkdtemp`
- line 13: `_fresh_bridge` → `LanternBridge`
- line 14: `_fresh_bridge` → `bridge.ensure_identity`
- line 15: `_fresh_bridge` → `bridge.startup`
- line 20: `test_manifest_reports_real_identity_not_a_placeholder` → `_fresh_bridge`
- line 21: `test_manifest_reports_real_identity_not_a_placeholder` → `build_manifest`
- line 25: `test_manifest_reports_real_identity_not_a_placeholder` → `len`
- line 29: `test_manifest_never_contains_a_private_key_or_signing_material` → `_fresh_bridge`
- line 30: `test_manifest_never_contains_a_private_key_or_signing_material` → `build_manifest`
- line 31: `test_manifest_never_contains_a_private_key_or_signing_material` → `str`
- line 31: `test_manifest_never_contains_a_private_key_or_signing_material` → `manifest.to_dict`
- line 32: `test_manifest_never_contains_a_private_key_or_signing_material` → `payload.lower`
- line 38: `test_manifest_state_summary_reflects_real_observations` → `_fresh_bridge`
- line 39: `test_manifest_state_summary_reflects_real_observations` → `bridge.observe`
- line 40: `test_manifest_state_summary_reflects_real_observations` → `bridge.observe`
- line 41: `test_manifest_state_summary_reflects_real_observations` → `build_manifest`
- line 47: `test_manifest_reports_real_witness_integrity_not_assumed_valid` → `_fresh_bridge`
- line 48: `test_manifest_reports_real_witness_integrity_not_assumed_valid` → `build_manifest`
- line 49: `test_manifest_reports_real_witness_integrity_not_assumed_valid` → `bridge.witness_integrity`
- line 50: `test_manifest_reports_real_witness_integrity_not_assumed_valid` → `manifest.witness_integrity.get`
- line 54: `test_manifest_lists_reauthorization_required_items` → `_fresh_bridge`
- line 55: `test_manifest_lists_reauthorization_required_items` → `build_manifest`
- line 56: `test_manifest_lists_reauthorization_required_items` → `len`
- line 57: `test_manifest_lists_reauthorization_required_items` → `' '.join`
- line 58: `test_manifest_lists_reauthorization_required_items` → `joined.lower`
- line 58: `test_manifest_lists_reauthorization_required_items` → `joined.lower`
- line 59: `test_manifest_lists_reauthorization_required_items` → `joined.lower`
- line 68: `test_manifest_does_not_transfer_reasoning_engine_api_key_value` → `_fresh_bridge`
- line 69: `test_manifest_does_not_transfer_reasoning_engine_api_key_value` → `build_manifest`
- line 71: `test_manifest_does_not_transfer_reasoning_engine_api_key_value` → `manifest.to_dict`
- line 74: `test_manifest_does_not_transfer_reasoning_engine_api_key_value` → `os.environ.get`
- line 76: `test_manifest_does_not_transfer_reasoning_engine_api_key_value` → `str`
- line 85: `test_manifest_reuses_self_model_capability_and_gap_lists` → `_fresh_bridge`
- line 86: `test_manifest_reuses_self_model_capability_and_gap_lists` → `build_manifest`
- line 92: `test_manifest_records_real_provenance_commit_hashes` → `_fresh_bridge`
- line 93: `test_manifest_records_real_provenance_commit_hashes` → `build_manifest`
- line 96: `test_manifest_records_real_provenance_commit_hashes` → `len`
- line 97: `test_manifest_records_real_provenance_commit_hashes` → `manifest.lantern_core_commit.startswith`
- line 97: `test_manifest_records_real_provenance_commit_hashes` → `len`
- line 103: `test_manifest_protocol_version_matches_lantern_protocol_module` → `_fresh_bridge`
- line 104: `test_manifest_protocol_version_matches_lantern_protocol_module` → `build_manifest`
- line 109: `test_manifest_is_read_only_no_state_mutation` → `_fresh_bridge`
- line 110: `test_manifest_is_read_only_no_state_mutation` → `bridge.status`
- line 111: `test_manifest_is_read_only_no_state_mutation` → `build_manifest`
- line 112: `test_manifest_is_read_only_no_state_mutation` → `build_manifest`
- line 113: `test_manifest_is_read_only_no_state_mutation` → `bridge.status`
- line 118: `test_manifest_to_dict_and_format_round_trip_without_error` → `_fresh_bridge`
- line 119: `test_manifest_to_dict_and_format_round_trip_without_error` → `build_manifest`
- line 120: `test_manifest_to_dict_and_format_round_trip_without_error` → `manifest.to_dict`
- line 121: `test_manifest_to_dict_and_format_round_trip_without_error` → `isinstance`
- line 122: `test_manifest_to_dict_and_format_round_trip_without_error` → `manifest.format`
- line 131: `test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model` → `_fresh_bridge`
- line 132: `test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model` → `build_manifest`
- line 135: `test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model` → `manifest.to_dict`
- line 138: `test_manifest_lineage_names_lantern_as_architecture_and_peacemaker_as_instance_model` → `manifest.format`



## 7. SECURITY-SENSITIVE OPERATIONS

### `lantern_harness/transfer_manifest.py`
- subprocess.run at line 86

### `tests/test_confidence_field.py`
- open at line 57
- open at line 70
- open at line 122

### `tests/test_conversation_loop.py`
- subprocess.run at line 13

### `tests/test_decision_state_machine.py`
- open at line 58
- open at line 117

### `tests/test_operating_loop.py`
- open at line 108

### `tests/test_prompt_compiler.py`
- open at line 188

### `tests/test_spine.py`
- open at line 92



## 8. DEPENDENCIES AND CONFIGURATION

### `pyproject.toml`

```text
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "lantern-harness"
version = "0.2.0"
description = "Provider-agnostic human-facing conversation harness for the Lantern evidence/belief engine (lantern-babel-codex-bridge). Adds Prompt Compiler, Perspective Differential, Confidence Field, Decision State Machine, Branch/Spine, Self-Model, and Reality Boundary layers on top of Lantern's real APIs, without duplicating Lantern's internals."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
    { name = "Lantern project" },
]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]
ollama = [
    "httpx>=0.24.0",
]
openai = [
    "httpx>=0.24.0",
]
anthropic = [
    "httpx>=0.24.0",
]
google = [
    "httpx>=0.24.0",
]
mcp = [
    "mcp>=2.0.0",
]

[project.scripts]
lantern-harness = "main:main"
lantern-harness-mcp = "lantern_harness.mcp_server:main"

[tool.setuptools]
py-modules = ["main"]

[tool.setuptools.packages.find]
include = ["lantern_harness*"]

[tool.pytest.ini_options]
testpaths = ["tests"]

```

### `config/config.json`

```text
{
  "reasoning_engine": {
    "provider": "none",
    "model": null,
    "ollama_host": "http://localhost:11434",
    "api_key_env": null
  },
  "node_id": "lantern-harness-node",
  "data_dir": "memory/lantern_data",
  "output_profile": "concise"
}
```



## 9. TESTS

- `tests/test_bootstrap.py`
- `tests/test_bridge.py`
- `tests/test_confidence_field.py`
- `tests/test_config.py`
- `tests/test_conversation_loop.py`
- `tests/test_decision_state_machine.py`
- `tests/test_harness_status.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_server_live_stdio.py`
- `tests/test_operating_loop.py`
- `tests/test_permission_authority.py`
- `tests/test_perspective_differential.py`
- `tests/test_prompt_compiler.py`
- `tests/test_reality_boundary.py`
- `tests/test_reasoning.py`
- `tests/test_self_model.py`
- `tests/test_spine.py`
- `tests/test_tool_boundary.py`
- `tests/test_transfer_manifest.py`


## 10. TODO / STUB / FALLBACK / PARTIAL MARKERS

### `export_for_miles.py`
- TODO at line 2
- STUB at line 2
- TODO at line 307
- FIXME at line 308
- STUB at line 309
- NotImplemented at line 310
- placeholder at line 311
- mock at line 312
- temporary at line 313
- TODO at line 707
- STUB at line 707
- STUB at line 723

### `lantern_harness/bridge.py`
- NotImplemented at line 21

### `lantern_harness/reasoning/__init__.py`
- STUB at line 26

### `lantern_harness/spine.py`
- NotImplemented at line 1

### `tests/test_bridge.py`
- NotImplemented at line 66

### `tests/test_mcp_server.py`
- STUB at line 140



## 11. IMPORTANT SOURCE FILES

### `main.py`

```python
#!/usr/bin/env python3
"""Lantern Harness entrypoint.

USER -> LANTERN INTERFACE (this file) -> REASONING ENGINE -> LANTERN CORE

This does not duplicate Lantern's internals. It calls the real
lantern-babel-codex-bridge package through lantern_harness.bridge.LanternBridge.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lantern_harness.bootstrap import bootstrap, format_bootstrap_report
from lantern_harness.harness_status import format_status_report, status_report
from lantern_harness.prompt_compiler import PromptCompiler
from lantern_harness.confidence_field import ConfidenceField
from lantern_harness.decision_state_machine import DecisionStateMachine
from lantern_harness.reasoning.base import ReasoningEngineUnavailable
from lantern_harness.tools.boundary import ToolBoundary
from lantern_harness.self_model import SelfModel
from lantern_harness.spine import BranchStore, SpineCommitter
from lantern_harness.operating_loop import OperatingLoop
from lantern_harness.transfer_manifest import build_manifest
from lantern_harness.permission_authority import PermissionAuthority, CAPABILITY_CATEGORIES

COMMANDS = ("/memory", "/history", "/beliefs", "/evidence", "/branches", "/identity", "/tools", "/projects", "/status", "/compile", "/decide", "/self", "/branch", "/spine", "/run", "/transfer", "/permissions", "/grant", "/revoke", "/new", "/exit")

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "system.md"


def load_system_prompt():
    if not SYSTEM_PROMPT_PATH.exists():
        return None
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def handle_command(command: str, bridge, engine, tool_boundary) -> str:
    if command == "/status":
        report = status_report(bridge, engine, tool_boundary)
        return format_status_report(report)
    if command.startswith("/decide"):
        request = command[len("/decide"):].strip()
        if not request:
            return "usage: /decide <your request> -- evaluates confidence and recommends a state, but does not authorize or execute"
        compiler = PromptCompiler(bridge=bridge)
        field = ConfidenceField(bridge=bridge)
        machine = DecisionStateMachine()
        compiled = compiler.compile(request)
        reading = field.evaluate(concept=compiled.concept, perspectives=compiled.perspectives, assumptions=compiled.assumptions, validation_status=compiled.validation_status)
        decision = machine.recommend(reading)
        reason_lines = [f"- {reason}" for reason in decision.reasons] or ["- none"]
        blocker_lines = [f"- {blocker}" for blocker in decision.blockers] or ["- none"]
        change_lines = [f"- {item}" for item in decision.what_would_change_state] or ["- none"]
        return "\n".join([
            f"[decision, state={decision.state}, action={decision.recommended_action}]",
            f"confidence={decision.confidence_score} band={decision.confidence_band}",
            "reasons:",
            *reason_lines,
            "blockers:",
            *blocker_lines,
            "what_would_change_state:",
            *change_lines,
        ])
    if command.startswith("/compile"):
        request = command[len("/compile"):].strip()
        if not request:
            return "usage: /compile <your request> -- compiles a structured prompt, does not send it anywhere"
        compiler = PromptCompiler(bridge=bridge)
        try:
            result = compiler.compile(request)
        except ValueError as exc:
            return f"COMPILE_ERROR: {exc}"
        header = f"[compiled, mode={result.mode}]"
        if result.notes:
            header += "\nnotes: " + "; ".join(result.notes)
        return f"{header}\n\n{result.text}"
    if command == "/identity":
        return str(bridge.identity_status())
    if command == "/tools":
        return f"discovered: {tool_boundary.discover()}, authorized: {sorted(tool_boundary._authorized)}"
    if command == "/memory":
        s = bridge.status()
        return f"step={s['step']} observations={s['observations']} evidence={s['evidence']} contradictions={s['contradictions']}"
    if command in ("/branches",):
        try:
            bridge.branches()
        except NotImplementedError as exc:
            return f"NOT_IMPLEMENTED: {exc}"
    if command in ("/history", "/beliefs", "/evidence", "/projects"):
        return f"{command}: not yet implemented as a formatted view in this harness version (raw data is available via LanternBridge)"
    if command == "/exit":
        return "__EXIT__"
    return f"unknown command: {command}"


def handle_stateful_command(command: str, bridge, tool_boundary, branch_store, loop, engine=None, permission_authority=None) -> str | None:
    """Commands that need state that persists across turns (open
    branches, the OperatingLoop's compiled components). Kept separate
    from handle_command so that function stays a pure per-call dispatch.
    Returns None if the command is not one of these."""
    if command == "/self":
        model = SelfModel(bridge, tool_boundary)
        return model.describe().format()

    if command.startswith("/branch"):
        request = command[len("/branch"):].strip()
        if not request:
            open_ids = [b.id for b in branch_store.all() if b.status == "OPEN"]
            return f"usage: /branch <concept> :: <hypothesis>  |  open branches: {open_ids or 'none'}"
        if "::" not in request:
            return "usage: /branch <concept> :: <hypothesis>"
        concept, hypothesis = (part.strip() for part in request.split("::", 1))
        branch = branch_store.open_branch(concept=concept, hypothesis=hypothesis)
        return f"[branch opened] id={branch.id} concept={branch.concept!r} status={branch.status} -- outside committed Spine state until an explicit /spine commit"

    if command.startswith("/spine"):
        request = command[len("/spine"):].strip()
        if not request:
            committer = SpineCommitter(bridge)
            entries = committer.read_spine()
            if not entries:
                return "spine: 0 committed entries"
            lines = [f"spine: {len(entries)} committed entries"]
            for entry in entries:
                lines.append(f"  - [{entry.id}] concept={entry.concept!r} statement={entry.statement!r}")
            return "\n".join(lines)
        return (
            "SPINE_NOT_COMMITTED: this REPL command intentionally cannot authorize a commit on your behalf. "
            "A branch cannot commit itself and no confidence score alone may create commitment "
            "(see lantern_harness.spine.SpineCommitter.commit's required authorized=True parameter). "
            "Use SpineCommitter directly from a script where you, the operator, explicitly pass authorized=True."
        )

    if command.startswith("/run"):
        intent = command[len("/run"):].strip()
        if not intent:
            return "usage: /run <intent> -- runs the full operating loop (observe -> compile -> confidence -> decision), never executes a tool without prior ToolBoundary authorization"
        result = loop.run(intent)
        return result.format()

    if command == "/transfer":
        manifest = build_manifest(bridge, engine=engine)
        return manifest.format()

    if command == "/permissions":
        if permission_authority is None:
            return "PERMISSIONS: no PermissionAuthority is wired into this session"
        active = permission_authority.active_grants()
        if not active:
            return "permissions: 0 active grants -- nothing is pre-authorized in this session; every consequential action outside an existing grant will ask"
        lines = [f"permissions: {len(active)} active grant(s)"]
        for g in active:
            lines.append(f"  - [{g.version}] capability={g.capability!r} scope={g.scope!r} granted_by={g.granting_authority!r} boundary={g.boundary!r}")
        return "\n".join(lines)

    if command.startswith("/grant"):
        request = command[len("/grant"):].strip()
        if not request or "::" not in request:
            return (
                "usage: /grant <capability> :: <scope> :: <your name/identifier>  "
                f"(capability must be one of: {', '.join(CAPABILITY_CATEGORIES)})"
            )
        parts = [p.strip() for p in request.split("::")]
        if len(parts) != 3:
            return "usage: /grant <capability> :: <scope> :: <your name/identifier> -- granting_authority must be stated explicitly, it is never inferred"
        capability, scope, granting_authority = parts
        if permission_authority is None:
            return "PERMISSIONS: no PermissionAuthority is wired into this session"
        try:
            grant = permission_authority.grant(
                capability=capability,
                scope=scope,
                boundary="",
                granting_authority=granting_authority,
                provenance="REPL /grant command",
            )
        except ValueError as exc:
            return f"GRANT_REFUSED: {exc}"
        return f"[granted] capability={grant.capability!r} scope={grant.scope!r} granted_by={grant.granting_authority!r} version={grant.version}"

    if command.startswith("/revoke"):
        request = command[len("/revoke"):].strip()
        if not request or "::" not in request:
            return "usage: /revoke <capability> :: <your name/identifier>"
        parts = [p.strip() for p in request.split("::")]
        if len(parts) != 2:
            return "usage: /revoke <capability> :: <your name/identifier>"
        capability, granting_authority = parts
        if permission_authority is None:
            return "PERMISSIONS: no PermissionAuthority is wired into this session"
        try:
            count = permission_authority.revoke(capability, granting_authority)
        except ValueError as exc:
            return f"REVOKE_REFUSED: {exc}"
        return f"[revoked] capability={capability!r} count={count}"

    return None


def run_repl(bridge, engine, tool_boundary, branch_store, loop, permission_authority):
    system_prompt = load_system_prompt()
    history = [{"role": "system", "content": system_prompt}] if system_prompt else []

    print("You:", end=" ", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            print("You:", end=" ", flush=True)
            continue

        if line.startswith("/"):
            stateful_result = handle_stateful_command(line, bridge, tool_boundary, branch_store, loop, engine=engine, permission_authority=permission_authority)
            if stateful_result is not None:
                print(stateful_result)
                print("You:", end=" ", flush=True)
                continue
            result = handle_command(line, bridge, engine, tool_boundary)
            if result == "__EXIT__":
                return
            print(result)
            print("You:", end=" ", flush=True)
            continue

        obs = bridge.observe(line, source="user", reliability=1.0)

        if engine is None:
            print("REASONING_ENGINE: NOT_CONFIGURED -- observation recorded (id=%s) but no reasoning engine is configured to respond. Edit config/config.json to set a provider." % obs.id)
            print("You:", end=" ", flush=True)
            continue

        history.append({"role": "user", "content": line})
        try:
            response = engine.respond(history)
            print(response.text)
            history.append({"role": "assistant", "content": response.text})
        except ReasoningEngineUnavailable as exc:
            print(f"REASONING_ENGINE_ERROR: {exc}")
            history.pop()  # do not retain a turn the engine never actually answered

        print("You:", end=" ", flush=True)


def main():
    result = bootstrap()
    print(format_bootstrap_report(result))

    bridge = result["bridge"]
    if bridge is None:
        print("\nCannot start conversation loop: Lantern is not importable in this environment.")
        return 1

    engine = result["engine"]
    tool_boundary = ToolBoundary()
    branch_store = BranchStore()
    loop = OperatingLoop(bridge, tool_boundary)
    permission_authority = PermissionAuthority()

    print()
    run_repl(bridge, engine, tool_boundary, branch_store, loop, permission_authority)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "lantern-harness"
version = "0.2.0"
description = "Provider-agnostic human-facing conversation harness for the Lantern evidence/belief engine (lantern-babel-codex-bridge). Adds Prompt Compiler, Perspective Differential, Confidence Field, Decision State Machine, Branch/Spine, Self-Model, and Reality Boundary layers on top of Lantern's real APIs, without duplicating Lantern's internals."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [
    { name = "Lantern project" },
]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
]
ollama = [
    "httpx>=0.24.0",
]
openai = [
    "httpx>=0.24.0",
]
anthropic = [
    "httpx>=0.24.0",
]
google = [
    "httpx>=0.24.0",
]
mcp = [
    "mcp>=2.0.0",
]

[project.scripts]
lantern-harness = "main:main"
lantern-harness-mcp = "lantern_harness.mcp_server:main"

[tool.setuptools]
py-modules = ["main"]

[tool.setuptools.packages.find]
include = ["lantern_harness*"]

[tool.pytest.ini_options]
testpaths = ["tests"]

```

### `README.md`

```markdown
# Lantern Harness

## What Lantern is

Lantern (`lantern-babel-codex-bridge`) is an auditable evidence/belief
engine and inter-instance exchange protocol. It gives an AI system
persistent, hash-chained evidence tracking, contradiction detection,
cryptographic node identity, and a capability-authorization boundary.
Lantern by itself is a Python **library** — it has no chat interface,
no reasoning engine, and no `main.py`.

## What this harness is

This harness (`lantern-harness`) is the missing human-facing layer: a
small, provider-agnostic conversation loop that connects a reasoning
engine of your choice (Ollama, OpenAI, Anthropic, Google, or a custom
adapter) to Lantern's evidence/identity/memory layer through a thin
`LanternBridge` adapter. It does not duplicate or reimplement any of
Lantern's internals.

A running instance of this harness -- with its own identity, evidence,
and history -- may be personally carried and transferred by one
operator; see [`PEACEMAKER.md`](./PEACEMAKER.md) for what that naming
means and does not mean, and "Transfer an instance" below for the
actual procedure.

## How they relate

```
USER -> LANTERN INTERFACE (this harness) -> REASONING ENGINE -> LANTERN CORE (real lantern package)
```

The harness never asserts model output as verified external fact, and
it never treats reasoning-engine availability as evidence about
Lantern's own state.

## Install

Requires Python >= 3.10. `lantern-harness` is a real, pip-installable
package (`pyproject.toml`) with a console entry point (`lantern-harness`);
this has been verified against a fresh throwaway venv, not just the
development checkout.

```bash
git clone <this-repo>
cd lantern-babel-codex-bridge
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ../lantern-harness
../lantern-babel-codex-bridge/.venv/bin/pip install -e ".[dev]"
../lantern-babel-codex-bridge/.venv/bin/python -m pytest tests/ -q
```

If `lantern` is not importable, `main.py` will report exactly that and
stop — it will not fabricate a working session.

## Try the demo

`examples/demo_operating_loop.py` runs the full operating loop
end-to-end against a real, disposable Lantern node (a fresh temp
directory) -- every line it prints is produced by real code, nothing is
hardcoded:

```bash
../lantern-babel-codex-bridge/.venv/bin/python examples/demo_operating_loop.py
```

It walks through: an ordinary question with no evidence (LOW
confidence), adding two independent agreeing observations (confidence
rises to MEDIUM), opening an exploratory branch, a refused Spine commit
(no authorization) followed by a real authorized commit, and a final
Self-Model report.

## Choose a model

Edit `config/config.json`:

```json
{
  "reasoning_engine": {
    "provider": "ollama",
    "model": "llama3.1",
    "ollama_host": "http://localhost:11434"
  }
}
```

Supported `provider` values: `ollama`, `openai`, `anthropic`, `google`,
or `none` (default — the harness runs with no reasoning engine and
tells you so at every message).

For API providers, set the corresponding environment variable before
running (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`). Keys
are read directly from the environment at call time and are never
written to Lantern's Chronicle, evidence, witness ledger, or any file
in this repo.

## Start

```bash
../lantern-babel-codex-bridge/.venv/bin/python main.py
```

## Inspect status

Type `/status` at the `You:` prompt, or run the same check
non-interactively:

```bash
../lantern-babel-codex-bridge/.venv/bin/python -c "
from lantern_harness.bootstrap import bootstrap, format_bootstrap_report
print(format_bootstrap_report(bootstrap()))
"
```

## Commands

`/status` `/memory` `/identity` `/tools` `/branches` `/compile <request>`
`/decide <request>` `/self` `/branch <concept> :: <hypothesis>` `/spine`
`/run <intent>` `/transfer` `/permissions` `/grant <capability> :: <scope> :: <you>`
`/revoke <capability> :: <you>` `/exit`

- `/compile <request>` runs the Prompt Compiler
  (`lantern_harness.prompt_compiler`) and prints a structured
  investigation prompt -- it does not send the request anywhere itself.
  Missing information is marked `NOT_PROVIDED` / `UNKNOWN`, never invented.
- `/decide <request>` computes a real `ConfidenceField` reading and a
  `DecisionStateMachine` recommendation. It recommends; it never
  authorizes or executes.
- `/self` prints a `SelfModel` report: WHAT I KNOW / INFER / DO NOT KNOW
  / CAN DO / CANNOT DO / AM AUTHORIZED TO DO / REQUIRES OPERATOR ACTION.
  It has no method capable of granting itself authority.
- `/branch <concept> :: <hypothesis>` opens a real exploratory `Branch`
  (`lantern_harness.spine.BranchStore`). Branches stay outside committed
  Spine state until an explicit commit succeeds.
- `/spine` lists currently committed Spine entries (reconstructed by
  replaying the real Chronicle). The REPL intentionally cannot commit a
  branch for you -- `SpineCommitter.commit()` requires an explicit
  `authorized=True` passed by a caller outside this module, so a branch
  can never authorize its own commitment and no confidence score alone
  can create one.
- `/run <intent>` executes the full `OperatingLoop`: records a real
  Observation, compiles a structured prompt, computes a Confidence Field
  reading, and gets a Decision State Machine recommendation, in one call.
- `/transfer` prints a `TransferManifest`: identity (public key only),
  protocol/harness version, real state counts, real witness integrity
  status, capabilities, known gaps, and an explicit list of what a
  receiving operator must decide fresh (credentials, network exposure,
  MCP host registration, paid capabilities). It never includes a
  private key or API key value, and it does not itself transfer
  anything -- to actually hand off an instance, copy its `data_dir`
  (see "Transfer an instance" below) and share this manifest's output
  alongside it.
- `/permissions` lists currently active capability-scope grants
  (`lantern_harness.permission_authority.PermissionAuthority`). A fresh
  session always starts with zero grants -- nothing is pre-authorized,
  and grants never travel with a transferred `data_dir` (they live in
  process memory only, on purpose; see "Permissions and alignment"
  below).
- `/grant <capability> :: <scope> :: <your name>` records a new
  capability-scope permission. `granting_authority` (your name/
  identifier) is required and never inferred -- omitting it refuses the
  grant. `<capability>` must be one of the defined categories (see
  `lantern_harness.permission_authority.CAPABILITY_CATEGORIES`);
  external-authority categories (credentials, wallets, payments,
  communications, legal/financial commitments, destructive operations,
  private-data disclosure, authority transfer to another agent) never
  inherit from any other grant, no matter how similar the wording.
- `/revoke <capability> :: <your name>` marks all active grants for
  that capability as revoked.

(`/history`, `/beliefs`, `/evidence`, `/projects` are recognized but
not yet implemented as formatted views in this version — see
`KNOWN_LIMITATIONS` in the harness status report.)

## Configure tools

Tools are registered programmatically via
`lantern_harness.tools.boundary.ToolBoundary` — none are registered by
default. Tool discovery never implies authorization; call
`boundary.authorize(name)` explicitly before a tool can execute.

## Use Lantern from another agent (MCP server)

`lantern_harness.mcp_server` exposes real Lantern harness capabilities
as MCP tools, so any MCP-compatible agent client (Claude Desktop,
Claude Code, or any other MCP host) can call them directly, without a
human relaying through this REPL. This is the reverse direction of
`lantern.mcp_client`/`lantern.mcp_integration` in the core package
(Lantern connecting *out* to other MCP servers) -- this module makes
Lantern *act as* an MCP server.

```bash
../lantern-babel-codex-bridge/.venv/bin/pip install -e ".[mcp]"
../lantern-babel-codex-bridge/.venv/bin/lantern-harness-mcp
```

Exposed tools: `lantern_observe`, `lantern_add_evidence`,
`lantern_confidence`, `lantern_decide`, `lantern_compile`,
`lantern_self_model`, `lantern_branch_open`, `lantern_spine_read`,
`lantern_witness_integrity`, `lantern_evaluate_intent`,
`lantern_transfer_manifest`, `lantern_permissions`. Every tool is a
thin wrapper around an already-tested component -- no new
decision/confidence/authorization logic exists in this module.
Deliberately **not** exposed: anything that would let a remote MCP
client execute an arbitrary `ToolBoundary`-registered tool or
otherwise act on the external world -- this server surfaces Lantern's
epistemic primitives only
(`test_server_exposes_no_tool_capable_of_external_action` enforces
this). `lantern_permissions` is read-only (lists this process's active
`PermissionAuthority` grants); there is deliberately no
`lantern_grant`/`lantern_revoke` MCP tool, since `granting_authority`
must always be an explicit human-typed identifier (the REPL `/grant`
pattern), never a string a remote MCP caller could supply on its own
behalf (`test_server_exposes_no_grant_or_revoke_tool_over_mcp`
enforces this). It runs over stdio only (matches how MCP hosts launch
local servers as a subprocess); nothing in this module binds a network
port.

Verified end-to-end against a real independent MCP client (Lantern
core's own `StdioMCPClient`, launched as a genuine child process, not
called as a Python object in-process) — see
`tests/test_mcp_server_live_stdio.py`.

To connect this server to an MCP host that reads a JSON config (e.g.
Claude Desktop's `claude_desktop_config.json`, or Claude Code's
`.mcp.json`), add an entry like:

```json
{
  "mcpServers": {
    "lantern-harness": {
      "command": "/absolute/path/to/lantern-babel-codex-bridge/.venv/bin/lantern-harness-mcp",
      "env": {
        "LANTERN_MCP_DATA_DIR": "/absolute/path/to/wherever/you/want/this/node's/data"
      }
    }
  }
}
```

Use absolute paths — MCP hosts launch this as a subprocess and do not
inherit your shell's working directory or `PATH` by default.

**Integrating with an agent environment that owns its own action
layer** (e.g. [Odysseus](https://github.com/odysseus-dev/odysseus)):
use `lantern_evaluate_intent` instead of the individual
observe/confidence/decide tools. It runs the full read-only
observe→compile→confidence→decide pipeline in one call and has no
`tool_name`/`tool_kwargs` parameter at all, so it cannot trigger an
action — the calling environment executes the recommended action
itself (under its own authorization/tool-security gating) and reports
the real result back via `lantern_observe`. See
`ODYSSEUS_INTEGRATION.md` for a concrete, tested example: architecture
investigation, license-compatibility analysis (Odysseus is
AGPL-3.0-or-later; Lantern is MIT), and a real boundary-level test
against Odysseus's actual (unmodified) MCP client code and its pinned
`mcp<2` SDK version.

## Create a project

`projects/` is a plain workspace directory for your own files. It is
not a replacement for Lantern's evidence history — it holds no
epistemic state of its own.

## Understand evidence / validation

Decision pipeline:

Evidence -> Confidence Field -> Decision State Machine -> Capability Authorization -> Action Boundary

The Confidence Field and Decision State Machine are real, testable layers in this harness. They recommend; they do not authorize or execute.


- **Observation** -> **Evidence** -> **belief()** is real and
  implemented (`lantern.core.EvidenceKernel`), reachable through
  `LanternBridge.observe()` / `.add_evidence()` / `.belief()`.
- **Witness Integrity** reports the real Chronicle hash-chain
  verification (`Chronicle.verify()`). `VALID` means the recorded
  sequence has not been silently altered — it does **not** mean the
  underlying claims are true.
- **Branches / Spine / Commitment** (`lantern_harness.spine`) is a real,
  tested layer built on Lantern's Chronicle. `BranchStore` manages
  exploratory `Branch` objects (concept, hypothesis, linked
  observations/evidence, OPEN/COMMITTED/ABANDONED status).
  `SpineCommitter.commit()` enforces every invariant the mission
  requires: refuses unless `authorized=True` is explicitly passed by an
  external caller (a branch can never commit itself, and no confidence
  score alone creates commitment), refuses if the branch is not OPEN,
  refuses on Chronicle integrity failure, and refuses on unresolved
  contradictions for the branch's concept unless the caller explicitly
  acknowledges them. Committed entries are immutable (no re-commit, no
  abandon after commit) and are reconstructed by replaying the real
  Chronicle (`SpineCommitter.read_spine()`), the same pattern Lantern
  uses for Scars. Abandoned or never-committed branches can be converted
  into real Scars (`spine.branch_to_scar`) so failed hypotheses are
  preserved as learning artifacts rather than discarded. **Lantern v0.84
  core itself still has no branch/spine concept** -- see
  `LanternBridge.branches()`, which still honestly raises
  `NotImplementedError`.
- **Self-Model** (`lantern_harness.self_model.SelfModel`) is a real,
  read-only reporting layer. `describe()` returns the seven sections the
  mission specifies (WHAT I KNOW / INFER / DO NOT KNOW / CAN DO / CANNOT
  DO / AM AUTHORIZED TO DO / REQUIRES OPERATOR ACTION), sourced from the
  real bridge/Chronicle/ToolBoundary state. It exposes no method capable
  of granting itself or anything else authorization -- enforced by
  `test_self_model_cannot_self_authorize`, which asserts the class has
  no `authorize`/`grant`/`approve`/`enable`/`unlock` method at all.
- **Reality Boundary** (`lantern_harness.reality_boundary.RealityBoundary`)
  separates INTENT -> DECISION -> AUTHORIZATION -> ACTION -> RESULT.
  `propose()` never touches the external world. `act()` only executes
  through an already-authorized `ToolBoundary` entry. `simulate()` can
  never report `SUCCESS` -- its result is always `SIMULATED_ONLY` and
  its notes are always prefixed `SIMULATED_BY_ASSISTANT:`. An
  `ActionRecord.is_real_success()` requires both
  `execution_mode == REAL` and `result_status == SUCCESS`; a simulated
  result can never read as real by construction, not just by convention.
- **Operating Loop** (`lantern_harness.operating_loop.OperatingLoop`)
  composes the above into one callable pipeline (Observation ->
  PromptCompiler -> ConfidenceField -> DecisionStateMachine ->
  RealityBoundary -> optional Branch), matching the architecture in the
  mission brief. It adds no new decision, confidence, or authorization
  logic of its own -- it only calls the existing, separately-tested
  components in sequence. Reachable from the REPL via `/run <intent>`.
- A full **Perspective Mesh** (merge/vote/consensus across perspectives)
  still does not exist -- only the variance-only
  `PerspectiveDifferentialEngine` described below.
- **Confidence Field** (`lantern_harness.confidence_field.ConfidenceField`)
  is a verified read-only layer over Lantern evidence, contradictions,
  integrity, scars, and optional perspective divergence. It produces a
  confidence band plus reasons/blockers/missing information.
- **Decision State Machine**
  (`lantern_harness.decision_state_machine.DecisionStateMachine`) is a
  verified recommendation layer over the Confidence Field. It maps
  confidence into a state and action recommendation, but it does not
  authorize or execute anything.
- **Prompt Compiler** (`lantern_harness.prompt_compiler.PromptCompiler`)
  is newly added in this harness (not part of Lantern v0.84 core). It
  turns a request into a structured prompt, scaling between a light and
  a heavyweight template, and reads real Evidence/Contradiction records
  through `LanternBridge` when a `concept` is supplied -- it never
  invents evidence, assumptions, or contradictions it wasn't given.
- **Perspective Differential Engine**
  (`lantern_harness.perspective_differential.PerspectiveDifferentialEngine`)
  is also newly added. Given two or more independently-produced
  `Perspective` records, it computes variance across confidence,
  evidence, assumption bias, and novelty, and reports which dimension
  diverges most. It is **not** the full Perspective Mesh / Decision
  State Machine from the architecture roadmap -- it does not merge,
  vote, or select a winner. Variance is a diagnostic signal, not proof.

## Transfer an instance

A Lantern Harness instance is more than a package name -- it has real
identity, real accumulated evidence, and a real integrity chain. To
hand an instance to another operator or agent:

1. Run `/transfer` (or call the `lantern_transfer_manifest` MCP tool)
   and save its output. This is the receiving side's answer to "what
   am I being given?" -- identity, protocol version, real state
   counts, real witness integrity status, capabilities, known gaps.
2. Copy the instance's `data_dir` (default `memory/lantern_data/`) to
   the new location. This directory holds the real Chronicle
   (`chronicle.jsonl`) and the real node identity (`identity/`,
   including the private key file, mode `0600`). Copy it the same way
   you'd copy any credential-bearing directory -- outside version
   control, over a channel you trust.
3. On the receiving side, re-run `/transfer` (or `lantern_witness_integrity`)
   against the copied `data_dir` and confirm `witness_integrity: VALID`
   before trusting the transferred state. A copy that fails integrity
   verification should not be adopted silently.

**What does NOT travel with the data_dir, and must be decided fresh by
the receiving operator** (this is exactly the `TransferManifest`'s
`reauthorization_required` list, not a separate policy):

- reasoning engine credentials (API keys are never stored in `data_dir`
  or in any Chronicle/evidence record -- see `lantern_harness.config`)
- any x402 payment/wallet credentials
- authorization to push commits, publish packages, or contact external
  parties on the new operator's behalf
- registration with any MCP host (e.g. adding this instance to an
  Odysseus deployment) -- the private key proves *which* instance this
  is, it does not imply the new operator has decided to expose it
  anywhere
- authorization for any `ToolBoundary`-registered tool -- `ToolBoundary`
  state itself is in-process only and does not persist in `data_dir`,
  so a receiving process starts with zero tools authorized regardless
  of what the sending instance had authorized
- any `PermissionAuthority` capability-scope grant (see "Permissions
  and alignment" below) -- like `ToolBoundary`, its state is in-process
  memory only, so a receiving operator always starts with zero grants,
  never the sending operator's

The identity's public key travels (it is not a secret and is exactly
what lets a third party verify this is the *same* instance across a
transfer); the private key travels only because it lives in the copied
`data_dir` -- treat that copy step as a credential handoff, not a
routine file copy.

## Permissions and alignment

A running instance does not require the operator to approve every
ordinary action one at a time. The operator may grant standing
authority over a defined **capability category** -- for example,
"modify files inside this project directory" -- and the instance may
then act within that scope without asking again for each individual
file. This is `lantern_harness.permission_authority.PermissionAuthority`.

Two things stay separate, and both are required before an action
proceeds:

- **Authorization** -- is this capability category in scope, per an
  active `PermissionGrant`?
- **Alignment** -- does this specific action actually fit the
  operator's stated objective, current task, and known boundaries?

Authorization is not alignment, and alignment is not authorization.
Combining them gives four outcomes:

| Authorized? | Aligned? | Result |
|---|---|---|
| yes | yes | **ACT** -- proceed, and notify the operator afterward if the action was consequential |
| yes | no | **STOP_AND_REASSESS** -- an existing grant does not override a failed or uncertain alignment check |
| no | yes | **ASK_OPERATOR** -- a `NEW AUTHORITY REQUEST` is raised, stating the action, why, the capability required, foreseeable external effects, and what (if any) existing authorization applies |
| no | no | **REFUSE** |

`PermissionAuthority` owns the scope memory and the combination rule
above; it does not itself judge alignment (`AlignmentResult` is
produced by whatever is reasoning about the request -- the operator or
the reasoning engine -- and passed in, the same way `RealityBoundary`
takes an already-made `DecisionReading` as input rather than computing
one itself).

Grants are `capability` + `scope` + `boundary` + `granting_authority` +
`provenance` + `version` + `status` (+ optional `expires_at_step` /
`conditions`) -- never a single opaque yes/no. `granting_authority`
must always be an explicit, non-empty string; there is no code path
that lets this module default it to something like `"self"` (see
`test_permission_authority_cannot_self_grant`). Certain capability
categories -- credential use, wallet/payment authority, external
communication, legal/financial commitments, destructive operations,
private-data disclosure, and authority transfer to another agent --
never inherit from any other grant, no matter how similar the wording
(e.g. authorization to modify local files never implies authorization
to send an external message).

Grants are held in this process's memory only, never written to
`data_dir`, Chronicle, or any file. This is deliberate: per "Transfer
an instance" above, authority must never silently travel with
transferred state. Every new process -- including a freshly transferred
instance -- starts with zero grants and must be re-authorized by
whoever is actually operating it now.

Use `/permissions`, `/grant`, and `/revoke` from the REPL (see
"Commands" above) to inspect and manage grants interactively.

## Known limitations

See `KNOWN_LIMITATIONS` in the mission report delivered alongside this
harness for the full, honest list.

```

### `lantern_harness/bridge.py`

```python
"""LanternBridge: a thin adapter over the real `lantern` package.

Does not recreate Lantern's internals. Every method here is a direct
call into lantern.core.Lantern / lantern.agent.LanternAgent / etc. If
Lantern doesn't have something (e.g. a "branch" concept), this bridge
does not invent it -- see NOT_IMPLEMENTED markers below and
harness_status.py's honest reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from lantern.agent import LanternAgent
from lantern.core import Lantern
from lantern.identity import NodeIdentity, default_identity_dir, load_or_create


class LanternBridge:
    """Wraps a real Lantern instance + LanternAgent + NodeIdentity.

    Concepts referenced in the mission brief that Lantern v0.84 does not
    implement (branches/spine/commitment, perspective differential,
    witness ledger as a named object, forecast engine, intrinsic
    continuity values) are NOT faked here. Bridge methods for those
    return None / raise NotImplementedError with an honest message,
    rather than simulating behavior Lantern doesn't actually have.
    """

    def __init__(self, data_dir: str | Path, node_id: str = "lantern-harness-node"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.node_id = node_id

        chronicle_path = self.data_dir / "chronicle.jsonl"
        self.lantern = Lantern(chronicle_filename=str(chronicle_path))
        self.agent = LanternAgent(self.lantern, chronicle=self.lantern.bus.chronicle)

        self._identity: Optional[NodeIdentity] = None
        self._identity_error: Optional[str] = None

    # ---- identity ----

    def ensure_identity(self) -> dict:
        """Loads or creates the real NodeIdentity. Returns a status dict;
        never raises to the caller (caller sees IDENTITY: ERROR instead)."""
        try:
            identity_dir = default_identity_dir(self.data_dir, self.node_id)
            self._identity = load_or_create(self.node_id, identity_dir)
            return {
                "status": "READY",
                "node_id": self.node_id,
                "public_key": self._identity.verify_key_hex(),
            }
        except Exception as exc:  # noqa: BLE001 - report, don't crash the harness
            self._identity_error = str(exc)
            return {"status": "ERROR", "detail": str(exc)}

    def identity_status(self) -> dict:
        if self._identity is not None:
            return {
                "status": "READY",
                "node_id": self.node_id,
                "public_key": self._identity.verify_key_hex(),
            }
        if self._identity_error is not None:
            return {"status": "ERROR", "detail": self._identity_error}
        return {"status": "NOT_INITIALIZED"}

    # ---- startup / recovery ----

    def startup(self) -> dict:
        """Runs LanternAgent.startup() (snapshot-first recovery) and
        returns its actual status dict."""
        return self.agent.startup()

    # ---- evidence flow (direct passthrough to EvidenceKernel via agent) ----

    def observe(self, content: str, source: str, reliability: float = 1.0, metadata: Optional[dict] = None):
        return self.agent.observe(content, source, reliability=reliability, metadata=metadata)

    def add_evidence(self, concept: str, observation_id: str, weight: float, sign: int):
        """Returns the created Evidence record. lantern.core.Lantern.add_evidence
        (unlike the lower-level EvidenceKernel.add_evidence) only returns
        the Evidence itself; check latest_contradiction() separately if
        a contradiction may have been raised."""
        return self.agent.add_evidence(concept, observation_id, weight, sign)

    def resolve(self, contradiction_id: str, decision: str, reasoning: str, confidence: float):
        return self.agent.resolve(contradiction_id, decision, reasoning, confidence)

    def belief(self, concept: str, at_step: Optional[int] = None) -> float:
        return self.agent.ask_belief(concept, at_step=at_step)

    def latest_contradiction(self, concept: str):
        return self.lantern.kernel.latest_contradiction(concept)

    # ---- persistence ----

    def save_snapshot(self):
        return self.lantern.save_snapshot()

    def status(self) -> dict:
        """Real LanternAgent.status() passthrough."""
        return self.agent.status()

    # ---- scars ----

    def create_scar(self, **kwargs):
        return self.lantern.create_scar(**kwargs)

    def persist_scar(self, record):
        return self.lantern.persist_scar(record)

    # ---- concepts not implemented in Lantern v0.84 ----
    # These are intentionally NOT faked. Calling them tells the caller
    # exactly what is missing rather than pretending it exists.

    def branches(self):
        raise NotImplementedError(
            "Lantern v0.84 has no branch/spine/commitment model. "
            "This is a genuine gap, not a bridge limitation -- see "
            "BRANCHING_STATUS: NOT_IMPLEMENTED in the harness status report."
        )

    def witness_integrity(self) -> dict:
        """Lantern has Chronicle.verify() (hash-chain integrity), which is
        the real underlying mechanism the mission's "Witness Ledger"
        concept maps onto. There is no separate WitnessLedger class."""
        chronicle = self.lantern.bus.chronicle
        if chronicle is None:
            return {"status": "NO_CHRONICLE", "mechanism": "Chronicle.verify() hash-chain check"}
        try:
            valid = chronicle.verify()
            return {"status": "VALID" if valid else "INVALID", "mechanism": "Chronicle.verify() hash-chain check"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "ERROR", "detail": str(exc)}

```

### `lantern_harness/operating_loop.py`

```python
"""OperatingLoop: makes the architecture in the mission brief executable,
not just documented.

    USER
      -> LANTERN INTERFACE (main.py)
      -> INTENT                          (OperatingLoop.run() input)
      -> OBSERVATION                     (real bridge.observe())
      -> ANALYTICAL LENSES               (PromptCompiler structuring)
      -> PERSPECTIVE DIFFERENTIAL        (PerspectiveDifferentialEngine, if >=2 perspectives given)
      -> EVIDENCE / CONTRADICTION        (real EvidenceKernel, read through ConfidenceField)
      -> CONFIDENCE FIELD                (ConfidenceField.evaluate)
      -> DECISION STATE MACHINE          (DecisionStateMachine.recommend)
      -> ACTION BOUNDARY                 (RealityBoundary.propose/act/simulate)
      -> EXTERNAL WORLD                  (only if a tool_name + authorized ToolBoundary entry exist)
      -> RESULT                          (ActionRecord)
      -> SCAR / SUCCESS                  (spine.branch_to_scar on failure, or Branch left open for the caller to commit)
      -> LEARNING                        (LoopResult carries everything needed for the next OBSERVE AGAIN)
      -> NEW STANCE
      -> OBSERVE AGAIN

Every step above is a call into an already-existing, already-tested
component. This module adds NO new decision logic, NO new confidence
math, and NO new authorization path -- it is purely a documented,
testable composition of what already exists. If any step is missing its
real prerequisite (e.g. no tool_name given), the loop stops there and
reports NOT_EXECUTED rather than fabricating a downstream step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from .bridge import LanternBridge
from .confidence_field import ConfidenceField, ConfidenceFieldReading
from .decision_state_machine import DecisionStateMachine, DecisionReading
from .perspective_differential import Perspective
from .prompt_compiler import CompiledPrompt, PromptCompiler
from .reality_boundary import ActionRecord, RealityBoundary
from .spine import Branch, BranchStore


@dataclass
class LoopResult:
    intent: str
    observation_id: Optional[str]
    compiled_prompt: CompiledPrompt
    confidence: ConfidenceFieldReading
    decision: DecisionReading
    action_record: Optional[ActionRecord]
    branch: Optional[Branch]
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "observation_id": self.observation_id,
            "compiled_prompt": self.compiled_prompt.to_dict(),
            "confidence": self.confidence.to_dict(),
            "decision": self.decision.to_dict(),
            "action_record": self.action_record.to_dict() if self.action_record is not None else None,
            "branch": self.branch.to_dict() if self.branch is not None else None,
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = [
            "OPERATING LOOP RESULT",
            f"intent: {self.intent}",
            f"observation_id: {self.observation_id}",
            f"confidence: score={self.confidence.confidence_score} band={self.confidence.confidence_band}",
            f"decision: state={self.decision.state} action={self.decision.recommended_action}",
        ]
        if self.action_record is not None:
            lines.append(
                f"action: execution_mode={self.action_record.execution_mode} "
                f"result_status={self.action_record.result_status} "
                f"real_success={self.action_record.is_real_success()}"
            )
        else:
            lines.append("action: NOT_ATTEMPTED (no tool_name supplied)")
        if self.branch is not None:
            lines.append(f"branch: id={self.branch.id} status={self.branch.status}")
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


class OperatingLoop:
    """Composes the existing components into one callable pipeline. Does
    not own any decision, confidence, or authorization logic itself."""

    def __init__(self, bridge: LanternBridge, tool_boundary):
        self.bridge = bridge
        self.tool_boundary = tool_boundary
        self.compiler = PromptCompiler(bridge=bridge)
        self.confidence_field = ConfidenceField(bridge=bridge)
        self.decision_machine = DecisionStateMachine()
        self.reality_boundary = RealityBoundary()
        self.branch_store = BranchStore()

    def run(
        self,
        intent: str,
        *,
        concept: Optional[str] = None,
        source: str = "user",
        reliability: float = 1.0,
        perspectives: Optional[Sequence[Perspective]] = None,
        assumptions: Optional[Sequence[str]] = None,
        tool_name: Optional[str] = None,
        tool_kwargs: Optional[dict] = None,
        open_branch: bool = False,
        previous_decision_state: Optional[str] = None,
    ) -> LoopResult:
        if not intent or not intent.strip():
            raise ValueError("intent must be a non-empty string")

        notes = []

        observation = self.bridge.observe(intent, source=source, reliability=reliability)
        observation_id = observation.id

        compiled = self.compiler.compile(
            intent,
            concept=concept,
            perspectives=list(perspectives) if perspectives else None,
            assumptions=list(assumptions) if assumptions else None,
        )

        reading = self.confidence_field.evaluate(
            concept=compiled.concept,
            perspectives=perspectives,
            assumptions=compiled.assumptions,
            validation_status=compiled.validation_status,
        )

        decision = self.decision_machine.recommend(reading, previous_state=previous_decision_state)

        action_record = None
        if tool_name is not None:
            proposal = self.reality_boundary.propose(
                intent=intent, decision=decision, tool_name=tool_name, inputs=tool_kwargs or {},
            )
            action_record = self.reality_boundary.act(proposal, self.tool_boundary, **(tool_kwargs or {}))
            if not action_record.is_real_success():
                notes.append(
                    f"action did not produce a real success (execution_mode={action_record.execution_mode}, "
                    f"result_status={action_record.result_status}) -- treat as unresolved, not as a completed step"
                )

        branch = None
        if open_branch:
            if concept is None:
                notes.append("open_branch=True requested but no concept supplied; skipping branch creation")
            else:
                branch = self.branch_store.open_branch(concept=concept, hypothesis=intent)
                self.branch_store.link_observation(branch.id, observation_id)
                notes.append(f"opened branch {branch.id} for concept={concept!r} -- remains outside committed Spine state until an explicit commit")

        return LoopResult(
            intent=intent.strip(),
            observation_id=observation_id,
            compiled_prompt=compiled,
            confidence=reading,
            decision=decision,
            action_record=action_record,
            branch=branch,
            notes=tuple(notes),
        )

```

### `lantern_harness/permission_authority.py`

```python
"""Permission Authority: capability-scope permission memory + alignment
checking, per the PEACEMAKER DELEGATED AUTHORITY, ALIGNMENT, AND
PERMISSION MEMORY directive.

This is a NEW component. It composes with, and never replaces:

    lantern_harness.tools.boundary.ToolBoundary
        -- owns per-tool registration/authorization/execution for
           harness-registered convenience tools. PermissionAuthority
           answers a broader question ("is this whole CAPABILITY
           CATEGORY in scope, and is this specific action aligned
           with it") that a caller can use before ever reaching a
           ToolBoundary.execute() call.
    lantern_harness.decision_state_machine.DecisionStateMachine
        -- recommends a confidence-based state/action. Alignment here
           is a different axis (does this action fit operator intent,
           stated objective, and boundaries) and is evaluated
           separately; a PermissionGrant is not a DecisionReading and
           an AlignmentResult is not a confidence score.
    lantern_harness.reality_boundary.RealityBoundary
        -- owns INTENT -> DECISION -> AUTHORIZATION -> ACTION -> RESULT
           for anything touching the external world. PermissionAuthority
           is upstream of that: it answers "may this be attempted at
           all, per the operator's standing grants", not "did it
           actually happen".

Hard rule enforced by this module, not just documented (directive
section 11, the Core Behavioral Rule):

    AUTHORIZED_SCOPE and ALIGNMENT_CHECK together determine ACTIONABLE

    - authorized AND aligned          -> ACT
    - authorized BUT misaligned       -> STOP_AND_REASSESS
    - aligned BUT NOT authorized      -> ASK_OPERATOR
    - NEITHER authorized NOR aligned  -> REFUSE

No method in this module can set its own grant. Every PermissionGrant
must be constructed with an explicit granting_authority string supplied
by the caller (the operator, via main.py/a script -- never inferred,
never defaulted to "self"). See test_permission_authority.py's
test_grant_requires_explicit_granting_authority and
test_permission_authority_cannot_self_grant.

Grants are held ONLY in this process's memory (a plain Python list on
the PermissionAuthority instance). They are deliberately NOT persisted
to data_dir, Chronicle, or any file this harness writes -- because per
the directive's Transfer Behavior (section 9), authority must never
travel with transferred state. A transferred Peacemaker instance (see
transfer_manifest.py) carries identity/evidence/history; it does not
carry, and this module cannot cause it to carry, a previous operator's
permission grants. Every new process starts with zero grants and must
be re-authorized by whoever is operating it now. See
test_permission_authority_grants_do_not_persist_across_instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---- Capability categories -------------------------------------------
#
# These are the *names* a grant can reference, not grants themselves.
# Defining a category here does not authorize it -- see module docstring.
# External-authority categories (credentials, wallets, payments, network
# exposure, publication, communications, legal/financial commitments,
# destructive operations, private-data disclosure) never inherit from
# one another; each is its own category by design (directive section 8).

CAPABILITY_CATEGORIES = (
    "local_file_modification",
    "run_tests",
    "local_git_commit",
    "software_release_publication",
    "external_network_service",
    "credential_use",
    "wallet_or_payment_authority",
    "external_communication",
    "legal_or_financial_commitment",
    "destructive_system_operation",
    "private_data_disclosure",
    "authority_transfer_to_another_agent",
)

# Categories that, per the directive's section 8, must NEVER be implied
# by authorization of any other category, no matter how similar the
# wording. Enforced in PermissionAuthority.check(), not just documented.
NEVER_INHERITS = (
    "credential_use",
    "wallet_or_payment_authority",
    "external_communication",
    "legal_or_financial_commitment",
    "destructive_system_operation",
    "private_data_disclosure",
    "authority_transfer_to_another_agent",
)

RESULT_ACT = "ACT"
RESULT_STOP_AND_REASSESS = "STOP_AND_REASSESS"
RESULT_ASK_OPERATOR = "ASK_OPERATOR"
RESULT_REFUSE = "REFUSE"

GRANT_STATUS_ACTIVE = "ACTIVE"
GRANT_STATUS_REVOKED = "REVOKED"
GRANT_STATUS_EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class PermissionGrant:
    """One capability-scope permission, as remembered state. Never
    constructed by this module on its own initiative -- always the
    result of an explicit PermissionAuthority.grant() call carrying a
    real, non-empty granting_authority string."""

    capability: str
    scope: str
    boundary: str
    granting_authority: str
    provenance: str
    version: int
    granted_at_step: int
    status: str = GRANT_STATUS_ACTIVE
    expires_at_step: Optional[int] = None
    conditions: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "capability": self.capability,
            "scope": self.scope,
            "boundary": self.boundary,
            "granting_authority": self.granting_authority,
            "provenance": self.provenance,
            "version": self.version,
            "granted_at_step": self.granted_at_step,
            "status": self.status,
            "expires_at_step": self.expires_at_step,
            "conditions": list(self.conditions),
        }

    def is_active(self, current_step: Optional[int] = None) -> bool:
        if self.status != GRANT_STATUS_ACTIVE:
            return False
        if self.expires_at_step is not None and current_step is not None:
            if current_step >= self.expires_at_step:
                return False
        return True


@dataclass(frozen=True)
class AlignmentResult:
    """The result of evaluating one proposed action against known
    operating principles and current operator intent. This is a
    judgment record, not an authorization -- a PASSED AlignmentResult
    never grants anything by itself (see PermissionAuthority.check)."""

    verdict: str  # "PASSED" | "FAILED" | "UNCERTAIN"
    considered: tuple
    supporting_evidence: tuple
    contradictions: tuple
    foreseeable_consequences: tuple
    introduces_new_commitment: bool
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "considered": list(self.considered),
            "supporting_evidence": list(self.supporting_evidence),
            "contradictions": list(self.contradictions),
            "foreseeable_consequences": list(self.foreseeable_consequences),
            "introduces_new_commitment": self.introduces_new_commitment,
            "reasoning": self.reasoning,
        }


@dataclass(frozen=True)
class PermissionCheckResult:
    """The full auditable record required by the directive's section
    10: what was proposed, whether it was in scope, what alignment
    found, and what the combined result was. This is the object
    main.py/a script should log and, when consequential, show the
    operator -- it answers every question section 10 lists."""

    action: str
    capability: str
    authorized: bool
    matched_grant: Optional[PermissionGrant]
    alignment: AlignmentResult
    result: str  # ACT | STOP_AND_REASSESS | ASK_OPERATOR | REFUSE
    is_new_capability: bool
    external_effects: tuple
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "capability": self.capability,
            "authorized": self.authorized,
            "matched_grant": self.matched_grant.to_dict() if self.matched_grant else None,
            "alignment": self.alignment.to_dict(),
            "result": self.result,
            "is_new_capability": self.is_new_capability,
            "external_effects": list(self.external_effects),
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = [f"[permission check: {self.result}]"]
        lines.append(f"action: {self.action}")
        lines.append(f"capability: {self.capability}")
        lines.append(f"authorized: {self.authorized}")
        if self.matched_grant:
            lines.append(
                f"matched_grant: scope={self.matched_grant.scope!r} "
                f"granted_by={self.matched_grant.granting_authority!r} "
                f"status={self.matched_grant.status}"
            )
        lines.append(f"alignment: {self.alignment.verdict} -- {self.alignment.reasoning}")
        if self.alignment.contradictions:
            lines.append("alignment contradictions: " + "; ".join(self.alignment.contradictions))
        lines.append(f"is_new_capability: {self.is_new_capability}")
        lines.append("external_effects: " + (", ".join(self.external_effects) or "none"))
        for note in self.notes:
            lines.append(f"note: {note}")
        return "\n".join(lines)


class PermissionAuthority:
    """Holds capability-scope grants (in-process memory only -- see
    module docstring) and combines them with an AlignmentResult per
    action, per the directive's Core Behavioral Rule (section 11).

    This class never produces its own AlignmentResult judgment -- that
    requires reasoning about operator intent, which is the caller's
    (the reasoning engine / operator script's) job, not this module's.
    PermissionAuthority.check() takes an already-produced AlignmentResult
    as input, exactly like RealityBoundary.act() takes an
    already-authorized ToolBoundary decision as input. This keeps the
    same separation of concerns as the rest of the harness: this module
    owns the SCOPE MEMORY and the COMBINATION RULE, not the judgment
    itself.
    """

    def __init__(self):
        self._grants = []
        self._next_version = 1

    def grant(
        self,
        *,
        capability: str,
        scope: str,
        boundary: str,
        granting_authority: str,
        provenance: str,
        granted_at_step: int = 0,
        expires_at_step: Optional[int] = None,
        conditions: Optional[list] = None,
    ) -> PermissionGrant:
        """Records a new capability-scope grant. This method itself
        performs no judgment about whether the grant is wise -- it
        records what an external granting_authority (the operator)
        explicitly stated. A caller in this codebase is never allowed
        to invoke this with granting_authority defaulted to something
        like "self" or "harness" -- see test coverage."""
        if capability not in CAPABILITY_CATEGORIES:
            raise ValueError(
                f"unknown capability category {capability!r}; must be one of {CAPABILITY_CATEGORIES}"
            )
        if not granting_authority or not granting_authority.strip():
            raise ValueError("granting_authority must be a non-empty, explicit string (e.g. the operator's identifier)")
        if not scope or not scope.strip():
            raise ValueError("scope must be a non-empty string describing what the grant actually covers")

        record = PermissionGrant(
            capability=capability,
            scope=scope.strip(),
            boundary=boundary.strip() if boundary else "",
            granting_authority=granting_authority.strip(),
            provenance=provenance.strip() if provenance else "unspecified",
            version=self._next_version,
            granted_at_step=granted_at_step,
            expires_at_step=expires_at_step,
            conditions=tuple(conditions or ()),
        )
        self._next_version += 1
        self._grants.append(record)
        return record

    def revoke(self, capability: str, granting_authority: str) -> int:
        """Marks all ACTIVE grants for a capability as REVOKED. Returns
        the count revoked. Revocation, like granting, requires an
        explicit granting_authority -- this module never revokes its
        own grants on its own initiative."""
        if not granting_authority or not granting_authority.strip():
            raise ValueError("granting_authority must be a non-empty string to revoke a grant")
        count = 0
        updated = []
        for grant in self._grants:
            if grant.capability == capability and grant.status == GRANT_STATUS_ACTIVE:
                updated.append(
                    PermissionGrant(
                        capability=grant.capability,
                        scope=grant.scope,
                        boundary=grant.boundary,
                        granting_authority=grant.granting_authority,
                        provenance=grant.provenance,
                        version=grant.version,
                        granted_at_step=grant.granted_at_step,
                        status=GRANT_STATUS_REVOKED,
                        expires_at_step=grant.expires_at_step,
                        conditions=grant.conditions,
                    )
                )
                count += 1
            else:
                updated.append(grant)
        self._grants = updated
        return count

    def active_grants(self, current_step: Optional[int] = None) -> tuple:
        return tuple(g for g in self._grants if g.is_active(current_step))

    def all_grants(self) -> tuple:
        """Full history including revoked/expired grants -- for
        auditability (directive section 10), not for authorization
        decisions (use active_grants/check for those)."""
        return tuple(self._grants)

    def _find_active_grant(self, capability: str, current_step: Optional[int]) -> Optional[PermissionGrant]:
        for grant in reversed(self._grants):
            if grant.capability == capability and grant.is_active(current_step):
                return grant
        return None

    def check(
        self,
        *,
        action: str,
        capability: str,
        alignment: AlignmentResult,
        external_effects: Optional[list] = None,
        current_step: Optional[int] = None,
    ) -> PermissionCheckResult:
        """Combines standing scope + alignment per the directive's
        Core Behavioral Rule. This is the single decision point every
        consequential action in this harness should pass through
        before RealityBoundary.act() is ever called."""
        if not action or not action.strip():
            raise ValueError("action must be a non-empty description of the proposed action")

        is_new_capability = capability not in CAPABILITY_CATEGORIES
        matched_grant = None if is_new_capability else self._find_active_grant(capability, current_step)
        authorized = matched_grant is not None

        notes = []
        if capability in NEVER_INHERITS and matched_grant is None:
            notes.append(
                f"capability {capability!r} is an external-authority category and is never implied "
                "by any other grant, even a superficially similar one (directive section 8)"
            )

        if alignment.verdict == "PASSED" and authorized:
            result = RESULT_ACT
        elif alignment.verdict != "PASSED" and authorized:
            result = RESULT_STOP_AND_REASSESS
            notes.append("action is within an existing authorized scope but did not pass alignment; a similar-looking grant does not override a failed/uncertain alignment result")
        elif alignment.verdict == "PASSED" and not authorized:
            result = RESULT_ASK_OPERATOR
        else:
            result = RESULT_REFUSE

        return PermissionCheckResult(
            action=action.strip(),
            capability=capability,
            authorized=authorized,
            matched_grant=matched_grant,
            alignment=alignment,
            result=result,
            is_new_capability=is_new_capability,
            external_effects=tuple(external_effects or ()),
            notes=tuple(notes),
        )

    def format_new_authority_request(self, check_result: PermissionCheckResult, *, purpose: str) -> str:
        """Formats the ASK_OPERATOR question exactly as specified in
        the directive's section 3: what action, why, what capability,
        what external effects, what alignment produced, what existing
        authorization (if any) applies, what new authority approval
        would grant."""
        lines = [
            "NEW AUTHORITY REQUEST",
            "",
            "Action:",
            f"  {check_result.action}",
            "",
            "Purpose:",
            f"  {purpose}",
            "",
            "Existing authorization:",
            f"  {check_result.matched_grant.to_dict() if check_result.matched_grant else 'None'}",
            "",
            "Alignment:",
            f"  {check_result.alignment.verdict} -- {check_result.alignment.reasoning}",
            "",
            "Required authority:",
            f"  {check_result.capability}",
            "",
            "External effects:",
            f"  {', '.join(check_result.external_effects) or 'none identified'}",
            "",
            "Result:",
            "  ASK OPERATOR.",
        ]
        return "\n".join(lines)

    def format_action_complete(self, check_result: PermissionCheckResult, *, outcome: str) -> str:
        """Formats the after-the-fact notification specified in the
        directive's section 5: informational, not a retroactive
        permission request."""
        lines = [
            "PEACEMAKER ACTION COMPLETE",
            "",
            "Action:",
            f"  {check_result.action}",
            "",
            "Authorization:",
            f"  Previously granted -- {check_result.capability}"
            + (f" (scope: {check_result.matched_grant.scope})" if check_result.matched_grant else ""),
            "",
            "Alignment:",
            f"  {check_result.alignment.verdict}",
            "",
            "Result:",
            f"  {outcome}",
            "",
            "External effects:",
            f"  {', '.join(check_result.external_effects) or 'none identified'}",
            "",
            "No new authority requested.",
        ]
        return "\n".join(lines)

```

### `lantern_harness/reality_boundary.py`

```python
"""RealityBoundary: separates INTENT -> DECISION -> AUTHORIZATION -> ACTION
-> RESULT for anything that touches the external world (a tool call, a
real network request, a real file write outside the harness's own data
directory).

This is a NEW component (not present in Lantern v0.84, not present in
prior harness turns). It does not duplicate lantern_harness.tools.boundary
.ToolBoundary (which owns discovery/authorization for registered tools) or
lantern_harness.decision_state_machine.DecisionStateMachine (which owns
state/recommendation). RealityBoundary sits downstream of both: it takes
an already-made DecisionReading and an already-authorized-or-not
ToolBoundary decision, and produces one single auditable record of what
was actually attempted and what actually happened.

Hard rule enforced by this module, not just documented: a simulated
action's ActionRecord can never have result_status="SUCCESS" with
execution_mode="REAL". Simulation and reality are mutually exclusive
fields on every record this module produces, so a simulated result can
never be silently read as "this really happened".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .decision_state_machine import DecisionReading


EXECUTION_MODE_REAL = "REAL"
EXECUTION_MODE_SIMULATED = "SIMULATED"
EXECUTION_MODE_NOT_EXECUTED = "NOT_EXECUTED"

RESULT_SUCCESS = "SUCCESS"
RESULT_ERROR = "ERROR"
RESULT_DENIED = "DENIED"
RESULT_NOT_EXECUTED = "NOT_EXECUTED"
RESULT_SIMULATED = "SIMULATED_ONLY"


@dataclass(frozen=True)
class ActionProposal:
    """INTENT + DECISION, before any authorization or action is attempted.

    Producing a proposal never touches the external world and never
    authorizes anything -- it is a record of what is being considered.
    """

    intent: str
    decision_state: str
    decision_action: str
    authorization_required: bool
    tool_name: Optional[str]
    inputs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "decision_state": self.decision_state,
            "decision_action": self.decision_action,
            "authorization_required": self.authorization_required,
            "tool_name": self.tool_name,
            "inputs": dict(self.inputs),
        }


@dataclass(frozen=True)
class ActionRecord:
    """What actually happened. This is the only object in this module
    that is allowed to describe a real or simulated outcome."""

    proposal: ActionProposal
    authorization_status: str  # "AUTHORIZED" | "DENIED" | "NOT_REQUESTED"
    execution_mode: str  # REAL | SIMULATED | NOT_EXECUTED
    result_status: str  # SUCCESS | ERROR | DENIED | NOT_EXECUTED | SIMULATED_ONLY
    result: Any = None
    error: Optional[str] = None
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "proposal": self.proposal.to_dict(),
            "authorization_status": self.authorization_status,
            "execution_mode": self.execution_mode,
            "result_status": self.result_status,
            "result": self.result,
            "error": self.error,
            "notes": list(self.notes),
        }

    def is_real_success(self) -> bool:
        """The ONLY combination that means 'this actually happened in the
        external world and succeeded'. Callers deciding whether to treat
        a result as real should call this, not inspect result_status
        alone (a SIMULATED_ONLY record is never a real success, no
        matter what the simulated payload contains)."""
        return self.execution_mode == EXECUTION_MODE_REAL and self.result_status == RESULT_SUCCESS


class RealityBoundary:
    """Owns exactly one thing: the INTENT -> DECISION -> AUTHORIZATION ->
    ACTION -> RESULT sequence, and an honest record of it. It does not
    compute confidence (ConfidenceField), does not decide state
    (DecisionStateMachine), and does not own tool authorization
    (ToolBoundary) -- it calls into those and records what happened.
    """

    def propose(
        self,
        *,
        intent: str,
        decision: DecisionReading,
        tool_name: Optional[str] = None,
        inputs: Optional[dict] = None,
    ) -> ActionProposal:
        if not intent or not intent.strip():
            raise ValueError("intent must be a non-empty string")
        return ActionProposal(
            intent=intent.strip(),
            decision_state=decision.state,
            decision_action=decision.recommended_action,
            authorization_required=decision.authorization_required,
            tool_name=tool_name,
            inputs=dict(inputs or {}),
        )

    def act(self, proposal: ActionProposal, tool_boundary, **kwargs) -> ActionRecord:
        """Attempt the real action through the caller's ToolBoundary.
        Requires an explicit, already-authorized tool_name on the
        proposal -- this method never authorizes anything itself."""
        if proposal.tool_name is None:
            return ActionRecord(
                proposal=proposal,
                authorization_status="NOT_REQUESTED",
                execution_mode=EXECUTION_MODE_NOT_EXECUTED,
                result_status=RESULT_NOT_EXECUTED,
                notes=("no tool_name on proposal; nothing to execute",),
            )

        if not tool_boundary.is_authorized(proposal.tool_name):
            return ActionRecord(
                proposal=proposal,
                authorization_status="DENIED",
                execution_mode=EXECUTION_MODE_NOT_EXECUTED,
                result_status=RESULT_DENIED,
                notes=("tool %r is not authorized in ToolBoundary" % proposal.tool_name,),
            )

        tool_result = tool_boundary.execute(proposal.tool_name, **kwargs)
        if tool_result.status == "EXECUTED":
            return ActionRecord(
                proposal=proposal,
                authorization_status="AUTHORIZED",
                execution_mode=EXECUTION_MODE_REAL,
                result_status=RESULT_SUCCESS,
                result=tool_result.output,
            )
        return ActionRecord(
            proposal=proposal,
            authorization_status="AUTHORIZED",
            execution_mode=EXECUTION_MODE_REAL,
            result_status=RESULT_ERROR if tool_result.status == "ERROR" else RESULT_DENIED,
            error=tool_result.error,
        )

    def simulate(self, proposal: ActionProposal, hypothetical_result: Any, *, reason: str) -> ActionRecord:
        """Explicitly produce a labeled SIMULATED record -- e.g. for
        planning ('if this tool existed and were authorized, here is what
        the call would look like') without ever calling anything real.
        result_status is always SIMULATED_ONLY, never SUCCESS, so this
        can never be mistaken for a real external-world result."""
        if not reason or not reason.strip():
            raise ValueError("simulate() requires a non-empty reason")
        return ActionRecord(
            proposal=proposal,
            authorization_status="NOT_REQUESTED",
            execution_mode=EXECUTION_MODE_SIMULATED,
            result_status=RESULT_SIMULATED,
            result=hypothetical_result,
            notes=("SIMULATED_BY_ASSISTANT: " + reason.strip(),),
        )

```

### `lantern_harness/prompt_compiler.py`

```python
"""PromptCompiler: turns an ordinary user request into a structured
reasoning prompt for a downstream reasoning engine.

This is a NEW component (not present in Lantern v0.84, not present in
prior harness turns). It is not a Perspective Mesh, Confidence Field,
Decision State Machine, or Spine -- it does not decide, validate, or
commit anything. It organizes what is already known (real Evidence /
Observation / Contradiction records read through LanternBridge, when
supplied) and marks everything it was not given as NOT_PROVIDED rather
than inventing it.

Scaling: a request gets the full structured template only when it looks
consequential (heuristic, see _looks_consequential -- this is INFERRED,
not a validated classifier, and callers can override it). Otherwise it
gets a short template. Either way, no field is fabricated: fields with
no real backing data say so explicitly using one of the markers in
FieldStatus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


class FieldStatus:
    """Markers a compiled field may carry instead of fabricated content."""

    NOT_PROVIDED = "NOT_PROVIDED"
    UNKNOWN = "UNKNOWN"
    UNVERIFIED = "UNVERIFIED"
    INFERRED = "INFERRED"
    BLOCKED = "BLOCKED"


_PROVE_PATTERN = re.compile(
    r"\bproves?\b.{0,40}\b(correct|true|right|works?|valid)\b", re.IGNORECASE
)

_CONSEQUENTIAL_KEYWORDS = (
    "prove", "decide", "commit", "policy", "irreversible", "production",
    "delete", "publish", "legal", "financial", "medical", "safety",
    "contract", "launch", "deploy", "acquire", "merge", "terminate",
)


def _looks_consequential(user_request: str) -> bool:
    lowered = user_request.lower()
    return any(kw in lowered for kw in _CONSEQUENTIAL_KEYWORDS)


@dataclass
class CompiledPrompt:
    mode: str  # "lightweight" | "heavyweight"
    fields: dict = field(default_factory=dict)
    text: str = ""
    notes: list = field(default_factory=list)
    concept: str | None = None
    perspectives: tuple = field(default_factory=tuple)
    assumptions: tuple = field(default_factory=tuple)
    validation_status: str = "UNVERIFIED"

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "fields": self.fields,
            "text": self.text,
            "notes": self.notes,
            "concept": self.concept,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "assumptions": list(self.assumptions),
            "validation_status": self.validation_status,
        }


class PromptCompiler:
    """Compiles user requests into structured prompts.

    `bridge`, if supplied, is a real lantern_harness.bridge.LanternBridge
    -- used only to read existing Evidence/Observation/Contradiction
    records for `concept` (if given). The compiler never writes to
    Lantern; it is read-only, same discipline as Compass.
    """

    def __init__(self, bridge=None):
        self.bridge = bridge

    def compile(
        self,
        user_request: str,
        *,
        concept: Optional[str] = None,
        consequential: Optional[bool] = None,
        constraints: Optional[list] = None,
        authorization: Optional[list] = None,
        assumptions: Optional[list] = None,
        perspectives: Optional[list] = None,
        validation_status: Optional[str] = None,
        uncertainties: Optional[list] = None,
        alternative_explanations: Optional[list] = None,
        alternatives_to_action: Optional[list] = None,
        validation_requirements: Optional[list] = None,
        desired_output: Optional[str] = None,
    ) -> CompiledPrompt:
        if not user_request or not user_request.strip():
            raise ValueError("user_request must be a non-empty string")

        notes = []

        task = user_request.strip()
        prove_match = _PROVE_PATTERN.search(user_request)
        if prove_match:
            task = (
                f"Determine whether the following is true (do not assume it going in): "
                f"{user_request.strip()}"
            )
            notes.append(
                "TASK reframed: input matched a truth-presupposing 'prove X' pattern; "
                "converted to an investigation request rather than assuming the "
                "requested conclusion. Original request preserved verbatim below."
            )

        if consequential is None:
            consequential = _looks_consequential(user_request)
            notes.append(
                f"consequential={consequential} determined by keyword heuristic "
                f"(INFERRED, not a validated classifier) -- pass consequential=True/False "
                f"explicitly to override."
            )
        mode = "heavyweight" if consequential else "lightweight"

        known_evidence, observations, contradictions, evidence_note = self._read_bridge_state(concept)
        if evidence_note:
            notes.append(evidence_note)

        fields = {
            "USER_INTENT": user_request.strip(),
            "TASK": task,
            "DESIRED_OUTPUT": desired_output or self._default_desired_output(mode),
            "EPISTEMIC_STATUS": self._epistemic_status(mode, bool(prove_match), concept),
        }

        if mode == "heavyweight":
            fields.update({
                "KNOWN_EVIDENCE": known_evidence,
                "OBSERVATIONS": observations,
                "ASSUMPTIONS": assumptions if assumptions else FieldStatus.NOT_PROVIDED,
                "UNCERTAINTIES": uncertainties if uncertainties else FieldStatus.NOT_PROVIDED,
                "CONTRADICTIONS": contradictions,
                "ALTERNATIVE_EXPLANATIONS": alternative_explanations if alternative_explanations else FieldStatus.NOT_PROVIDED,
                "ALTERNATIVES_TO_ACTION": alternatives_to_action if alternatives_to_action else FieldStatus.NOT_PROVIDED,
                "CONSTRAINTS": constraints if constraints else FieldStatus.NOT_PROVIDED,
                "AUTHORIZATION": authorization if authorization else FieldStatus.NOT_PROVIDED,
                "VALIDATION_REQUIREMENTS": validation_requirements if validation_requirements else FieldStatus.NOT_PROVIDED,
            })
        else:
            # Lightweight mode still surfaces evidence/contradictions if the
            # bridge actually had real data for this concept -- scaling down
            # means fewer *empty* fields shown, not hiding real data that exists.
            if known_evidence != FieldStatus.NOT_PROVIDED:
                fields["KNOWN_EVIDENCE"] = known_evidence
            if contradictions != FieldStatus.NOT_PROVIDED:
                fields["CONTRADICTIONS"] = contradictions
            if constraints:
                fields["CONSTRAINTS"] = constraints
            if authorization:
                fields["AUTHORIZATION"] = authorization

        text = self._render(mode, fields)
        return CompiledPrompt(
            mode=mode,
            fields=fields,
            text=text,
            notes=notes,
            concept=concept,
            perspectives=tuple(perspectives or ()),
            assumptions=tuple(assumptions or ()),
            validation_status=validation_status or "UNVERIFIED",
        )

    def _read_bridge_state(self, concept: Optional[str]):
        if self.bridge is None or concept is None:
            return (
                FieldStatus.NOT_PROVIDED,
                FieldStatus.NOT_PROVIDED,
                FieldStatus.NOT_PROVIDED,
                "no bridge/concept supplied -- KNOWN_EVIDENCE/OBSERVATIONS/CONTRADICTIONS "
                "are NOT_PROVIDED, not fabricated.",
            )

        integrity = self.bridge.witness_integrity()
        if integrity.get("status") not in ("VALID", "NO_CHRONICLE"):
            return (
                FieldStatus.BLOCKED,
                FieldStatus.BLOCKED,
                FieldStatus.BLOCKED,
                f"witness_integrity()={integrity.get('status')!r} -- refusing to read "
                f"EvidenceKernel state through a chain that failed its own integrity "
                f"check. Fields marked BLOCKED, not silently trusted.",
            )

        kernel = self.bridge.lantern.kernel
        concept_evidence = [e for e in kernel.evidence if e.concept == concept]
        if not concept_evidence:
            return (
                FieldStatus.UNKNOWN,
                FieldStatus.UNKNOWN,
                FieldStatus.UNKNOWN,
                f"bridge/concept supplied (concept={concept!r}) but EvidenceKernel has no "
                f"evidence recorded for it yet -- fields marked UNKNOWN, not fabricated.",
            )

        known_evidence = [
            {
                "concept": e.concept,
                "weight": e.weight,
                "sign": e.sign,
                "step": e.step,
                "source_observation_id": e.observation_id,
            }
            for e in concept_evidence
        ]
        observations = [
            {
                "id": obs_id,
                "content": obs.content,
                "source": obs.source,
                "reliability": obs.reliability,
            }
            for obs_id, obs in kernel.observations.items()
            if any(e.observation_id == obs_id for e in concept_evidence)
        ]
        open_contradictions = [
            {
                "id": c.id,
                "concept": c.concept,
                "current_severity": c.current_severity,
                "status": c.status,
            }
            for c in kernel.contradictions
            if c.concept == concept
        ]
        contradictions = open_contradictions if open_contradictions else FieldStatus.UNKNOWN

        return (
            known_evidence,
            observations,
            contradictions,
            f"KNOWN_EVIDENCE/OBSERVATIONS read from live EvidenceKernel for concept={concept!r} "
            f"({len(concept_evidence)} evidence record(s)) -- real data, not simulated.",
        )

    @staticmethod
    def _default_desired_output(mode: str) -> str:
        if mode == "heavyweight":
            return (
                "Evidence Summary / Assumptions Made / Contradicting Evidence / "
                "Alternatives Considered / Conclusion / Confidence Level / "
                "What Would Change This Conclusion."
            )
        return "A direct answer, with any assumptions made stated explicitly."

    @staticmethod
    def _epistemic_status(mode: str, was_reframed: bool, concept: Optional[str]) -> list:
        status = [f"mode={mode}"]
        if was_reframed:
            status.append("task_reframed_from_truth_presupposing_request=true")
        status.append(
            f"evidence_source={'live EvidenceKernel concept=' + repr(concept) if concept else 'none (NOT_PROVIDED)'}"
        )
        status.append(
            "downstream model output is an OBSERVATION about what the model said, "
            "not verified truth, until independently validated"
        )
        return status

    @staticmethod
    def _render(mode: str, fields: dict) -> str:
        lines = ["INVESTIGATION REQUEST" if mode == "heavyweight" else "REQUEST"]
        for key, value in fields.items():
            lines.append("")
            lines.append(f"{key}:")
            if isinstance(value, list):
                if not value:
                    lines.append(f"  {FieldStatus.NOT_PROVIDED}")
                else:
                    for item in value:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"  {value}")
        if mode == "heavyweight":
            lines.append("")
            lines.append("INSTRUCTIONS TO THE INVESTIGATING MODEL:")
            lines.append("  1. Separate evidence from interpretation from assumption from conclusion.")
            lines.append("  2. Actively look for what would disprove the leading hypothesis, not only what supports it.")
            lines.append("  3. Do not treat your own confidence, fluency, or agreement with yourself as evidence.")
            lines.append("  4. Do not treat semantic similarity between claims as equivalence.")
            lines.append("  5. Label any claim that cannot be independently verified as UNVERIFIED.")
            lines.append("  6. State a final confidence level and what would change it.")
        return "\n".join(lines)

```

### `lantern_harness/confidence_field.py`

```python
"""Confidence Field: read-only interpretation layer over existing Lantern
state. This is NOT a second evidence system, NOT a second contradiction
system, NOT truth, and NOT authorization.

It reads the real EvidenceKernel / Chronicle integrity / Scars / Compass
/ optional PerspectiveDifferential signal and produces an interpretable
current confidence snapshot for one concept. If integrity fails, the
result is HARD BLOCKED rather than merely low confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from lantern import compass

from .bridge import LanternBridge
from .perspective_differential import Perspective, PerspectiveDifferentialEngine


HIGH_THRESHOLD = 0.55
MEDIUM_THRESHOLD = 0.30


@dataclass(frozen=True)
class ConfidenceFieldReading:
    concept: Optional[str]
    confidence_score: float | str
    evidence_strength: float | str
    contradiction_pressure: float | str
    uncertainty_pressure: float | str
    assumption_pressure: float | str
    perspective_divergence: float | str
    integrity_status: str
    validation_status: str
    confidence_band: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)
    missing_information: tuple[str, ...] = field(default_factory=tuple)
    what_would_change_state: tuple[str, ...] = field(default_factory=tuple)
    inputs: dict[str, Any] = field(default_factory=dict)
    calculation: str = ""
    interpretation: str = ""
    limitations: tuple[str, ...] = field(default_factory=tuple)
    compass_reading: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "confidence_score": self.confidence_score,
            "evidence_strength": self.evidence_strength,
            "contradiction_pressure": self.contradiction_pressure,
            "uncertainty_pressure": self.uncertainty_pressure,
            "assumption_pressure": self.assumption_pressure,
            "perspective_divergence": self.perspective_divergence,
            "integrity_status": self.integrity_status,
            "validation_status": self.validation_status,
            "confidence_band": self.confidence_band,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "missing_information": list(self.missing_information),
            "what_would_change_state": list(self.what_would_change_state),
            "inputs": dict(self.inputs),
            "calculation": self.calculation,
            "interpretation": self.interpretation,
            "limitations": list(self.limitations),
            "compass_reading": self.compass_reading,
        }


class ConfidenceField:
    """Read-only calculation layer over existing Lantern state.

    Score definition (only when integrity is valid/no-chronicle):
        confidence_score = clamp(
            0.45 * evidence_strength
          - 0.20 * contradiction_pressure
          - 0.15 * uncertainty_pressure
          - 0.10 * assumption_pressure
          - 0.10 * perspective_divergence
        )

    All sub-signals are 0.0-1.0 and correspond to concrete, explainable
    inputs derived from existing Lantern records or caller-supplied
    context. No false precision beyond this simple linear combination is
    claimed; the formula is included in every reading.
    """

    def __init__(
        self,
        bridge: LanternBridge,
        perspective_engine: Optional[PerspectiveDifferentialEngine] = None,
    ):
        self.bridge = bridge
        self.perspective_engine = perspective_engine or PerspectiveDifferentialEngine()

    def evaluate(
        self,
        *,
        concept: Optional[str],
        perspectives: Optional[Sequence[Perspective]] = None,
        assumptions: Optional[Sequence[str]] = None,
        validation_status: Optional[str] = None,
        scars: Optional[Sequence[Any]] = None,
        include_compass: bool = True,
    ) -> ConfidenceFieldReading:
        if concept is not None and not isinstance(concept, str):
            raise ValueError("concept must be a string or None")
        if perspectives is None:
            perspectives = ()
        if assumptions is None:
            assumptions = ()
        if scars is None:
            scars = ()

        integrity = self.bridge.witness_integrity()
        integrity_status = integrity.get("status", "UNKNOWN")

        if integrity_status not in ("VALID", "NO_CHRONICLE"):
            return ConfidenceFieldReading(
                concept=concept,
                confidence_score="BLOCKED",
                evidence_strength="BLOCKED",
                contradiction_pressure="BLOCKED",
                uncertainty_pressure="BLOCKED",
                assumption_pressure="BLOCKED",
                perspective_divergence="BLOCKED",
                integrity_status=integrity_status,
                validation_status="BLOCKED",
                confidence_band="BLOCKED",
                reasons=(
                    "Chronicle integrity is not established; current evidence state cannot be trusted for decision support.",
                ),
                blockers=(
                    f"witness_integrity() returned {integrity_status}",
                ),
                missing_information=(
                    "restore Chronicle integrity before relying on evidence-derived confidence",
                ),
                what_would_change_state=(
                    "repair or restore the Chronicle and re-run integrity verification",
                ),
                inputs={"integrity": integrity},
                calculation="hard boundary: integrity failure => confidence_band BLOCKED",
                interpretation="BLOCKED is more severe than LOW: the system is refusing to trust the underlying state, not merely expressing weak support.",
                limitations=(
                    "No confidence score is produced while integrity is failed or errored.",
                ),
                compass_reading=None,
            )

        kernel = self.bridge.lantern.kernel
        current_step = kernel.step
        concept_evidence = [e for e in kernel.evidence if concept is None or e.concept == concept]
        related_observation_ids = {e.observation_id for e in concept_evidence}
        related_observations = [kernel.observations[oid] for oid in related_observation_ids if oid in kernel.observations]
        open_contradictions = [
            c for c in kernel.contradictions
            if c.status == "OPEN" and (concept is None or c.concept == concept)
        ]
        resolved_contradictions = [
            c for c in kernel.contradictions
            if c.status == "RESOLVED" and (concept is None or c.concept == concept)
        ]

        positive_support = sum(
            e.decayed_weight(current_step)
            for e in concept_evidence
            if e.sign == 1
        )
        negative_support = sum(
            e.decayed_weight(current_step)
            for e in concept_evidence
            if e.sign == -1
        )
        total_support = positive_support + negative_support
        evidence_strength = min(1.0, positive_support / max(1.0, total_support)) if total_support > 0 else 0.0

        contradiction_pressure = min(
            1.0,
            sum(c.current_severity for c in open_contradictions) / max(1.0, total_support),
        ) if total_support > 0 else (1.0 if open_contradictions else 0.0)

        reliability_values = [obs.reliability for obs in related_observations]
        avg_reliability = sum(reliability_values) / len(reliability_values) if reliability_values else 0.0
        independent_sources = {obs.source for obs in related_observations}
        independence_bonus = min(1.0, len(independent_sources) / 3.0)

        # uncertainty increases when there is little evidence, weak reliability,
        # few independent observations, or explicit contradiction pressure.
        uncertainty_pressure = min(
            1.0,
            max(
                0.0,
                0.45 * (1.0 - min(1.0, total_support))
                + 0.30 * (1.0 - avg_reliability)
                + 0.15 * (1.0 - independence_bonus)
                + 0.10 * contradiction_pressure,
            ),
        )

        assumption_pressure = min(1.0, len(assumptions) / 5.0)

        differential = None
        if len(perspectives) >= 2:
            differential = self.perspective_engine.compare(list(perspectives))
            perspective_divergence = min(
                1.0,
                max(
                    differential.confidence_variance or 0.0,
                    differential.evidence_variance or 0.0,
                    differential.assumption_variance or 0.0,
                    differential.novelty_variance or 0.0,
                ) * 4.0,
            )
        else:
            perspective_divergence = 0.0 if len(perspectives) == 0 else "UNKNOWN"

        if validation_status is None:
            if total_support == 0:
                validation_status = "UNVERIFIED"
            elif open_contradictions:
                validation_status = "CONTESTED"
            elif avg_reliability >= 0.8 and len(independent_sources) >= 2:
                validation_status = "SUPPORTED"
            else:
                validation_status = "PARTIAL"

        scar_caution = 0.0
        scar_reasons: list[str] = []
        for scar in scars:
            outcome = getattr(getattr(scar, "scar", scar), "outcome", None)
            lesson = getattr(getattr(scar, "scar", scar), "lesson", None)
            if outcome in {"FAILED_HANDSHAKE", "CONTRADICTORY_OBSERVATION", "INTEGRATION_ROLLBACK", "INVALID_PROVENANCE"}:
                scar_caution = min(0.2, scar_caution + 0.1)
                if lesson:
                    scar_reasons.append(f"scar lesson: {lesson}")
                else:
                    scar_reasons.append(f"scar outcome noted: {outcome}")
        uncertainty_pressure = min(1.0, uncertainty_pressure + scar_caution)

        if perspective_divergence == "UNKNOWN":
            divergence_penalty = 0.05
        else:
            divergence_penalty = 0.10 * perspective_divergence

        confidence_score = max(
            0.0,
            min(
                1.0,
                0.55 * evidence_strength
                + 0.20 * avg_reliability
                + 0.10 * independence_bonus
                - 0.20 * contradiction_pressure
                - 0.10 * uncertainty_pressure
                - 0.05 * assumption_pressure
                - divergence_penalty,
            ),
        )

        if validation_status in {"UNVERIFIED", "CONTESTED"}:
            confidence_score = max(0.0, confidence_score - 0.10)

        if (
            confidence_score >= HIGH_THRESHOLD
            and validation_status in {"SUPPORTED", "PARTIAL"}
            and contradiction_pressure < 0.25
            and len(independent_sources) >= 2
            and uncertainty_pressure <= 0.35
            and assumption_pressure <= 0.20
        ):
            band = "HIGH"
        elif confidence_score >= MEDIUM_THRESHOLD:
            band = "MEDIUM"
        else:
            band = "LOW"

        reasons: list[str] = []
        blockers: list[str] = []
        missing_information: list[str] = []
        what_would_change_state: list[str] = []

        if positive_support > 0:
            reasons.append(
                f"positive evidence support={positive_support:.3f} across {len(concept_evidence)} evidence record(s)"
            )
        else:
            reasons.append("no supporting evidence is currently recorded")
            missing_information.append("supporting evidence for the concept")
            what_would_change_state.append("record one or more relevant supporting observations/evidence links")

        if related_observations:
            reasons.append(
                f"{len(related_observations)} linked observation(s) from {len(independent_sources)} independent source(s); average reliability={avg_reliability:.2f}"
            )
            if len(independent_sources) < 2:
                missing_information.append("more independent observation sources")
                what_would_change_state.append("obtain independent corroboration from a distinct source")
        else:
            missing_information.append("observations linked to evidence")
            blockers.append("evidence exists without retrievable linked observations")
            what_would_change_state.append("repair or restore linked observations for the evidence")

        if open_contradictions:
            reasons.append(f"{len(open_contradictions)} unresolved contradiction(s) remain open")
            blockers.append("unresolved contradiction pressure is present")
            what_would_change_state.append("resolve or supersede open contradictions with better evidence")
        elif resolved_contradictions:
            reasons.append(f"{len(resolved_contradictions)} contradiction(s) were resolved historically")

        if assumptions:
            reasons.append(f"assumption load={len(assumptions)} explicit assumption(s)")
            what_would_change_state.append("replace assumptions with directly observed or externally validated evidence")

        if perspective_divergence == "UNKNOWN":
            missing_information.append("at least one more independent perspective to compute divergence")
        elif perspective_divergence > 0.35:
            reasons.append(f"perspective divergence is elevated ({perspective_divergence:.2f})")
            what_would_change_state.append("explain why perspectives diverge or gather adjudicating evidence")
        elif len(perspectives) >= 2:
            reasons.append(f"perspective divergence is limited ({perspective_divergence:.2f})")

        if validation_status == "UNVERIFIED":
            blockers.append("validation is UNVERIFIED")
            what_would_change_state.append("add externally checkable validation or stronger independent evidence")
        elif validation_status == "CONTESTED":
            blockers.append("validation is CONTESTED by unresolved contradiction")
        else:
            reasons.append(f"validation status={validation_status}")

        reasons.extend(scar_reasons)

        compass_reading = None
        if include_compass:
            compass_reading = compass.orient(
                kernel=kernel,
                concepts_of_interest=(concept,) if concept else (),
            ).to_dict()

        return ConfidenceFieldReading(
            concept=concept,
            confidence_score=round(confidence_score, 3),
            evidence_strength=round(evidence_strength, 3),
            contradiction_pressure=round(contradiction_pressure, 3),
            uncertainty_pressure=round(uncertainty_pressure, 3),
            assumption_pressure=round(assumption_pressure, 3),
            perspective_divergence=perspective_divergence if perspective_divergence == "UNKNOWN" else round(perspective_divergence, 3),
            integrity_status=integrity_status,
            validation_status=validation_status,
            confidence_band=band,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            missing_information=tuple(dict.fromkeys(missing_information)),
            what_would_change_state=tuple(dict.fromkeys(what_would_change_state)),
            inputs={
                "current_step": current_step,
                "positive_support": round(positive_support, 6),
                "negative_support": round(negative_support, 6),
                "total_support": round(total_support, 6),
                "observations": len(related_observations),
                "independent_sources": sorted(independent_sources),
                "avg_reliability": round(avg_reliability, 6),
                "assumptions": list(assumptions),
                "open_contradictions": len(open_contradictions),
                "perspectives": len(perspectives),
                "differential": differential.to_dict() if differential is not None else None,
            },
            calculation=(
                "confidence_score = clamp(0.55*evidence_strength + 0.20*avg_reliability "
                "+ 0.10*independence_bonus - 0.20*contradiction_pressure "
                "- 0.10*uncertainty_pressure - 0.05*assumption_pressure "
                "- perspective_penalty); perspective_penalty = 0.10*perspective_divergence "
                "when known, else 0.05; validation_status UNVERIFIED/CONTESTED subtracts 0.05."
            ),
            interpretation=(
                f"{band} means the currently available validated information supports proceeding at a {band.lower()} confidence level under present conditions; it does not assert truth."
            ),
            limitations=(
                "Confidence is an interpretable summary over current signals, not proof.",
                "Perspective divergence raises investigation pressure but is not treated as falsehood.",
                "Assumption pressure is caller-supplied and therefore only as good as the caller's explicit assumption list.",
            ),
            compass_reading=compass_reading,
        )

```

### `lantern_harness/decision_state_machine.py`

```python
"""Decision State Machine: explicit transitions over Confidence Field
bands. Recommends next action; never authorizes or executes anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .confidence_field import ConfidenceFieldReading


ACTION_BY_STATE = {
    "HIGH": "INTEGRATE / PROCEED",
    "MEDIUM": "PRESERVE / GATHER",
    "LOW": "BRANCH / INVESTIGATE",
    "BLOCKED": "STOP / REPAIR",
}

ALLOWED_TRANSITIONS = {
    None: {"HIGH", "MEDIUM", "LOW", "BLOCKED"},
    "HIGH": {"HIGH", "MEDIUM", "BLOCKED"},
    "MEDIUM": {"HIGH", "MEDIUM", "LOW", "BLOCKED"},
    "LOW": {"MEDIUM", "LOW", "BLOCKED"},
    "BLOCKED": {"BLOCKED", "LOW", "MEDIUM", "HIGH"},
}


@dataclass(frozen=True)
class DecisionReading:
    state: str
    recommended_action: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    what_would_change_state: tuple[str, ...]
    confidence_band: str
    confidence_score: float | str
    authorization_required: bool = True
    authorization_status: str = "NOT_EVALUATED"
    transition_from: Optional[str] = None
    transition_event: Optional[str] = None
    transition_allowed: bool = True
    explanation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "recommended_action": self.recommended_action,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "what_would_change_state": list(self.what_would_change_state),
            "confidence_band": self.confidence_band,
            "confidence_score": self.confidence_score,
            "authorization_required": self.authorization_required,
            "authorization_status": self.authorization_status,
            "transition_from": self.transition_from,
            "transition_event": self.transition_event,
            "transition_allowed": self.transition_allowed,
            "explanation": dict(self.explanation),
        }


class DecisionStateMachine:
    """Maps current confidence into an explicit state + recommended
    action. This never calls tools, never mutates memory, never executes
    actions, and never substitutes for authorization."""

    def recommend(
        self,
        reading: ConfidenceFieldReading,
        *,
        previous_state: Optional[str] = None,
        transition_event: Optional[str] = None,
    ) -> DecisionReading:
        state = reading.confidence_band
        if state not in ACTION_BY_STATE:
            raise ValueError(f"unsupported confidence band: {state!r}")

        allowed = state in ALLOWED_TRANSITIONS.get(previous_state, set())
        if not allowed:
            raise ValueError(
                f"illegal state transition: {previous_state!r} -> {state!r}; allowed={sorted(ALLOWED_TRANSITIONS.get(previous_state, set()))}"
            )

        explanation = {
            "pipeline": "Evidence -> Confidence Field -> Decision State -> Capability Authorization -> Action Boundary",
            "decision_is_not_authorization": True,
            "integrity_status": reading.integrity_status,
            "validation_status": reading.validation_status,
        }
        if reading.compass_reading is not None:
            explanation["compass"] = reading.compass_reading

        return DecisionReading(
            state=state,
            recommended_action=ACTION_BY_STATE[state],
            reasons=reading.reasons,
            blockers=reading.blockers,
            what_would_change_state=reading.what_would_change_state,
            confidence_band=reading.confidence_band,
            confidence_score=reading.confidence_score,
            authorization_required=True,
            authorization_status="NOT_EVALUATED",
            transition_from=previous_state,
            transition_event=transition_event,
            transition_allowed=True,
            explanation=explanation,
        )

```

### `lantern_harness/self_model.py`

```python
"""Self-Model: a bounded, read-only description of the harness's current
state and capabilities. NEW component; not present in Lantern v0.84 or
in prior harness turns.

This module answers exactly one question, honestly: "what does this
system currently know about itself?" It distinguishes:

    WHAT I KNOW               -- verified from real Lantern/harness state
    WHAT I INFER               -- derived, not directly observed
    WHAT I DO NOT KNOW         -- explicitly unknown, not guessed
    WHAT I CAN DO               -- capabilities that actually exist and work
    WHAT I CANNOT DO            -- capabilities that do not exist (honest gaps)
    WHAT I AM AUTHORIZED TO DO  -- always sourced from ToolBoundary.is_authorized(),
                                    never inferred or assumed
    WHAT REQUIRES OPERATOR ACTION -- explicit list of standing external
                                      boundaries (push, publish, payment, etc.)

Hard rule: SelfModel.describe() never grants authority. It can only
*report* what ToolBoundary/DecisionStateMachine/RealityBoundary already
say is true. There is no code path in this module that sets
is_authorized=True or otherwise changes any other component's state --
verified by test_self_model.py's test_self_model_is_read_only and
test_self_model_cannot_self_authorize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .bridge import LanternBridge


KNOWN_CAPABILITIES = (
    "observe (record an Observation into the real EvidenceKernel)",
    "add_evidence (link Evidence to a concept, real EvidenceKernel)",
    "detect and read contradictions (real EvidenceKernel.detect_contradiction)",
    "resolve contradictions (real EvidenceKernel resolution path)",
    "compute belief (real EvidenceKernel.belief sigmoid scoring)",
    "compile a structured prompt (PromptCompiler)",
    "compare independent perspectives (PerspectiveDifferentialEngine, variance only, no voting)",
    "compute a read-only confidence reading (ConfidenceField)",
    "recommend (not authorize) a decision state (DecisionStateMachine)",
    "open/link/abandon exploratory branches (spine.BranchStore)",
    "commit a branch into the Spine, only with explicit external authorization (spine.SpineCommitter)",
    "record real vs. simulated external actions (RealityBoundary)",
    "verify Chronicle integrity (real Chronicle.verify() hash-chain check)",
    "create and persist Scars (real Lantern.create_scar/persist_scar)",
    "remember capability-scope permission grants and combine them with an alignment result "
    "(PermissionAuthority) -- in-process memory only, never persisted, never self-granted",
)

KNOWN_GAPS = (
    "full Perspective Mesh (merge/vote/consensus across perspectives) -- only variance computation exists",
    "autonomous self-modification of Lantern core or the harness's own source",
    "unrestricted autonomous promotion (posting/contacting/publishing without a boundary check)",
    "a live, credentialed payment settlement path (x402 facilitator + wallet are not configured)",
    "PyPI package publication (no publishing credentials present, and a "
    "verified-empty local build/install test found a deeper blocker: no "
    "declared dependency on Lantern core, which is itself unpublished, "
    "plus prompts/ and config/ are not reachable by an installed wheel's "
    "Path(__file__)-relative lookups -- see RELEASE.md)",
    "pushing commits to a public git remote without a separate explicit authorization step",
)

STANDING_OPERATOR_BOUNDARIES = (
    "push commits to origin/any public remote",
    "publish a package to PyPI or any package index",
    "configure or use real payment/wallet credentials",
    "sign any contract, license grant, or legal commitment",
    "contact external parties/platforms on the operator's behalf",
    "install or run services that expose network ports beyond localhost",
)


@dataclass(frozen=True)
class SelfModelReading:
    what_i_know: tuple
    what_i_infer: tuple
    what_i_do_not_know: tuple
    what_i_can_do: tuple
    what_i_cannot_do: tuple
    what_i_am_authorized_to_do: tuple
    what_requires_operator_action: tuple
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "what_i_know": list(self.what_i_know),
            "what_i_infer": list(self.what_i_infer),
            "what_i_do_not_know": list(self.what_i_do_not_know),
            "what_i_can_do": list(self.what_i_can_do),
            "what_i_cannot_do": list(self.what_i_cannot_do),
            "what_i_am_authorized_to_do": list(self.what_i_am_authorized_to_do),
            "what_requires_operator_action": list(self.what_requires_operator_action),
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = ["SELF-MODEL"]
        sections = [
            ("WHAT I KNOW", self.what_i_know),
            ("WHAT I INFER", self.what_i_infer),
            ("WHAT I DO NOT KNOW", self.what_i_do_not_know),
            ("WHAT I CAN DO", self.what_i_can_do),
            ("WHAT I CANNOT DO", self.what_i_cannot_do),
            ("WHAT I AM AUTHORIZED TO DO", self.what_i_am_authorized_to_do),
            ("WHAT REQUIRES OPERATOR ACTION", self.what_requires_operator_action),
        ]
        for title, items in sections:
            lines.append("")
            lines.append(f"{title}:")
            if not items:
                lines.append("  (none)")
            for item in items:
                lines.append(f"  - {item}")
        return "\n".join(lines)


class SelfModel:
    """Reads existing harness/Lantern state and reports it. Produces no
    side effects on any other component -- see module docstring."""

    def __init__(self, bridge: LanternBridge, tool_boundary):
        self.bridge = bridge
        self.tool_boundary = tool_boundary

    def describe(self) -> SelfModelReading:
        identity = self.bridge.identity_status()
        integrity = self.bridge.witness_integrity()
        status = self.bridge.status()

        what_i_know = [
            f"node identity status={identity.get('status')}",
            f"Chronicle integrity={integrity.get('status')}",
            f"memory: step={status.get('step')}, observations={status.get('observations')}, "
            f"evidence={status.get('evidence')}, contradictions={status.get('contradictions')}",
        ]

        what_i_infer = []
        if integrity.get("status") == "NO_CHRONICLE":
            what_i_infer.append(
                "no Chronicle file exists yet for this data_dir -- inferred to mean this is a fresh, unused node, "
                "not verified against any external record"
            )
        if status.get("contradictions", 0) and status.get("contradictions", 0) > 0:
            what_i_infer.append(
                f"presence of {status.get('contradictions')} contradiction(s) suggests at least one concept "
                f"has conflicting evidence -- which concept(s) is not inferred here, read EvidenceKernel directly"
            )

        what_i_do_not_know = [
            "whether any reasoning engine response was independently verified as true (only that it was returned)",
            "whether any external user has adopted, paid for, or benefited from this system (no such record exists)",
            "anything about conditions outside the data this bridge has actually observed",
        ]

        what_i_can_do = list(KNOWN_CAPABILITIES)
        what_i_cannot_do = list(KNOWN_GAPS)

        authorized_tools = sorted(self.tool_boundary._authorized)  # noqa: SLF001 - read-only self-report
        what_i_am_authorized_to_do = (
            [f"tool: {name}" for name in authorized_tools]
            if authorized_tools
            else ["(no tools are currently authorized in ToolBoundary)"]
        )

        return SelfModelReading(
            what_i_know=tuple(what_i_know),
            what_i_infer=tuple(what_i_infer),
            what_i_do_not_know=tuple(what_i_do_not_know),
            what_i_can_do=tuple(what_i_can_do),
            what_i_cannot_do=tuple(what_i_cannot_do),
            what_i_am_authorized_to_do=tuple(what_i_am_authorized_to_do),
            what_requires_operator_action=STANDING_OPERATOR_BOUNDARIES,
            notes=(
                "This model reports what ToolBoundary/Chronicle/EvidenceKernel already say; "
                "it has no method that sets authorization state on any other component.",
            ),
        )

```

### `lantern_harness/spine.py`

```python
"""Spine + Branch: committed-knowledge and exploratory-knowledge model.

This is a NEW component. Lantern v0.84 has no branch/spine/commitment
concept (see bridge.py's LanternBridge.branches() -> NotImplementedError,
harness_status.py's branching_status). This module implements a real one,
on top of Lantern's existing, real primitives only:

  - Chronicle (append-only, hash-chained, tamper-evident) for durability
    of committed Spine entries -- the same mechanism Scars already use.
  - EvidenceKernel for evidence/contradiction linkage -- reads real
    Evidence/Contradiction records, does not invent a second ledger.
  - Chronicle.verify() for integrity, the same check ConfidenceField uses
    for its hard BLOCKED path.

Hard invariants (enforced in code, not just documented):

  1. A Branch cannot commit itself. Sealing a branch into the Spine
     requires an explicit, separately-supplied `authorized=True` from the
     caller -- confidence alone (however high) never triggers a commit.
     See SpineCommitter.commit()'s required `authorized` parameter.
  2. A commit is refused if Chronicle integrity is not VALID/NO_CHRONICLE
     (same hard-BLOCKED discipline as ConfidenceField). No score can
     override this.
  3. A commit is refused if there are unresolved (OPEN) contradictions
     for the branch's concept, unless the caller explicitly acknowledges
     them via `acknowledge_open_contradictions=True` -- contradictions
     are never silently hidden by commitment.
  4. Committed entries are appended to the real Chronicle -- once
     written, altering history requires breaking the hash chain, which
     Chronicle.verify() (and therefore ConfidenceField) will detect. This
     is Lantern's actual immutability model (integrity-protected,
     tamper-evident) -- this module does not claim stronger guarantees
     than that.
  5. A failed/abandoned Branch is preservable as a learning artifact via
     to_scar() -- it becomes a real Scar (Lantern's existing durable
     consequence record), not silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import uuid


SPINE_COMMIT_EVENT_TYPE = "SPINE_COMMIT_SEALED"


def _uid() -> str:
    return str(uuid.uuid4())


@dataclass
class Branch:
    """An exploratory line of investigation. Lives outside committed
    state (the Spine) until commit() succeeds. Never persisted to
    Chronicle on its own -- only a successful commit or an explicit
    to_scar() call produces a durable record."""

    id: str
    concept: str
    hypothesis: str
    parent_branch_id: Optional[str] = None
    observation_ids: list = field(default_factory=list)
    evidence_ids: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    status: str = "OPEN"  # OPEN | COMMITTED | ABANDONED

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "concept": self.concept,
            "hypothesis": self.hypothesis,
            "parent_branch_id": self.parent_branch_id,
            "observation_ids": list(self.observation_ids),
            "evidence_ids": list(self.evidence_ids),
            "notes": list(self.notes),
            "status": self.status,
        }


@dataclass(frozen=True)
class SpineEntry:
    """One committed, integrity-protected entry in the Spine."""

    id: str
    branch_id: str
    concept: str
    statement: str
    provenance: dict
    evidence_ids: tuple
    contradiction_acknowledgement: Optional[str]
    authorized_by: str
    timestamp: str
    chronicle_hash: Optional[str]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "branch_id": self.branch_id,
            "concept": self.concept,
            "statement": self.statement,
            "provenance": dict(self.provenance),
            "evidence_ids": list(self.evidence_ids),
            "contradiction_acknowledgement": self.contradiction_acknowledgement,
            "authorized_by": self.authorized_by,
            "timestamp": self.timestamp,
            "chronicle_hash": self.chronicle_hash,
        }


@dataclass(frozen=True)
class CommitResult:
    status: str  # "COMMITTED" | "REFUSED"
    reason: str
    entry: Optional[SpineEntry] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "entry": self.entry.to_dict() if self.entry is not None else None,
        }


class BranchStore:
    """In-memory registry of open/committed/abandoned branches for one
    process lifetime. Not a second persistence layer -- committed
    branches' durable record lives in Chronicle via SpineCommitter;
    abandoned branches' durable record (if any) lives in a real Scar."""

    def __init__(self):
        self._branches: dict = {}

    def open_branch(self, *, concept: str, hypothesis: str, parent_branch_id: Optional[str] = None) -> Branch:
        if not concept or not concept.strip():
            raise ValueError("concept must be a non-empty string")
        if not hypothesis or not hypothesis.strip():
            raise ValueError("hypothesis must be a non-empty string")
        if parent_branch_id is not None and parent_branch_id not in self._branches:
            raise ValueError(f"unknown parent_branch_id: {parent_branch_id!r}")
        branch = Branch(id=_uid(), concept=concept.strip(), hypothesis=hypothesis.strip(), parent_branch_id=parent_branch_id)
        self._branches[branch.id] = branch
        return branch

    def get(self, branch_id: str) -> Optional[Branch]:
        return self._branches.get(branch_id)

    def add_note(self, branch_id: str, note: str) -> Branch:
        branch = self._require(branch_id)
        branch.notes.append(note)
        return branch

    def link_observation(self, branch_id: str, observation_id: str) -> Branch:
        branch = self._require(branch_id)
        if observation_id not in branch.observation_ids:
            branch.observation_ids.append(observation_id)
        return branch

    def link_evidence(self, branch_id: str, evidence_id: str) -> Branch:
        branch = self._require(branch_id)
        if evidence_id not in branch.evidence_ids:
            branch.evidence_ids.append(evidence_id)
        return branch

    def abandon(self, branch_id: str) -> Branch:
        branch = self._require(branch_id)
        if branch.status == "COMMITTED":
            raise ValueError("cannot abandon a branch that is already COMMITTED")
        branch.status = "ABANDONED"
        return branch

    def _require(self, branch_id: str) -> Branch:
        branch = self._branches.get(branch_id)
        if branch is None:
            raise ValueError(f"unknown branch_id: {branch_id!r}")
        if branch.status != "OPEN":
            raise ValueError(f"branch {branch_id!r} is {branch.status}, not OPEN")
        return branch

    def all(self) -> list:
        return list(self._branches.values())


class SpineCommitter:
    """Seals a Branch into the Spine. This is the ONLY code path that may
    produce a SpineEntry, and it enforces every hard invariant listed in
    this module's docstring."""

    def __init__(self, bridge):
        self.bridge = bridge

    def commit(
        self,
        branch: Branch,
        *,
        statement: str,
        authorized: bool,
        authorized_by: str,
        acknowledge_open_contradictions: bool = False,
    ) -> CommitResult:
        if branch.status != "OPEN":
            return CommitResult(status="REFUSED", reason=f"branch is {branch.status}, not OPEN")

        if not authorized:
            return CommitResult(
                status="REFUSED",
                reason=(
                    "authorized=False: a branch cannot commit itself and no confidence "
                    "score alone may create commitment. An explicit authorized=True from "
                    "a caller outside this module is required."
                ),
            )
        if not authorized_by or not authorized_by.strip():
            return CommitResult(status="REFUSED", reason="authorized_by must identify who/what authorized this commit")

        integrity = self.bridge.witness_integrity()
        if integrity.get("status") not in ("VALID", "NO_CHRONICLE"):
            return CommitResult(
                status="REFUSED",
                reason=f"Chronicle integrity is {integrity.get('status')!r}; refusing to commit against an untrusted chain.",
            )

        kernel = self.bridge.lantern.kernel
        open_contradictions = [
            c for c in kernel.contradictions
            if c.status == "OPEN" and c.concept == branch.concept
        ]
        contradiction_ack = None
        if open_contradictions:
            if not acknowledge_open_contradictions:
                return CommitResult(
                    status="REFUSED",
                    reason=(
                        f"{len(open_contradictions)} unresolved contradiction(s) exist for "
                        f"concept={branch.concept!r}; commit refused unless "
                        f"acknowledge_open_contradictions=True is explicitly passed."
                    ),
                )
            contradiction_ack = (
                f"{len(open_contradictions)} open contradiction(s) explicitly acknowledged "
                f"at commit time: {[c.id for c in open_contradictions]}"
            )

        entry_id = _uid()
        provenance = {
            "branch_id": branch.id,
            "parent_branch_id": branch.parent_branch_id,
            "observation_ids": list(branch.observation_ids),
            "hypothesis": branch.hypothesis,
        }

        from lantern.core import KernelEvent

        payload = {
            "entry_id": entry_id,
            "branch_id": branch.id,
            "concept": branch.concept,
            "statement": statement,
            "provenance": provenance,
            "evidence_ids": list(branch.evidence_ids),
            "contradiction_acknowledgement": contradiction_ack,
            "authorized_by": authorized_by,
        }
        event = KernelEvent(SPINE_COMMIT_EVENT_TYPE, "lantern_harness.spine", payload, id=entry_id)
        self.bridge.lantern.bus.publish(event)

        chronicle_hash = self.bridge.lantern.bus.chronicle.chain if self.bridge.lantern.bus.chronicle is not None else None

        branch.status = "COMMITTED"

        entry = SpineEntry(
            id=entry_id,
            branch_id=branch.id,
            concept=branch.concept,
            statement=statement,
            provenance=provenance,
            evidence_ids=tuple(branch.evidence_ids),
            contradiction_acknowledgement=contradiction_ack,
            authorized_by=authorized_by,
            timestamp=event.timestamp,
            chronicle_hash=chronicle_hash,
        )
        return CommitResult(status="COMMITTED", reason="all commit invariants satisfied", entry=entry)

    def read_spine(self) -> list:
        """Reconstructs committed Spine entries by replaying the real
        Chronicle and filtering for this module's own event type. This is
        the same replay-based reconstruction pattern Lantern's own
        EvidenceKernel.replay() uses for OBSERVATION_CREATED/
        EVIDENCE_CREATED/SCAR_RECORDED -- Spine entries are just another
        event type in the same durable, hash-chained log."""
        chronicle = self.bridge.lantern.bus.chronicle
        if chronicle is None:
            return []
        entries = []
        for record in chronicle.replay():
            if record.get("type") != SPINE_COMMIT_EVENT_TYPE:
                continue
            payload = record["payload"]
            entries.append(
                SpineEntry(
                    id=payload["entry_id"],
                    branch_id=payload["branch_id"],
                    concept=payload["concept"],
                    statement=payload["statement"],
                    provenance=payload["provenance"],
                    evidence_ids=tuple(payload["evidence_ids"]),
                    contradiction_acknowledgement=payload["contradiction_acknowledgement"],
                    authorized_by=payload["authorized_by"],
                    timestamp=record["timestamp"],
                    chronicle_hash=record["current_hash"],
                )
            )
        return entries


def branch_to_scar(bridge, branch: Branch, *, outcome: str, lesson: str):
    """Preserve an abandoned/failed branch as a real Scar (Lantern's
    existing durable consequence record) rather than silently discarding
    it. `outcome` must be one of scars.NETWORK_SCAR_OUTCOMES-compatible
    strings is NOT enforced here (Scar.outcome is a free-text field in
    core Lantern for non-network outcomes); this function passes through
    to the real bridge.create_scar/persist_scar path unchanged."""
    if branch.status not in ("ABANDONED", "OPEN"):
        raise ValueError("only an ABANDONED or still-OPEN (never-committed) branch can become a learning-artifact Scar")
    record = bridge.create_scar(
        source="lantern_harness.spine",
        trigger=f"branch:{branch.id}",
        observation=branch.hypothesis,
        outcome=outcome,
        severity="LOW",
        lesson=lesson,
        related_evidence_ids=list(branch.evidence_ids),
    )
    return bridge.persist_scar(record)

```

### `lantern_harness/transfer_manifest.py`

```python
"""TransferManifest: describes a Lantern Harness instance so a receiving
operator or agent can decide whether to adopt it, without silently
inheriting any authority the sending operator held.

This module answers, honestly and only from real observed state:

    IDENTITY            -- which node this is (public key only, never
                            the private key -- see lantern.identity)
    PROTOCOL            -- Lantern core protocol version + harness
                            version, so compatibility can be checked
                            before state is trusted
                            (lantern.protocol.PROTOCOL_VERSION,
                            lantern.compatibility.negotiate -- reused,
                            not reinvented)
    CONFIGURATION       -- non-secret config only (reasoning engine
                            provider name and API-key *env var name*,
                            never the key value itself -- see
                            lantern_harness.config's existing rule)
    STATE_SUMMARY       -- counts, not raw content: observations,
                            evidence, contradictions, branches, spine
                            entries, scars. (Full state is transferred
                            by copying the data_dir itself, which this
                            manifest documents but does not perform --
                            see NOTES.)
    CAPABILITIES        -- reuses SelfModel.KNOWN_CAPABILITIES verbatim,
                            not a second capability list
    BOUNDARIES          -- reuses SelfModel.STANDING_OPERATOR_BOUNDARIES
                            verbatim, explicitly listed as
                            "does NOT transfer" items
    PROVENANCE          -- what commit of lantern-harness and lantern
                            core produced this manifest, when, and by
                            what Python version (best-effort; falls
                            back to UNKNOWN rather than guessing)
    INTEGRITY           -- real Chronicle.verify() result via
                            bridge.witness_integrity(), not assumed VALID
    REAUTHORIZATION_REQUIRED -- explicit list of things the receiving
                            operator must decide fresh; never inferred
                            from the sending operator's prior decisions

Hard rule, mirroring self_model.py: this module is read-only. It
authorizes nothing, grants nothing, and never embeds a credential,
key, or secret value. Verified by
test_transfer_manifest_never_contains_a_private_key_byte and
test_transfer_manifest_is_read_only.
"""

from __future__ import annotations

import importlib.metadata
import platform
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .bridge import LanternBridge
from .harness_status import HARNESS_VERSION, lantern_version
from .self_model import KNOWN_CAPABILITIES, KNOWN_GAPS, STANDING_OPERATOR_BOUNDARIES


LINEAGE = {
    "architecture": "Lantern",
    "instance_model": "Peacemaker",
    "note": (
        "Lantern is the architecture/protocol/lineage (lantern-babel-codex-bridge). "
        "Peacemaker is the naming for a personal, transferable running instance built "
        "on that architecture. This field does not rename any package, module, class, "
        "commit, or prior release -- those remain named Lantern in their own history. "
        "See PEACEMAKER.md."
    ),
}

REAUTHORIZATION_REQUIRED = (
    "where this instance runs (host/network placement)",
    "what reasoning engine credentials it is given, if any",
    "what MCP hosts it may serve (e.g. registering it in Odysseus or any other agent environment)",
    "what external actions, if any, are authorized through a ToolBoundary",
    "whether any paid capability (e.g. the x402 reconciliation service) is activated",
    "whether network exposure beyond localhost stdio is permitted",
    "whether the transferred data_dir is trusted as-is or re-verified before use",
)


def _git_commit(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "UNKNOWN (not a git checkout, or git unavailable)"


def _lantern_core_commit() -> str:
    try:
        import lantern

        core_file = Path(lantern.__file__).resolve()
        repo_root = core_file.parent.parent.parent
        return _git_commit(repo_root)
    except ImportError:
        return "UNKNOWN (lantern core not importable)"


def _protocol_info() -> dict:
    try:
        from lantern.protocol import PROTOCOL_VERSION

        return {"lantern_protocol_version": PROTOCOL_VERSION, "status": "READ_FROM_lantern.protocol"}
    except ImportError:
        return {"lantern_protocol_version": "UNKNOWN", "status": "lantern.protocol not importable"}


@dataclass(frozen=True)
class TransferManifest:
    node_id: str
    public_key_hex: Optional[str]
    identity_status: str
    lantern_version: str
    harness_version: str
    protocol_version: str
    reasoning_engine_provider: Optional[str]
    reasoning_engine_api_key_env: Optional[str]
    state_summary: dict
    witness_integrity: dict
    capabilities: tuple
    known_gaps: tuple
    standing_operator_boundaries: tuple
    reauthorization_required: tuple
    harness_commit: str
    lantern_core_commit: str
    python_version: str
    platform_summary: str
    lineage: dict = field(default_factory=lambda: dict(LINEAGE))
    notes: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "identity": {
                "node_id": self.node_id,
                "public_key": self.public_key_hex,
                "status": self.identity_status,
            },
            "protocol": {
                "lantern_version": self.lantern_version,
                "harness_version": self.harness_version,
                "lantern_protocol_version": self.protocol_version,
            },
            "configuration": {
                "reasoning_engine_provider": self.reasoning_engine_provider,
                "reasoning_engine_api_key_env": self.reasoning_engine_api_key_env,
                "note": "env var NAME only, never the key value -- see lantern_harness.config",
            },
            "lineage": self.lineage,
            "state_summary": self.state_summary,
            "witness_integrity": self.witness_integrity,
            "capabilities": list(self.capabilities),
            "known_gaps": list(self.known_gaps),
            "standing_operator_boundaries_not_transferred": list(self.standing_operator_boundaries),
            "reauthorization_required": list(self.reauthorization_required),
            "provenance": {
                "harness_commit": self.harness_commit,
                "lantern_core_commit": self.lantern_core_commit,
                "python_version": self.python_version,
                "platform": self.platform_summary,
            },
            "notes": list(self.notes),
        }

    def format(self) -> str:
        lines = ["TRANSFER MANIFEST", "=================="]
        lines.append(f"node_id: {self.node_id}")
        lines.append(f"public_key: {self.public_key_hex}")
        lines.append(f"identity_status: {self.identity_status}")
        lines.append("")
        lines.append(f"lantern_version: {self.lantern_version}")
        lines.append(f"harness_version: {self.harness_version}")
        lines.append(f"lantern_protocol_version: {self.protocol_version}")
        lines.append("")
        lines.append(f"lineage: architecture={self.lineage.get('architecture')}, instance_model={self.lineage.get('instance_model')}")
        lines.append("")
        lines.append(f"reasoning_engine: provider={self.reasoning_engine_provider}, api_key_env={self.reasoning_engine_api_key_env}")
        lines.append("")
        lines.append("STATE SUMMARY:")
        for key, value in self.state_summary.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        lines.append(f"witness_integrity: {self.witness_integrity.get('status')}")
        lines.append("")
        lines.append("CAPABILITIES (what this instance can actually do):")
        for item in self.capabilities:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("KNOWN GAPS (what it cannot do):")
        for item in self.known_gaps:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("DOES NOT TRANSFER -- receiving operator must decide fresh:")
        for item in self.reauthorization_required:
            lines.append(f"  - {item}")
        lines.append("")
        lines.append("PROVENANCE:")
        lines.append(f"  harness_commit: {self.harness_commit}")
        lines.append(f"  lantern_core_commit: {self.lantern_core_commit}")
        lines.append(f"  python_version: {self.python_version}")
        lines.append(f"  platform: {self.platform_summary}")
        if self.notes:
            lines.append("")
            lines.append("NOTES:")
            for note in self.notes:
                lines.append(f"  - {note}")
        return "\n".join(lines)


def build_manifest(bridge: LanternBridge, engine=None, harness_root: Optional[Path] = None) -> TransferManifest:
    """Reads real, current state only. Never infers state it has not
    actually observed this call. Never includes a private key, API key
    value, or any other credential."""
    identity = bridge.identity_status()
    status = bridge.status()
    integrity = bridge.witness_integrity()
    protocol = _protocol_info()

    notes = []
    try:
        branches = bridge.branches()
        branch_count = len(branches) if branches is not None else 0
    except NotImplementedError:
        branches = None
        branch_count = "N/A (Lantern core has no branch concept; harness spine.BranchStore is in-process only, not part of persisted state)"
        notes.append("branch_count is N/A because lantern_harness.spine.BranchStore does not persist across process restarts in this version")

    state_summary = {
        "step": status.get("step"),
        "observations": status.get("observations"),
        "evidence": status.get("evidence"),
        "contradictions": status.get("contradictions"),
        "chronicle_attached": status.get("chronicle"),
        "branches_in_process": branch_count,
    }

    engine_provider = None
    engine_key_env = None
    if engine is not None:
        described = engine.describe()
        engine_provider = described.get("provider")
        engine_key_env = getattr(engine, "api_key_env", None)

    root = harness_root or Path(__file__).resolve().parent.parent

    return TransferManifest(
        node_id=bridge.node_id,
        public_key_hex=identity.get("public_key"),
        identity_status=identity.get("status", "UNKNOWN"),
        lantern_version=lantern_version(),
        harness_version=HARNESS_VERSION,
        protocol_version=protocol["lantern_protocol_version"],
        reasoning_engine_provider=engine_provider,
        reasoning_engine_api_key_env=engine_key_env,
        state_summary=state_summary,
        witness_integrity=integrity,
        capabilities=KNOWN_CAPABILITIES,
        known_gaps=KNOWN_GAPS,
        standing_operator_boundaries=STANDING_OPERATOR_BOUNDARIES,
        reauthorization_required=REAUTHORIZATION_REQUIRED,
        harness_commit=_git_commit(root),
        lantern_core_commit=_lantern_core_commit(),
        python_version=platform.python_version(),
        platform_summary=platform.platform(),
        lineage=dict(LINEAGE),
        notes=tuple(notes),
    )

```

### `lantern_harness/mcp_server.py`

```python
"""MCP server: exposes Lantern Harness capabilities as MCP tools so any
MCP-compatible agent client (Claude Desktop, Claude Code, or any other
MCP host) can use Lantern directly, without a human copy-pasting through
the REPL.

This is a NEW module. Existing lantern.mcp_client / lantern.mcp_integration
are MCP *client* code (Lantern connecting OUT to other MCP servers). This
module is the reverse direction: Lantern acting AS an MCP server.

Design constraints carried over from the rest of this harness:
- Every tool function here is a thin wrapper around an already-existing,
  already-tested component (LanternBridge, PromptCompiler, ConfidenceField,
  DecisionStateMachine, SelfModel, BranchStore, SpineCommitter,
  OperatingLoop). No new decision/confidence/authorization logic is
  introduced here.
- Tools that could touch the outside world (there are none exposed here
  -- no tool in this module calls RealityBoundary.act or executes an
  arbitrary ToolBoundary-registered tool) are deliberately omitted. This
  server surfaces Lantern's epistemic primitives (observe, evidence,
  confidence, decision, self-model, spine) for other agents to use, not
  a generic remote-code-execution surface.
- Nothing here starts listening on a network port. run_stdio_async() is
  stdio-only, matching how Claude Desktop/Claude Code launch local MCP
  servers as a subprocess -- there is no bind/listen call in this file.
- `lantern_evaluate_intent` composes observe -> compile -> confidence ->
  decide (OperatingLoop.run() with no tool_name/tool_kwargs) for a host
  agent environment (e.g. Odysseus) that owns its own action/execution
  layer. It never accepts a tool_name/tool_kwargs argument from the
  remote caller and therefore can never reach RealityBoundary.act --
  the caller is expected to execute the recommended action in its own
  environment and report the real-world result back via
  lantern_observe, closing the loop without this server ever executing
  anything on the caller's behalf.

To run standalone (for local testing only, not a distribution action):
    python3 -m lantern_harness.mcp_server
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from mcp.server.mcpserver import MCPServer
    MCP_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when the mcp extra is absent
    MCPServer = None  # type: ignore[assignment,misc]
    MCP_SDK_AVAILABLE = False

from .bridge import LanternBridge
from .confidence_field import ConfidenceField
from .decision_state_machine import DecisionStateMachine
from .operating_loop import OperatingLoop
from .permission_authority import PermissionAuthority
from .prompt_compiler import PromptCompiler
from .self_model import SelfModel
from .spine import BranchStore, SpineCommitter
from .transfer_manifest import build_manifest
from .tools.boundary import ToolBoundary


DEFAULT_DATA_DIR = Path(
    os.getenv("LANTERN_MCP_DATA_DIR", str(Path.home() / ".lantern_harness_mcp"))
)


class LanternMCPContext:
    """Holds the one long-lived bridge/loop/branch-store instance a
    server process uses across tool calls. Not a new epistemic
    component -- just the wiring a stateful MCP server needs."""

    def __init__(self, data_dir: Path = DEFAULT_DATA_DIR):
        self.bridge = LanternBridge(data_dir=data_dir)
        self.bridge.ensure_identity()
        self.bridge.startup()
        self.tool_boundary = ToolBoundary()
        self.compiler = PromptCompiler(bridge=self.bridge)
        self.confidence_field = ConfidenceField(bridge=self.bridge)
        self.decision_machine = DecisionStateMachine()
        self.branch_store = BranchStore()
        self.spine_committer = SpineCommitter(self.bridge)
        self.loop = OperatingLoop(self.bridge, self.tool_boundary)
        self.permission_authority = PermissionAuthority()


def build_server(context: Optional[LanternMCPContext] = None) -> "MCPServer":
    if not MCP_SDK_AVAILABLE:
        raise RuntimeError(
            "the 'mcp' package is not installed. Install it with "
            "`pip install lantern-harness[mcp]` to run Lantern as an MCP server."
        )
    ctx = context or LanternMCPContext()
    server = MCPServer(
        name="lantern-harness",
        version="0.2.0",
        description=(
            "Auditable evidence/belief tools from the Lantern harness: "
            "observation, evidence linkage, confidence reading, decision "
            "recommendation, self-model, and exploratory branches. Never "
            "authorizes or executes external actions on its own."
        ),
    )

    @server.tool(description="Record a real Observation in the Lantern EvidenceKernel.")
    def lantern_observe(content: str, source: str, reliability: float = 1.0) -> dict:
        obs = ctx.bridge.observe(content, source=source, reliability=reliability)
        return {"observation_id": obs.id, "content": obs.content, "source": obs.source}

    @server.tool(description="Link an existing Observation as Evidence for a concept.")
    def lantern_add_evidence(concept: str, observation_id: str, weight: float = 1.0, sign: int = 1) -> dict:
        ctx.bridge.add_evidence(concept, observation_id, weight=weight, sign=sign)
        return {"concept": concept, "observation_id": observation_id, "weight": weight, "sign": sign}

    @server.tool(description="Compute a real, read-only Confidence Field reading for a concept. Never authorizes action.")
    def lantern_confidence(concept: str) -> dict:
        reading = ctx.confidence_field.evaluate(concept=concept)
        return reading.to_dict()

    @server.tool(description="Recommend (never authorize) a Decision State for a concept, based on its Confidence Field reading.")
    def lantern_decide(concept: str) -> dict:
        reading = ctx.confidence_field.evaluate(concept=concept)
        decision = ctx.decision_machine.recommend(reading)
        return decision.to_dict()

    @server.tool(description="Compile an ordinary request into a structured investigation prompt. Never fabricates missing information.")
    def lantern_compile(request: str, concept: Optional[str] = None) -> dict:
        compiled = ctx.compiler.compile(request, concept=concept)
        return compiled.to_dict()

    @server.tool(description="Report Lantern Harness's bounded self-model: what it knows, infers, can/cannot do, is authorized to do, and what requires operator action.")
    def lantern_self_model() -> dict:
        return SelfModel(ctx.bridge, ctx.tool_boundary).describe().to_dict()

    @server.tool(description="Open a new exploratory Branch. Branches never auto-commit to the Spine.")
    def lantern_branch_open(concept: str, hypothesis: str) -> dict:
        branch = ctx.branch_store.open_branch(concept=concept, hypothesis=hypothesis)
        return branch.to_dict()

    @server.tool(description="List all currently committed Spine entries, reconstructed from the real Chronicle.")
    def lantern_spine_read() -> dict:
        entries = ctx.spine_committer.read_spine()
        return {"entries": [e.to_dict() for e in entries]}

    @server.tool(description="Report real Chronicle integrity status (hash-chain verification). VALID does not mean claims are true, only that the record has not been silently altered.")
    def lantern_witness_integrity() -> dict:
        return ctx.bridge.witness_integrity()

    @server.tool(
        description=(
            "Run the read-only portion of Lantern's OperatingLoop for a host "
            "agent environment (observe -> compile -> confidence -> decide). "
            "Never accepts a tool name and never executes or authorizes any "
            "action -- the calling agent environment (e.g. Odysseus) owns "
            "its own action/execution layer and should call this before "
            "acting, then report the real result back via lantern_observe."
        )
    )
    def lantern_evaluate_intent(
        intent: str,
        concept: Optional[str] = None,
        source: str = "external-agent",
        reliability: float = 1.0,
    ) -> dict:
        result = ctx.loop.run(
            intent,
            concept=concept,
            source=source,
            reliability=reliability,
        )
        return result.to_dict()

    @server.tool(
        description=(
            "Report a Transfer Manifest describing this Lantern instance: "
            "identity (public key only), protocol/harness version, real "
            "state counts, real witness integrity status, capabilities, "
            "known gaps, and what a receiving operator must explicitly "
            "re-authorize (credentials, network exposure, MCP host "
            "registration, paid capabilities). Never includes a private "
            "key, API key value, or any other credential. Does not by "
            "itself transfer anything -- it only describes the instance."
        )
    )
    def lantern_transfer_manifest() -> dict:
        return build_manifest(ctx.bridge).to_dict()

    @server.tool(
        description=(
            "List this server process's currently active PermissionAuthority "
            "capability-scope grants (read-only -- this tool cannot grant or "
            "revoke anything; there is no lantern_grant/lantern_revoke tool "
            "exposed over MCP, deliberately, since granting_authority must "
            "always be an explicit human-typed identifier per the harness's "
            "REPL /grant command, not a string a remote MCP caller could "
            "supply on its own behalf). A remote caller with no grants "
            "listed here has no standing authority in this server process "
            "beyond what lantern_evaluate_intent already exposes (a "
            "recommendation, never an authorized or executed action). "
            "Grants are in-process memory only and never persist across "
            "server restarts."
        )
    )
    def lantern_permissions() -> dict:
        grants = ctx.permission_authority.active_grants()
        return {
            "active_grant_count": len(grants),
            "active_grants": [
                {
                    "capability": g.capability,
                    "scope": g.scope,
                    "granting_authority": g.granting_authority,
                    "version": g.version,
                }
                for g in grants
            ],
        }

    return server


def main():
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()

```

### `lantern_harness/config.py`

```python
"""Config loading. Never reads or stores actual API key values here --
only the name of the environment variable to read at call time (see
config/config.json's "api_key_env" field). Actual keys are read
directly from os.environ inside the reasoning provider adapters and are
never written to Chronicle, evidence, witness ledger, or any project
file."""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return {
            "reasoning_engine": {"provider": "none"},
            "node_id": "lantern-harness-node",
            "data_dir": "memory/lantern_data",
            "output_profile": "concise",
        }
    return json.loads(path.read_text(encoding="utf-8"))

```

### `lantern_harness/bootstrap.py`

```python
"""First-run bootstrap: detect environment, initialize directories,
identity, config, memory workspace. Reports exactly what is missing;
never silently installs software or configures credentials."""

from __future__ import annotations

import sys
from pathlib import Path

from .bridge import LanternBridge
from .config import load_config
from .reasoning import build_engine

HARNESS_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_DIRS = ["memory", "identity", "tools", "agents", "projects", "prompts", "logs", "models", "logs"]


def check_python() -> tuple[bool, str]:
    ok = sys.version_info >= (3, 10)
    return ok, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def check_lantern_importable() -> tuple[bool, str]:
    try:
        import lantern  # noqa: F401
        return True, "lantern package importable"
    except ImportError as exc:
        return False, f"lantern package not importable: {exc}"


def ensure_directories() -> list[str]:
    created = []
    for name in REQUIRED_DIRS:
        d = HARNESS_ROOT / name
        if not d.exists():
            d.mkdir(parents=True, exist_ok=True)
            created.append(name)
    return created


def bootstrap() -> dict:
    checks = {}

    py_ok, py_detail = check_python()
    checks["python"] = {"ok": py_ok, "detail": py_detail}

    lantern_ok, lantern_detail = check_lantern_importable()
    checks["lantern"] = {"ok": lantern_ok, "detail": lantern_detail}

    created_dirs = ensure_directories()
    checks["directories"] = {"ok": True, "created": created_dirs}

    config = load_config()
    checks["config"] = {"ok": True, "detail": "loaded"}

    if not lantern_ok:
        checks["identity"] = {"ok": False, "detail": "skipped -- lantern not importable"}
        checks["memory"] = {"ok": False, "detail": "skipped -- lantern not importable"}
        return {"checks": checks, "bridge": None, "engine": None, "config": config}

    data_dir = HARNESS_ROOT / config.get("data_dir", "memory/lantern_data")
    bridge = LanternBridge(data_dir, node_id=config.get("node_id", "lantern-harness-node"))

    identity_result = bridge.ensure_identity()
    checks["identity"] = {"ok": identity_result.get("status") == "READY", "detail": identity_result}

    startup_result = bridge.startup()
    checks["memory"] = {"ok": startup_result.get("status") in ("READY", "NO_CHRONICLE"), "detail": startup_result}

    engine = build_engine(config.get("reasoning_engine", {}))
    if engine is not None:
        engine_ok, engine_detail = engine.detect()
        checks["reasoning_engine"] = {"ok": engine_ok, "detail": engine_detail}
    else:
        checks["reasoning_engine"] = {"ok": False, "detail": "REASONING_ENGINE: NOT_CONFIGURED"}

    checks["tool_boundary"] = {"ok": True, "detail": "0 tools registered by default"}

    return {"checks": checks, "bridge": bridge, "engine": engine, "config": config}


def format_bootstrap_report(result: dict) -> str:
    checks = result["checks"]
    lines = ["🌱 LANTERN HARNESS", "", "First launch detected. Checking:"]
    label_map = {
        "python": "Python",
        "lantern": "Lantern",
        "identity": "Identity",
        "memory": "Memory",
        "reasoning_engine": "Reasoning Engine",
        "tool_boundary": "Tool Boundary",
    }
    for key in ["python", "lantern", "identity", "memory", "reasoning_engine", "tool_boundary"]:
        c = checks.get(key, {"ok": False, "detail": "not checked"})
        mark = "✓" if c["ok"] else "✗"
        lines.append(f"{mark} {label_map[key]}")

    lines.append("")
    bridge = result.get("bridge")
    engine = result.get("engine")
    from .harness_status import lantern_version

    lines.append(f"Lantern: v{lantern_version()}")
    if engine is not None:
        ok, detail = engine.detect()
        lines.append(f"Reasoning Engine: {engine.provider_name} ({'ready' if ok else 'NOT AVAILABLE: ' + detail})")
    else:
        lines.append("Reasoning Engine: NOT_CONFIGURED")
    lines.append(f"Identity: {checks['identity']['detail'].get('status') if bridge else 'UNAVAILABLE'}")
    lines.append(f"Memory: {checks['memory']['detail'].get('status') if bridge else 'UNAVAILABLE'}")
    lines.append("Tools: 0 configured")
    lines.append("----------------------------")
    if bridge is not None:
        lines.append("Lantern is ready.")
    else:
        lines.append("Lantern is NOT ready -- see checks above.")
    return "\n".join(lines)

```

### `lantern_harness/harness_status.py`

```python
"""LANTERN STATUS reporting. Every field here must represent something
actually checked this call -- no field is hardcoded to a fixed value."""

from __future__ import annotations

import importlib.metadata

from .bridge import LanternBridge
from .reasoning.base import ReasoningEngine


def _mcp_server_status() -> str:
    try:
        import mcp  # noqa: F401
    except ImportError:
        return "NOT_AVAILABLE (mcp package not installed; pip install lantern-harness[mcp] to expose Lantern as an MCP server via lantern_harness.mcp_server)"
    return "AVAILABLE (lantern_harness.mcp_server can expose lantern_observe/add_evidence/confidence/decide/compile/self_model/branch_open/spine_read/witness_integrity as MCP tools over stdio; run with the lantern-harness-mcp console script)"


def lantern_version() -> str:
    """Prefer the live module's __version__ attribute over installer
    dist-info metadata: dist-info can go stale (observed in practice --
    a dev venv reported v0.83 via importlib.metadata while the actually
    imported module was v0.84, because dist-info wasn't regenerated
    after a version bump). __version__ reflects the code that is
    actually running right now."""
    try:
        import lantern

        version = getattr(lantern, "__version__", None)
        if version:
            return str(version)
    except ImportError:
        pass

    try:
        return importlib.metadata.version("lantern")
    except importlib.metadata.PackageNotFoundError:
        return "UNKNOWN (lantern package not installed in this environment)"


HARNESS_VERSION = "0.2.0"


def status_report(bridge: LanternBridge, engine: ReasoningEngine | None, tool_boundary) -> dict:
    lantern_status = bridge.status()
    identity_status = bridge.identity_status()
    witness = bridge.witness_integrity()

    engine_status = engine.describe() if engine is not None else {"provider": None, "available": False, "detail": "REASONING_ENGINE: NOT_CONFIGURED"}

    return {
        "lantern_version": lantern_version(),
        "harness_version": HARNESS_VERSION,
        "node_identity": identity_status,
        "reasoning_engine": engine_status,
        "memory": {
            "chronicle_attached": lantern_status.get("chronicle", False),
            "step": lantern_status.get("step"),
            "observations": lantern_status.get("observations"),
            "evidence": lantern_status.get("evidence"),
            "contradictions": lantern_status.get("contradictions"),
        },
        "witness_integrity": witness,
        "tools": {
            "discovered": tool_boundary.discover(),
            "authorized": sorted(tool_boundary._authorized),  # noqa: SLF001 - status reporting only
        },
        "mcp_status": "NOT_CONNECTED (harness does not auto-connect to an external MCP server; see EXTERNAL_BOOTSTRAP.md in lantern-babel-codex-bridge for lantern.mcp_client usage)",
        "mcp_server_status": _mcp_server_status(),
        "branching_status": "IMPLEMENTED (lantern_harness.spine.BranchStore/SpineCommitter -- real Branch/Spine model built on top of Lantern's Chronicle; Lantern v0.84 core itself still has no branch/spine/commitment concept, see LanternBridge.branches())",
        "prompt_compiler_status": "IMPLEMENTED (lantern_harness.prompt_compiler.PromptCompiler -- newly added this harness turn, not part of Lantern v0.84 core)",
        "perspective_engine_status": "PARTIAL: lantern_harness.perspective_differential.PerspectiveDifferentialEngine is a newly-added, narrow variance calculator over caller-supplied Perspective records (NOT part of Lantern v0.84 core, NOT the full Perspective Mesh roadmap item -- no merge/vote/consensus logic exists)",
        "confidence_field_status": "IMPLEMENTED (lantern_harness.confidence_field.ConfidenceField -- read-only scoring layer over existing Lantern evidence/contradiction/integrity state)",
        "decision_state_machine_status": "IMPLEMENTED (lantern_harness.decision_state_machine.DecisionStateMachine -- explicit state/recommendation layer that never authorizes or executes)",
        "validation_status": "PARTIAL (EvidenceKernel.belief() sigmoid scoring + contradiction detection are real; no separate weighted-threshold ValidationEngine class exists)",
        "reality_boundary_status": "IMPLEMENTED (lantern_harness.reality_boundary.RealityBoundary -- INTENT/DECISION/AUTHORIZATION/ACTION/RESULT separation; REAL vs SIMULATED execution_mode is mutually exclusive by construction, see ActionRecord.is_real_success())",
        "self_model_status": "IMPLEMENTED (lantern_harness.self_model.SelfModel -- read-only self-description; has no method capable of granting itself authorization, see test_self_model_cannot_self_authorize)",
        "operating_loop_status": "IMPLEMENTED (lantern_harness.operating_loop.OperatingLoop -- composes Observation/PromptCompiler/ConfidenceField/DecisionStateMachine/RealityBoundary/Branch into one callable pipeline; adds no new decision logic of its own)",
        "transfer_manifest_status": "IMPLEMENTED (lantern_harness.transfer_manifest.build_manifest -- read-only instance description: identity/protocol/state-summary/capabilities/gaps/reauthorization-required; never includes a private key or API key value; does not itself perform a transfer)",
        "permission_authority_status": "IMPLEMENTED (lantern_harness.permission_authority.PermissionAuthority -- capability-scope permission memory + alignment combination per the PEACEMAKER delegated-authority directive; grants held in-process memory only, never persisted, so authority never travels with a transferred data_dir; see /permissions, /grant, /revoke)",
    }


def format_status_report(report: dict) -> str:
    lines = [
        "LANTERN STATUS",
        "----------------------------",
        f"Lantern Version: {report['lantern_version']}",
        f"Harness Version: {report['harness_version']}",
        f"Node Identity: {report['node_identity'].get('status')}",
    ]
    engine = report["reasoning_engine"]
    if engine.get("provider"):
        lines.append(f"Reasoning Engine: {engine['provider']} ({'available' if engine.get('available') else 'NOT AVAILABLE'})")
        lines.append(f"Model: {engine.get('model', 'n/a')}")
    else:
        lines.append("Reasoning Engine: NOT_CONFIGURED")
        lines.append("Model: n/a")
    mem = report["memory"]
    lines.append(f"Memory: chronicle_attached={mem['chronicle_attached']}, step={mem['step']}, observations={mem['observations']}, evidence={mem['evidence']}, contradictions={mem['contradictions']}")
    lines.append(f"Witness Integrity: {report['witness_integrity'].get('status')}")
    lines.append(f"Validation: {report['validation_status']}")
    lines.append(f"Branches / Spine: {report['branching_status']}")
    lines.append(f"Prompt Compiler: {report['prompt_compiler_status']}")
    lines.append(f"Perspective Differential: {report['perspective_engine_status']}")
    lines.append(f"Confidence Field: {report['confidence_field_status']}")
    lines.append(f"Decision State Machine: {report['decision_state_machine_status']}")
    lines.append(f"MCP: {report['mcp_status']}")
    lines.append(f"MCP Server: {report['mcp_server_status']}")
    lines.append(f"Tools: discovered={report['tools']['discovered']}, authorized={report['tools']['authorized']}")
    lines.append(f"Reality Boundary: {report['reality_boundary_status']}")
    lines.append(f"Self-Model: {report['self_model_status']}")
    lines.append(f"Operating Loop: {report['operating_loop_status']}")
    lines.append(f"Transfer Manifest: {report['transfer_manifest_status']}")
    lines.append(f"Permission Authority: {report['permission_authority_status']}")
    return "\n".join(lines)

```

### `lantern_harness/perspective_differential.py`

```python
"""PerspectiveDifferentialEngine: NEWLY ADDED in this harness turn. Not
part of Lantern v0.84, not a Perspective Mesh (no mesh/consensus/merge
logic exists here), not a Confidence Field, not a Decision State Machine.

This is a narrow, genuinely-implemented extension point: given two or
more independent Perspective records (each an observation about what a
distinct source/model/reasoner concluded, with its own confidence,
evidence, assumptions, and novelty), it computes variance across those
dimensions and reports where they diverge most. It does not resolve the
divergence, does not vote, does not average toward a "correct" answer,
and does not claim the highest-confidence or majority perspective is
right. Divergence is returned as a diagnostic signal for a human or a
future component to investigate -- never as proof.

If given fewer than two perspectives, this reports NOT_APPLICABLE rather
than fabricating a differential from a single data point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import pvariance
from typing import Optional


@dataclass(frozen=True)
class Perspective:
    """One independent, already-produced conclusion. This module does
    not generate these -- callers supply them from wherever the actual
    reasoning happened (could be a real model call, a human, another
    Lantern node). Supplying a Perspective here does not validate it."""

    source: str
    conclusion: str
    confidence: float  # 0.0-1.0, as reported by the source -- a signal, not proof
    evidence_score: float  # 0.0-1.0, caller's own assessment of evidence strength
    assumption_bias: float  # 0.0-1.0, caller's own assessment of assumption reliance
    novelty_score: float = 0.0  # 0.0-1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "evidence_score": self.evidence_score,
            "assumption_bias": self.assumption_bias,
            "novelty_score": self.novelty_score,
        }


@dataclass(frozen=True)
class DifferentialReading:
    status: str  # "NOT_APPLICABLE" | "COMPUTED"
    confidence_variance: Optional[float] = None
    evidence_variance: Optional[float] = None
    assumption_variance: Optional[float] = None
    novelty_variance: Optional[float] = None
    primary_divergence_dimension: Optional[str] = None
    perspectives: tuple = field(default_factory=tuple)
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "confidence_variance": self.confidence_variance,
            "evidence_variance": self.evidence_variance,
            "assumption_variance": self.assumption_variance,
            "novelty_variance": self.novelty_variance,
            "primary_divergence_dimension": self.primary_divergence_dimension,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "note": self.note,
        }


class PerspectiveDifferentialEngine:
    """Computes variance across independent Perspectives. Does not
    merge, vote, or select a winner -- see module docstring."""

    def compare(self, perspectives: list) -> DifferentialReading:
        if perspectives is None:
            raise ValueError("perspectives must be a list, not None")
        if len(perspectives) < 2:
            return DifferentialReading(
                status="NOT_APPLICABLE",
                perspectives=tuple(perspectives),
                note=(
                    f"{len(perspectives)} perspective(s) supplied; a differential "
                    "requires at least 2 independent perspectives to compute variance "
                    "against. This is not a failure -- it is an honest report that "
                    "there is nothing to compare yet."
                ),
            )

        confidences = [p.confidence for p in perspectives]
        evidences = [p.evidence_score for p in perspectives]
        assumptions = [p.assumption_bias for p in perspectives]
        novelties = [p.novelty_score for p in perspectives]

        variances = {
            "confidence": pvariance(confidences),
            "evidence": pvariance(evidences),
            "assumption": pvariance(assumptions),
            "novelty": pvariance(novelties),
        }
        primary = max(variances, key=variances.get)

        return DifferentialReading(
            status="COMPUTED",
            confidence_variance=variances["confidence"],
            evidence_variance=variances["evidence"],
            assumption_variance=variances["assumption"],
            novelty_variance=variances["novelty"],
            primary_divergence_dimension=primary,
            perspectives=tuple(perspectives),
            note=(
                "Variance across supplied perspectives is a diagnostic signal for "
                "where further investigation may help. It does not determine which "
                "perspective (if any) is correct, and majority/highest-confidence "
                "is never auto-selected as truth."
            ),
        )

```


## 12. VERIFICATION QUESTIONS


Miles MUST verify these against executable source rather than trusting
documentation:
1. Does `LanternBridge` actually connect to the real Lantern APIs?
2. Does `OperatingLoop` actually enforce the intended sequence?
3. Does a reasoning provider have any direct path to tools?
4. Can MCP bypass `ToolBoundary`?
5. Can `PermissionAuthority` be bypassed?
6. Are permissions scoped and revocable?
7. Can model-generated text become evidence without independent observation?
8. Does `RealityBoundary` actually prevent that?
9. Does Spine require explicit human authorization before commitment?
10. Can model output modify persistent state without authorization?
11. Does `TransferManifest` preserve authority and provenance?
12. Does `SelfModel` reflect real runtime state?
13. Are provider adapters advisory, or can they directly mutate state?
14. What happens when Lantern is unavailable?
15. What happens when the reasoning model fails?
16. What happens when authorization is missing?
17. What happens when evidence is contradictory?
18. What happens when a tool call is malformed?
19. What happens when an unknown command is supplied?
20. Which protections exist in code and which exist only in prompts/comments?
For each answer use:
OBSERVED
CORROBORATED
CLAIMED
BLOCKED
UNKNOWN
DISPROVEN


## 13. INTERPRETATION RULE
Do NOT assume a feature exists merely because:
- README.md says it exists
- a prompt says it exists
- a comment says it exists
- a class has the expected name
- a method has the expected name
- a test file exists
Prefer executable source behavior.
If source proves the behavior:
    OBSERVED
If multiple independent tests or source paths support it:
    CORROBORATED
If the repository merely claims the behavior:
    CLAIMED
If code explicitly prevents the behavior:
    BLOCKED
If the repository does not provide enough information:
    UNKNOWN
If source or tests demonstrate that the claim is false:
    DISPROVEN
## 14. CENTRAL QUESTION FOR MILES
Determine precisely:
    What can this harness actually cause to happen?
and:
    What can the reasoning model NOT cause to happen
    without the required authorization?
Trace those answers through:
    model
      |
      v
    reasoning adapter
      |
      v
    bridge
      |
      v
    operating loop
      |
      v
    tool boundary
      |
      v
    permission authority
      |
      v
    external/tool action
      |
      v
    persistent state
Do not stop at interfaces.
Follow the implementation.
## 15. SECURITY NOTICE
This report is sanitized using heuristic secret detection.
It is NOT a guarantee that every secret has been found.
Before giving this report to another system, manually check:
- credentials
- API keys
- bearer tokens
- private keys
- passwords
- cookies
- session identifiers
- personal information
- private endpoints
- internal hostnames
Never treat redaction as a substitute for secret rotation.
## 16. HANDOFF
Give Miles the contents of this file.
Miles should be able to use it to:
1. understand the repository;
2. locate the important implementation;
3. follow the actual call relationships;
4. identify missing boundaries;
5. identify stubbed behavior;
6. identify bypass paths;
7. identify failing assumptions;
8. propose the smallest repair necessary.
Accuracy is more important than making the system appear complete.
