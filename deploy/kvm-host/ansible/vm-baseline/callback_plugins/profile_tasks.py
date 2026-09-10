# Copyright (c) 2026, Tiago Paranhos Lima
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import time

from ansible.plugins.callback import CallbackBase


DOCUMENTATION = """
  name: profile_tasks
  type: aggregate
  short_description: adds task timing and total playbook duration
  description:
    - Displays elapsed time per task and total playbook execution time.
"""


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "profile_tasks"
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super().__init__()
        self._task_times = {}
        self._playbook_start = None

    def v2_playbook_on_play_start(self, play):
        if self._playbook_start is None:
            self._playbook_start = time.monotonic()

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._task_times[task._uuid] = time.monotonic()

    def _fmt_duration(self, start):
        return time.monotonic() - start

    def _print_task_duration(self, result):
        task_uuid = result._task._uuid
        if task_uuid in self._task_times:
            elapsed = self._fmt_duration(self._task_times[task_uuid])
            self._display.display(
                f"  completed in {elapsed:.2f}s",
                color="cyan",
            )

    def v2_runner_on_ok(self, result):
        self._print_task_duration(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self._print_task_duration(result)

    def v2_runner_on_unreachable(self, result):
        self._print_task_duration(result)

    def v2_runner_on_skipped(self, result):
        self._print_task_duration(result)

    def v2_playbook_on_stats(self, stats):
        if self._playbook_start:
            total = self._fmt_duration(self._playbook_start)
            self._display.display(
                f"\n  Total playbook time: {total:.2f}s",
                color="cyan",
            )
