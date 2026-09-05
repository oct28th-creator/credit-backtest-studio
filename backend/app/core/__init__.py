"""Platform core: run identity, reproducibility and job lifecycle.

These modules hold no credit-risk logic. They are the substrate an agent
needs in order to run many experiments safely: every run is identified by a
manifest hash, every run is immutable, and every run has an observable
lifecycle.
"""
