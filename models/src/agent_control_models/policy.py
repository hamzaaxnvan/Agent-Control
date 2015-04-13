from .base import BaseModel
from .controls import ControlDefinition, UnrenderedTemplateControl


class Control(BaseModel):
    """A control with identity and configuration.

    For rendered controls (raw or template-backed), ``control`` is a
    ``ControlDefinition``.  For unrendered template controls, ``control``
    is an ``UnrenderedTemplateControl``.
