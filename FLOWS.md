# FLOWS

## Overview
Grounded flow summary from 106 entrypoint candidate(s) and 425 detected flow(s).

Target path: `C:\jetabot res 8\JetaDirectaBot`
Scan root: `.`

## Confirmed Flows
### Confirmed Flows

Grounded sections derived from the analyzed `.archify` artifacts.

- **Subsystems: 72 detected.**
  Evidence: artifact:.archify/architecture-context.json
- **Services: 72 detected.**
  Evidence: artifact:.archify/services.json
- **Routes: 106 detected.**
  Evidence: artifact:.archify/routes.json
- **Tables: 0 detected.**
  Evidence: artifact:.archify/database.json

## Inferred Flow Notes
### Inferred Flow Notes

Inferred summary: These notes are inferred from grounded artifact relationships and remain labeled as inference.

- Inferred: **Inferred: repository boundaries likely follow the detected subsystem, service, route, and persistence surfaces.**
  Evidence: artifact:.archify/architecture-context.json, artifact:.archify/services.json
- Inferred: **Inferred: when evidence is weak, expand this document conservatively and prefer explicit confirmation over assumptions.**
  Evidence: artifact:.archify/docs-summary.json, artifact:.archify/facts.json

## Open Questions / Uncertainty
### Open Questions

- Inferred: **Does `subsystem-10-0-esports-extension` really depend on `subsystem-1-0-apis` through `calls`?**
  Evidence: edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_apis_dpm_api_py_call_get:esports_extension/models/tracker.py:181:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_apis_dpm_api_py_call_len:esports_extension/models/tracker.py:106:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_apis_dpm_api_py_call_len:esports_extension/models/tracker.py:110:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_apis_dpm_api_py_call_len:esports_extension/models/tracker.py:234:0
- Inferred: **Does `subsystem-10-0-esports-extension` really depend on `subsystem-20-0-core` through `calls`?**
  Evidence: edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_register_player_commands_py_call_getattr:esports_extension/models/tracker.py:101:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_register_player_commands_py_call_getattr:esports_extension/models/tracker.py:102:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_register_player_commands_py_call_getattr:esports_extension/models/tracker.py:220:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_register_player_commands_py_call_getattr:esports_extension/models/tracker.py:222:0
- Inferred: **Does `subsystem-10-0-esports-extension` really depend on `subsystem-3-0-copa` through `calls`?**
  Evidence: edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_copa_registro_py_call_all:esports_extension/models/tracker.py:112:0, edge:symbol_esports_extension_models_tracker_py_method_trackedmatch_enrich_from_event_details:calls:ref_copa_registro_py_call_all:esports_extension/models/tracker.py:475:0, edge:symbol_esports_extension_models_tracker_py_method_trackedmatch_enrich_from_event_details:calls:ref_copa_registro_py_call_enumerate:esports_extension/models/tracker.py:484:0, edge:symbol_esports_extension_models_tracker_py_method_trackedmatch_enrich_from_event_details:calls:ref_copa_registro_py_call_enumerate:esports_extension/models/tracker.py:519:0
- Inferred: **Does `subsystem-10-0-esports-extension` really depend on `subsystem-7-0-core` through `calls`?**
  Evidence: edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_rank_data_py_call_sum:esports_extension/models/tracker.py:222:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_rank_data_py_call_sum:esports_extension/models/tracker.py:223:0
- Inferred: **Does `subsystem-10-0-esports-extension` really depend on `subsystem-9-0-core` through `calls`?**
  Evidence: edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_historial_commands_py_call_next:esports_extension/models/tracker.py:220:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_historial_commands_py_call_next:esports_extension/models/tracker.py:237:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_historial_commands_py_call_next:esports_extension/models/tracker.py:238:0, edge:symbol_esports_extension_models_tracker_py_method_trackedgame_enrich_from_live_stats:calls:ref_core_historial_commands_py_call_next:esports_extension/models/tracker.py:297:0
- Inferred: **Does `subsystem-11-0-models` really depend on `subsystem-0-0-esports-extension` through `calls`?**
  Evidence: edge:symbol_models_bootcamp_player_py_method_account_from_dict:calls:ref_esports_extension_models_live_py_call_cls:models/bootcamp_player.py:59:0, edge:symbol_models_bootcamp_player_py_method_account_from_leaderboard:calls:ref_esports_extension_models_live_py_call_cls:models/bootcamp_player.py:30:0, edge:symbol_models_bootcamp_player_py_method_account_from_leaderboard:calls:ref_esports_extension_models_live_py_call_raw_data_get:models/bootcamp_player.py:28:0, edge:symbol_models_bootcamp_player_py_method_account_from_leaderboard:calls:ref_esports_extension_models_live_py_call_raw_data_get:models/bootcamp_player.py:35:0
- Inferred: **Does `subsystem-11-0-models` really depend on `subsystem-1-0-apis` through `calls`?**
  Evidence: edge:symbol_models_bootcamp_player_py_method_account_from_dict:calls:ref_apis_dpm_api_py_call_data_get:models/bootcamp_player.py:58:0, edge:symbol_models_bootcamp_player_py_method_account_from_dict:calls:ref_apis_dpm_api_py_call_data_get:models/bootcamp_player.py:62:0, edge:symbol_models_bootcamp_player_py_method_account_from_dict:calls:ref_apis_dpm_api_py_call_data_get:models/bootcamp_player.py:63:0, edge:symbol_models_bootcamp_player_py_method_account_from_dict:calls:ref_apis_dpm_api_py_call_data_get:models/bootcamp_player.py:64:0
- Inferred: **Does `subsystem-11-0-models` really depend on `subsystem-10-0-esports-extension` through `calls`?**
  Evidence: edge:symbol_models_bootcamp_player_py_method_bootcampplayer_add_account:calls:ref_esports_extension_models_tracker_py_call_append:models/bootcamp_player.py:98:0
