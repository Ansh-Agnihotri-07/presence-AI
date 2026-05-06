"""
AI Router — 4-Engine Autonomous Cognitive Routing Hub (Phase 2.1.1).

Engine state model (per engine):
  detected  = module imported successfully
  available = probe success + valid API key + connectivity
  healthy   = runtime success rate > 50% (from rolling perf data)
  latency   = avg latency from rolling window
  failures  = total failure count
  last_error = most recent error message

Routing uses ONLY available engines. Detected-but-unavailable are skipped.
Healthy status affects priority within cognitive_router, not eligibility.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Any

from core.config import config
from ai import local_ai_engine
from ai import groq_engine
from ai import gemini_engine
from ai import cloud_ai_engine
from ai.task_analyzer import analyze_task
from ai.cognitive_router import select_strategy
from ai.hybrid_synthesizer import synthesize
from ai.engine_health import health_registry
from ai.schema_validator import validate_groq_schema
from ai.rate_limiter import rate_limiter
from system.usage_tracker import UsageTracker
from system.cost_guard import CostGuard
from system.safety_guard import SafetyGuard
import httpx

logger = logging.getLogger("presence.ai.router")

# ── Global guards ──
_usage_tracker: UsageTracker | None = None
_cost_guard: CostGuard | None = None
_safety_guard: SafetyGuard | None = None

# ═══════════════════════════════════════
# ── Engine Registry (single source of truth)
# ═══════════════════════════════════════

_PERF_WINDOW = 50

def _new_engine_entry() -> dict:
    return {
        "detected": True,       # module imported (always True since we import at top)
        "available": False,     # probe success + valid key
        "healthy": False,       # runtime success rate > 50%
        "latency": 0.0,         # avg latency from rolling window
        "failures": 0,          # cumulative failure count
        "last_error": None,     # most recent error string
        # internal rolling data
        "_latencies": deque(maxlen=_PERF_WINDOW),
        "_successes": deque(maxlen=_PERF_WINDOW),
    }

engine_registry: dict[str, dict] = {
    "local":  _new_engine_entry(),
    "groq":   _new_engine_entry(),
    "gemini": _new_engine_entry(),
    "cloud":  _new_engine_entry(),
}


def _record_perf(engine: str, latency: float, success: bool, error: str | None = None, error_type: str = "unknown"):
    """Record engine performance and update healthy/latency/failures via strict registry."""
    reg = engine_registry[engine]
    
    if not success:
        reg["failures"] += 1
        reg["last_error"] = error
        health_registry.record_failure(engine, error_type=error_type)
    else:
        health_registry.record_success(engine, latency)


def _is_usable(engine: str) -> bool:
    """Check if an engine is available AND healthy for routing using strict quorum rules."""
    reg = engine_registry[engine]
    if not reg["available"]: return False
    return health_registry.is_eligible(engine)


def get_engine_stats() -> dict[str, dict[str, Any]]:
    """Return clean stats for each engine (from health registry)."""
    stats = {}
    for name, reg in engine_registry.items():
        h = health_registry.registry.get(name, {})
        stats[name] = {
            "detected": reg["detected"],
            "available": reg["available"],
            "healthy": health_registry.is_eligible(name),
            "avg_latency": round(h.get("latency_avg", 0.0), 3),
            "success_rate": round(1.0 - h.get("failure_rate", 0.0), 2),
            "total_calls": h.get("success_count", 0) + h.get("failure_count", 0),
            "failures": reg["failures"],
            "last_error": reg["last_error"],
        }
    return stats


# ═══════════════════════════════════════
# ── Initialization (parallel probing)
# ═══════════════════════════════════════

async def init_router():
    """Initialize router — probe all engines in parallel with 1.5s timeout."""
    global _usage_tracker, _cost_guard, _safety_guard

    _usage_tracker = UsageTracker(config.MEMORY_DIR)
    _cost_guard = CostGuard(config, _usage_tracker)
    _safety_guard = SafetyGuard(config, _cost_guard)

    # Parallel probe with timeout
    results = await asyncio.gather(
        _probe_engine("local"),
        _probe_engine("groq"),
        _probe_engine("gemini"),
        _probe_engine("cloud"),
        return_exceptions=True,
    )

    for i, name in enumerate(["local", "groq", "gemini", "cloud"]):
        success = results[i] is True
        engine_registry[name]["available"] = success
        if success:
            engine_registry[name]["healthy"] = True  # initial probe success = healthy

    # ── Boot logging: separate detected / available / healthy ──
    detected = [n for n, r in engine_registry.items() if r["detected"]]
    available = [n.upper() for n, r in engine_registry.items() if r["available"]]
    healthy = [n.upper() for n, r in engine_registry.items() if r["healthy"]]
    unavailable = [n.upper() for n, r in engine_registry.items() if r["detected"] and not r["available"]]

    logger.info(f"Engines Detected:   {', '.join(n.upper() for n in detected)}")
    logger.info(f"Engines Available:  {', '.join(available) if available else 'NONE'}")
    logger.info(f"Engines Healthy:    {', '.join(healthy) if healthy else 'NONE'}")
    if unavailable:
        logger.info(f"Engines Unavailable: {', '.join(unavailable)}")
    logger.info(f"  FREE_MODE={config.FREE_MODE} | MAX_CALLS={config.MAX_CALLS_PER_DAY}")


async def _probe_engine(engine: str) -> bool:
    """Probe a single engine with timeout."""
    try:
        if engine == "local":
            return await asyncio.wait_for(local_ai_engine.probe_local(), timeout=1.5)
        elif engine == "groq":
            if not config.GROQ_API_KEY:
                engine_registry["groq"]["last_error"] = "No API key configured"
                return False
            return await asyncio.wait_for(groq_engine.probe_groq(config.GROQ_API_KEY), timeout=1.5)
        elif engine == "gemini":
            if not config.GEMINI_API_KEY:
                engine_registry["gemini"]["last_error"] = "No API key configured"
                return False
            return await asyncio.wait_for(gemini_engine.probe_gemini(config.GEMINI_API_KEY), timeout=1.5)
        elif engine == "cloud":
            return await asyncio.wait_for(_probe_openrouter(), timeout=1.5)
    except asyncio.TimeoutError:
        engine_registry[engine]["last_error"] = "Probe timeout"
        logger.warning(f"Engine probe TIMEOUT: {engine}")
        return False
    except Exception as e:
        engine_registry[engine]["last_error"] = str(e)
        logger.warning(f"Engine probe FAILED: {engine} -- {e}")
        return False
    return False


async def _probe_openrouter() -> bool:
    """Probe OpenRouter endpoint."""
    if not config.OPENAI_API_KEY or config.OPENAI_API_KEY.startswith("sk-your"):
        engine_registry["cloud"]["last_error"] = "No API key configured"
        return False
    import httpx
    async with httpx.AsyncClient(timeout=1.5) as client:
        resp = await client.get(
            config.OPENAI_API_BASE.rstrip("/") + "/models",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
        )
        return resp.status_code in (200, 401, 403)


# ═══════════════════════════════════════
# ── Engine call functions
# ═══════════════════════════════════════

async def _call_local(system_prompt: str, user_message: str, context: str,
                      temperature: float, max_tokens: int) -> dict[str, Any]:
    model = config.LOCAL_MODEL
    logger.info(f">>> LOCAL: {model}")
    start = time.monotonic()
    try:
        result = await local_ai_engine.chat(
            system_prompt=system_prompt, user_message=user_message,
            context=context, model=model, temperature=temperature,
            max_tokens=max_tokens, host=config.OLLAMA_HOST,
        )
        latency = time.monotonic() - start
        result["latency"] = latency
        result["mode"] = "local"
        result["model"] = model
        _record_perf("local", latency, True)
        assert _usage_tracker is not None
        _usage_tracker.record_call(model=model, mode="local", tokens=result.get("tokens", 0))
        return result
    except Exception as e:
        _record_perf("local", time.monotonic() - start, False, str(e))
        raise


async def _call_groq(system_prompt: str, user_message: str, context: str,
                     temperature: float, max_tokens: int) -> dict[str, Any]:
    model = config.GROQ_MODEL
    logger.info(f">>> GROQ: {model}")
    
    # ── Strict API Validation ──
    valid_schema, reason = validate_groq_schema(model, temperature, max_tokens)
    if not valid_schema:
        raise ValueError(f"Schema Constraint Error: {reason}")
        
    if not rate_limiter.check_and_consume("groq"):
        raise ValueError("Rate limit token exhausted")
        
    start = time.monotonic()
    try:
        result = await groq_engine.chat(
            system_prompt=system_prompt, user_message=user_message,
            context=context, model=model, temperature=temperature,
            max_tokens=max_tokens, api_key=config.GROQ_API_KEY,
        )
        _record_perf("groq", result.get("latency", time.monotonic() - start), True)
        assert _usage_tracker is not None
        _usage_tracker.record_call(model=model, mode="groq", tokens=result.get("tokens", 0))
        return result
    except Exception as e:
        _record_perf("groq", time.monotonic() - start, False, str(e))
        raise


async def _call_gemini(system_prompt: str, user_message: str, context: str,
                       temperature: float, max_tokens: int) -> dict[str, Any]:
    model = config.GEMINI_MODEL
    logger.info(f">>> GEMINI: {model}")
    
    if not rate_limiter.check_and_consume("gemini"):
        raise ValueError("Rate limit token exhausted")
        
    start = time.monotonic()
    try:
        result = await gemini_engine.chat(
            system_prompt=system_prompt, user_message=user_message,
            context=context, model=model, temperature=temperature,
            max_tokens=max_tokens, api_key=config.GEMINI_API_KEY,
        )
        _record_perf("gemini", result.get("latency", time.monotonic() - start), True)
        assert _usage_tracker is not None
        _usage_tracker.record_call(model=model, mode="gemini", tokens=result.get("tokens", 0))
        return result
    except Exception as e:
        _record_perf("gemini", time.monotonic() - start, False, str(e))
        raise


async def _call_cloud(system_prompt: str, user_message: str, context: str,
                      temperature: float, max_tokens: int) -> dict[str, Any]:
    model = config.MODEL_LOCK
    logger.info(f">>> CLOUD: {model}")
    start = time.monotonic()
    try:
        result = await cloud_ai_engine.chat(
            system_prompt=system_prompt, user_message=user_message,
            context=context, model=model, temperature=temperature,
            max_tokens=max_tokens, api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_API_BASE,
        )
        latency = time.monotonic() - start
        result["latency"] = latency
        result["mode"] = "cloud"
        result["model"] = model
        _record_perf("cloud", latency, True)
        assert _usage_tracker is not None
        _usage_tracker.record_call(model=model, mode="cloud", tokens=result.get("tokens", 0))
        return result
    except Exception as e:
        _record_perf("cloud", time.monotonic() - start, False, str(e))
        raise


# Engine dispatch map
_ENGINE_CALLERS = {
    "local": _call_local,
    "groq": _call_groq,
    "gemini": _call_gemini,
    "cloud": _call_cloud,
}


# ═══════════════════════════════════════
# ── Main routing entry point
# ═══════════════════════════════════════

async def route_llm(
    system_prompt: str,
    user_message: str,
    context: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    mode: str = "chat",
) -> tuple[str, dict[str, Any]]:
    """
    Route an LLM call through the 4-engine autonomous cognitive system.
    Routes ONLY to usable (available AND healthy) engines. Never to detected-but-unavailable.
    """
    if _safety_guard is None:
        await init_router()

def _validate_runtime_trace(text: str, trace: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """
    CRITICAL INFRASTRUCTURE GATE:
    Trace must absolutely reflect physical execution reality.
    If states are claimed without physical response backing, execution raises an Integrity fault.
    """
    success_count = len(trace.get("engines_succeeded", []))
    engines_called = len(trace.get("engines_called", []))
    
    if trace.get("quorum_reached") and success_count < engines_called:
        logger.error(f"[TRACE VIOLATION] Quorum claimed but only {success_count}/{engines_called} engines succeeded. Forcing single/partial.")
        trace["quorum_reached"] = False
        
    if trace.get("synthesis_executed") and success_count < 2:
        logger.error(f"[TRACE VIOLATION] Synthesis claimed with only {success_count} responses.")
        raise ValueError("Trace Integrity Violation: Synthesis executed without at least 2 outputs.")
        
    if trace.get("execution_mode") == "parallel" and success_count < 2:
        logger.error(f"[TRACE VIOLATION] Parallel mode claimed without at least 2 successes. Forcing single.")
        trace["execution_mode"] = "single"
        
    return text, trace

async def route_llm(
    system_prompt: str,
    user_message: str,
    context: str = "",
    temperature: float | None = None,
    max_tokens: int | None = None,
    mode: str = "chat",
) -> tuple[str, dict[str, Any]]:
    """
    Route an LLM call through the 4-engine autonomous cognitive system.
    Routes ONLY to usable (available AND healthy) engines. Never to detected-but-unavailable.
    """
    if _safety_guard is None:
        await init_router()
    temperature = temperature if temperature is not None else config.LLM_TEMPERATURE
    max_tokens = max_tokens or config.LLM_MAX_TOKENS

    # ── Dynamic re-probe of previously unavailable engines ──
    reprobe_tasks = []
    for eng_name in ["local", "groq", "gemini"]:
        if not engine_registry[eng_name]["available"]:
            reprobe_tasks.append((eng_name, _probe_engine(eng_name)))

    if reprobe_tasks:
        names, coros = zip(*reprobe_tasks)
        results = await asyncio.gather(*coros, return_exceptions=True)
        for name, result in zip(names, results):
            if result is True:
                engine_registry[name]["available"] = True
                engine_registry[name]["healthy"] = True
                logger.info(f"Engine recovered: {name}")

    # ── Get availability booleans for cognitive_router ──
    local_avail = _is_usable("local")
    groq_avail = _is_usable("groq")
    gemini_avail = _is_usable("gemini")
    cloud_avail = _is_usable("cloud")

    # ── Cognitive analysis ──
    analysis = analyze_task(user_message)
    strategy = select_strategy(analysis, local_avail, groq_avail, gemini_avail, cloud_avail)

    strategy_name = strategy["strategy"]
    engines = strategy["engines"]
    is_hybrid = strategy.get("execution_mode", "single") == "parallel" and len(engines) > 1

    # ── Strict Trace Boilerplate ──
    # Execution trace is built emergent POST-execution
    trace = {
        "health_checked": True,
        "eligible_engines": [e for e in engines if _is_usable(e)],
        "engines_called": [],
        "engines_responded": [],
        "engines_succeeded": [],
        "engines_failed": {},
        "outputs_collected": 0,
        "quorum_reached": False,
        "synthesis_executed": False,
        "fallback_triggered": False,
        "hybrid_used": False,
        "rate_limits": {k: round(v.tokens, 1) for k, v in rate_limiter.buckets.items()},
        "cooldowns": {e: health_registry.registry[e].get("cooldown_until", 0) for e in engines},
        "execution_mode": "single", # DEFAULT, only changed if valid_outputs >= 2
    }

    # ── OFFLINE ──
    if strategy_name == "offline":
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine=none hybrid=false")
        return (
            "I'm in offline mode -- no AI engines available. "
            "Start Ollama for local intelligence, or check your API keys.",
            trace
        )

    # ── Execute engine calls based on strategy ──
    call_args = (system_prompt, user_message, context, temperature, max_tokens)
    
    # Pre-check safety
    safe_engines = []
    for eng in engines:
        model_map = {"local": config.LOCAL_MODEL, "groq": config.GROQ_MODEL,
                     "gemini": config.GEMINI_MODEL, "cloud": config.MODEL_LOCK}
        model = model_map.get(eng, config.LOCAL_MODEL)
        assert _safety_guard is not None
        check = _safety_guard.validate_request(model, eng)
        if check["safe"]:
            safe_engines.append(eng)
        else:
            logger.warning(f"Safety block on {eng}: {check['reason']}")
            
    if not safe_engines:
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine=blocked hybrid=false")
        return _validate_runtime_trace("All engines blocked by safety check.", trace)

    # Strategy Execution Map
    if strategy_name == "local_only":
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine=local hybrid=false")
        trace["engines_called"].append("local")
        trace["execution_order"] = ["local"]
        result = await _safe_call("local", _call_local, trace, *call_args)
        if result: return _validate_runtime_trace(result["text"], trace)
        
    elif strategy_name == "groq_fast":
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine=groq hybrid=false")
        trace["engines_called"].append("groq")
        trace["execution_order"] = ["groq"]
        result = await _safe_call("groq", _call_groq, trace, *call_args)
        if result: return _validate_runtime_trace(result["text"], trace)
        
    elif strategy_name == "gemini_deep":
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine=gemini hybrid=false")
        trace["engines_called"].append("gemini")
        trace["execution_order"] = ["gemini"]
        result = await _safe_call("gemini", _call_gemini, trace, *call_args)
        if result: return _validate_runtime_trace(result["text"], trace)
        
    elif strategy_name == "hybrid_full":
        # ── Pre-Hybrid Health Gate ──
        scores = [health_registry.compute_score(e) for e in safe_engines]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        if len(safe_engines) < 2 or avg_score < 0.5:
            logger.info(f"[HYBRID] Health gate failed. eligible={len(safe_engines)}, avg_score={avg_score:.2f}")
            trace["execution_mode"] = "single"
            strategy_name = "fallback" # Fallthrough to safety sequential execution
        else:
            logger.info(f"[HYBRID] Health gate passed: {', '.join(safe_engines)}")
            logger.info(f"[HYBRID] Rate limit status: OK")
            logger.info(f"[HYBRID] Schema validation: OK")
            logger.info(f"[HYBRID] Calling engines: {', '.join(safe_engines)}")
            
            trace["execution_order"] = []
            for eng in safe_engines:
                trace["engines_called"].append(eng)
                trace["execution_order"].append(eng)
                
            tasks = []
            for eng in safe_engines:
                caller = _ENGINE_CALLERS.get(eng)
                if caller:
                    tasks.append(_safe_call_hybrid(eng, caller, trace, *call_args))

            results = await asyncio.gather(*tasks)
            valid_results = [r for r in results if r is not None]
            success_count = len(valid_results)

            trace["outputs_collected"] = success_count
            
            # --- EMERGENT TRACE STATES ---
            if success_count == len(engines):
                logger.info("[HYBRID] Absolute Quorum achieved")
                trace["quorum_reached"] = True
            else:
                logger.info("[HYBRID] Absolute Quorum not reached (partial success)")
                trace["quorum_reached"] = False

            if success_count >= 2:
                trace["execution_mode"] = "parallel"
                trace["hybrid_used"] = True
            else:
                logger.info("[HYBRID] Fallback to single-engine execution")
                trace["execution_mode"] = "single"
            
            if success_count == 1:
                return _validate_runtime_trace(valid_results[0]["text"], trace)
            elif success_count > 1:
                logger.info("[HYBRID] True hybrid synthesis engaged")
                trace["synthesis_executed"] = True
                try:
                    syn = await synthesize(
                        valid_results,
                        task_type=analysis.get("task_type", "chat"),
                        strategy=strategy_name,
                        user_prompt=user_message,
                    )
                    logger.info("[HYBRID] Synthesis completed")
                    trace.update(syn)
                    return _validate_runtime_trace(syn["text"], trace)
                except Exception as e:
                    logger.error(f"[HYBRID] Synthesis failed: {e}")
                    trace["synthesis_executed"] = False
                    # Fallthrough to sequential recovery if synthesis hard-crashes

    # Fallthrough for sequentially failing primary engines OR explicitly offline routing 
    if strategy_name not in ("local_only", "groq_fast", "gemini_deep", "hybrid_full"):
        primary_eng = safe_engines[0] if safe_engines else 'none'
        logger.info(f"[ROUTER] mode={mode.upper()} strategy={strategy_name} engine={primary_eng} hybrid=false")
        trace["execution_order"] = []
        for eng in safe_engines:
            trace["engines_called"].append(eng)
            trace["execution_order"].append(eng)
            caller = _ENGINE_CALLERS.get(eng)
            if caller:
                result = await _safe_call(eng, caller, trace, *call_args)
                if result:
                    return _validate_runtime_trace(result["text"], trace)

    # All primary execution attempts failed -> Real Fallback Chain
    logger.info(f"[ROUTER] mode={mode.upper()} strategy=FALLBACK engine=chain hybrid=false")
    trace["fallback_triggered"] = True
    fallback_text = await _fallback_chain(call_args, exclude=set(engines), trace=trace)
    return _validate_runtime_trace(fallback_text, trace)


async def _safe_call(engine: str, caller, trace: dict | None, *args) -> dict[str, Any] | None:
    """Call an engine safely, returning None on failure."""
    try:
        res = await caller(*args)
        if trace is not None and res is not None:
            trace["engines_responded"].append(engine)
            trace["engines_succeeded"].append(engine)
        return res
    except Exception as e:
        if trace is not None: trace["engines_responded"].append(engine)
        error_type = "unknown"
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 429:
                error_type = "rate_limit"
                rate_limiter.register_429(engine)
            elif e.response.status_code == 400:
                error_type = "schema"
        elif isinstance(e, ValueError) and "Schema" in str(e):
            error_type = "schema"
        elif isinstance(e, ValueError) and "Rate limit" in str(e):
            error_type = "rate_limit"

        _record_perf(engine, 0.0, False, str(e), error_type)
        if trace is not None: trace["engines_failed"][engine] = error_type
        logger.error(f"Engine {engine} FAILED: {e}")
        return None

async def _safe_call_hybrid(engine: str, caller, trace: dict | None, *args) -> dict[str, Any] | None:
    """Call an engine safely specifically for hybrid loops to emit mandatory logs."""
    try:
        res = await caller(*args)
        if trace is not None and res is not None:
            trace["engines_responded"].append(engine)
            trace["engines_succeeded"].append(engine)
            
        if engine == "local":
            logger.info("[HYBRID] local response received")
        else:
            logger.info(f"[HYBRID] Engine {engine} succeeded")
            
        return res
    except Exception as e:
        if trace is not None: trace["engines_responded"].append(engine)
        error_type = "unknown"
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 429:
                error_type = "rate_limit"
                rate_limiter.register_429(engine)
            elif e.response.status_code == 400:
                error_type = "schema"
        elif isinstance(e, ValueError) and "Schema" in str(e):
            error_type = "schema"
        elif isinstance(e, ValueError) and "Rate limit" in str(e):
            error_type = "rate_limit"

        _record_perf(engine, 0.0, False, str(e), error_type)
        if trace is not None: trace["engines_failed"][engine] = error_type
        logger.error(f"[HYBRID] Engine {engine} failed: {error_type}")
        return None


async def _fallback_chain(call_args: tuple, exclude: set[str] | None = None, trace: dict = None) -> str:
    """Dynamic fallback: try remaining USABLE engines in order."""
    exclude = exclude or set()
    chain = [
        ("local", _call_local),
        ("groq", _call_groq),
        ("gemini", _call_gemini),
        ("cloud", _call_cloud),
    ]
    for name, caller in chain:
        if name in exclude or not _is_usable(name):
            continue
        if trace is not None:
            trace["engines_called"].append(f"fallback_{name}")
            trace["execution_order"].append(f"fallback_{name}")
        result = await _safe_call(name, caller, trace, *call_args)
        if result:
            logger.info(f"Fallback succeeded: {name}")
            return result["text"]

    return "I'm having trouble with all AI engines right now. Please try again in a moment."


# ═══════════════════════════════════════
# ── Status API
# ═══════════════════════════════════════

def get_router_status() -> dict[str, Any]:
    """Full runtime-truth status of the autonomous router."""
    stats = get_engine_stats()
    return {
        "engines": stats,
        "active_engines": [n for n, s in stats.items() if s["available"]],
        "detected_engines": [n for n, s in stats.items() if s["detected"]],
        "unavailable_engines": [n for n, s in stats.items() if s["detected"] and not s["available"]],
        "healthy_engines": [n for n, s in stats.items() if s["healthy"]],
        "performance": stats,
        "cost_status": _cost_guard.get_status() if _cost_guard else {},
        "usage": _usage_tracker.get_summary() if _usage_tracker else {},
    }
