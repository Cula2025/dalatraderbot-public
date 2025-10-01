# -*- coding: utf-8 -*-
import inspect, types

def _is_params_class(obj):
    try:
        if inspect.isclass(obj):
            n = getattr(obj, "__name__", "")
            if n == "Params" or "params" in n.lower():
                return True
            ann = getattr(obj, "__annotations__", {})
            if ann:
                return True
    except Exception:
        pass
    return False

def _pick_callable(candidates):
    name_order = ("run_backtest", "backtest", "simulate", "run", "RUN_BT")
    by_name = {getattr(fn, "__name__", ""): fn for fn in candidates if isinstance(fn, types.FunctionType)}
    for nm in name_order:
        if nm in by_name:
            return by_name[nm]
    # fallback: någon med 2 pos. args
    for fn in candidates:
        if not isinstance(fn, types.FunctionType):
            continue
        try:
            sig = inspect.signature(fn)
            params = [p for p in sig.parameters.values()
                      if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
            if len(params) == 2:
                return fn
        except Exception:
            pass
    for fn in candidates:
        if isinstance(fn, types.FunctionType):
            return fn
    return None

def resolve_backtest():
    """Returnerar (modul, Params-klass|None, run_fn|None)."""
    from app.portfolio_signals import _import_backtest
    mod = _import_backtest()
    ns = vars(mod)
    params_cls = None
    for name, obj in ns.items():
        if _is_params_class(obj):
            params_cls = obj
            break
    run_fn = _pick_callable(list(ns.values()))
    return mod, params_cls, run_fn

def _build_params_obj(params_cls, prof_params: dict):
    if not params_cls:
        return prof_params or {}
    try:
        sig = inspect.signature(params_cls)
        kwargs = {}
        for name, p in sig.parameters.items():
            if name == "self":
                continue
            if prof_params and name in prof_params:
                kwargs[name] = prof_params[name]
        return params_cls(**kwargs)
    except Exception:
        try:
            return params_cls(**(prof_params or {}))
        except Exception:
            return prof_params or {}

def _call_run_fn(run_fn, profile: dict, params_obj):
    if run_fn is None:
        raise RuntimeError("Ingen körbar backtest-funktion hittades.")
    ticker   = profile.get("ticker")
    strategy = profile.get("strategy")
    sig = inspect.signature(run_fn)
    argnames = list(sig.parameters.keys())

    if "profile" in argnames:
        return run_fn(profile=profile)
    if len(argnames) == 1:
        return run_fn(params_obj)
    if set(argnames) >= {"ticker", "params"}:
        return run_fn(ticker=ticker, params=params_obj)
    if set(argnames) >= {"ticker", "strategy", "params"}:
        return run_fn(ticker=ticker, strategy=strategy, params=params_obj)
    if len(argnames) == 2:
        return run_fn(ticker, params_obj)

    # sista utväg
    kwargs = {"profile": profile, "ticker": ticker, "strategy": strategy, "params": params_obj}
    kwargs = {k: v for k, v in kwargs.items() if k in argnames}
    return run_fn(**kwargs)

def run_backtest(profile: dict):
    if not isinstance(profile, dict):
        raise TypeError("run_backtest() kräver en profil som dict.")
    _mod, params_cls, run_fn = resolve_backtest()
    params_obj = _build_params_obj(params_cls, profile.get("params") or {})
    return _call_run_fn(run_fn, profile, params_obj)

__all__ = ["resolve_backtest", "run_backtest"]
# --- compatibility wrapper: accept legacy signatures like (ticker, strategy, params, ...) ---
def _normalize_profile_args(*args, **kwargs):
    # If first arg is already a profile dict
    if args and isinstance(args[0], dict):
        prof = dict(args[0])
    else:
        prof = {}
        # Positional mapping: (ticker), (ticker, strategy), (ticker, params), (ticker, strategy, params)
        if len(args) >= 1:
            prof["ticker"] = args[0]
        if len(args) >= 2:
            if isinstance(args[1], dict):
                prof["params"] = args[1]
            else:
                prof["strategy"] = args[1]
        if len(args) >= 3 and isinstance(args[2], dict):
            prof["params"] = args[2]

    # Kwargs override/extend
    if "profile" in kwargs and isinstance(kwargs["profile"], dict):
        prof.update(kwargs["profile"])
    for k in ("ticker", "strategy", "params"):
        if k in kwargs:
            prof[k] = kwargs[k]

    if "params" not in prof or prof["params"] is None:
        prof["params"] = {}
    return prof

def run_backtest_compat(*args, **kwargs):
    profile = _sanitize_profile(_normalize_profile_args(*args, **kwargs))
    _mod, params_cls, run_fn = resolve_backtest()
    params_obj = _build_params_obj(params_cls, profile.get("params") or {})
    return _call_run_fn(run_fn, profile, params_obj)

# Replace original symbol so imports keep working
run_backtest = run_backtest_compat
# --- robust resolve_backtest override ---
def resolve_backtest():
    """
    Laddar din backtest-modul via _import_backtest() och försöker få ut ett namespace
    oavsett om _import_backtest() returnerar modul, modulnamn, dict eller annat objekt.
    Returnerar (module, ParamsClass|None, run_fn|None).
    """
    import types, importlib
    from app.portfolio_signals import _import_backtest

    raw = _import_backtest()

    mod = None
    ns = None

    # 1) Direkt modul?
    if isinstance(raw, types.ModuleType):
        mod = raw
        ns = vars(mod)
    else:
        # 2) Dict?
        if isinstance(raw, dict):
            ns = raw
            mod = None
        else:
            # 3) Sträng -> försök importera modulnamnet
            if isinstance(raw, str):
                try:
                    mod = importlib.import_module(raw)
                    ns = vars(mod)
                except Exception:
                    pass

            # 4) Annat objekt: försök med dess __module__
            if ns is None:
                mname = getattr(raw, "__module__", None)
                if mname:
                    try:
                        mod = importlib.import_module(mname)
                        ns = vars(mod)
                    except Exception:
                        pass

            # 5) Sista utväg: vars() direkt (om objektet råkar ha __dict__)
            if ns is None:
                try:
                    ns = vars(raw)
                except Exception as e:
                    raise RuntimeError(f"_import_backtest() gav ett otippat objekt ({type(raw).__name__}) som inte kan tolkas: {e}")

    # Hitta ev. Params-klass och kör-funktionen
    params_cls = None
    for name, obj in ns.items():
        if _is_params_class(obj):
            params_cls = obj
            break

    run_fn = _pick_callable(list(ns.values()))
    return mod, params_cls, run_fn
# --- tuple-aware resolve_backtest override ---
def _resolve_from_mixed(raw):
    """Bygg ett namespace ur modul/sträng/dict/objekt eller lista/tuple blandning."""
    import types, importlib
    items = list(raw) if isinstance(raw, (list, tuple)) else [raw]

    ns = {}
    first_mod = None

    for it in items:
        if isinstance(it, types.ModuleType):
            if first_mod is None:
                first_mod = it
            ns.update(vars(it))
            continue

        if isinstance(it, dict):
            ns.update(it)
            continue

        if isinstance(it, str):
            # tolka som modulnamn
            try:
                m = importlib.import_module(it)
                if first_mod is None:
                    first_mod = m
                ns.update(vars(m))
            except Exception:
                pass
            continue

        if isinstance(it, types.FunctionType):
            ns[getattr(it, "__name__", "run_fn")] = it
            continue

        # annars försök __dict__ eller modul från __module__
        try:
            ns.update(vars(it))
            continue
        except Exception:
            mname = getattr(it, "__module__", None)
            if mname:
                try:
                    m = importlib.import_module(mname)
                    if first_mod is None:
                        first_mod = m
                    ns.update(vars(m))
                except Exception:
                    pass

    return first_mod, ns

def resolve_backtest():
    """
    Robust: hanterar att _import_backtest() kan returnera modul, dict, sträng,
    objekt, funktion, eller en tuple/lista av sådana.
    """
    from app.portfolio_signals import _import_backtest
    raw = _import_backtest()
    mod, ns = _resolve_from_mixed(raw)

    # Hitta ev. Params-klass
    params_cls = None
    for name, obj in ns.items():
        if _is_params_class(obj):
            params_cls = obj
            break

    run_fn = _pick_callable(list(ns.values()))
    return mod, params_cls, run_fn
# --- debug wrapper: log stacktrace and retry with dict params ---
def _safe_print(*a, **k):
    try:
        print(*a, **k, flush=True)
    except Exception:
        pass

def run_backtest_compat(*args, **kwargs):
    import traceback, json
    profile = _sanitize_profile(_normalize_profile_args(*args, **kwargs))
    _mod, params_cls, run_fn = resolve_backtest()

    # 1) Försök med Params-objekt (som tidigare)
    try:
        params_obj = _build_params_obj(params_cls, profile.get("params") or {})
        _safe_print("[btwrap] run_backtest try#1",
                    "run_fn=", getattr(run_fn, "__name__", str(run_fn)),
                    "params_obj_type=", type(params_obj).__name__,
                    "profile_keys=", list(profile.keys()))
        return _call_run_fn(run_fn, profile, params_obj)
    except Exception as e1:
        _safe_print("[btwrap] run_backtest try#1 FAILED:", type(e1).__name__, str(e1))
        _safe_print("[btwrap] profile:", json.dumps({k: v for k, v in profile.items() if k != "params"}))
        try:
            _safe_print("[btwrap] params as dict:", json.dumps(profile.get("params") or {}))
        except Exception:
            _safe_print("[btwrap] params as dict: <non-serializable>")

        traceback.print_exc()

    # 2) Fallback: testa med ren dict för params
    try:
        params_dict = profile.get("params") or {}
        _safe_print("[btwrap] run_backtest try#2 (dict params)",
                    "run_fn=", getattr(run_fn, "__name__", str(run_fn)),
                    "params_type=", type(params_dict).__name__)
        return _call_run_fn(run_fn, profile, params_dict)
    except Exception as e2:
        _safe_print("[btwrap] run_backtest try#2 FAILED:", type(e2).__name__, str(e2))
        traceback.print_exc()
        # propagatera vidare så UI visar fel
        raise

# ensure symbol points to our latest wrapper
run_backtest = run_backtest_compat
def _sanitize_profile(profile: dict):
    # Prioritera profile["ticker"]; ta bort ev. krock i params
    if isinstance(profile, dict):
        params = profile.get("params")
        if isinstance(params, dict) and "ticker" in params:
            # rensa bort inre ticker helt (den ställer bara till det)
            params.pop("ticker", None)
    return profile
