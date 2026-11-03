"""Request-local debug events; deliberately separate from archived evidence."""
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel


class TraceEvent(BaseModel):
    sequence: int
    stage: str
    operation: str
    status: Literal['started', 'success', 'failed']
    source: Literal['application', 'model', 'tool']
    summary: str
    inputs: Any = None
    output: Any = None


class TraceRecorder:
    def __init__(self, progress: Callable[[dict], None] | None = None):
        self.progress = progress
        self.sequence = 0

    def record(self, stage: str, operation: str, summary: str, *, status='success',
               source='application', inputs=None, output=None) -> None:
        if self.progress is None:
            return
        self.sequence += 1
        event = TraceEvent(sequence=self.sequence, stage=stage, operation=operation,
                           status=status, source=source, summary=summary, inputs=inputs, output=output)
        self.progress({'type': 'trace', 'data': event.model_dump(mode='json')})
