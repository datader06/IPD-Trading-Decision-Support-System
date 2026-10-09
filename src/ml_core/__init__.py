"""Strategy-agnostic ML layer (Experiment 2 onward). Reads any frozen Phase A candidates file; never changes src/ml or Phase A.

Reuses, unchanged, the walk-forward folds (ml.splits), model families and grids (ml.models), thresholds (ml.thresholds),
evaluation (ml.evaluate) and the experiment runner (ml.experiment). Only the dataset/feature layer is new here.
"""
