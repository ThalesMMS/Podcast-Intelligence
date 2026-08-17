"""AI provider adapters.

Concrete adapters are imported by the provider registry rather than eagerly here. This keeps
unit tests and custom deployments from importing provider SDKs they do not use.
"""
