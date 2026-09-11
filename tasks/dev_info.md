
Approval
----------------------------------------------------------

- `gate.can_auto_run` (gate.py:21) holds any action no in the `allow_list`
- and a HARD FLOOR holds anything irreversible unless git makes it recoverable
- Held actions sit in `inbox` and do nothing until `approve <action_id>`
- or reset via git
