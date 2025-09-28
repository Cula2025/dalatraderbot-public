# -*- coding: utf-8 -*-
import inspect

def _find_callable(mod):
    if isinstance(mod, tuple):
        for it in mod:
            if callable(it):
                return it
        return None
    for name in ("backtest","run_backtest","simulate","run","main","execute"):
        fn = getattr(mod, name, None)
        if callable(fn):
            return fn
    for k, v in getattr(mod, "__dict__", {}).items():
        if not k.startswith("_") and callable(v):
            return v
    if callable(mod):
        return mod
    return None

def _call_best(fn, *args, **kwargs):
    sig = inspect.signature(fn)
    params = list(sig.parameters.values())
    has_varpos = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in params)
    has_varkw  = any(p.kind == inspect.Parameter.VAR_KEYWORD     for p in params)
    allowed_kw = {p.name for p in params
                  if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD,
                                inspect.Parameter.KEYWORD_ONLY)}
    pos_params = [p for p in params
                  if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                inspect.Parameter.POSITIONAL_OR_KEYWORD)]
    max_pos = len(pos_params)
    call_args = args if has_varpos else args[:max_pos]
    call_kwargs = kwargs if has_varkw else {k: v for k, v in kwargs.items() if k in allowed_kw}
    try:
        return fn(*call_args, **call_kwargs)
    except TypeError:
        filled, used_kw, ai = [], set(), 0
        for p in pos_params:
            if ai < len(call_args):
                filled.append(call_args[ai]); ai += 1
            elif p.name in call_kwargs:
                filled.append(call_kwargs[p.name]); used_kw.add(p.name)
            elif p.default is not inspect._empty:
                pass
        rest_kwargs = {k: v for k, v in call_kwargs.items() if k not in used_kw}
        return fn(*tuple(filled), **rest_kwargs)

def run_backtest(*args, **kwargs):
    from app.portfolio_signals import _import_backtest as _imp
    mod = _imp()
    fn = _find_callable(mod)
    if fn is None:
        raise TypeError("Hittar ingen backtest-funktion i modulen från _import_backtest()")
    return _call_best(fn, *args, **kwargs)
