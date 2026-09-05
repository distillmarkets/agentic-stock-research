"""Agentic Stock Research.

Tools for working with SEC fundamentals from the Distill Markets API alongside
data you hold on your own disk (end-of-day prices, for example). The toolkit
contains no third-party data and no downloaders for third-party data. Read
NOTICE before using it.

Modules
    client   cached, latency-logging client for the Distill Markets API, with an
             offline mode that refuses any call not already on disk
    stooq    readers for Stooq end-of-day files you have downloaded yourself
    joins    split-basis checks and inference, market capitalisation, return
             decomposition, forward returns
    analysis record anchors and exits, forward paths, event windows, segments,
             survival curves, within-cohort ranking, cluster resampling and nulls
    charts   house chart shapes for a study's figures

The rule for what lives here: a helper moves out of a study and into the package
when a SECOND study needs it. docs/agent-guide.md lists them.
"""

__version__ = "0.1.0"
