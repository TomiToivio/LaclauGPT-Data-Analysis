"""statsmodels backend for inference on reviewed corpus-level results."""
from __future__ import annotations

from typing import Any

from . import BackendUnavailable


def is_available() -> bool:
    try:
        import statsmodels  # noqa: F401
        return True
    except ImportError:
        return False


def _version() -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version("statsmodels")
    except Exception:
        return ""


def fit(dataset: Any, *, formula: str | None = None, method: str = "ols", **options: Any) -> dict[str, Any]:
    if not is_available():
        raise BackendUnavailable("statsmodels is not installed")
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("dataset must be a pandas.DataFrame of reviewed results")
    if method == "arima":
        endog = options.pop("endog", None)
        if endog is None:
            raise ValueError("arima requires endog")
        order = tuple(options.pop("order", (1, 1, 1)))
        trained = sm.tsa.ARIMA(dataset[endog] if isinstance(endog, str) else endog, order=order).fit()
    elif not formula:
        raise ValueError(f"method {method!r} requires a patsy formula")
    elif method == "ols":
        trained = smf.ols(formula, data=dataset).fit(**options)
    elif method == "logit":
        trained = smf.logit(formula, data=dataset).fit(**options)
    elif method == "glm":
        family = options.pop("family", None)
        trained = smf.glm(formula, data=dataset, family=family).fit(**options)
    else:
        raise ValueError(f"unknown statsmodels method: {method}")
    conf = trained.conf_int()
    params = trained.params
    pvalues = trained.pvalues
    return {
        "method": method,
        "formula": formula,
        "statsmodels_version": _version(),
        "n_observations": int(getattr(trained, "nobs", len(dataset))),
        "coefficients": {name: float(params[name]) for name in params.index},
        "p_values": {name: float(pvalues[name]) for name in pvalues.index},
        "confidence_intervals": {name: [float(conf.loc[name, 0]), float(conf.loc[name, 1])] for name in conf.index},
        "diagnostics": {
            "aic": float(trained.aic) if hasattr(trained, "aic") else None,
            "bic": float(trained.bic) if hasattr(trained, "bic") else None,
            "rsquared": float(trained.rsquared) if hasattr(trained, "rsquared") else None,
        },
        "boundary_note": "Statistical output is evidence; discourse-theoretical interpretation remains a reviewed analytical step.",
    }


def ttest(group_a: list[float], group_b: list[float]) -> dict[str, Any]:
    if not is_available():
        raise BackendUnavailable("statsmodels is not installed")
    import statsmodels.stats.weightstats as smws
    statistic, pvalue, df = smws.ttest_ind(group_a, group_b, usevar="unequal")
    return {
        "test": "ttest_ind",
        "statistic": float(statistic),
        "p_value": float(pvalue),
        "degrees_of_freedom": float(df),
        "n_a": len(group_a),
        "n_b": len(group_b),
        "statsmodels_version": _version(),
    }
